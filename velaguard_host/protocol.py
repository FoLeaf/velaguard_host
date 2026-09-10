"""VelaGuard NSH protocol — 权威口径见板端文档

contest2026_004_TeamFalcons/docs/velaguard-host-nsh-protocol.md

上位机只发文本行；稳定应答前缀 `vgpoint:`。
命令字节数（不含行结束）上限 120。
"""

from __future__ import annotations

import json
import re
from typing import Optional

from .models import (
    DeviceInfo,
    FrameStats,
    Point,
    PointTable,
    RegisterSample,
    TestReadResult,
    VgPointRead,
    VgPointStatus,
)

PROMPT_RE = re.compile(r"(?:nsh>|vela>)\s*$", re.MULTILINE)

# Official primary apply
SAFE_APPLY_CMD = "vgpoint apply --confirm"
CANDIDATE_PATH = "/data/velaguard/discover/point_table_candidate.json"
POINTS_PATH = "/data/velaguard/config/points.json"
MAX_CMD_BYTES = 120
TAG_RE = re.compile(r"^[A-Za-z0-9_]{1,23}$")
CMP_VALUES = ("ge", "le", "eq")

_OK_RE = re.compile(
    r"^vgpoint:\s+OK\s+cmd=(\S+)\s+table=(\S+)\s+n=(\d+)\s*$", re.MULTILINE
)
_ERR_RE = re.compile(
    r"^vgpoint:\s+ERR\s+cmd=(\S+)\s+code=(\S+)\s+msg=(\S+)\s*$", re.MULTILINE
)
_POINT_RE = re.compile(r"^vgpoint:\s+POINT\s+(.*)$", re.MULTILINE)
_READ_RE = re.compile(r"^vgpoint:\s+READ\s+(.*)$", re.MULTILINE)


class ProtocolError(ValueError):
    pass


def cmd_help() -> str:
    return "?"


# ---- vgpoint (primary, per board protocol doc) ----

def cmd_point_list(candidate: bool = False) -> str:
    return "vgpoint list -c" if candidate else "vgpoint list"


def cmd_point_add(
    tag: str,
    addr: int,
    reg: int,
    fc: int = 3,
    qty: int = 1,
    dtype: str = "int16",
    scale: float = 1.0,
    unit: str = "",
    cmp: str = "",
    warn: Optional[float] = None,
    crit: Optional[float] = None,
    fail_n: int = 3,
) -> str:
    tag = _check_tag(tag)
    addr = _check_addr(addr)
    reg = _check_reg(reg)
    fc = _check_fc(fc)
    qty = _check_qty(qty)
    dtype = _check_dtype(dtype)
    unit = _check_unit(unit)
    cmp = _check_cmp(cmp)
    fail_n = _check_fail_n(fail_n)
    parts = [
        "vgpoint",
        "add",
        "-t",
        tag,
        "-a",
        str(addr),
        "-r",
        str(reg),
        "-f",
        str(fc),
        "-q",
        str(qty),
        "-d",
        dtype,
        "-s",
        _fmt_num(scale),
    ]
    if unit:
        parts += ["-u", unit]
    if cmp:
        parts += ["-k", cmp]
    if warn is not None:
        parts += ["-w", _fmt_num(warn)]
    if crit is not None:
        parts += ["-C", _fmt_num(crit)]
    if fail_n != 3:
        parts += ["-n", str(fail_n)]
    return _check_length(" ".join(parts))


def cmd_point_set(tag: str, **fields) -> str:
    """Set optional fields on candidate. Clear: cmp='-', warn='-'/None with '-', etc."""
    tag = _check_tag(tag)
    parts = ["vgpoint", "set", tag]
    mapping = [
        ("addr", _check_addr),
        ("reg", _check_reg),
        ("fc", _check_fc),
        ("qty", _check_qty),
        ("fail_n", _check_fail_n),
    ]
    flag = {"addr": "-a", "reg": "-r", "fc": "-f", "qty": "-q", "fail_n": "-n"}
    for key, checker in mapping:
        if key in fields and fields[key] is not None:
            parts += [flag[key], str(checker(fields[key]))]
    if "dtype" in fields and fields["dtype"] is not None:
        if fields["dtype"] == "-":
            parts += ["-d", "-"]
        else:
            parts += ["-d", _check_dtype(fields["dtype"])]
    if "scale" in fields and fields["scale"] is not None:
        parts += ["-s", _fmt_num(fields["scale"])]
    if "unit" in fields and fields["unit"] is not None:
        u = fields["unit"]
        parts += ["-u", "-" if u == "" else _check_unit(u)]
    if "cmp" in fields and fields["cmp"] is not None:
        c = fields["cmp"]
        parts += ["-k", "-" if c in ("-", "", None) else _check_cmp(c)]
    if "warn" in fields:
        w = fields["warn"]
        if w == "-":
            parts += ["-w", "-"]
        elif w is not None:
            parts += ["-w", _fmt_num(float(w))]
    if "crit" in fields:
        c = fields["crit"]
        if c == "-":
            parts += ["-C", "-"]
        elif c is not None:
            parts += ["-C", _fmt_num(float(c))]
    return _check_length(" ".join(parts))


def cmd_point_del(tag: str) -> str:
    return _check_length(f"vgpoint del {_check_tag(tag)}")


def cmd_point_test(tag: Optional[str] = None) -> str:
    if tag:
        return _check_length(f"vgpoint test {_check_tag(tag)}")
    return "vgpoint test"


def cmd_point_apply(confirm: bool = False) -> str:
    """Without --confirm board must ERR need_confirm (not dry-run success)."""
    return SAFE_APPLY_CMD if confirm else "vgpoint apply"


def cmd_point_abort() -> str:
    return "vgpoint abort"


# ---- optional discovery / inspect helpers (legacy board tools) ----

def cmd_scan(addr_min: int = 1, addr_max: int = 32) -> str:
    if addr_min < 1 or addr_max > 247 or addr_min > addr_max:
        raise ProtocolError(f"invalid address range {addr_min}-{addr_max}")
    return f"vgdiscover scan -a {addr_min}-{addr_max}"


def cmd_cfg_dump() -> str:
    return "vgcfg dump"


def cmd_stats_dump(slave: Optional[int] = None) -> str:
    return "vgstats dump" if slave is None else f"vgstats dump {slave}"


def cmd_vgmodbus(addr: int, reg: int, qty: int = 1, loops: int = 1) -> str:
    return f"vgmodbus -a {_check_addr(addr)} -r {_check_reg(reg)} -c {max(1, qty)} -n {loops} -i 0"


def cmd_cat_points(path: str = POINTS_PATH) -> str:
    return f"cat {path}"


# ---- validators ----

def _check_tag(tag: str) -> str:
    tag = (tag or "").strip()
    if not TAG_RE.match(tag):
        raise ProtocolError(f"invalid tag {tag!r} (need [A-Za-z0-9_]{{1,23}})")
    return tag


def _check_addr(addr: int) -> int:
    a = int(addr)
    if a < 1 or a > 247:
        raise ProtocolError(f"invalid addr {a}")
    return a


def _check_reg(reg: int) -> int:
    r = int(reg)
    if r < 0 or r > 65535:
        raise ProtocolError(f"invalid reg {r}")
    return r


def _check_fc(fc: int) -> int:
    f = int(fc)
    if f not in (3, 4):
        raise ProtocolError(f"invalid fc {f} (3|4)")
    return f


def _check_qty(qty: int) -> int:
    q = int(qty)
    if q < 1 or q > 4:
        raise ProtocolError(f"invalid qty {q} (1-4)")
    return q


def _check_dtype(dtype: str) -> str:
    d = (dtype or "int16").strip()
    if d not in ("int16", "uint16"):
        raise ProtocolError(f"invalid dtype {d}")
    return d


def _check_unit(unit: str) -> str:
    u = (unit or "")[:7]
    if any(ord(c) > 127 for c in u):
        raise ProtocolError("unit must be ASCII, max 7")
    return u


def _check_cmp(cmp: str) -> str:
    c = (cmp or "").strip()
    if c and c not in CMP_VALUES:
        raise ProtocolError(f"invalid cmp {c}")
    return c


def _check_fail_n(n: int) -> int:
    v = int(n)
    if v < 1 or v > 20:
        raise ProtocolError(f"invalid fail_n {v}")
    return v


def _fmt_num(x: float) -> str:
    f = float(x)
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return f"{f:g}"


def _check_length(cmd: str) -> str:
    n = len(cmd.encode("ascii", errors="ignore"))
    if n > MAX_CMD_BYTES:
        raise ProtocolError(f"command too_long ({n}>{MAX_CMD_BYTES} bytes)")
    return cmd


# ---- parsers ----

def strip_prompt(text: str) -> str:
    return PROMPT_RE.sub("", text)


def parse_vgpoint_status(text: str) -> Optional[VgPointStatus]:
    body = strip_prompt(text)
    m = _OK_RE.search(body)
    if m:
        return VgPointStatus(
            ok=True,
            cmd=m.group(1),
            table=m.group(2),
            n=int(m.group(3)),
            raw=m.group(0),
        )
    m = _ERR_RE.search(body)
    if m:
        return VgPointStatus(
            ok=False,
            cmd=m.group(1),
            code=m.group(2),
            msg=m.group(3),
            raw=m.group(0),
        )
    return None


def parse_vgpoint_points(text: str) -> list[Point]:
    points: list[Point] = []
    for m in _POINT_RE.finditer(strip_prompt(text)):
        kv = _kv(m.group(1))
        if "tag" not in kv:
            continue
        points.append(
            Point(
                tag=kv["tag"],
                addr=int(kv.get("addr", 0)),
                fc=int(kv.get("fc", 3)),
                reg=int(kv.get("reg", 0)),
                qty=int(kv.get("qty", 1)),
                dtype=kv.get("dtype", "int16"),
                scale=float(kv.get("scale", 1)),
                unit="" if kv.get("unit", "") == "-" else kv.get("unit", ""),
                cmp="" if kv.get("cmp", "-") == "-" else kv.get("cmp", ""),
                warn=_opt_float(kv.get("warn")),
                crit=_opt_float(kv.get("crit")),
                fail_n=int(kv.get("fail_n", 3)),
            )
        )
    return points


def parse_vgpoint_reads(text: str) -> list[VgPointRead]:
    reads: list[VgPointRead] = []
    for m in _READ_RE.finditer(strip_prompt(text)):
        kv = _kv(m.group(1))
        raw_s = kv.get("raw", "-")
        val_s = kv.get("value", "-")
        reads.append(
            VgPointRead(
                tag=kv.get("tag", ""),
                raw=None if raw_s == "-" else int(raw_s),
                value=None if val_s == "-" else float(val_s),
                ok=kv.get("ok", "0") == "1",
            )
        )
    return reads


def _kv(fragment: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for tok in fragment.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            out[k] = v
    return out


def _opt_float(s: Optional[str]) -> Optional[float]:
    if s is None or s == "-" or s == "":
        return None
    return float(s)


def extract_json_object(text: str) -> Optional[dict]:
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def parse_point_table_json(text: str, path: str = "") -> Optional[PointTable]:
    obj = extract_json_object(text)
    if not obj or "points" not in obj:
        return None
    bus = obj.get("bus") or {}
    table = PointTable(
        schema_version=int(obj.get("schema_version", 1)),
        device=str(bus.get("device", "")),
        baud=int(bus.get("baud", 0) or 0),
        hits=[int(x) for x in obj.get("hits") or []],
        path=path,
    )
    for p in obj.get("points") or []:
        table.points.append(
            Point(
                tag=str(p.get("tag", "")),
                addr=int(p.get("addr", 0)),
                fc=int(p.get("fc", 3)),
                reg=int(p.get("reg", 0)),
                qty=int(p.get("qty", 1)),
                dtype=str(p.get("dtype", "int16")),
                scale=float(p.get("scale", 1.0)),
                unit=str(p.get("unit", "")),
                cmp=str(p.get("cmp", "") or ""),
                warn=p.get("warn") if p.get("warn") is not None else None,
                crit=p.get("crit") if p.get("crit") is not None else None,
                fail_n=int(p.get("fail_n", 3)),
            )
        )
    return table


def parse_test_read(text: str) -> Optional[TestReadResult]:
    body = strip_prompt(text)
    m = re.search(r"addr=(\d+) reg=(\d+):(.*)", body)
    if not m:
        return None
    result = TestReadResult(addr=int(m.group(1)), reg=int(m.group(2)))
    for sm in re.finditer(r"\[(\d+)\]=(\d+)(?:\s+\(([-\d.]+)\))?", m.group(3)):
        scaled = float(sm.group(3)) if sm.group(3) is not None else None
        result.samples.append(
            RegisterSample(reg=int(sm.group(1)), raw=int(sm.group(2)), scaled=scaled)
        )
    return result


def parse_vgmodbus_regs(text: str) -> Optional[TestReadResult]:
    body = strip_prompt(text)
    m = re.search(r"addr=(\d+) start=(\d+):(.*)", body)
    if not m:
        return None
    result = TestReadResult(addr=int(m.group(1)), reg=int(m.group(2)))
    for sm in re.finditer(r"\[(\d+)\]=(\d+)", m.group(3)):
        result.samples.append(
            RegisterSample(reg=int(sm.group(1)), raw=int(sm.group(2)))
        )
    return result


def parse_scan(text: str) -> list[int]:
    return [
        int(m.group(1))
        for m in re.finditer(r"^\s*addr=(\d+)\s*$", strip_prompt(text), re.MULTILINE)
    ]


def parse_cfg_dump(text: str) -> DeviceInfo:
    body = strip_prompt(text)
    info = DeviceInfo(raw=body)
    m = re.search(
        r"vgcfg:\s+(FACTORY|OK)\s+seq=(\d+)\s+schema=(\d+)\s+committed=(\d+)\s+name=(\S+)",
        body,
    )
    if m:
        info.source = m.group(1)
        info.seq = int(m.group(2))
        info.schema = int(m.group(3))
        info.committed = int(m.group(4))
        info.name = m.group(5)
    return info


def parse_stats_dump(text: str) -> list[FrameStats]:
    body = strip_prompt(text)
    out: list[FrameStats] = []
    for m in re.finditer(
        r"vgstats:\s+slave=(\d+)\s+window=(\d+)\s+total=(\d+)\s+ok=(\d+)\s+"
        r"crc=(\d+)\s+timeout=(\d+)\s+echo=(\d+)\s+other=(\d+)\s+"
        r"lat_min=(\d+)\s+lat_max=(\d+)\s+lat_avg=(\d+)",
        body,
    ):
        out.append(
            FrameStats(
                slave=int(m.group(1)),
                window=int(m.group(2)),
                total=int(m.group(3)),
                ok=int(m.group(4)),
                crc=int(m.group(5)),
                timeout=int(m.group(6)),
                echo=int(m.group(7)),
                other=int(m.group(8)),
                lat_min_ms=int(m.group(9)),
                lat_max_ms=int(m.group(10)),
                lat_avg_ms=int(m.group(11)),
            )
        )
    return out


def command_ack_ok(command: str, text: str) -> bool:
    body = strip_prompt(text)
    if command.startswith("vgpoint"):
        st = parse_vgpoint_status(text)
        return bool(st and st.ok)
    low = body.lower()
    if "error" in low or "failed" in low or "usage:" in low:
        return False
    if command.startswith("vgcfg dump"):
        return "vgcfg:" in low and ("OK" in body or "FACTORY" in body)
    if command.startswith("cat "):
        return "{" in body and "}" in body
    return bool(body.strip())
