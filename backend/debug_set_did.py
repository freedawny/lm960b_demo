import sys, time
sys.path.insert(0, '/Users/bonniedeng/文件/Source/lm960b_demo/backend')
import serial
from uapps_codec import build_frame, UappsFrame, T_CON, CODE_PUT, _next_id, _make_token, encode_uri_path, encode_size_option, PREAMBLE, parse_frame

PORT = '/dev/cu.PL2303G-USBtoUART10'
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=2)
print(f'[serial] 已打开 {PORT}\n')

# 设置 DID = 1 (0x0001)
did_value = b'\x00\x01'
mid = _next_id()
uapps_opts = encode_uri_path('0/3/1') + encode_size_option(len(did_value))
frame = build_frame(UappsFrame(
    msg_type=T_CON, code=CODE_PUT, msg_id=mid,
    token=_make_token(mid),
    uapps_options=uapps_opts,
    payload=did_value,
))
print(f'TX SET DID=1: {frame.hex(" ")}')
ser.reset_input_buffer()
ser.write(frame)
ser.flush()
time.sleep(1)
data = ser.read(ser.in_waiting)
print(f'RX: {data.hex(" ") if data else "(无响应)"}')
result = parse_frame(data)
if result:
    print(f'  → code=0x{result[0].code:02x} (0x44=Changed=成功)')

ser.close()
