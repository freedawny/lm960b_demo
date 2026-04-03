"""
debug_did_scan.py — 用 DID 格式扫描从节点

@1.<DID>/2 → 查 MAC（确认节点存在）
@1.<DID>/3/20 → 查信道模式
@1.<DID>/104/1 → ping

DID 是 16-bit 整数，用十进制字符串表示（如 "1", "2", "3"...）
"""

import time
import serial
from uapps_codec import build_get, build_ping, PREAMBLE, \
    build_frame, UappsFrame, T_CON, CODE_PUT, _next_id, _make_token, \
    encode_uri_path, encode_size_option

PORT = "/dev/tty.usbserial-10"
BAUD = 115200
TIMEOUT = 4.0
MASTER_MAC = "4C5A001F884E"


def query(ser, path, label=""):
    frame = build_get(path)
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
        return None, None

    idx = buf.find(PREAMBLE)
    after = buf[idx+8:] if idx >= 0 else buf
    code = after[1] if len(after) > 1 else 0
    pl = b""
    for i in range(len(after)):
        if after[i] == 0xff:
            j = i + 1
            while j < len(after) and after[j] != 0xff:
                j += 1
            pl = after[j+1:] if j < len(after) else after[i+1:]
            break
    return code, pl


def ping_did(ser, did_str):
    """用 DID 格式 ping：@1.<DID>/104/1"""
    path = f"1.{did_str}/104/1"
    mid = _next_id()
    payload = b"\x11" * 10
    uapps_opts = encode_uri_path(path) + encode_size_option(0x2A)
    frame = build_frame(UappsFrame(
        msg_type=T_CON, code=CODE_PUT, msg_id=mid,
        token=_make_token(mid), uapps_options=uapps_opts,
        payload=payload,
    ))
    t0 = time.monotonic()
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
                time.sleep(0.1)
                buf.extend(ser.read(ser.in_waiting))
                break

    if buf and PREAMBLE in buf:
        rtt = round((time.monotonic() - t0) * 1000)
        return True, rtt
    return False, None


def main():
    ser = serial.Serial(PORT, BAUD, timeout=0.1)
    print(f"[serial] 已打开 {PORT}")
    print(f"主模组 MAC: {MASTER_MAC}\n")

    print("DID  | MAC                | 信道模式 | Ping RTT")
    print("-----|--------------------|---------|---------")

    for did in range(1, 20):
        did_str = str(did)

        # 查 MAC
        code, mac_pl = query(ser, f"1.{did_str}/2")
        if code != 0x45 or not mac_pl or len(mac_pl) < 6:
            continue

        mac = mac_pl[:6].hex().upper()
        if mac == MASTER_MAC:
            # 跳过主模组自身
            continue

        # 查信道模式
        code2, mode_pl = query(ser, f"1.{did_str}/3/20")
        mode_val = mode_pl[0] if code2 == 0x45 and mode_pl else None
        mode_str = {0: "PLC", 1: "wireless", 2: "dual"}.get(mode_val, f"0x{mode_val:02x}" if mode_val is not None else "?")

        # Ping
        reachable, rtt = ping_did(ser, did_str)
        rtt_str = f"{rtt}ms" if rtt else "timeout"

        print(f"  {did:<3} | {mac} | {mode_str:<8} | {rtt_str}")

    print("\n扫描完成")
    ser.close()


if __name__ == "__main__":
    main()
