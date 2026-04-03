import sys, time
sys.path.insert(0, '/Users/bonniedeng/文件/Source/lm960b_demo/backend')
import serial
from uapps_codec import build_frame, UappsFrame, T_CON, CODE_PUT, _next_id, _make_token, encode_uri_path, parse_frame

PORT = '/dev/tty.usbserial-10'
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=2)
print(f'[serial] 已打开 {PORT}')
print('警告：即将恢复主模组出厂设置，3秒后执行，Ctrl+C 取消...')
time.sleep(3)

mid = _next_id()
frame = build_frame(UappsFrame(
    msg_type=T_CON, code=CODE_PUT, msg_id=mid,
    token=_make_token(mid),
    uapps_options=encode_uri_path('0/1/2'),
    payload=b'',
))
print(f'TX 恢复出厂: {frame.hex(" ")}')
ser.reset_input_buffer()
ser.write(frame)
ser.flush()
time.sleep(2)
data = ser.read(ser.in_waiting)
print(f'RX: {data.hex(" ") if data else "(无响应/模组已重启)"}')

ser.close()
print('完成，请等待模组重启（约5秒），然后对从节点做同样操作')
