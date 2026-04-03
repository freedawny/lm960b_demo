# Milestone v0.1 — 2026-04-03

## 功能完成情况

### 协议层
- 逆向厂商测试软件日志，修正寻址格式：`0.<mac>/`（小写），非文档描述的 `1.<MAC>/`
- Token 修正为小端序（文档描述有误）
- 广播发现改用 `@0.ffffffffffff/2`，从节点响应正常
- 远程查询用 `@0.<mac_lower>/<resource>`

### 后端
- FastAPI + WebSocket，串口异步读写（`asyncio` + `run_in_executor`）
- 周期广播发现（每 30s）+ 轮询（信道模式、频段、可达性，每 5s）
- 新 WebSocket 客户端连接时推送当前节点状态快照
- 主动上报帧（NODE_JOIN）处理：`T_CON`/`T_NON` 帧尝试提取 MAC

### 前端
- ECharts 拓扑图，节点颜色：橙=双模，绿=PLC，蓝=无线，灰=离线
- 节点状态表（MAC、角色、状态、模式、RTT）
- 事件时间线（最新5条，区分 join/timeout/recover/mode）
- WebSocket 断线自动重连（3s）

### 环境
- 串口：`/dev/cu.usbserial-10`（FTDI），主模组 MAC `4C5A001F884E`
- 从模组 MAC `4C5A001F884F`，DID 已设为 1
- 启动：`./run.sh`，访问 `http://localhost:8000`

## 待完成
- 从节点断电恢复后可达性恢复验证（Ping 已改用 `@0.<mac>/1`）
- 模式切换上报帧格式（需实际抓包确认，协议文档 C4）
- NODE_JOIN 上报帧格式（需实际抓包确认，协议文档 C3）
- CRC 校验（协议文档 C2，目前无校验）
