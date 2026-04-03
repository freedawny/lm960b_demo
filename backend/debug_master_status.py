import sys, time
sys.path.insert(0, '/Users/bonniedeng/文件/Source/lm960b_demo/backend')
import serial
from uapps_codec import build_get, PREAMBLE, parse_frame

PORT = '/dev/tty.usbserial-10'
BAUD = 115200

ser = serial.Serial(PORT, BAUD, timeout=2)
print(f'[serial] 已打开 {PORT}\n')

def query(path):
    frame = build_get(path)
    ser.reset_input_buffer()
    ser.write(frame)
    ser.flush()
    time.sleep(1)
    data = ser.read(ser.in_waiting)
    result = parse_frame(data)
    payload = result[0].payload if result else b''
    print(f'@{path} → payload: {payload.hex(" ") if payload else "(空/无响应)"}')
    return payload

# 在网节点数
query('0/4/1')

# 主模组完整信息
query('0/1')

# 主模组信道模式
p = query('0/3/20')
if p:
    print(f'  信道模式: {p[0]} (0=PLC, 1=wireless, 2=dual)')

ser.close()
