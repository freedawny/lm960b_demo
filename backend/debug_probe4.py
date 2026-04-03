"""
debug_probe4.py — 系统性探测节点列表接口

策略：
1. 尝试 @0/4 对象下所有可能的子资源格式
2. 尝试 @0/3/x 更多子项（可能有节点表）
3. 尝试 @2/x 对象
4. 监听主动上报（发完查询后等待）
"""

import time
import serial
from uapps_codec import build_get, build_frame, UappsFrame, T_CON, CODE_PUT, _next_id, _make_token, encode_uri_path, PREAMBLE

PORT = "/dev/tty.usbserial-10"
BAUD = 115200
TIMEOUT = 3.0


def query(ser, path, label="", method="GET"):
    if method == "GET":
        frame = build_get(path)
    else:
        mid = _next_id()
        frame = build_frame(UappsFrame(
            msg_type=T_CON, code=CODE_PUT, msg_id=mid,
            token=_make_token(mid), uapps_options=encode_uri_path(path),
        ))
    print(f"\n[TX {method}] @{path} {label}  {frame[8:].hex(' ')}")
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
                    0x84:"4.04 NotFound", 0x80:"4.00 BadReq",
                    0x85:"4.05 NotAllowed", 0x81:"4.01 Unauth"}.get(code, f"0x{code:02x}")
        # 找 payload
        payload = b""
        i = 0
        while i < len(after):
            if after[i] == 0xff:
                j = i + 1
                while j < len(after) and after[j] != 0xff:
                    j += 1
                if j < len(after):
                    payload = after[j+1:]
                else:
                    payload = after[i+1:]
                break
            i += 1
        print(f"[RX] {code_str}  payload={payload.hex(' ') if payload else '(empty)'}")
    else:
        print(f"[RX] 无响应（超时）")


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[serial] 已打开 {PORT}\n")

    # @0/3/x 更多子项（已知 20=信道模式, 21=频段, 1=DID）
    print("=== @0/3/x 扫描 ===")
    for i in [2, 3, 4, 5, 6, 7, 8, 9, 10, 22, 23, 30, 31, 50, 100]:
        query(ser, f"0/3/{i}")

    # @0/2/x 子项
    print("\n=== @0/2/x 扫描 ===")
    for i in range(1, 8):
        query(ser, f"0/2/{i}")

    # @2/x 对象
    print("\n=== @2/x 扫描 ===")
    for i in range(1, 8):
        query(ser, f"2/{i}")

    # @3/x 对象
    print("\n=== @3/x 扫描 ===")
    for i in range(1, 5):
        query(ser, f"3/{i}")

    # 尝试 PUT @0/4/3（可能需要 PUT 触发）
    print("\n=== PUT @0/4/3 ===")
    query(ser, "0/4/3", "PUT触发?", method="PUT")

    ser.close()


if __name__ == "__main__":
    main()
