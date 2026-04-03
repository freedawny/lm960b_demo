"""
debug_join.py — 监听 NODE_JOIN 上报

持续监听串口 120 秒，打印所有收到的原始字节和解析结果。
请在运行后重启从节点（断电再上电）。
"""

import time
import struct
import serial
from uapps_codec import PREAMBLE, parse_frame

PORT = "/dev/tty.usbserial-10"
BAUD = 115200


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.05)
    print(f"[serial] 已打开 {PORT}")
    print("请现在重启从节点（断电再上电），监听 120 秒...\n")

    buf = bytearray()
    deadline = time.monotonic() + 120.0
    frame_count = 0

    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if not chunk:
            continue

        buf.extend(chunk)
        ts = time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"
        print(f"[{ts}] RX {len(chunk)}B: {chunk.hex(' ')}")

        # 尝试解析完整帧
        while True:
            result = parse_frame(bytes(buf))
            if result is None:
                break
            frame, consumed = result
            buf = buf[consumed:]
            frame_count += 1
            tname = {0: "CON", 1: "NON", 2: "ACK", 3: "RST"}.get(frame.msg_type, "?")
            cname = {
                0x45: "2.05 Content", 0x44: "2.04 Changed",
                0x84: "4.04 NotFound", 0x80: "4.00 BadReq",
                0x01: "0.01 GET", 0x03: "0.03 PUT",
            }.get(frame.code, f"0x{frame.code:02x}")
            print(f"  ↳ FRAME#{frame_count} type={tname} code={cname} "
                  f"id=0x{frame.msg_id:04x} token={frame.token.hex()} "
                  f"uapps_opts={frame.uapps_options.hex(' ')} "
                  f"payload={frame.payload.hex(' ') if frame.payload else '(empty)'}")

            # 尝试从 payload 提取 MAC
            if frame.payload and len(frame.payload) >= 6:
                for i in range(0, len(frame.payload) - 5, 1):
                    candidate = frame.payload[i:i+6]
                    # 过滤全 0 和全 FF
                    if any(b != 0 for b in candidate) and any(b != 0xFF for b in candidate):
                        print(f"     possible MAC @ offset {i}: {candidate.hex(':').upper()}")

    print(f"\n[done] 共收到 {frame_count} 帧")
    ser.close()


if __name__ == "__main__":
    main()
