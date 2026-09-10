"""Data models for VelaGuard host (no Qt dependency)."""

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


@dataclass(frozen=True)
class Point:
    tag: str
    addr: int
    fc: int
    reg: int
    qty: int
    dtype: str
    scale: float
    unit: str = ""

    def scaled(self, raw: int) -> float:
        if self.dtype in ("int16", "uint16", "int", "uint"):
            return raw * self.scale
        return float(raw)


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
    source: str = ""  # OK | FACTORY | unknown
    seq: int = 0
    schema: int = 0
    committed: int = 0
    name: str = ""
    raw: str = ""
