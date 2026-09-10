"""Unit tests for VelaGuard NSH protocol helpers (no hardware, no Qt)."""

from __future__ import annotations

import pytest

from velaguard_host import protocol


def test_cmd_scan_range_validation():
    assert protocol.cmd_scan(1, 32) == "vgdiscover scan -a 1-32"
    with pytest.raises(ValueError):
        protocol.cmd_scan(10, 5)


def test_cmd_apply_separates_confirm():
    assert protocol.cmd_apply(False) == "vgdiscover apply"
    assert protocol.cmd_apply(True) == protocol.SAFE_APPLY_CMD
    assert "confirm" not in protocol.cmd_apply(False)


def test_parse_scan():
    text = (
        "vgdiscover: scan /dev/rs485 @9600 addr 1..8\r\n"
        "vgdiscover: found 2 slave(s):\n"
        "  addr=1\n"
        "  addr=5\n"
        "nsh> "
    )
    hits = protocol.parse_scan(text)
    assert [h.addr for h in hits] == [1, 5]


def test_parse_test_read():
    text = "vgdiscover: addr=1 reg=0: [0]=255 (25.5) [1]=10 (1.0)\nnsh> "
    r = protocol.parse_test_read(text)
    assert r is not None
    assert r.addr == 1
    assert r.reg == 0
    assert len(r.samples) == 2
    assert r.samples[0].raw == 255
    assert r.samples[0].scaled == pytest.approx(25.5)


def test_parse_apply_dry_and_confirm():
    dry = "vgdiscover: dry-run apply → 3 points to /data/velaguard/config/points.json (use --confirm)\nnsh> "
    ok = "vgdiscover: applied 3 points → /data/velaguard/config/points.json\nnsh> "
    assert protocol.parse_apply(dry)["dry_run"] is True
    assert protocol.parse_apply(ok)["applied"] is True
    assert protocol.parse_apply(ok)["count"] == 3


def test_parse_cfg_dump():
    text = "vgcfg: OK seq=12 schema=1 committed=1 name=discovered\nnsh> "
    info = protocol.parse_cfg_dump(text)
    assert info.source == "OK"
    assert info.seq == 12
    assert info.name == "discovered"


def test_parse_stats():
    text = (
        "vgstats: slave=1 window=32 total=100 ok=98 crc=1 timeout=1 "
        "echo=0 other=0 lat_min=2 lat_max=40 lat_avg=8\nnsh> "
    )
    stats = protocol.parse_stats_dump(text)
    assert len(stats) == 1
    assert stats[0].crc == 1
    assert stats[0].error_rate == pytest.approx(0.02)


def test_parse_point_table_json_with_noise():
    text = (
        "cat /data/velaguard/config/points.json\n"
        '{"schema_version":1,"bus":{"device":"/dev/rs485","baud":9600},'
        '"hits":[1,2],"points":[{"tag":"T1","addr":1,"fc":3,"reg":0,'
        '"qty":1,"dtype":"int16","scale":0.100,"unit":"C"}]}\n'
        "nsh> "
    )
    table = protocol.parse_point_table_json(text)
    assert table is not None
    assert table.baud == 9600
    assert table.hits == [1, 2]
    assert table.points[0].tag == "T1"
    assert table.points[0].scaled(255) == pytest.approx(25.5)


def test_parse_probe():
    text = (
        "vgdiscover: probe addr=1 blocks=2\n"
        "  fc=3 start=0 count=8 sample[0]=255 sample[1]=10\n"
        "  fc=4 start=0 count=4 sample[0]=1 sample[1]=2\n"
        "nsh> "
    )
    addr, blocks = protocol.parse_probe(text)
    assert addr == 1
    assert len(blocks) == 2
    assert blocks[0].fc == 3


def test_command_ack_ok():
    assert protocol.command_ack_ok(
        "vgdiscover apply --confirm", "applied 2 points → x\nnsh> "
    )
    assert not protocol.command_ack_ok(
        "vgdiscover apply --confirm", "vgdiscover: no saved state — run dump first\n"
    )
    assert protocol.command_ack_ok("vgcfg dump", "vgcfg: OK seq=1 name=x\n")


def test_cmd_vgmodbus():
    assert protocol.cmd_vgmodbus(1, 0, 4, 1) == "vgmodbus -a 1 -r 0 -c 4 -n 1 -i 0"
