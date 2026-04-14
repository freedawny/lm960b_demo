"""
poller.py — 周期查询任务

策略：
  - 启动后先查主模组 MAC（@0/2）
  - 然后发广播发现帧（CON GET @0.ffffffffffff/2）
    等待 BROADCAST_WINDOW 秒收集所有从节点 ACK，每个 ACK payload 含从节点 6字节 MAC
  - 之后每轮（默认 5s）对所有已知从节点依次执行：
      1. GET @0.<mac_lower>/3/20  → 信道模式
      2. GET @0.<mac_lower>/3/21  → 无线频段
      3. GET @0.<mac_lower>/1    → 可达性（RTT）
  - 每隔 DISCOVER_INTERVAL 重新广播一次，发现新加入的从节点
  - LM960B 无主动上报机制，节点加入/模式切换均靠轮询感知（实测确认 2026-04-04）
  - 结果通过回调 on_result(event_dict) 推给 main.py
"""

import asyncio
import time
import logging
from typing import Callable, Awaitable

from uapps_codec import (
    build_get, build_ping, build_broadcast_discover,
    T_ACK, CODE_CONTENT, CODE_CHANGED,
    extract_mac, extract_channel_mode, CHANNEL_MODE_NAMES,
    get_last_msg_id,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL     = 5.0   # 秒，每轮轮询间隔
RESPONSE_TIMEOUT  = 3.0   # 秒，单播请求等待超时
BROADCAST_WINDOW  = 5.0   # 秒，广播后收集 ACK 的窗口
DISCOVER_INTERVAL = 30.0  # 秒，重新广播发现的间隔


class Poller:
    def __init__(
        self,
        send_bytes: Callable[[bytes], Awaitable[None]],
        on_result: Callable[[dict], Awaitable[None]],
    ):
        self._send = send_bytes
        self._on_result = on_result

        # msg_id -> asyncio.Future，单播请求等待
        self._pending: dict[int, asyncio.Future] = {}

        # 广播发现：收集广播 ACK 中的 MAC，key=广播 msg_id，value=Queue
        self._broadcast_queue: asyncio.Queue | None = None
        self._broadcast_mid: int | None = None

        # 已知从节点 MAC 集合（12位大写十六进制字符串）
        self.slave_macs: set[str] = set()

        # 主模组 MAC（首次查询后填入）
        self.master_mac: str | None = None

        self._running = False
        self._task: asyncio.Task | None = None

    # ── 外部接口 ──────────────────────────────────────────────────

    def start(self):
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    def add_slave(self, mac: str):
        """动态注册新发现的从节点（广播发现 ACK 或外部调用时使用）"""
        mac = mac.upper()
        if mac not in self.slave_macs:
            self.slave_macs.add(mac)
            logger.info(f"[poller] 新从节点注册: {mac}")

    def feed_response(self, msg_id: int, frame):
        """
        main.py 收到串口帧后调用。
        - 单播请求：派发给对应 Future
        - 广播 ACK：投入广播收集队列
        """
        # 广播 ACK：msg_id 与广播帧相同，投入队列
        if self._broadcast_queue is not None and msg_id == self._broadcast_mid:
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(self._broadcast_queue.put_nowait, frame)
            return

        # 单播响应
        fut = self._pending.get(msg_id)
        if fut and not fut.done():
            loop = fut.get_loop()
            loop.call_soon_threadsafe(fut.set_result, frame)

    # ── 内部实现 ──────────────────────────────────────────────────

    async def _send_and_wait(self, raw: bytes, msg_id: int) -> object | None:
        """发送帧并等待对应 msg_id 的单播响应，超时返回 None"""
        loop = asyncio.get_event_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[msg_id] = fut
        try:
            await self._send(raw)
            return await asyncio.wait_for(asyncio.shield(fut), timeout=RESPONSE_TIMEOUT)
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending.pop(msg_id, None)

    async def _query_master_mac(self):
        """查询主模组 MAC（@0/2）"""
        raw = build_get("0/2")
        mid = get_last_msg_id()
        resp = await self._send_and_wait(raw, mid)
        if resp is None:
            logger.warning("[poller] 主模组 @0/2 超时")
            return
        mac = extract_mac(resp.payload)
        if mac:
            self.master_mac = mac
            logger.info(f"[poller] 主模组 MAC: {mac}")
            await self._on_result({"type": "master_info", "mac": mac})

    async def _discover_slaves(self):
        """
        广播发现从节点。
        发送 NON POST @1.FFFFFFFFFFFF/104/3（code=0x02），
        等待 BROADCAST_WINDOW 秒收集所有从节点 ACK。
        每个 ACK 的 payload 为从节点 MAC（6字节）。
        """
        raw, mid = build_broadcast_discover()
        self._broadcast_mid = mid
        self._broadcast_queue = asyncio.Queue()

        logger.info(f"[poller] 广播发现，msg_id=0x{mid:04x}，等待 {BROADCAST_WINDOW}s...")
        await self._send(raw)

        deadline = time.monotonic() + BROADCAST_WINDOW
        found = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                frame = await asyncio.wait_for(
                    self._broadcast_queue.get(), timeout=remaining
                )
                mac = extract_mac(frame.payload)
                if mac and mac != self.master_mac:
                    if mac not in self.slave_macs:
                        self.slave_macs.add(mac)
                        found += 1
                        logger.info(f"[poller] 广播发现从节点: {mac}")
                        await self._on_result({"type": "slave_found", "mac": mac})
            except asyncio.TimeoutError:
                break

        self._broadcast_queue = None
        self._broadcast_mid = None
        logger.info(f"[poller] 广播发现结束，本次新增 {found} 个从节点，共 {len(self.slave_macs)} 个")

    async def _poll_slave(self, mac: str):
        """对单个从节点执行一轮查询"""
        mac_lower = mac.lower()

        # 1. 信道模式
        raw = build_get(f"0.{mac_lower}/3/20")
        resp = await self._send_and_wait(raw, get_last_msg_id())
        mode_val = None
        if resp is not None:
            mode_val = extract_channel_mode(resp.payload)

        # 2. 无线频段
        raw = build_get(f"0.{mac_lower}/3/21")
        resp2 = await self._send_and_wait(raw, get_last_msg_id())
        band_val = None
        if resp2 is not None and resp2.payload:
            band_val = resp2.payload[0]

        # 3. 用 @0.<mac>/1 查基本信息判断可达性（厂商实测有效）
        t0 = time.monotonic()
        raw = build_get(f"0.{mac_lower}/1")
        resp3 = await self._send_and_wait(raw, get_last_msg_id())
        rtt_ms = None
        reachable = False
        if resp3 is not None:
            rtt_ms = round((time.monotonic() - t0) * 1000)
            reachable = True

        await self._on_result({
            "type": "node_status",
            "mac": mac,
            "reachable": reachable,
            "mode": CHANNEL_MODE_NAMES.get(mode_val) if mode_val is not None else None,
            "mode_val": mode_val,
            "band": band_val,
            "rtt_ms": rtt_ms,
            "ts": time.time(),
        })

    async def _loop(self):
        # 1. 获取主模组 MAC
        while self._running and self.master_mac is None:
            await self._query_master_mac()
            if self.master_mac is None:
                await asyncio.sleep(2.0)

        # 2. 首次广播发现
        await self._discover_slaves()

        last_discover = time.monotonic()

        # 3. 轮询循环
        while self._running:
            t_start = time.monotonic()

            # 定期重新广播发现
            if t_start - last_discover >= DISCOVER_INTERVAL:
                await self._discover_slaves()
                last_discover = time.monotonic()

            for mac in list(self.slave_macs):
                try:
                    await self._poll_slave(mac)
                except Exception as e:
                    logger.exception(f"[poller] 轮询 {mac} 异常: {e}")

            elapsed = time.monotonic() - t_start
            sleep_time = max(0.0, POLL_INTERVAL - elapsed)
            await asyncio.sleep(sleep_time)
