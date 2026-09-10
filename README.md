# VelaGuard Host 上位机

面向 [contest2026_004_TeamFalcons / VelaGuard](\\wsl.localhost\Debian\home\hello19y\openvela\contest2026_004_TeamFalcons) 的 Windows 配置/监视上位机。

**以原工程 UI 为基础**（Qt Designer `window.py` / `config.py` / `sourcecard_ui.py` + PNG 图标资源），主机通信改为 **openvela NSH 文本协议**（ST-LINK COM3，115200 8N1）。

- 侧栏图标：`dashboard.png` / `data.png` / `configuration.png` 等（`res.qrc` → `res_rc.py`）
- 数据源卡片：`sensor.png`（`sourcecard_src.qrc`）
- 不占用 RS485；落盘需在控制台手动 `vgdiscover apply --confirm`
- 协议规范：[`docs/PROTOCOL.md`](docs/PROTOCOL.md)
- 特性说明：[`docs/compose/spec/velaguard-host.md`](docs/compose/spec/velaguard-host.md)

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
| `main.py` | 入口；挂接原 UI 与 NSH |
| `window.py` / `res_rc.py` | 主窗口 Designer 生成 + 图标资源 |
| `config.py` | 添加数据源对话框 |
| `sourcecard_ui.py` / `sourcecard_src_rc.py` | 传感器卡片 + sensor 图 |
| `velaguard_host/nsh_session.py` | 串口行会话 |
| `velaguard_host/protocol.py` | NSH 命令构造 / 输出解析 |
| `velaguard_host/worker.py` | Qt 工作线程 |
| `tests/test_protocol.py` | 协议单测（无硬件） |

旧 `EB90/ED` 二进制帧路径已废弃，见 `docs/PROTOCOL.md` §9。
