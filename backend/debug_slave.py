import sys, time
sys.path.insert(0, '/Users/bonniedeng/文件/Source/lm960b_demo/backend')
import serial
from uapps_codec import build_get, PREAMBLE, parse_frame, extract_mac, extract_channel_mode, CHANNEL_MODE_NAMES

PORT = '/dev/cu.PL2303G-USBtoUART10'
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
    print(f'@{path} RX: {data.hex(" ") if data else "(无响应)"}')
    return data

# 查 MAC
data = query('0/2')
result = parse_frame(data)
if result:
    mac = extract_mac(result[0].payload)
    print(f'  → MAC: {mac}')

# 查 DID
data = query('0/3/1')
result = parse_frame(data)
if result and len(result[0].payload) >= 2:
    did = int.from_bytes(result[0].payload[:2], 'big')
    print(f'  → DID: {did} (0x{did:04x})')

# 查信道模式
data = query('0/3/20')
result = parse_frame(data)
if result:
    mode = extract_channel_mode(result[0].payload)
    print(f'  → 信道模式: {mode} ({CHANNEL_MODE_NAMES.get(mode, "?")})' )

ser.close()
