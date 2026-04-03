"""
debug_probe5.py — 深入分析 @0/3/2 和节点相关接口

@0/3/2 返回 12 字节，可能是节点列表或网络状态。
同时探测 @0/3/2/x 子项和其他可能包含从节点 MAC 的接口。
"""

import time
import serial
from uapps_codec import build_get, PREAMBLE

PORT = "/dev/tty.usbserial-10"
BAUD = 115200
TIMEOUT = 3.0


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
                buf.extend(ser.read(ser.in_waiting))
                break

    if buf:
        idx = buf.find(PREAMBLE)
        after = buf[idx+8:] if idx >= 0 else buf
        code = after[1] if len(after) > 1 else 0
        code_str = {0x45:"2.05 Content", 0x44:"2.04 Changed",
                    0x84:"4.04 NotFound", 0x80:"4.00 BadReq"}.get(code, f"0x{code:02x}")
        payload = b""
        for i in range(len(after)):
            if after[i] == 0xff:
                j = i + 1
                while j < len(after) and after[j] != 0xff:
                    j += 1
                payload = after[j+1:] if j < len(after) else after[i+1:]
                break
        print(f"[RX] {code_str}  payload={payload.hex(' ') if payload else '(empty)'}")
        if payload and len(payload) >= 6:
            # 尝试解析为 MAC 地址
            for i in range(0, len(payload) - 5, 6):
                mac = payload[i:i+6]
                if any(b != 0 for b in mac):
                    print(f"     → 可能的MAC[{i//6}]: {mac.hex(':').upper()}")
    else:
        print(f"[RX] 无响应（超时）")


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[serial] 已打开 {PORT}\n")

    # 重复查询 @0/3/2 几次，看是否变化
    print("=== @0/3/2 重复查询（观察是否包含从节点信息）===")
    for i in range(3):
        query(ser, "0/3/2", f"第{i+1}次")
        time.sleep(0.5)

    # @0/3/2 子项
    print("\n=== @0/3/2/x 子项 ===")
    for i in range(1, 10):
        query(ser, f"0/3/2/{i}")

    # @0/4/9 返回 00，探测周边
    print("\n=== @0/4/x 更多 ===")
    for i in [9, 13, 14, 15, 16, 17, 18, 19]:
        query(ser, f"0/4/{i}")

    # 尝试 @0/4/9/x
    print("\n=== @0/4/9/x ===")
    for i in range(1, 6):
        query(ser, f"0/4/9/{i}")

    # 尝试用从节点索引 0 查询
    print("\n=== @0/4/0 ===")
    query(ser, "0/4/0")

    # @0/1 详细解析（基本信息里可能有节点数）
    print("\n=== @0/1 详细 ===")
    query(ser, "0/1", "基本信息")

    ser.close()


if __name__ == "__main__":
    main()
