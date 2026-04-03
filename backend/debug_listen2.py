"""
debug_listen2.py — 监听串口，同时每 3 秒发一次 @0/4/3 查询
打印所有收到的原始字节，持续 60 秒
"""

import time
import threading
import serial
from uapps_codec import build_get, PREAMBLE

PORT = "/dev/tty.usbserial-10"
BAUD = 115200


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.05)
    print(f"[serial] 已打开 {PORT}，监听 60 秒...")
    print("请在此期间重启从节点（断电再上电），观察 NODE_JOIN 上报帧\n")

    # 后台线程每 5 秒发一次 @0/4/3
    def sender():
        time.sleep(2)
        while True:
            frame = build_get("0/4/3")
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] TX @0/4/3: {frame[8:].hex(' ')}")
            ser.write(frame)
            ser.flush()
            time.sleep(5)

    t = threading.Thread(target=sender, daemon=True)
    t.start()

    buf = bytearray()
    deadline = time.monotonic() + 60.0

    while time.monotonic() < deadline:
        chunk = ser.read(ser.in_waiting or 1)
        if not chunk:
            continue
        buf.extend(chunk)
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] RX raw ({len(chunk)}B): {chunk.hex(' ')}")

        # 每次收到完整帧就解码打印
        while PREAMBLE in buf:
            idx = buf.find(PREAMBLE)
            if idx > 0:
                buf = buf[idx:]
            next_idx = buf.find(PREAMBLE, len(PREAMBLE))
            if next_idx > 0:
                frame_bytes = bytes(buf[:next_idx])
                buf = buf[next_idx:]
                _print_frame(frame_bytes)
            else:
                break

    print(f"\n[done] 监听结束")
    ser.close()


def _print_frame(data: bytes):
    pre = len(PREAMBLE)
    if len(data) < pre + 4:
        return
    p = pre
    first  = data[p];  t = (first >> 4) & 3;  tkl = first & 0xF
    code   = data[p+1]
    msg_id = (data[p+2] << 8) | data[p+3]
    p += 4
    token  = data[p:p+tkl];  p += tkl
    rest   = data[p:]
    tname  = {0:"CON",1:"NON",2:"ACK",3:"RST"}.get(t,"?")
    cname  = {0x45:"2.05 Content",0x44:"2.04 Changed",
              0x84:"4.04 NotFound",0x80:"4.00 BadReq",
              0x01:"0.01 GET",0x03:"0.03 PUT"}.get(code, f"0x{code:02x}")
    print(f"  ↳ FRAME type={tname} code={cname} id=0x{msg_id:04x} "
          f"token={token.hex()} rest={rest.hex(' ')}")


if __name__ == "__main__":
    main()
