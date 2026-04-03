import time
import serial
from uapps_codec import build_broadcast_discover, PREAMBLE

ser = serial.Serial('/dev/tty.usbserial-10', 115200, timeout=0.1)
frame, mid = build_broadcast_discover()
print('TX:', frame.hex(' '))
ser.write(frame)
ser.flush()

buf = bytearray()
deadline = time.monotonic() + 5.0
while time.monotonic() < deadline:
    chunk = ser.read(ser.in_waiting or 1)
    if chunk:
        buf.extend(chunk)

if buf:
    print('RX:', buf.hex(' '))
    # 提取 payload（两个 0xFF 之后）
    after = buf[buf.find(PREAMBLE)+len(PREAMBLE):]
    ff_count = 0
    for i, b in enumerate(after):
        if b == 0xFF:
            ff_count += 1
            if ff_count == 2:
                payload = after[i+1:]
                print('payload:', payload.hex(' '))
                if len(payload) >= 6:
                    print('MAC:', payload[:6].hex().upper())
                break
else:
    print('(无响应)')
ser.close()
