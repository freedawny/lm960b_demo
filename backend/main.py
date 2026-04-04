"""
main.py — FastAPI + WebSocket + 串口读写 + 内存态节点表
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
import serial

from uapps_codec import parse_frame, T_ACK, T_CON, T_NON
from poller import Poller

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

SERIAL_PORT = "/dev/cu.usbserial-10"
SERIAL_BAUD = 115200

ws_clients: Set[WebSocket] = set()
poller: Poller | None = None


# ── 串口读取（纯 asyncio，run_in_executor 做阻塞读）────────────────

async def serial_reader(ser: serial.Serial):
    """持续从串口读取字节，解析帧后派发"""
    buf = bytearray()
    loop = asyncio.get_event_loop()

    def _read_chunk() -> bytes:
        # 阻塞读，最多 64 字节，timeout=1s
        return ser.read(64)

    while True:
        try:
            chunk = await loop.run_in_executor(None, _read_chunk)
        except Exception as e:
            logger.warning(f"[serial] 读取异常: {e}")
            await asyncio.sleep(0.1)
            continue

        if not chunk:
            continue

        logger.debug(f"[serial] RX raw: {chunk.hex(' ')}")
        buf.extend(chunk)

        # 尝试解析完整帧
        while True:
            result = parse_frame(bytes(buf))
            if result is None:
                break
            frame, consumed = result
            buf = buf[consumed:]
            await handle_rx_frame(frame)


async def serial_writer_loop(ser: serial.Serial, queue: asyncio.Queue):
    """从队列取字节写入串口"""
    loop = asyncio.get_event_loop()
    while True:
        data = await queue.get()
        try:
            await loop.run_in_executor(None, ser.write, data)
            logger.debug(f"[serial] TX: {data.hex(' ')}")
        except Exception as e:
            logger.exception(f"[serial] 写入失败: {e}")


async def handle_rx_frame(frame):
    """处理收到的串口帧"""
    logger.info(f"[serial] RX frame: type={frame.msg_type} code=0x{frame.code:02x} id=0x{frame.msg_id:04x} payload={frame.payload.hex()}")

    if frame.msg_type == T_ACK and poller:
        # 统一派发：单播响应和广播 ACK 都走 feed_response
        # poller 内部根据 _broadcast_mid 区分
        poller.feed_response(frame.msg_id, frame)

    elif frame.msg_type in (T_CON, T_NON):
        # LM960B 实测无主动上报（C3/C4 已确认），此分支仅作日志记录
        logger.info(f"[serial] 意外收到 CON/NON 帧，payload={frame.payload.hex()}")


# ── WebSocket 广播 ────────────────────────────────────────────────

async def broadcast_event(event: dict):
    logger.info(f"[ws] broadcast: {event}")
    if not ws_clients:
        return
    dead = set()
    for client in ws_clients:
        try:
            await client.send_json(event)
        except Exception:
            dead.add(client)
    ws_clients.difference_update(dead)


# ── FastAPI 应用 ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global poller

    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=1)
        logger.info(f"[serial] 已连接: {SERIAL_PORT}")
    except Exception as e:
        logger.error(f"[serial] 无法打开串口 {SERIAL_PORT}: {e}")
        sys.exit(1)

    write_queue: asyncio.Queue = asyncio.Queue()

    async def send_bytes(data: bytes):
        await write_queue.put(data)

    poller = Poller(send_bytes=send_bytes, on_result=broadcast_event)

    reader_task = asyncio.create_task(serial_reader(ser))
    writer_task = asyncio.create_task(serial_writer_loop(ser, write_queue))

    poller.start()
    logger.info("[main] 启动完成，等待前端连接...")

    yield

    poller.stop()
    reader_task.cancel()
    writer_task.cancel()
    ser.close()


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    ws_clients.add(websocket)
    logger.info(f"[ws] 客户端已连接，当前 {len(ws_clients)} 个")

    # 推送当前已知状态给新客户端
    if poller:
        if poller.master_mac:
            await websocket.send_json({"type": "master_info", "mac": poller.master_mac})
        for mac in poller.slave_macs:
            await websocket.send_json({"type": "node_join", "mac": mac})

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_clients.discard(websocket)
        logger.info(f"[ws] 客户端断开，剩余 {len(ws_clients)} 个")


_FRONTEND = Path(__file__).parent.parent / "frontend" / "index.html"

@app.get("/")
async def serve_index():
    return FileResponse(_FRONTEND)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="info")
