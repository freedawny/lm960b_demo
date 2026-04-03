"""
debug_discover.py — 广播探测 + 监听所有上报帧

发送广播 ping (@1.FFFFFFFFFFFF/104/3)，然后持续监听 10 秒，
打印所有收到的原始帧，帮助分析从节点响应和 NODE_JOIN 格式。
"""

import time
import serial
from uapps_codec import PREAMBLE, build_frame, UappsFrame, T_NON, CODE_PUT, _next_id, _make_token, encode_uri_path, encode_size_option

PORT = "/dev/tty.usbserial-10"
BAUD = 115200


def build_broadcast_ping(payload: bytes = b"\x11" * 10) -> bytes:
    """广播 ping @1.FFFFFFFFFFFF/104/3 (NON)"""
    mid = _next_id()
    path = "1.FFFFFFFFFFFF/104/3"
    uapps_opts = encode_uri_path(path) + encode_size_option(0x2A)
    return build_frame(UappsFrame(
        msg_type=T_NON,
        code=CODE_PUT,
        msg_id=mid,
        token=_make_token(mid),
        uapps_options=uapps_opts,
        payload=payload,
    ))


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[serial] 已打开 {PORT}")

    # 发广播 ping
    frame = build_broadcast_ping()
    print(f"\n[TX broadcast ping] {frame.hex(' ')}\n")
    ser.write(frame)
    ser.flush()

    # 监听 15 秒，打印所有收到的字节
    print("[RX] 监听 15 秒，打印所有收到的帧...\n")
    buf = bytearray()
    deadline = time.monotonic() + 15.0

    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf.extend(chunk)
            # 每次收到前导码就尝试打印一帧
            while PREAMBLE in buf:
                idx = buf.find(PREAMBLE)
                if idx > 0:
                    print(f"[RX garbage before preamble] {buf[:idx].hex(' ')}")
                    buf = buf[idx:]
                # 找下一个前导码确定帧边界
                next_idx = buf.find(PREAMBLE, len(PREAMBLE))
                if next_idx > 0:
                    frame_bytes = buf[:next_idx]
                    buf = buf[next_idx:]
                    print(f"[RX frame] {frame_bytes.hex(' ')}")
                    _decode_frame(frame_bytes)
                    print()
                else:
                    break  # 等更多数据

    # 打印剩余
    if buf:
        print(f"[RX remaining] {buf.hex(' ')}")

    ser.close()


def _decode_frame(data: bytes):
    """简单解码打印字段"""
    pre_len = len(PREAMBLE)
    if len(data) < pre_len + 4:
        print("  (too short)")
        return
    pos = pre_len
    first  = data[pos]
    t      = (first >> 4) & 0x03
    tkl    = first & 0x0F
    code   = data[pos+1]
    msg_id = (data[pos+2] << 8) | data[pos+3]
    pos += 4
    token  = data[pos:pos+tkl]
    pos += tkl
    rest   = data[pos:]
    type_name = {0: "CON", 1: "NON", 2: "ACK", 3: "RST"}.get(t, "?")
    print(f"  type={type_name} code=0x{code:02x} id=0x{msg_id:04x} token={token.hex()} rest={rest.hex(' ')}")


if __name__ == "__main__":
    main()
