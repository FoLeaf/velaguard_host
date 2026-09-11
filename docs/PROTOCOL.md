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
| §4 点字段 id/name/addr/fc/reg/qty/dtype/scale/unit/cmp/warn/crit/fail_n | `models.Point` + add/set 构造 |
| §5.6/§9 apply 必须 `--confirm`，与 test 分步 | UI「确认落盘」独立确认框 |
| §2 命令 ≤120 字节（UTF-8） | `_check_length` / `cmd_byte_len` / `MAX_CMD_BYTES` |
| §4 id `[A-Za-z0-9_]{1,23}` | `_check_id` |
| §4 name UTF-8 1..47 字节，可中文 | `_check_name`；卡片显示 name，操作仍按 id |
| §5.2 add `-i` / `-N`，不再使用 `-t` | `cmd_point_add`；超长 name 则 add 后再 `set -N` |
| §7 `dup_id` / `no_id` | 导入已存在则改 set；编辑/删除按 id |

## 2. 上位机推荐流程

```text
打开串口 → ? / vgpoint list
新增点位（对话框 → vgpoint add）或导入 JSON 点表
删除点位（单点 × / 勾选批量 / 参数表多选）
试读候选（vgpoint test → 打印 READ）
【停住，人确认】
确认落盘（vgpoint apply --confirm）
可选：vgpoint list 核对
```

禁止：`test` 后脚本自动 `apply`；把 add/set 与 apply 写在同一行。

点表 JSON 导入格式见 [`POINT_TABLE_JSON.md`](POINT_TABLE_JSON.md)。导入与删除都只改候选表，不会自动 `apply --confirm`。删光候选后，`apply --confirm` 应把已确认表写成空表（需板端允许「候选文件存在且 n=0」；候选文件缺失仍是 `no_candidate`）。

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
