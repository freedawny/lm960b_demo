"""
uapps_codec.py — 串口帧编解码

串口帧结构（基于厂商测试软件日志逆向确认）：
  [ 前导码 8字节 ] [ 消息头 ] [ 0xFF ] [ Uapps选项（URI-Path等）] [ 0xFF ] [ payload ]

关键修正（基于厂商日志分析）：
  1. CoAP 选项域永远为空，0xFF 紧跟在 token 后面（Flag1）
  2. URI-Path 是带 '@' 前缀的单个 Uapps 选项（选项号 10）
  3. Token 固定 2 字节，内容 = msg_id 的小端序字节（厂商实测）
  4. 广播发现用 @0.ffffffffffff/2（小写，前缀0.），不是 @1.FFFFFFFFFFFF/104/3
  5. 远程查询用 @0.<mac12lower>/<resource>（小写MAC，前缀0.）
"""

import struct
from dataclasses import dataclass, field
from typing import Optional

PREAMBLE = bytes([0x1B, 0x1B, 0x1B, 0x1B, 0x1B, 0x0A, 0x1B, 0x0A])

# 消息类型
T_CON = 0b00
T_NON = 0b01
T_ACK = 0b10

# CoAP 方法码 / 响应码
CODE_GET     = 0x01  # 0.01
CODE_POST    = 0x02  # 0.02  广播专用
CODE_PUT     = 0x03  # 0.03
CODE_CHANGED = 0x44  # 2.04
CODE_CONTENT = 0x45  # 2.05


@dataclass
class UappsFrame:
    msg_type: int         # T_CON / T_NON / T_ACK
    code: int             # 方法码或响应码
    msg_id: int           # 16-bit 消息 ID
    token: bytes          # 固定 2 字节
    uapps_options: bytes  # Uapps 选项域原始字节（不含 Flag2）
    payload: bytes = field(default=b"")


# ── msg_id 计数器 ─────────────────────────────────────────────────

_msg_id_counter = 0


def _next_id() -> int:
    global _msg_id_counter
    _msg_id_counter = (_msg_id_counter + 1) & 0xFFFF
    return _msg_id_counter


def get_last_msg_id() -> int:
    return _msg_id_counter


def _make_token(msg_id: int) -> bytes:
    # 厂商实测：token = msg_id 小端序
    return struct.pack("<H", msg_id)


# ── URI-Path Uapps 选项编码（选项号 10）────────────────────────────

def encode_uri_path(path: str) -> bytes:
    """
    将路径编码为 Uapps URI-Path 选项（选项号 10）。
    值 = '@' + path 的 ASCII 字节串。

    示例：
      '0/2'                  → a4 40 30 2f 32
      '0/3/20'               → a7 40 30 2f 33 2f 32 30
      '0.112233445566/104/1' → ad 08 40 30 2e ... (扩展length)
    """
    value = ("@" + path).encode("ascii")
    length = len(value)
    if length < 13:
        return bytes([0xA0 | length]) + value
    else:
        return bytes([0xAD, length - 13]) + value


def encode_size_option(size: int) -> bytes:
    """
    Uapps SIZE 选项（选项号 11，delta=1 相对上一个选项号 10）。
    示例 Ping 帧：11 2a → delta=1, length=1, value=0x2a=42
    value 直接传入 size 字节值。
    """
    assert size <= 0xFF, "size > 255 暂不支持"
    return bytes([0x11, size])


# ── 帧构建 ────────────────────────────────────────────────────────

def build_frame(frame: UappsFrame) -> bytes:
    """
    构建完整串口帧。

    结构：
      前导码 | VER+T+TKL | Code | MsgID(2B) | Token(2B)
      | FF | Uapps选项 | FF | payload
      （无 payload 时末尾 FF 和 payload 均省略）
    """
    tkl = len(frame.token)
    first = (0b01 << 6) | (frame.msg_type << 4) | tkl
    header = bytes([first, frame.code]) + struct.pack(">H", frame.msg_id) + frame.token

    body = header + b"\xFF" + frame.uapps_options
    if frame.payload:
        body += b"\xFF" + frame.payload

    return PREAMBLE + body


def build_get(path: str) -> bytes:
    """构建 CON GET 请求帧"""
    mid = _next_id()
    return build_frame(UappsFrame(
        msg_type=T_CON,
        code=CODE_GET,
        msg_id=mid,
        token=_make_token(mid),
        uapps_options=encode_uri_path(path),
    ))


def build_ping(mac_hex: str, payload: bytes = b"\x11" * 10) -> bytes:
    """
    构建单播 Ping 帧（CON PUT @0.<mac>/104/1）
    厂商实测：前缀 0. 小写 MAC
    mac_hex: 12位十六进制，大小写均可
    """
    mac_lower = mac_hex.lower().strip()
    assert len(mac_lower) == 12 and mac_lower.replace('a','').replace('b','').replace('c','').replace('d','').replace('e','').replace('f','').isdigit() or mac_lower.isalnum(), \
        f"MAC 必须为 12 位十六进制: {mac_hex!r}"
    mid = _next_id()
    path = f"0.{mac_lower}/104/1"
    uapps_opts = encode_uri_path(path) + encode_size_option(0x2A)
    return build_frame(UappsFrame(
        msg_type=T_CON,
        code=CODE_PUT,
        msg_id=mid,
        token=_make_token(mid),
        uapps_options=uapps_opts,
        payload=payload,
    ))


def build_broadcast_discover() -> tuple[bytes, int]:
    """
    广播发现从节点（CON GET @0.ffffffffffff/2）
    厂商实测格式：GET，URI = @0.ffffffffffff/2（小写，前缀0.）
    从节点回 ACK，payload 含从节点 MAC（6字节）。
    """
    mid = _next_id()
    path = "0.ffffffffffff/2"
    return build_frame(UappsFrame(
        msg_type=T_CON,
        code=CODE_GET,
        msg_id=mid,
        token=_make_token(mid),
        uapps_options=encode_uri_path(path),
    )), mid


# ── 帧解析 ────────────────────────────────────────────────────────

def parse_frame(data: bytes) -> Optional[tuple["UappsFrame", int]]:
    """
    尝试从 data 解析一帧。
    返回 (UappsFrame, consumed_bytes) 或 None（数据不足/无前导码）。
    """
    pos = data.find(PREAMBLE)
    if pos < 0:
        return None
    pos += len(PREAMBLE)

    if pos + 4 > len(data):
        return None

    first  = data[pos]
    t      = (first >> 4) & 0x03
    tkl    = first & 0x0F
    code   = data[pos + 1]
    msg_id = struct.unpack_from(">H", data, pos + 2)[0]
    pos += 4

    if pos + tkl > len(data):
        return None
    token = data[pos:pos + tkl]
    pos += tkl

    # 跳过 Flag1 (0xFF)
    if pos >= len(data):
        return None
    if data[pos] == 0xFF:
        pos += 1

    # 读取 Uapps 选项域直到 0xFF 或数据末尾
    uapps_opts_start = pos
    while pos < len(data) and data[pos] != 0xFF:
        if pos >= len(data):
            return None
        opt_byte = data[pos]
        delta_nibble  = (opt_byte >> 4) & 0x0F
        length_nibble = opt_byte & 0x0F
        pos += 1
        # 扩展 delta
        if delta_nibble == 13:
            if pos >= len(data): return None
            pos += 1
        elif delta_nibble == 14:
            if pos + 1 >= len(data): return None
            pos += 2
        # 扩展 length
        if length_nibble == 13:
            if pos >= len(data): return None
            ext_len = data[pos] + 13
            pos += 1
        elif length_nibble == 14:
            if pos + 1 >= len(data): return None
            ext_len = struct.unpack_from(">H", data, pos)[0] + 269
            pos += 2
        else:
            ext_len = length_nibble
        pos += ext_len
    uapps_options = data[uapps_opts_start:pos]

    # 跳过 Flag2 (0xFF)
    if pos < len(data) and data[pos] == 0xFF:
        pos += 1

    # payload：读到下一个前导码或数据末尾
    next_pre = data.find(PREAMBLE, pos)
    if next_pre < 0:
        payload = data[pos:]
        consumed = len(data)
    else:
        payload = data[pos:next_pre]
        consumed = next_pre

    return UappsFrame(
        msg_type=t,
        code=code,
        msg_id=msg_id,
        token=token,
        uapps_options=uapps_options,
        payload=payload,
    ), consumed


# ── payload 提取工具 ──────────────────────────────────────────────

def extract_mac(payload: bytes) -> Optional[str]:
    """从 @0/2 响应 payload（6字节）提取 MAC 地址字符串"""
    if len(payload) >= 6:
        return payload[:6].hex().upper()
    return None


def extract_channel_mode(payload: bytes) -> Optional[int]:
    """从 @0/3/20 响应 payload（1字节）提取信道模式值"""
    if len(payload) >= 1:
        return payload[0]
    return None


CHANNEL_MODE_NAMES = {0: "PLC", 1: "wireless", 2: "dual"}
