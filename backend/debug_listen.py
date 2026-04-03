"""
debug_listen.py — 纯监听，打印所有串口原始字节，不发任何帧

用途：观察主模组是否有主动上报，以及上报帧的原始格式。
"""

import time
import serial

PORT = "/dev/tty.usbserial-10"
BAUD = 115200


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[serial] 已打开 {PORT}，监听 30 秒...\n")

    deadline = time.monotonic() + 30.0
    buf = bytearray()

    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf.extend(chunk)
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] RX ({len(chunk)}B): {chunk.hex(' ')}")

    print(f"\n[total] {len(buf)} bytes received")
    if buf:
        print(f"[total hex] {buf.hex(' ')}")

    ser.close()


if __name__ == "__main__":
    main()
