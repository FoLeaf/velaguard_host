---
feature: velaguard-host
status: delivered
updated: 2026-09-09
branch: feature/velaguard-host
commits: 8f6cd1f..3b77e3b
---

# VelaGuard 上位机主机侧适配

## Report

**What was built** — 在**原工程 UI**（Designer + PNG 图标）上实现 **`vgpoint` NSH 点表主机**：新增点位（`vgpoint add`）→ 试读候选（`vgpoint test`，展示 `READ`）→ 人工确认 → 确认落盘（`vgpoint apply --confirm`）/ 放弃候选（`abort`）。命令与应答以板端 `docs/velaguard-host-nsh-protocol.md` 为唯一权威。参数页文案改为协议说明；状态芯片显示 NSH 连接态。

**Verification** — `pytest tests`：8 passed（vgpoint 构造/解析）；`compileall`：PASS；minimal 下原 UI 构造 + 图标加载：PASS。

**Journey log** — 1) 权威协议改为板端 vgpoint 文档，不再以 vgdiscover apply 为主路径。2) 对话框无阈值字段时先 add 基础点，阈值可 `set`。3) tag 强制 ASCII `[A-Za-z0-9_]`。4) 板端固件若未实现 vgpoint，上位机仍按规范发送。

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
