"""
debug_serial.py — 串口收发调试脚本

直接发 @0/2 查询帧，打印原始 TX/RX 字节，不依赖 FastAPI。
用法：python3 debug_serial.py
"""

import time
import serial
from uapps_codec import build_get, PREAMBLE

PORT = "/dev/tty.usbserial-10"
BAUD = 115200

def main():
    ser = serial.Serial(PORT, BAUD, timeout=5)
    print(f"[serial] 已打开 {PORT}")

    # 构建 @0/2 查询帧
    frame = build_get("0/2")
    print(f"[TX] {frame.hex(' ')}")
    ser.write(frame)
    ser.flush()

    # 等待响应，最多 5 秒
    print("[RX] 等待响应...")
    buf = bytearray()
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf.extend(chunk)
            print(f"[RX] {chunk.hex(' ')}")
            # 收到前导码后再等一点让完整帧到达
            if PREAMBLE in buf and len(buf) > len(PREAMBLE) + 4:
                time.sleep(0.1)
                chunk2 = ser.read(ser.in_waiting)
                if chunk2:
                    buf.extend(chunk2)
                    print(f"[RX] {chunk2.hex(' ')}")
                break

    if not buf:
        print("[RX] 无数据，模组未响应")
    else:
        print(f"[RX total] {buf.hex(' ')}")

    ser.close()

if __name__ == "__main__":
    main()
