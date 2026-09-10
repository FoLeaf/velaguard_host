"""VelaGuard Host point models (no Qt)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ProbeHit:
    addr: int


@dataclass(frozen=True)
class ProbeBlock:
    fc: int
    start: int
    count: int
    sample0: int
    sample1: int


@dataclass
class Point:
    tag: str
    addr: int
    fc: int = 3
    reg: int = 0
    qty: int = 1
    dtype: str = "int16"
    scale: float = 1.0
    unit: str = ""
    cmp: str = ""  # ge | le | eq | empty
    warn: Optional[float] = None
    crit: Optional[float] = None
    fail_n: int = 3

    def scaled(self, raw: int) -> float:
        return float(raw) * float(self.scale)


@dataclass
class PointTable:
    schema_version: int = 1
    device: str = "/dev/rs485"
    baud: int = 9600
    hits: list[int] = field(default_factory=list)
    points: list[Point] = field(default_factory=list)
    path: str = ""


@dataclass
class RegisterSample:
    reg: int
    raw: int
    scaled: Optional[float] = None


@dataclass
class TestReadResult:
    addr: int
    reg: int
    samples: list[RegisterSample] = field(default_factory=list)


@dataclass
class VgPointStatus:
    """One stable vgpoint OK/ERR line."""

    ok: bool
    cmd: str = ""
    table: str = ""  # candidate | committed
    n: int = 0
    code: str = ""
    msg: str = ""
    raw: str = ""


@dataclass
class VgPointRead:
    tag: str
    raw: Optional[int]
    value: Optional[float]
    ok: bool


@dataclass
class FrameStats:
    slave: int
    window: int = 0
    total: int = 0
    ok: int = 0
    crc: int = 0
    timeout: int = 0
    echo: int = 0
    other: int = 0
    lat_min_ms: int = 0
    lat_max_ms: int = 0
    lat_avg_ms: int = 0

    @property
    def error_rate(self) -> float:
        if self.total <= 0:
            return 0.0
        return (self.crc + self.timeout + self.echo + self.other) / self.total


@dataclass
class DeviceInfo:
    source: str = ""
    seq: int = 0
    schema: int = 0
    committed: int = 0
    name: str = ""
    raw: str = ""
