"""VelaGuard NSH command builders and response parsers.

All device I/O is text over ST-LINK VCP. This module has no Qt/serial deps.
Command names and output patterns mirror board sources under
contest2026_004_TeamFalcons/app/velaguard/ (vgdiscover.c, vgcfg.c, vgstats.c,
modbus_collector.c).
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
    ProbeBlock,
    ProbeHit,
    RegisterSample,
    TestReadResult,
)

PROMPT_RE = re.compile(r"(?:nsh>|vela>)\s*$", re.MULTILINE)
SAFE_APPLY_CMD = "vgdiscover apply --confirm"
CANDIDATE_PATH = "/data/velaguard/discover/point_table_candidate.json"
POINTS_PATH = "/data/velaguard/config/points.json"


def cmd_help() -> str:
    return "?"


def cmd_scan(addr_min: int = 1, addr_max: int = 32) -> str:
    if addr_min < 1 or addr_max > 247 or addr_min > addr_max:
        raise ValueError(f"invalid address range {addr_min}-{addr_max}")
    return f"vgdiscover scan -a {addr_min}-{addr_max}"


def cmd_probe(addr: int, fc_mode: str = "both") -> str:
    if addr < 1 or addr > 247:
        raise ValueError(f"invalid slave addr {addr}")
    if fc_mode not in ("3", "4", "both"):
        raise ValueError(f"invalid fc_mode {fc_mode}")
    return f"vgdiscover probe -a {addr} -t {fc_mode}"


def cmd_dump(path: Optional[str] = None) -> str:
    if path:
        return f"vgdiscover dump -o {path}"
    return "vgdiscover dump"


def cmd_test_read(addr: int, reg: int, qty: int = 2) -> str:
    if addr < 1 or addr > 247:
        raise ValueError(f"invalid slave addr {addr}")
    if qty < 1 or qty > 16:
        raise ValueError(f"invalid qty {qty} (1-16)")
    return f"vgdiscover test-read -a {addr} -r {reg} -c {qty}"


def cmd_apply(confirm: bool = False) -> str:
    return SAFE_APPLY_CMD if confirm else "vgdiscover apply"


def cmd_cfg_dump() -> str:
    return "vgcfg dump"


def cmd_cfg_probe() -> str:
    return "vgcfg probe"


def cmd_stats_dump(slave: Optional[int] = None) -> str:
    if slave is None:
        return "vgstats dump"
    return f"vgstats dump {slave}"


def cmd_vgmodbus(addr: int, reg: int, qty: int = 1, loops: int = 1) -> str:
    if addr < 1 or addr > 247:
        raise ValueError(f"invalid slave addr {addr}")
    if qty < 1:
        raise ValueError(f"invalid qty {qty}")
    return f"vgmodbus -a {addr} -r {reg} -c {qty} -n {loops} -i 0"


def cmd_cat_points(path: str = POINTS_PATH) -> str:
    return f"cat {path}"


def strip_prompt(text: str) -> str:
    return PROMPT_RE.sub("", text)


def extract_json_object(text: str) -> Optional[dict]:
    """Find the first balanced JSON object in a mixed NSH transcript."""
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
                blob = text[start : i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    return None
    return None


def parse_scan(text: str) -> list[ProbeHit]:
    hits: list[ProbeHit] = []
    for m in re.finditer(r"^\s*addr=(\d+)\s*$", strip_prompt(text), re.MULTILINE):
        hits.append(ProbeHit(addr=int(m.group(1))))
    return hits


def parse_probe(text: str) -> tuple[Optional[int], list[ProbeBlock]]:
    body = strip_prompt(text)
    m = re.search(r"probe addr=(\d+) blocks=(\d+)", body)
    blocks: list[ProbeBlock] = []
    for bm in re.finditer(
        r"fc=(\d+)\s+start=(\d+)\s+count=(\d+)\s+sample\[0\]=(\d+)\s+sample\[1\]=(\d+)",
        body,
    ):
        blocks.append(
            ProbeBlock(
                fc=int(bm.group(1)),
                start=int(bm.group(2)),
                count=int(bm.group(3)),
                sample0=int(bm.group(4)),
                sample1=int(bm.group(5)),
            )
        )
    addr = int(m.group(1)) if m else None
    return addr, blocks


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


def parse_apply(text: str) -> dict:
    body = strip_prompt(text)
    if "dry-run apply" in body:
        return {"applied": False, "dry_run": True, "count": _first_int(body, r"dry-run apply\s*→\s*(\d+)")}
    if "applied" in body and "points" in body:
        return {
            "applied": True,
            "dry_run": False,
            "count": _first_int(body, r"applied\s+(\d+)\s+points"),
        }
    return {"applied": False, "dry_run": False, "count": 0, "error": body.strip()[:200]}


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
            )
        )
    return table


def _first_int(text: str, pattern: str) -> int:
    m = re.search(pattern, text)
    return int(m.group(1)) if m else 0


def command_ack_ok(command: str, text: str) -> bool:
    """Heuristic success check for board CLI lines."""
    body = strip_prompt(text)
    low = body.lower()
    if "error" in low or "failed" in low or "usage:" in low:
        return False
    if command.startswith("vgdiscover apply"):
        return "applied" in low or "dry-run" in low
    if command.startswith("vgdiscover scan"):
        return "found" in low or "addr=" in low
    if command.startswith("vgdiscover probe"):
        return "probe addr=" in low
    if command.startswith("vgdiscover test-read"):
        return "addr=" in low and "[" in body
    if command.startswith("vgcfg dump"):
        return "vgcfg:" in low and ("OK" in body or "FACTORY" in body)
    if command.startswith("cat "):
        return "{" in body and "}" in body
    return bool(body.strip())
