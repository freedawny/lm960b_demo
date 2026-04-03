"""
debug_probe2.py — 深入探测 @0/4 子项，寻找节点列表
"""

import time
import serial
from uapps_codec import build_get, PREAMBLE

PORT = "/dev/tty.usbserial-10"
BAUD = 115200
TIMEOUT = 3.0


def query(ser, path):
    frame = build_get(path)
    print(f"\n[TX] @{path}  {frame[8:].hex(' ')}")
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
                time.sleep(0.2)
                chunk2 = ser.read(ser.in_waiting)
                if chunk2:
                    buf.extend(chunk2)
                break

    if buf:
        # 提取前导码后的内容
        idx = buf.find(PREAMBLE)
        if idx >= 0:
            payload_part = buf[idx + 8:]
            print(f"[RX] {buf.hex(' ')}")
            print(f"     → 前导码后: {payload_part.hex(' ')}")
            # 找 ff ff 后的 payload
            rest = payload_part
            for i in range(len(rest) - 1):
                if rest[i] == 0xff:
                    print(f"     → Flag后内容: {rest[i+1:].hex(' ')}")
                    break
    else:
        print(f"[RX] 无响应（超时）")


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[serial] 已打开 {PORT}\n")

    # 深入探测 @0/4 子项
    for i in range(1, 10):
        query(ser, f"0/4/{i}")

    # 探测 @0/4/1/x（可能是节点列表条目）
    print("\n--- 探测 @0/4/1/x ---")
    for i in range(1, 5):
        query(ser, f"0/4/1/{i}")

    # 探测 @0/4/0/x
    print("\n--- 探测 @0/4/0/x ---")
    for i in range(1, 5):
        query(ser, f"0/4/0/{i}")

    ser.close()


if __name__ == "__main__":
    main()
