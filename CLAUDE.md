# 给 AI Session 的上下文

## 项目简介

LM960B 双模自组网 Demo，用于香港消防署演示 PLBUS 双模（HPLC有线 + Sub-1GHz无线）自组网能力。
后续将扩展为多个 demo 场景，并用于联调测试。

## 当前版本

- `main` @ `v0.1.0`：稳定可演示版本，不要直接修改
- `dev`：日常开发分支，**当前应在此分支上工作**

开始工作前先确认分支：`git branch`，如果不在 `dev` 上，执行 `git checkout dev`。

## 分支规则

- **不要直接提交到 `main`**
- 日常开发在 `dev` 分支
- 新 demo 场景从 `dev` 切出 `feature/scene-xxx`
- 联调测试从 `dev` 或 `main` 切出 `test/xxx-yyyymmdd`，测试完不合并回主线
- 功能稳定后由开发者手动将 `dev` 合并到 `main` 并打 tag

## 开发规范

1. **禁止轻易执行"恢复出厂设置"类硬件操作**：涉及模组出厂复位、清除配置等不可逆操作，必须有明确的二次确认机制，不得在自动化流程中自动触发。
2. **写入失败时分次写入**：向模组写入失败后，拆分为更小分片逐次写入，每次写入后等待确认再继续。
3. **版本号遵循 semver**：`MAJOR.MINOR.PATCH`，当前阶段用 `0.x.y`，发布时打 tag `vX.Y.Z`。

## 硬件环境

- 串口（默认）：`/dev/cu.usbserial-1130`（PL2303）
- 串口（备用）：`/dev/cu.usbserial-10`（FTDI）
- 主模组 MAC：`4C5A001F884E`
- 从模组 MAC：`4C5A001F884F`（DID=1）
- 启动：`./run.sh`，访问 `http://localhost:8000`
- 切换串口：`SERIAL_PORT=/dev/cu.usbserial-10 ./run.sh`

## 协议关键点（已验证，勿改回）

- 寻址格式：`0.<mac>/`（小写），**不是** `1.<MAC>/`
- Token 为**小端序**（文档描述有误）
- 广播发现：`@0.ffffffffffff/2`
- 远程查询：`@0.<mac_lower>/<resource>`
