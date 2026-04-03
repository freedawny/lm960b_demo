"""
debug_probe3.py — 深入探测节点列表相关服务项
"""

import time
import serial
from uapps_codec import build_get, PREAMBLE

PORT = "/dev/tty.usbserial-10"
BAUD = 115200
TIMEOUT = 4.0


def query(ser, path, label=""):
    frame = build_get(path)
    print(f"\n[TX] @{path} {label}  {frame[8:].hex(' ')}")
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
                chunk2 = ser.read(ser.in_waiting)
                if chunk2:
                    buf.extend(chunk2)
                break

    if buf:
        idx = buf.find(PREAMBLE)
        if idx >= 0:
            after = buf[idx + 8:]
            code = after[1] if len(after) > 1 else 0
            code_str = {0x45: "2.05 Content", 0x44: "2.04 Changed",
                        0x84: "4.04 NotFound", 0x80: "4.00 BadReq",
                        0x85: "4.05 NotAllowed"}.get(code, f"0x{code:02x}")
            # 找 payload（ff 后的内容）
            payload = b""
            for i in range(len(after)):
                if after[i] == 0xff:
                    # 跳过 Uapps 选项到第二个 ff
                    j = i + 1
                    while j < len(after) and after[j] != 0xff:
                        j += 1
                    if j < len(after) and after[j] == 0xff:
                        payload = after[j+1:]
                    else:
                        payload = after[i+1:]
                    break
            print(f"[RX] code={code_str}  payload={payload.hex(' ') if payload else '(empty)'}")
            print(f"     raw={buf.hex(' ')}")
    else:
        print(f"[RX] 无响应（超时）")


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[serial] 已打开 {PORT}\n")

    # @0/4/3 超时，可能是节点列表，用不同索引试
    print("=== @0/4/3 重试 ===")
    query(ser, "0/4/3", "节点列表?")

    # 尝试 @0/4 下更多子项
    print("\n=== @0/4/x 全扫 ===")
    for i in [10, 11, 12, 20, 21, 100, 101, 104]:
        query(ser, f"0/4/{i}")

    # 尝试 @0/5/x（可能是另一个对象）
    print("\n=== @0/5/x ===")
    for i in range(1, 6):
        query(ser, f"0/5/{i}")

    # 尝试 @0/6/x
    print("\n=== @0/6/x ===")
    for i in range(1, 4):
        query(ser, f"0/6/{i}")

    # 尝试 @1.noda 格式但用主模组自己的 MAC
    print("\n=== 远程查询从节点（需要知道MAC）===")
    # 先查 @0/4/1 确认从节点数，再尝试 @0/4/3/1 等
    query(ser, "0/4/1", "从节点数")
    query(ser, "0/4/3/1", "节点列表条目1?")
    query(ser, "0/4/3/2", "节点列表条目2?")

    ser.close()


if __name__ == "__main__":
    main()
