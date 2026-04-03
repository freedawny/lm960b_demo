"""
debug_probe.py — 探测服务项

依次查询多个服务项，打印原始响应，帮助发现节点列表接口。
"""

import time
import serial
from uapps_codec import build_get, PREAMBLE, _msg_id_counter

PORT = "/dev/tty.usbserial-10"
BAUD = 115200
TIMEOUT = 3.0


def query(ser, path):
    frame = build_get(path)
    from uapps_codec import _msg_id_counter as mid
    print(f"\n[TX] @{path}  {frame.hex(' ')}")
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
                time.sleep(0.15)
                chunk2 = ser.read(ser.in_waiting)
                if chunk2:
                    buf.extend(chunk2)
                break

    if buf:
        print(f"[RX] {buf.hex(' ')}")
    else:
        print(f"[RX] 无响应（超时）")


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[serial] 已打开 {PORT}\n")

    # 已知服务项
    query(ser, "0/1")    # 基本信息
    query(ser, "0/2")    # MAC
    query(ser, "0/3/1")  # DID
    query(ser, "0/3/20") # 信道模式

    # 探测可能的节点列表服务项
    for path in ["0/4", "0/5", "0/6", "0/7", "0/8",
                 "0/4/1", "0/4/2", "0/5/1",
                 "1/1", "1/2", "1/3"]:
        query(ser, path)

    ser.close()


if __name__ == "__main__":
    main()
