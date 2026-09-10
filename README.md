# VelaGuard Host 上位机

面向 [contest2026_004_TeamFalcons / VelaGuard](\\wsl.localhost\Debian\home\hello19y\openvela\contest2026_004_TeamFalcons) 的 Windows 配置/监视上位机。

- 主机口：ST-LINK VCP（默认 COM3）上的 **openvela NSH 文本协议**（115200 8N1）
- 不占用 RS485；现场总线主站仅为板端
- 落盘必须用户显式确认：`vgdiscover apply --confirm`
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
| `main.py` | 入口 |
| `velaguard_host/nsh_session.py` | 串口行会话 |
| `velaguard_host/protocol.py` | NSH 命令构造 / 输出解析 |
| `velaguard_host/worker.py` | Qt 工作线程 |
| `velaguard_host/app_window.py` | 主界面 |
| `tests/test_protocol.py` | 协议单测（无硬件） |

旧 `EB90/ED` 二进制帧路径已废弃，见 `docs/PROTOCOL.md` §9。
