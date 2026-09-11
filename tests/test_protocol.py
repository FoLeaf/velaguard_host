"""Unit tests for vgpoint NSH protocol (board doc: velaguard-host-nsh-protocol.md)."""

from __future__ import annotations

import pytest

from velaguard_host import protocol


def test_cmd_point_add_basic():
    cmd = protocol.cmd_point_add(tag="temp", addr=1, reg=0, scale=0.1, unit="C", cmp="ge", warn=40, crit=55)
    assert cmd.startswith("vgpoint add -t temp -a 1 -r 0")
    assert "-s 0.1" in cmd
    assert "-k ge" in cmd
    assert "-w 40" in cmd
    assert "-C 55" in cmd
    assert len(cmd.encode()) <= protocol.MAX_CMD_BYTES


def test_cmd_point_add_tag_and_length():
    with pytest.raises(protocol.ProtocolError):
        protocol.cmd_point_add(tag="bad tag", addr=1, reg=0)
    long_tag = "a" * 24
    with pytest.raises(protocol.ProtocolError):
        protocol.cmd_point_add(tag=long_tag, addr=1, reg=0)
    # flood eq crit
    cmd = protocol.cmd_point_add(tag="flood", addr=2, reg=2, dtype="uint16", cmp="eq", crit=1)
    assert "-k eq" in cmd and "-C 1" in cmd


def test_cmd_point_apply_requires_confirm_flag():
    assert protocol.cmd_point_apply(False) == "vgpoint apply"
    assert protocol.cmd_point_apply(True) == protocol.SAFE_APPLY_CMD
    assert protocol.cmd_point_apply(True) == "vgpoint apply --confirm"


def test_parse_ok_err_point_read():
    text = (
        "vgpoint: POINT tag=temp addr=1 fc=3 reg=0 qty=1 dtype=int16 scale=0.1 "
        "unit=C cmp=ge warn=40 crit=55 fail_n=3\n"
        "vgpoint: READ tag=temp raw=401 value=40.1 ok=1\n"
        "vgpoint: READ tag=flood raw=- value=- ok=0\n"
        "vgpoint: OK cmd=test table=candidate n=1\n"
        "nsh> "
    )
    st = protocol.parse_vgpoint_status(text)
    assert st and st.ok and st.cmd == "test" and st.n == 1
    points = protocol.parse_vgpoint_points(text)
    assert points[0].tag == "temp"
    assert points[0].warn == 40
    assert points[0].crit == 55
    reads = protocol.parse_vgpoint_reads(text)
    assert reads[0].ok and reads[0].value == pytest.approx(40.1)
    assert not reads[1].ok and reads[1].raw is None


def test_parse_err_need_confirm():
    text = "vgpoint: ERR cmd=apply code=need_confirm msg=use_--confirm\nnsh> "
    st = protocol.parse_vgpoint_status(text)
    assert st and not st.ok and st.code == "need_confirm"


def test_cmd_point_set_clear_threshold():
    cmd = protocol.cmd_point_set("temp", cmp="-", warn="-", crit="-")
    assert cmd == "vgpoint set temp -k - -w - -C -"


def test_cmd_point_list_and_abort():
    assert protocol.cmd_point_list() == "vgpoint list"
    assert protocol.cmd_point_list(True) == "vgpoint list -c"
    assert protocol.cmd_point_abort() == "vgpoint abort"
    assert protocol.cmd_point_del("temp") == "vgpoint del temp"
    assert protocol.cmd_point_test() == "vgpoint test"
    assert protocol.cmd_point_test("temp") == "vgpoint test temp"


def test_command_ack_ok_vgpoint():
    assert protocol.command_ack_ok(
        "vgpoint apply --confirm",
        "vgpoint: OK cmd=apply table=committed n=2\nnsh> ",
    )
    assert not protocol.command_ack_ok(
        "vgpoint apply",
        "vgpoint: ERR cmd=apply code=need_confirm msg=missing\n",
    )


def test_has_prompt_strips_nuttx_ansi():
    raw = "vgpoint: OK cmd=list table=committed n=5\nnsh> \x1b[K"
    assert not protocol.PROMPT_RE.search(raw)
    assert protocol.has_prompt(raw)
    body = protocol.strip_prompt(raw)
    assert "nsh>" not in body
    assert "\x1b" not in body
    st = protocol.parse_vgpoint_status(raw)
    assert st and st.ok and st.n == 5


def test_parse_point_table_json_object_and_array():
    obj = """{"schema_version":1,"bus":{"device":"/dev/rs485","baud":9600},"points":[
      {"tag":"temp","addr":1,"fc":3,"reg":0,"qty":1,"dtype":"int16","scale":0.1,"unit":"C","cmp":"ge","warn":40,"crit":55,"fail_n":3},
      {"tag":"flood","addr":2,"fc":3,"reg":2,"qty":1,"dtype":"uint16","scale":1,"unit":"-","cmp":"eq","warn":"-","crit":1}
    ]}"""
    table = protocol.parse_point_table_json(obj)
    assert table is not None and len(table.points) == 2
    assert table.points[0].tag == "temp"
    assert table.points[0].warn == 40
    assert table.points[1].unit == ""
    assert table.points[1].warn is None
    assert table.points[1].crit == 1

    arr = '[{"tag":"temp","addr":1,"reg":0}]'
    table2 = protocol.parse_point_table_json(arr)
    assert table2 is not None and table2.points[0].fc == 3
    assert table2.points[0].dtype == "int16"

    cmd = protocol.cmd_point_add_from_point(table.points[0])
    assert cmd.startswith("vgpoint add -t temp -a 1 -r 0")
    set_cmd = protocol.cmd_point_set_from_point(table.points[1])
    assert set_cmd.startswith("vgpoint set flood")


def test_prepare_import_rows_rejects_dup_and_cap():
    p = protocol.Point(tag="temp", addr=1, reg=0)
    rows = protocol.prepare_import_rows([p, p])
    assert rows[0].ok and not rows[1].ok
    assert "重复" in rows[1].error

    too_many = [protocol.Point(tag=f"t{i}", addr=1, reg=i) for i in range(protocol.MAX_POINTS + 1)]
    rows = protocol.prepare_import_rows(too_many)
    assert rows[-1].error.startswith("超过")
    assert all(r.ok for r in rows[:-1])

    bad = protocol.prepare_import_rows([protocol.Point(tag="bad tag", addr=1, reg=0)])
    assert not bad[0].ok


def test_example_demo_json_prepares():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "examples" / "vgpoint_demo_points.json"
    table = protocol.parse_point_table_json(path.read_text(encoding="utf-8"), path=str(path))
    assert table is not None
    rows = protocol.prepare_import_rows(table.points)
    assert len(rows) == 2 and all(r.ok for r in rows)
    assert rows[0].add_cmd.startswith("vgpoint add -t temp")
