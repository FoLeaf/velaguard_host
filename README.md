# VelaGuard Host 上位机

面向 [contest2026_004_TeamFalcons / VelaGuard](\\wsl.localhost\Debian\home\hello19y\openvela\contest2026_004_TeamFalcons) 的 Windows 点表配置上位机。

**以原工程 UI 为基础**（Qt Designer `window.py` / `config.py` / `sourcecard_ui.py` + PNG 图标资源）。

主机口按板端 **`vgpoint` NSH 协议**；**唯一权威**是板端文档：

`contest2026_004_TeamFalcons/docs/velaguard-host-nsh-protocol.md`

- 侧栏图标：`dashboard.png` / `data.png` / `configuration.png`（`res.qrc`）
- 点位卡片：`sensor.png`（`sourcecard_src.qrc`）
- 流程：**新增 / 导入 / 删除点位 → 试读候选 → 人工确认 → 确认落盘**（`vgpoint apply --confirm`）
- 上位机对齐说明：[`docs/PROTOCOL.md`](docs/PROTOCOL.md)
- 点表导入 JSON 格式：[`docs/POINT_TABLE_JSON.md`](docs/POINT_TABLE_JSON.md)，示例 [`examples/vgpoint_demo_points.json`](examples/vgpoint_demo_points.json)

## 运行

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests -v
.\.venv\Scripts\python.exe -m compileall velaguard_host main.py tests
```

## 模块

| 路径 | 职责 |
|------|------|
| `main.py` | 入口；原 UI + vgpoint 接线 |
| `window.py` / `res_rc.py` / `*.png` | 主窗口与图标 |
| `config.py` | 新增点位对话框 |
| `sourcecard_ui.py` | 点位卡片 |
| `velaguard_host/protocol.py` | `vgpoint` 构造/解析 |
| `velaguard_host/nsh_session.py` | NSH 行会话 |
| `velaguard_host/worker.py` | Qt 工作线程 |
| `tests/test_protocol.py` | 协议单测 |

说明：板端 `vgpoint` 若尚未合入，串口会回 command not found——上位机仍按规范发送。
