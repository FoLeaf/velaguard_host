---
feature: velaguard-host
status: delivered
updated: 2026-09-09
branch: feature/velaguard-host
commits: 8f6cd1f..HEAD
---

# VelaGuard 上位机主机侧适配

## Report

**What was built** — 在**原工程 UI**（`window.py`/`config.py`/`sourcecard_ui.py` + PNG 图标资源）基础上做 VelaGuard NSH 适配：ST-LINK COM3 115200 文本会话；侧栏控制台/实时数据/参数设置与原视觉一致；新增数据源仍弹出原对话框并生成带 `sensor.png` 的卡片；「获取数据流」对本地监视点周期 `vgdiscover test-read`；控制台日志显示完整 NSH 回显。协议契约见 `docs/PROTOCOL.md`。EB90 帧从入口移除。

**Verification** — `pytest tests`：11 passed；`compileall velaguard_host main.py tests`：PASS；`QT_QPA_PLATFORM=minimal` 下原 UI 窗口构造（含图标资源加载）：见本轮命令输出。无板子 COM3，未做真机联调。

**Journey log** — 1) 首轮误做成纯控件新 UI，用户明确要求以原工程为基础、保留图片资源。2) 归档 `upper computer.7z` 与 git 基线 `8f6cd1f` 一致，已回退 Designer 壳。3) 协议层 `velaguard_host/protocol.py` 可保留复用。4) 板端落盘仍只能手动 `apply --confirm`。5) `parse_scan` 不再捏造地址。

## [S1] Problem

现有 `F:\Project\uppercomputer` 是未完成的 PyQt5「网关工具」：

- 串口读到 `decode_task` 为空，无协议解析；
- `create_new_source` 在串口未打开时崩溃；
- 依赖未声明（`crc` / `pyserial` / `PyQt5`），本地 `.venv` 已损坏；
- 组帧协议（`EB 90` + JSON + STM32 风格 CRC32 + `ED`）在板端 **没有对应实现**；
- 与 VelaGuard（contest2026_004_TeamFalcons）正式主机口不一致。

目标工程主机口是 **ST-LINK USB CDC（默认 COM3）上的 openvela NSH 文本控制台**。上位机 UI **必须以原工程 Designer 壳与图片资源为基础**，只替换通信与数据流逻辑，不得重写成无资源纯控件界面。

## [S2] Design

### 2.1 传输与会话

| 项 | 约定 |
|----|------|
| 物理口 | ST-LINK VCP，默认 `COM3`，115200 8N1 |
| 打开 | 不拉高 DTR/RTS，避免复位/丢会话 |
| 行结束 | `\n`（接受 `\r\n` 回显） |
| 提示符 | `nsh>` 或 `vela>`；收到提示符 = 命令结束 |
| 超时 | 默认 20s；`vgdiscover scan/probe` 可 45–60s；轮询 8s |
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

关键输出模式与 `protocol.py` / `docs/PROTOCOL.md` §5 一致。

### 2.3 安全与边界

1. `apply --confirm` 仅可在底部控制台**手动**执行；UI 不一键落盘。
2. 上位机不向 RS485 发 Modbus；现场总线主站仅为板端。
3. 「新增数据源」只创建**本地监视卡片**，不写板端点表。
4. 候选文件与 live 点表区分：candidate ≠ applied。
5. 断连时停止轮询，不重放未确认命令。

### 2.4 模块结构（以原 UI 为基）

```text
main.py                      # 入口：挂接原 UI + NSH（禁止纯控件重写）
window.py / res_rc.py / *.png   # 原主窗口 + 图标（保留）
config.py                    # 原添加数据源对话框（保留）
sourcecard_ui.py / sourcecard_src_rc.py / sensor.png  # 原卡片（保留）
velaguard_host/
  nsh_session.py / protocol.py / models.py / worker.py
docs/PROTOCOL.md
docs/compose/spec/velaguard-host.md
requirements.txt
tests/test_protocol.py
```

**禁止**用 `app_window.py` 一类无 Designer/无图片的纯控件界面替换原壳。

### 2.5 UI 接线（原控件语义）

| 原控件 | 行为 |
|--------|------|
| 侧栏 控制台 / 实时数据 / 参数设置 | 切换 `stackedWidget`；日志区 `textBrowser` 常显 |
| 打开串口 + 端口下拉 | 连接 NSH；成功后发送 `?` |
| 新增数据源 | 原 `Ui_Dialog`；生成 `source_card`（sensor 图） |
| 获取数据流 | 开始/停止周期 `test-read`，刷新卡片值 |
| 底部控制台 | 自由 NSH 行（在原日志区阅读回显） |

### 2.6 协议规范文档

`docs/PROTOCOL.md` 覆盖：角色、物理层、行协议、命令表、输出正则、JSON schema、错误语义、时序、板端源交叉引用。

## [S3] Out of Scope

- 板端 `vgpoint` 固件实现
- MQTT 遥测/OTA 主机功能
- 保留 EB90/ED 二进制帧
- 改 VelaGuard 固件或 WSL 工程文件
- 重写 Designer UI / 删除 PNG 资源

## Tasks

- [x] T1: 协议模块 `protocol.py` + `models.py` + `nsh_session.py` — acceptance: 命令构造与输出解析单测通过；无 Qt 依赖 (covers: S2.1 S2.2 S2.4)
- [x] T2: 恢复原 UI 壳并挂接 `main.py` — acceptance: 侧栏图标与卡片资源可加载；串口打开/关闭可用 (covers: S2.4 S2.5)
- [x] T3: 数据源/轮询/控制台接线 — acceptance: test-read 驱动卡片；apply 仅手动 (covers: S2.2 S2.3 S2.5)
- [x] T4: `docs/PROTOCOL.md` + `requirements.txt` — acceptance: 文档与 `protocol.py` 一致 (covers: S2.6)
- [x] T5: 去掉 EB90 主路径与纯控件 UI — acceptance: `main.py` 不依赖 EB90；无 `app_window.py` 入口 (covers: S2.4)
- [x] T6: 单测与静态验证 — acceptance: `pytest tests` 全绿；compileall 通过 (covers: S2 S3)
