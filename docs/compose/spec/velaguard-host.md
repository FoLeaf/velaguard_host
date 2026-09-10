---
feature: velaguard-host
status: delivered
updated: 2026-09-09
branch: feature/velaguard-host
commits: 8f6cd1f..a22db3d
---

# VelaGuard 上位机主机侧适配

## Report

**What was built** — 将未完成的通用 PyQt5 网关工具重写为 VelaGuard **NSH 配置/监视主机**：ST-LINK COM3 115200 文本会话；`vgdiscover` 扫描/探测/dump/试读/`apply`（落盘需独立确认）；点表 JSON 拉取与表格展示；`vgcfg`/`vgstats`；周期监视；自由终端与日志。协议契约写在 `docs/PROTOCOL.md`，与板端 `vgdiscover.c`/`vgcfg.c`/`vgstats.c`/`modbus_collector.c` 交叉引用。旧 `EB90/ED` 二进制帧从主入口移除（板端本无实现）。

**Verification** — `pytest tests`：11 passed；`compileall velaguard_host main.py tests`：PASS；`QT_QPA_PLATFORM=minimal` 下窗口构造（标题 + 4 个 Tab）：PASS。无板子 COM3，未做真机联调。

**Journey log** — 1) 用户选定 NSH 而非二进制帧，与 `09-09-nsh-vgpoint-host-editor` 对齐但 Host 只用已实现命令。2) 项目 PRD R7 原写「先不要 Windows GUI」；本任务按用户显式要求交付 GUI，文档中标明与 R7 的差异。3) 本地 `.venv` 损坏已重建；PyQt5 首装走清华镜像。4) `SerialController` 初版线程模型在 minimal platform 下崩溃，改为无 parent 的 `QThread` + queued signals。5) `parse_scan` 曾在仅有 `found N` 时捏造 `addr=1..N`，审查后删除该降级。

## [S1] Problem

现有 `F:\Project\uppercomputer` 是未完成的 PyQt5「网关工具」：

- 串口读到 `decode_task` 为空，无协议解析；
- `create_new_source` 在串口未打开时崩溃；
- 依赖未声明（`crc` / `pyserial` / `PyQt5`），本地 `.venv` 已损坏；
- 组帧协议（`EB 90` + JSON + STM32 风格 CRC32 + `ED`）在板端 **没有对应实现**；
- 与 VelaGuard（contest2026_004_TeamFalcons）正式主机口不一致。

目标工程的主机口是 **ST-LINK USB CDC（默认 COM3）上的 openvela NSH 文本控制台**，不是二进制帧。已实现命令包括 `vgdiscover` / `vgcfg` / `vgstats` / `vgmodbus` 等；`vgpoint` 仍是赛后任务。RS485 只给板当 Modbus 主站，上位机不得占用。

需要：把上位机优化为结构清晰的 **VelaGuard 配置/监视主机**，协议对齐板端 NSH，并给出可执行的协议规范。

## [S2] Design

### 2.1 传输与会话

| 项 | 约定 |
|----|------|
| 物理口 | ST-LINK VCP，默认 `COM3`，115200 8N1 |
| 打开 | 不拉高 DTR/RTS，避免复位/丢会话 |
| 行结束 | `\n`（接受 `\r\n` 回显） |
| 提示符 | `nsh>` 或 `vela>`；收到提示符 = 命令结束 |
| 超时 | 默认 20s；`vgdiscover scan/probe` 可 45–60s |
| 并发 | 单连接单命令；UI 线程不阻塞，读写在 QThread |

### 2.2 NSH 命令契约（上位机可调用）

上位机 **只使用已实现命令**，不依赖 `vgpoint`。

```text
?
vgdiscover scan [-a min-max]
vgdiscover probe -a <addr> [-t 3|4|both]
vgdiscover dump [-o path]
vgdiscover test-read -a <addr> -r <reg> [-c qty]
vgdiscover apply --confirm
vgcfg dump
vgcfg probe
vgstats dump [slave]
vgmodbus -a <slave> -r <reg> -c <qty> -n 1
cat /data/velaguard/config/points.json
cat /data/velaguard/discover/point_table_candidate.json
ls /data/velaguard/config
mount
```

关键输出模式（解析用）：

- 扫描：`found N slave(s):` + 行 `  addr=N`
- 探测：`probe addr=N blocks=M` + `fc=… start=… count=… sample[0]=…`
- 试读：`addr=A reg=R: [R]=v ([s]) …`
- 落盘：`applied N points → …`；无 `--confirm` 时 `dry-run apply`
- 配置：`vgcfg: OK|FACTORY seq=… name=…`
- 统计：`vgstats: slave=… total=… ok=… crc=… timeout=…`
- 点表 JSON：`schema_version` / `bus` / `hits` / `points[]`

### 2.3 安全与边界

1. `apply` 必须用户显式点「确认落盘」，不得与 dump/test 绑在同一操作。
2. 上位机不向 RS485 发 Modbus；现场总线主站仅为板端。
3. 不实现 Agent 写点表；不实现 MQTT 下发配置。
4. 候选文件与 live 点表区分展示：candidate ≠ applied。
5. 断连时清空会话状态，不重放未确认的 apply。

### 2.4 模块结构（优化后）

```text
main.py                      # 入口
velaguard_host/
  __init__.py
  nsh_session.py             # 串口会话：打开/关闭/发命令/等提示符
  protocol.py                # 命令构造 + 输出解析（无 Qt 依赖）
  models.py                  # Point / FrameStats / ProbeHit / DeviceInfo
  worker.py                  # QThread worker + 信号
  app_window.py              # 主窗口与页面编排
docs/PROTOCOL.md             # 协议规范（人读 + 实现对照）
docs/compose/spec/velaguard-host.md
requirements.txt
tests/test_protocol.py       # 解析器与命令构造单测（无 GUI）
```

旧 UI 生成文件（`window.py` / `config.py` / `sourcecard_ui.py`）与二进制帧代码不再作为主路径；`main1.py` 删除或归档说明。资源图可保留但新 UI 可不引用。

### 2.5 UI 页面（功能，不重做视觉皮肤）

1. **连接**：端口列表、波特率、打开/关闭、状态、最近错误。
2. **探查**：地址范围、扫描/探测/试读/落盘（落盘需二次确认）。
3. **点表**：拉取 `points.json` / candidate，表格展示 tag/addr/fc/reg/scale/unit。
4. **监视**：周期 `test-read` 或 `vgmodbus`，展示 raw 与 scaled。
5. **终端**：自由 NSH 行 + 完整日志。

### 2.6 协议规范文档

`docs/PROTOCOL.md` 覆盖：角色、物理层、行协议、命令表、输出正则、JSON schema、错误语义、时序（发现→候选→确认）、与板端源文件交叉引用。

## [S3] Out of Scope

- 板端 `vgpoint` 固件实现（赛后任务 `09-09-nsh-vgpoint-host-editor`）
- MQTT 遥测/OTA 主机功能
- 保留 EB90/ED 二进制帧协议
- 改 VelaGuard 固件或 WSL 工程文件
- 产线 HMI 复刻、云端 Agent

## Tasks

- [x] T1: 协议模块 `protocol.py` + `models.py` + `nsh_session.py` — acceptance: 命令构造与输出解析单测通过；无 Qt 依赖 (covers: S2.1 S2.2 S2.4)
- [x] T2: GUI 骨架 `app_window.py` + `worker.py` + `main.py` — acceptance: 可列出端口、打开串口、发 `?` 并显示回显 (covers: S2.4 S2.5)
- [x] T3: 探查/点表/监视/终端页面接线 — acceptance: 扫描与 test-read 路径调用正确命令；apply 有独立确认 (covers: S2.2 S2.3 S2.5)
- [x] T4: `docs/PROTOCOL.md` + `requirements.txt` + 依赖修复说明 — acceptance: 协议文档与 `protocol.py` 字面量一致；requirements 可装 (covers: S2.6)
- [x] T5: 清理旧主路径引用 — acceptance: `python -m compileall` 通过；`main.py` 不再依赖 EB90 帧 (covers: S2.4)
- [x] T6: 单测与静态验证 — acceptance: `pytest tests` 全绿；compileall 通过 (covers: S2 S3)
