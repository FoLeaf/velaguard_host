# 点表导入文件格式规范

上位机 **导入点表** 只接受 **UTF-8 JSON**。字段与板端 `points.json` / `vgpoint add` 对齐。权威命令口径仍是板端：

`contest2026_004_TeamFalcons/docs/velaguard-host-nsh-protocol.md`

示例文件：[`examples/vgpoint_demo_points.json`](../examples/vgpoint_demo_points.json)

导入只写入**候选表**（逐条 `vgpoint add -i`，id 已存在则 `set`）。**不会**自动 `vgpoint test` 或 `vgpoint apply --confirm`。

每个点两个身份字段：`id`（主键）和 `name`（显示名）。查找、去重、`set` / `del` / `test` 一律按 `id`。旧字段 `tag` **不是**身份字段：对象里只有 `tag`、没有合法 `id` 的点会丢弃，不会升成 `id`。

---

## 1. 三种合法外形

**A. 完整点表对象（推荐，与板端落盘文件一致）**

```json
{
  "schema_version": 1,
  "bus": { "device": "/dev/rs485", "baud": 9600 },
  "hits": [1, 2],
  "points": [ { "id": "temp", "name": "温度", "addr": 1, "reg": 0 } ]
}
```

`bus`、`hits` 可省略，导入时忽略，不发给板端。

**B. 只有 points**

```json
{ "points": [ { "id": "temp", "addr": 1, "reg": 0 } ] }
```

**C. 顶层数组**

```json
[ { "id": "temp", "addr": 1, "reg": 0 } ]
```

---

## 2. 点对象字段

| 字段 | 类型 | 必填 | 缺省 | 约束 |
|------|------|------|------|------|
| `id` | string | 是 | — | `[A-Za-z0-9_]{1,23}`，文件内不可重复，区分大小写 |
| `name` | string | 否 | 等于 `id` | UTF-8，1–47 字节；禁止 ASCII 空白、`=`、`"`、`\` 和控制字符；可中文、可重复 |
| `addr` | int | 是 | — | Modbus 从站 1–247 |
| `reg` | int | 是 | — | 起始寄存器，≥0 |
| `fc` | int | 否 | `3` | 仅 `3`（读保持）或 `4`（读输入） |
| `qty` | int | 否 | `1` | 1–4 |
| `dtype` | string | 否 | `int16` | `int16` 或 `uint16` |
| `scale` | number | 否 | `1` | 倍率 |
| `unit` | string | 否 | 空 | ASCII，最长 7；`""` / `"-"` 视为未设 |
| `cmp` | string | 否 | 空 | `ge` / `le` / `eq`；空或 `"-"` 表示不做模拟量告警 |
| `warn` | number | 否 | 未设 | 预警阈值；空或 `"-"` 视为未设 |
| `crit` | number | 否 | 未设 | 严重阈值；空或 `"-"` 视为未设 |
| `fail_n` | int | 否 | `3` | 连续失败次数 |

点数上限 **32**（与板端 `VG_DISCOVER_MAX_POINTS` 相同）。

每条转换成的 NSH 命令（不含换行）≤ **120 字节**（按 UTF-8 计）。名称较长时上位机会先 `add`（不带 `-N`）再 `set <id> -N <name>`。

---

## 3. 完整示例

```json
{
  "schema_version": 1,
  "bus": { "device": "/dev/rs485", "baud": 9600 },
  "points": [
    {
      "id": "temp",
      "name": "温度",
      "addr": 1,
      "fc": 3,
      "reg": 0,
      "qty": 1,
      "dtype": "int16",
      "scale": 0.1,
      "unit": "C",
      "cmp": "ge",
      "warn": 40,
      "crit": 55,
      "fail_n": 3
    },
    {
      "id": "flood",
      "name": "水浸",
      "addr": 2,
      "fc": 3,
      "reg": 2,
      "qty": 1,
      "dtype": "uint16",
      "scale": 1,
      "unit": "",
      "cmp": "eq",
      "crit": 1,
      "fail_n": 3
    }
  ]
}
```

---

## 4. 预览校验失败的常见原因

- 不是 JSON，或既没有 `points` 也不是点对象数组
- 缺少合法 `id`（含空格/中文，或超过 23 字符）；仅有旧字段 `tag` 不算
- 文件内两个点 `id` 相同
- `name` 含空格、`=`、引号，或超过 47 字节
- `addr` 不在 1–247，`fc` 不是 3/4
- 超过 32 点
- 拼出的 `vgpoint add ...` 超过 120 字节（且无法拆成 add + set name）

有任一行标红时，上位机不会开始导入、也不会往串口发命令。
