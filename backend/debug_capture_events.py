"""
debug_capture_events.py — 捕获主动上报帧（NODE_JOIN / 模式切换）

用途：
  - C3：触发从节点断电再上电，观察 NODE_JOIN 上报帧原始格式
  - C4：断开从节点有线路径，观察模式切换上报帧原始格式

操作步骤：
  1. python debug_capture_events.py
  2. 对从节点断电再上电（触发 NODE_JOIN）
  3. 断开从节点有线路径（触发模式切换）
  4. Ctrl+C 停止，复制输出到文档

输出：每帧打印时间戳 + 完整原始字节 + 解码字段
"""

import sys
import time
import struct
import serial

PORT = "/dev/cu.usbserial-10"
BAUD = 115200
PREAMBLE = bytes([0x1B, 0x1B, 0x1B, 0x1B, 0x1B, 0x0A, 0x1B, 0x0A])

TYPE_NAMES = {0: "CON", 1: "NON", 2: "ACK", 3: "RST"}
CODE_NAMES = {
    0x01: "0.01 GET", 0x02: "0.02 POST", 0x03: "0.03 PUT",
    0x44: "2.04 Changed", 0x45: "2.05 Content",
    0x80: "4.00 BadRequest", 0x84: "4.04 NotFound",
}

frame_count = 0


def decode_frame(data: bytes, ts: str):
    global frame_count
    pre = len(PREAMBLE)
    if len(data) < pre + 4:
        return

    p = pre
    first  = data[p]
    t      = (first >> 4) & 0x03
    tkl    = first & 0x0F
    code   = data[p + 1]
    msg_id = struct.unpack_from(">H", data, p + 2)[0]
    p += 4

    token = data[p:p + tkl]
    p += tkl

    rest = data[p:]

    frame_count += 1
    tname = TYPE_NAMES.get(t, f"?({t})")
    cname = CODE_NAMES.get(code, f"0x{code:02x}")

    print(f"\n{'='*60}")
    print(f"[{ts}] FRAME #{frame_count}")
    print(f"  raw  : {data.hex(' ')}")
    print(f"  type : {tname}  code : {cname}  id : 0x{msg_id:04x}")
    print(f"  token: {token.hex() or '(none)'}")
    print(f"  rest : {rest.hex(' ') or '(empty)'}")

    # 尝试解析 rest 中的 payload（跳过选项域）
    payload = _extract_payload(rest)
    if payload:
        print(f"  payload ({len(payload)}B): {payload.hex(' ')}")
        if len(payload) == 6:
            mac = payload.hex().upper()
            print(f"  → 疑似 MAC: {mac}")
        elif len(payload) == 1:
            print(f"  → 疑似单字节值: 0x{payload[0]:02x} ({payload[0]})")


def _extract_payload(rest: bytes) -> bytes:
    """跳过选项域（到第二个 0xFF），返回 payload"""
    # 跳过第一个 0xFF（Flag1，CoAP选项结束）
    p = 0
    if p < len(rest) and rest[p] == 0xFF:
        p += 1
    # 跳过 Uapps 选项直到第二个 0xFF（Flag2）
    while p < len(rest) and rest[p] != 0xFF:
        opt_byte = rest[p]
        delta_n  = (opt_byte >> 4) & 0x0F
        len_n    = opt_byte & 0x0F
        p += 1
        if delta_n == 13:
            p += 1
        elif delta_n == 14:
            p += 2
        if len_n == 13:
            if p >= len(rest): break
            ext = rest[p] + 13; p += 1; p += ext
        elif len_n == 14:
            if p + 1 >= len(rest): break
            ext = struct.unpack_from(">H", rest, p)[0] + 269; p += 2; p += ext
        else:
            p += len_n
    if p < len(rest) and rest[p] == 0xFF:
        p += 1
    return rest[p:]


def main():
    try:
        ser = serial.Serial(PORT, BAUD, timeout=0.05)
    except Exception as e:
        print(f"[error] 无法打开串口 {PORT}: {e}")
        sys.exit(1)

    print(f"[serial] 已打开 {PORT}，持续监听，Ctrl+C 停止")
    print("请操作硬件触发事件：")
    print("  - 从节点断电再上电  → 捕获 NODE_JOIN（C3）")
    print("  - 断开从节点有线路径 → 捕获模式切换（C4）\n")

    buf = bytearray()
    try:
        while True:
            chunk = ser.read(ser.in_waiting or 1)
            if not chunk:
                continue
            ts = time.strftime("%H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"
            buf.extend(chunk)

            # 提取完整帧
            while True:
                idx = buf.find(PREAMBLE)
                if idx < 0:
                    buf.clear()
                    break
                if idx > 0:
                    buf = buf[idx:]
                next_idx = buf.find(PREAMBLE, len(PREAMBLE))
                if next_idx > 0:
                    frame_bytes = bytes(buf[:next_idx])
                    buf = buf[next_idx:]
                    decode_frame(frame_bytes, ts)
                else:
                    break

    except KeyboardInterrupt:
        print(f"\n\n[done] 共捕获 {frame_count} 帧，串口已关闭")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
