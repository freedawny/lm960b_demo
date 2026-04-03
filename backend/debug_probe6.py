"""
debug_probe6.py — 用 PUT 方式查询节点列表，并解析 @0/1 结构

@0/4/3 可能需要 PUT 带索引 payload 才能返回节点信息。
同时解析 @0/1 的 23 字节结构。
"""

import time
import struct
import serial
from uapps_codec import (
    build_get, build_frame, UappsFrame,
    T_CON, CODE_PUT, _next_id, _make_token,
    encode_uri_path, encode_size_option, PREAMBLE
)

PORT = "/dev/tty.usbserial-10"
BAUD = 115200
TIMEOUT = 4.0


def query_raw(ser, path, method="GET", payload=b""):
    if method == "GET":
        frame = build_get(path)
    else:
        mid = _next_id()
        uapps_opts = encode_uri_path(path)
        if payload:
            uapps_opts += encode_size_option(len(payload))
        frame = build_frame(UappsFrame(
            msg_type=T_CON, code=CODE_PUT, msg_id=mid,
            token=_make_token(mid),
            uapps_options=uapps_opts,
            payload=payload,
        ))
    print(f"\n[TX {method}] @{path} payload={payload.hex() if payload else ''}  {frame[8:].hex(' ')}")
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()

    buf = bytearray()
    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf.extend(chunk)
            if PREAMBLE in buf and len(buf) > len(PREAMBLE) + 4:
                time.sleep(0.3)
                buf.extend(ser.read(ser.in_waiting))
                break

    if not buf:
        print("[RX] 无响应（超时）")
        return None

    idx = buf.find(PREAMBLE)
    after = buf[idx+8:] if idx >= 0 else buf
    code = after[1] if len(after) > 1 else 0
    code_str = {0x45:"2.05 Content", 0x44:"2.04 Changed",
                0x84:"4.04 NotFound", 0x80:"4.00 BadReq",
                0x85:"4.05 NotAllowed"}.get(code, f"0x{code:02x}")
    # 提取 payload（两个 0xFF 之后）
    pl = b""
    i = 0
    while i < len(after):
        if after[i] == 0xff:
            j = i + 1
            while j < len(after) and after[j] != 0xff:
                j += 1
            pl = after[j+1:] if j < len(after) else after[i+1:]
            break
        i += 1
    print(f"[RX] {code_str}  payload({len(pl)}B)={pl.hex(' ')}")
    return pl


def parse_0_1(payload: bytes):
    """尝试解析 @0/1 的 23 字节 payload"""
    if len(payload) < 23:
        return
    print(f"\n  @0/1 结构解析（{len(payload)}字节）:")
    print(f"  [0]    = 0x{payload[0]:02x}  (版本/类型?)")
    print(f"  [1]    = 0x{payload[1]:02x}  (子版本?)")
    print(f"  [2-3]  = {payload[2]:02x} {payload[3]:02x}  (DID? = {struct.unpack_from('>H', payload, 2)[0]})")
    print(f"  [4]    = 0x{payload[4]:02x}  (?)")
    print(f"  [5]    = 0x{payload[5]:02x}  (信道模式? 01=PLC,02=dual)")
    print(f"  [6-7]  = {payload[6]:02x} {payload[7]:02x}  (?)")
    print(f"  [8-9]  = {payload[8]:02x} {payload[9]:02x}  (?)")
    print(f"  [10-11]= {payload[10]:02x} {payload[11]:02x}  (?)")
    print(f"  [12]   = 0x{payload[12]:02x}  (?)")
    print(f"  [13]   = 0x{payload[13]:02x}  (从节点数? = {payload[13]})")
    print(f"  [14]   = 0x{payload[14]:02x}  (?)")
    print(f"  [15-20]= {payload[15:21].hex(':')}  (主模组MAC?)")
    print(f"  [21-22]= {payload[21]:02x} {payload[22]:02x}  (?)")


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[serial] 已打开 {PORT}\n")

    # 解析 @0/1
    pl = query_raw(ser, "0/1")
    if pl:
        parse_0_1(pl)

    # PUT @0/4/3 带不同 payload（索引 0, 1, 2）
    print("\n=== PUT @0/4/3 带索引 payload ===")
    for idx_val in [b"\x00", b"\x01", b"\x02", b"\x00\x00", b"\x01\x00"]:
        query_raw(ser, "0/4/3", method="PUT", payload=idx_val)

    # 尝试 @0/4/3 GET 但先 PUT 触发
    print("\n=== PUT @0/4/3 再 GET ===")
    query_raw(ser, "0/4/3", method="PUT", payload=b"\x00")
    time.sleep(0.5)
    query_raw(ser, "0/4/3")

    # 尝试 @1.noda 格式用广播地址查节点列表
    print("\n=== 广播 ping 再监听 2 秒 ===")
    from uapps_codec import build_frame, UappsFrame, T_NON, encode_size_option
    mid = _next_id()
    path = "1.FFFFFFFFFFFF/104/3"
    uapps_opts = encode_uri_path(path) + encode_size_option(0x2A)
    bcast = build_frame(UappsFrame(
        msg_type=T_NON, code=CODE_PUT, msg_id=mid,
        token=_make_token(mid), uapps_options=uapps_opts,
        payload=b"\x11" * 10,
    ))
    print(f"[TX NON broadcast] {bcast[8:].hex(' ')}")
    ser.reset_input_buffer()
    ser.write(bcast)
    ser.flush()

    buf = bytearray()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf.extend(chunk)
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] RX: {chunk.hex(' ')}")
    if not buf:
        print("[RX] 无响应")

    ser.close()


if __name__ == "__main__":
    main()
