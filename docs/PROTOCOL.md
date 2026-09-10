# VelaGuard 上位机协议说明

**唯一权威口径（命令与应答）**：板端文档

`\\wsl.localhost\Debian\home\hello19y\openvela\contest2026_004_TeamFalcons\docs\velaguard-host-nsh-protocol.md`

（WSL 路径：`/home/hello19y/openvela/contest2026_004_TeamFalcons/docs/velaguard-host-nsh-protocol.md`）

本文件只描述**上位机实现如何对齐**，不复制命令表。若与板端文档冲突，以板端文档为准。

---

## 1. 实现对照

| 板端规范 | 上位机实现 |
|----------|------------|
| §2 会话 COM3 / 115200 / LF / `nsh>` | `velaguard_host/nsh_session.py` |
| §5 命令 `vgpoint …` | `velaguard_host/protocol.py` `cmd_point_*` |
| §6 稳定应答 `POINT`/`READ`/`OK`/`ERR` | `parse_vgpoint_*` |
| §4 点字段 tag/addr/fc/reg/qty/dtype/scale/unit/cmp/warn/crit/fail_n | `models.Point` + add/set 构造 |
| §5.6/§9 apply 必须 `--confirm`，与 test 分步 | UI「确认落盘」独立确认框 |
| §2 命令 ≤120 字节 | `_check_length` / `MAX_CMD_BYTES` |
| §4 tag `[A-Za-z0-9_]{1,23}` | `_check_tag` / `sanitize_tag` |

## 2. 上位机推荐流程

```text
打开串口 → ? / vgpoint list
新增点位（对话框 → vgpoint add）
试读候选（vgpoint test → 打印 READ）
【停住，人确认】
确认落盘（vgpoint apply --confirm）
可选：vgpoint list 核对
```

禁止：`test` 后脚本自动 `apply`；把 add/set 与 apply 写在同一行。

## 3. 与旧实现的关系

- 旧 EB90/CRC 帧：已废弃，板端无实现。
- `vgdiscover apply --confirm`：板端仍存在，但**点表写入主路径改为 `vgpoint apply --confirm`**。
- 本机 UI **保留原工程 Designer 壳与 PNG 资源**，不使用纯控件重写界面。

## 4. 变更策略

板端修改 `velaguard-host-nsh-protocol.md` 后，必须同步：

1. `velaguard_host/protocol.py`（构造与解析）
2. `tests/test_protocol.py`
3. 本文件「实现对照」中的差异说明

固件 `vgpoint` 若尚未上板，命令会得到 NSH `nsh: vgpoint: command not found` 一类输出——属预期，上位机仍按规范发送。
