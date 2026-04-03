"""
debug_probe7.py — 最终探测策略

1. 解析 @0/1 完整结构，找从节点 MAC
2. 尝试 @0/4/3 的不同 URI 格式（带 MAC、带 DID）
3. 尝试 @1.noda 格式直接 ping 已知 DID 范围
4. 监听主模组是否有延迟上报
"""

import time
import struct
import serial
from uapps_codec import build_get, PREAMBLE

PORT = "/dev/tty.usbserial-10"
BAUD = 115200
TIMEOUT = 3.0


def query(ser, path, label=""):
    frame = build_get(path)
    print(f"\n[TX] @{path} {label}")
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
        print(f"  → 无响应（超时）")
        return None

    idx = buf.find(PREAMBLE)
    after = buf[idx+8:] if idx >= 0 else buf
    code = after[1] if len(after) > 1 else 0
    code_str = {0x45:"Content", 0x44:"Changed", 0x84:"NotFound",
                0x80:"BadReq", 0x85:"NotAllowed"}.get(code, f"0x{code:02x}")
    pl = b""
    for i in range(len(after)):
        if after[i] == 0xff:
            j = i + 1
            while j < len(after) and after[j] != 0xff:
                j += 1
            pl = after[j+1:] if j < len(after) else after[i+1:]
            break
    print(f"  → {code_str}  {pl.hex(' ') if pl else '(empty)'}")
    return pl


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[serial] 已打开 {PORT}\n")

    # 1. 查 @0/4/3 用不同路径格式
    print("=== 尝试不同路径格式 ===")
    # 可能路径里需要用 DID=2（从 @0/1 得到）
    query(ser, "0/4/3/0")
    query(ser, "0/4/3/00")
    # 可能是 @0/4/<DID>
    query(ser, "0/4/2")   # DID=2
    # 可能是 @0/4/<index>/x
    for sub in ["mac", "2", "3", "4", "5", "6", "7", "8"]:
        query(ser, f"0/4/1/{sub}")

    # 2. 尝试 @1.noda 格式 ping 不同 DID
    # 协议里 @1.noda 中 noda 是 MAC，但也可能支持 DID
    print("\n=== 尝试 @1.<DID>/x 格式 ===")
    for did in ["1", "2", "3", "0001", "0002"]:
        query(ser, f"1.{did}/2")   # 查 MAC

    # 3. 监听 10 秒，看主模组是否有延迟上报
    print("\n=== 监听 10 秒（等待主动上报）===")
    buf = bytearray()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if chunk:
            buf.extend(chunk)
            print(f"  RX: {chunk.hex(' ')}")
    if not buf:
        print("  （静默）")

    # 4. 查 @0/4/3 最后再试一次（可能需要网络稳定后才响应）
    print("\n=== @0/4/3 最终尝试 ===")
    query(ser, "0/4/3")

    ser.close()


if __name__ == "__main__":
    main()
