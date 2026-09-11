"""VelaGuard Host — Designer 外壳 + 现代化中间页 + vgpoint NSH。

权威协议：
  contest2026_004_TeamFalcons/docs/velaguard-host-nsh-protocol.md
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QMessageBox,
    QSizePolicy,
    QSpacerItem,
    QSplitter,
    QWidget,
)

from window import Ui_Form  # noqa: F401  — 保留侧栏/顶栏/日志壳与 PNG

from theme import apply_theme
from velaguard_host import protocol
from velaguard_host.models import Point
from velaguard_host.worker import SerialController
from widgets import AddPointDialog, AddPointResult, ConsolePage, ImportPointsDialog, PointsPage, SessionPage
from widgets.import_points_dialog import load_import_rows, show_point_table_spec


@dataclass
class source_set:
    name: str
    tag: str
    slave_addr: int
    function_code: int
    start_addr: int
    data_len: int
    data_type: str
    formula: str
    unit: str
    candidate: bool = True
    pending_delete: bool = False
    was_committed: bool = False
    last_value: Optional[str] = None
    last_ok: Optional[bool] = None
    card_widget: Any = None
    cmp: str = ""
    warn: Optional[float] = None
    crit: Optional[float] = None
    extra: dict = field(default_factory=dict)


@dataclass
class _ImportJob:
    point: Point
    cmd: str
    kind: str = "add"
    retried_set: bool = False
    set_name_cmd: str = ""


@dataclass
class _DelJob:
    tag: str
    cmd: str
    kind: str = "del"  # list_c | abort | add | del


class mainUI(QWidget, Ui_Form):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.all_sources: list[source_set] = []
        self.ctl = SerialController(self)
        self.ctl.log.connect(self.update_textbrowser)
        self.ctl.connected.connect(self._on_nsh_connected)
        self.ctl.disconnected.connect(self._on_nsh_disconnected)
        self.ctl.command_done.connect(self._on_nsh_done)
        self.ctl.command_failed.connect(self._on_nsh_failed)
        self._pending_cmd = ""
        self._pending_kind = ""
        self._inflight = 0
        self._connecting = False
        self._drag_offset: Optional[QPoint] = None
        self._connected_port = ""
        self._import_queue: list = []
        self._import_index = 0
        self._import_ok = 0
        self._import_fail = 0
        self._importing = False
        self._import_current = None
        self._del_queue: list[_DelJob] = []
        self._del_index = 0
        self._del_ok = 0
        self._del_fail = 0
        self._deleting = False
        self._del_current: Optional[_DelJob] = None
        self._del_targets: list[str] = []
        self._edit_queue: list[_DelJob] = []
        self._edit_index = 0
        self._editing = False
        self._edit_current: Optional[_DelJob] = None
        self._edit_spec: Optional[AddPointResult] = None
        self._edit_set_cmds: list[str] = []
        self._pending_add_name_cmd = ""
        self.mainUI_custom()

    def mainUI_custom(self):
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("VelaGuard Host")

        self._strip_inline_styles()
        self._polish_shell()
        self._install_splitter()
        self._install_pages()
        self._wire_nav()

        self.pushButton_serial.setProperty("kind", "primary")
        self.pushButton_serial.style().unpolish(self.pushButton_serial)
        self.pushButton_serial.style().polish(self.pushButton_serial)
        self.pushButton_serial.clicked.connect(self.serial_toggle)

        self.label_2.setText("VelaGuard")
        self.label_3.setText("Host · vgpoint")
        self.label_4.hide()

        self.textBrowser.setLineWrapMode(self.textBrowser.NoWrap)
        self.textBrowser.setFont(QFont("JetBrains Mono", 10))
        self.textBrowser.clear()
        self.serial_port_list_init()

        self.update_textbrowser("[host] 协议: vgpoint NSH（板端 docs/velaguard-host-nsh-protocol.md）")
        self.update_textbrowser("[host] 流程: 新增/导入/删除点位 → 试读候选 → 人确认 → 确认落盘")
        self._set_online_chips(False)
        self._refresh_session()

    def _strip_inline_styles(self) -> None:
        for w in self.findChildren(QWidget):
            w.setStyleSheet("")

    def _polish_shell(self) -> None:
        self.verticalLayout_9.setContentsMargins(8, 8, 8, 8)
        self.verticalLayout_2.setContentsMargins(14, 22, 14, 16)
        self.verticalLayout_2.setSpacing(6)
        self.label_2.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.label_3.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.label_2.setMinimumHeight(28)
        self.label_3.setMinimumHeight(18)
        for btn in (
            self.pushButton_console,
            self.pushButton_realtimedata,
            self.pushButton_configuration,
        ):
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(40)
        self.comboBox_serial.setFixedHeight(34)
        self.comboBox_serial.setMaximumWidth(150)
        self.pushButton_serial.setFixedHeight(34)
        self.pushButton_serial.setFixedWidth(108)
        self.horizontalLayout_7.setSpacing(8)
        self.horizontalLayout_7.addStretch(1)

        first_expanding = True
        for i in range(self.verticalLayout_2.count() - 1, -1, -1):
            item = self.verticalLayout_2.itemAt(i)
            sp = item.spacerItem() if item else None
            if not sp:
                continue
            if sp.sizeHint().height() >= 200:
                self.verticalLayout_2.removeItem(item)
                self.verticalLayout_2.addItem(
                    QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)
                )
            elif first_expanding and (sp.expandingDirections() & Qt.Vertical):
                first_expanding = False
                self.verticalLayout_2.removeItem(item)
                self.verticalLayout_2.insertSpacerItem(
                    i, QSpacerItem(20, 16, QSizePolicy.Minimum, QSizePolicy.Fixed)
                )
        self.horizontalLayout_2.setContentsMargins(16, 8, 12, 8)
        self.horizontalLayout_2.setSpacing(12)
        self.frame_8.setMinimumHeight(80)
        self.frame_2.setMinimumWidth(168)

    def _install_splitter(self) -> None:
        layout = self.verticalLayout_3
        layout.removeWidget(self.frame)
        layout.removeWidget(self.frame_8)
        splitter = QSplitter(Qt.Vertical)
        splitter.setObjectName("logSplitter")
        splitter.addWidget(self.frame)
        splitter.addWidget(self.frame_8)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 160])
        splitter.setChildrenCollapsible(False)
        layout.addWidget(splitter)
        self._log_splitter = splitter

    def _install_pages(self) -> None:
        while self.stackedWidget.count():
            w = self.stackedWidget.widget(0)
            self.stackedWidget.removeWidget(w)
            w.deleteLater()

        self.page_console = ConsolePage()
        self.page_points = PointsPage()
        self.page_session = SessionPage()
        self.stackedWidget.addWidget(self.page_console)
        self.stackedWidget.addWidget(self.page_points)
        self.stackedWidget.addWidget(self.page_session)

        self.page_points.add_requested.connect(self.open_add_source_dialog)
        self.page_points.test_requested.connect(self.run_point_test)
        self.page_points.apply_requested.connect(self.confirm_apply)
        self.page_points.abort_requested.connect(self.abort_candidate)
        self.page_points.delete_requested.connect(self.delete_point)
        self.page_points.batch_delete_requested.connect(self.delete_points)
        self.page_points.edit_requested.connect(self.open_edit_dialog)
        self.page_points.import_requested.connect(self.open_import_dialog)
        self.page_points.format_spec_requested.connect(
            lambda: show_point_table_spec(self)
        )
        self.page_session.delete_requested.connect(self.delete_points)
        self.page_session.edit_requested.connect(self.open_edit_dialog)
        self.page_console.command_submitted.connect(self._on_console_command)

    def _wire_nav(self) -> None:
        for btn in (
            self.pushButton_console,
            self.pushButton_realtimedata,
            self.pushButton_configuration,
        ):
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.pushButton_console, 0)
        group.addButton(self.pushButton_realtimedata, 1)
        group.addButton(self.pushButton_configuration, 2)
        self._nav_group = group

        self.pushButton_console.clicked.connect(lambda: self._goto_page(0))
        self.pushButton_realtimedata.clicked.connect(lambda: self._goto_page(1))
        self.pushButton_configuration.clicked.connect(lambda: self._goto_page(2))
        self._goto_page(1)

    def _goto_page(self, index: int) -> None:
        self.stackedWidget.setCurrentIndex(index)
        mapping = {
            0: self.pushButton_console,
            1: self.pushButton_realtimedata,
            2: self.pushButton_configuration,
        }
        btn = mapping[index]
        if not btn.isChecked():
            btn.setChecked(True)

    def _set_online_chips(self, online: bool):
        from theme.palette import CRIT, OK

        color = OK if online else CRIT
        self.label.setStyleSheet(
            f"color:#FFFFFF; font-size:12px; font-weight:600;"
            f"border-radius:8px; background:{color}; padding:4px 12px;"
        )
        self.label.setText("NSH 已连接" if online else "NSH 未连接")
        self.page_points.set_online(online)
        self.page_console.set_online(online)
        port = self._connected_port or self.comboBox_serial.currentText().strip()
        self.page_session.set_port(port, online)

    def _set_busy(self, busy: bool, command: str = "") -> None:
        # NSH 单通道由工作线程排队；工具条只提示「执行中」，不再禁用四个流程按钮。
        self.page_points.set_busy(busy, command)
        self.pushButton_serial.setEnabled(not self._connecting)
        if self.pushButton_serial.text() == "打开串口":
            self.comboBox_serial.setEnabled(not self._connecting)

    # ---- 串口 ----
    def serial_toggle(self):
        if self.pushButton_serial.text() == "打开串口":
            port = self.comboBox_serial.currentText().strip()
            if not port:
                self.update_textbrowser("错误：请选择串口")
                return
            self._connecting = True
            self._set_busy(True)
            self.ctl.open(port, 115200)
            self.pushButton_serial.setText("关闭串口")
            self.comboBox_serial.setEnabled(False)
        else:
            self._connecting = False
            self._inflight = 0
            self._set_busy(False)
            self.ctl.close()
            self.pushButton_serial.setText("打开串口")
            self.comboBox_serial.setEnabled(True)
            self._connected_port = ""
            self._set_online_chips(False)

    def serial_port_list_init(self):
        self.comboBox_serial.clear()
        from velaguard_host.nsh_session import NshSession

        for port in NshSession.list_ports():
            self.comboBox_serial.addItem(port)
        for i in range(self.comboBox_serial.count()):
            if self.comboBox_serial.itemText(i).upper().startswith("COM3"):
                self.comboBox_serial.setCurrentIndex(i)
                break

    def _require_online(self) -> bool:
        if self.pushButton_serial.text() != "关闭串口":
            self.update_textbrowser("请先打开串口")
            return False
        return True

    def send_nsh(self, command: str, kind: str = "raw", timeout_s: float = 20.0) -> None:
        self._pending_cmd = command
        self._pending_kind = kind
        self._inflight += 1
        self._set_busy(True, command)
        self.update_textbrowser(f"$ {command}")
        self.ctl.send(command, timeout_s=timeout_s)

    def _finish_inflight(self) -> None:
        self._inflight = max(0, self._inflight - 1)
        self._pending_cmd = ""
        self._pending_kind = ""
        if self._inflight == 0 and not self._connecting:
            self._set_busy(False)
        elif self._inflight:
            self._set_busy(True, "排队中")

    def _on_nsh_connected(self, port: str):
        self._connecting = False
        self._connected_port = port
        self.update_textbrowser(f"已连接 {port} @ 115200（NSH）")
        self._set_online_chips(True)
        self.send_nsh(protocol.cmd_point_list(False), kind="list", timeout_s=5)

    def _on_nsh_disconnected(self):
        self.update_textbrowser("串口已断开")
        self._connecting = False
        self._inflight = 0
        self._connected_port = ""
        self._abort_import("串口已断开")
        self._abort_delete("串口已断开")
        self._abort_edit("串口已断开")
        self._pending_add_name_cmd = ""
        self._set_busy(False)
        self._set_online_chips(False)

    def _on_nsh_done(self, command: str, response: str) -> None:
        self.update_textbrowser(response)
        try:
            self._dispatch(command, response)
        except Exception as exc:
            self.update_textbrowser(f"[parse] {exc}")
        try:
            self._on_import_reply(command, response)
        except Exception as exc:
            self.update_textbrowser(f"[import] {exc}")
        try:
            self._on_del_reply(command, response)
        except Exception as exc:
            self.update_textbrowser(f"[del] {exc}")
        try:
            self._on_edit_reply(command, response)
        except Exception as exc:
            self.update_textbrowser(f"[edit] {exc}")
        self._finish_inflight()

    def _on_nsh_failed(self, command: str, error: str) -> None:
        self.update_textbrowser(f"! {command}: {error}")
        if command == "<connect>":
            self.pushButton_serial.setText("打开串口")
            self.comboBox_serial.setEnabled(True)
            self._connecting = False
            self._inflight = 0
            self._connected_port = ""
            self._abort_import("连接失败")
            self._abort_delete("连接失败")
            self._abort_edit("连接失败")
            self._set_online_chips(False)
            self._set_busy(False)
        else:
            try:
                self._on_import_transport_fail(command, error)
            except Exception as exc:
                self.update_textbrowser(f"[import] {exc}")
            try:
                self._on_del_transport_fail(command, error)
            except Exception as exc:
                self.update_textbrowser(f"[del] {exc}")
            try:
                self._on_edit_transport_fail(command, error)
            except Exception as exc:
                self.update_textbrowser(f"[edit] {exc}")
            self._finish_inflight()

    def _dispatch(self, command: str, response: str) -> None:
        if not command.startswith("vgpoint"):
            return
        st = protocol.parse_vgpoint_status(response)
        points = protocol.parse_vgpoint_points(response)
        reads = protocol.parse_vgpoint_reads(response)
        if command.startswith("vgpoint list"):
            is_cand = command.rstrip().endswith("-c")
            if is_cand:
                if points:
                    self._sync_cards_from_points(points, candidate=True)
            elif (st is not None and st.ok) or points:
                self._replace_committed_points(points)
        if reads:
            self._apply_reads(reads)
        if st:
            kind = "OK" if st.ok else f"ERR {st.code}"
            self.update_textbrowser(f"[parse] vgpoint {kind} cmd={st.cmd} n={st.n}")
            if st.ok and st.cmd == "add":
                follow = self._pending_add_name_cmd
                self._pending_add_name_cmd = ""
                if follow:
                    self.send_nsh(follow, kind="set", timeout_s=15)
            if st.ok and st.cmd == "apply":
                if st.n == 0:
                    self.update_textbrowser("[host] 已确认表已清空（n=0）")
                    self._clear_points()
                else:
                    self.update_textbrowser("[host] 已确认表已更新；正在 list 核对")
                    self.all_sources = [s for s in self.all_sources if not s.pending_delete]
                    for src in self.all_sources:
                        src.candidate = False
                        src.was_committed = True
                        src.pending_delete = False
                    self.page_points.mark_all_committed()
                    self._refresh_session()
                self.send_nsh(protocol.cmd_point_list(False), kind="list", timeout_s=5)
            if st.ok and st.cmd == "del":
                parts = command.split()
                tag = parts[2] if len(parts) >= 3 else ""
                if tag:
                    self._mark_deleted(tag)
                self.update_textbrowser("[host] 已从候选删除；确认落盘后才会从已确认表去掉")
            if st.ok and st.cmd == "abort":
                for src in self.all_sources:
                    src.pending_delete = False
                    if src.was_committed:
                        src.candidate = False
                self.page_points.clear_pending_deletes()
                self._refresh_session()
                if not self._deleting and not self._editing:
                    self.send_nsh(protocol.cmd_point_list(False), kind="list", timeout_s=5)
            if not st.ok and st.cmd == "add":
                self._pending_add_name_cmd = ""
            if not st.ok and st.cmd == "del":
                self.update_textbrowser(f"[host] 删除失败 code={st.code}")
            if not st.ok and st.code == "need_confirm":
                self.update_textbrowser("[host] apply 必须带 --confirm，已用确认对话框流程")
            if not st.ok and st.cmd == "apply" and st.code == "no_candidate":
                self.update_textbrowser(
                    "[host] 落盘失败：候选文件不存在，或当前固件仍拒绝空候选。"
                    "删光全部点后 apply 需要板端允许空候选文件写成空表；请重新编译烧录 vgpoint。"
                )

    def _on_console_command(self, command: str) -> None:
        if not self._require_online():
            return
        kind = "list" if command.startswith("vgpoint list") else "raw"
        timeout = 15.0 if kind == "list" else 20.0
        self.send_nsh(command, kind=kind, timeout_s=timeout)

    # ---- 点位操作 ----
    def open_add_source_dialog(self):
        if not self._require_online():
            return
        dialog = AddPointDialog(self)
        if dialog.exec_() != dialog.Accepted:
            self.update_textbrowser("取消新增点位。")
            return
        try:
            spec = dialog.result_values()
            cmd = protocol.cmd_point_add(
                point_id=spec.id,
                addr=spec.addr,
                reg=spec.reg,
                name=spec.name,
                fc=spec.fc,
                qty=spec.qty,
                dtype=spec.dtype,
                scale=spec.scale,
                unit=spec.unit,
                cmp=spec.cmp,
                warn=spec.warn,
                crit=spec.crit,
            )
            name_cmd = ""
            if spec.name and spec.name != spec.id and not protocol.add_includes_name(cmd):
                name_cmd = protocol.cmd_point_set(spec.id, name=spec.name)
        except (ValueError, protocol.ProtocolError) as exc:
            QMessageBox.warning(self, "参数无效", str(exc))
            return

        src = self._upsert_source(
            source_set(
                name=spec.name,
                tag=spec.id,
                slave_addr=spec.addr,
                function_code=spec.fc,
                start_addr=spec.reg,
                data_len=spec.qty,
                data_type=spec.dtype,
                formula=spec.formula,
                unit=spec.unit,
                candidate=True,
                was_committed=False,
                cmp=spec.cmp,
                warn=spec.warn,
                crit=spec.crit,
            )
        )
        src.card_widget = self.page_points.upsert(
            spec.id, unit=spec.unit, candidate=True, name=spec.name
        )
        self._refresh_session()
        self._pending_add_name_cmd = name_cmd
        self.send_nsh(cmd, kind="add", timeout_s=15)

    def open_edit_dialog(self, tag: str):
        tag = (tag or "").strip()
        if not tag:
            return
        if not self._require_online():
            return
        busy = self._queue_busy()
        if busy:
            self.update_textbrowser(f"[edit] {busy}进行中，请稍后再编辑")
            return
        src = next((s for s in self.all_sources if s.tag == tag), None)
        if src is None:
            QMessageBox.information(self, "编辑点位", f"找不到点 {tag}")
            return
        if src.pending_delete:
            QMessageBox.information(
                self,
                "编辑点位",
                "该点已标记待删除。请先「放弃候选」撤销删除后再改。",
            )
            return
        dialog = AddPointDialog(self, existing=self._spec_from_source(src))
        if dialog.exec_() != dialog.Accepted:
            self.update_textbrowser(f"[edit] 已取消 {tag}")
            return
        try:
            spec = dialog.result_values()
            spec.id = src.tag
            point = self._point_from_spec(spec)
            set_cmds = protocol.cmd_point_set_cmds_from_point(point)
        except (ValueError, protocol.ProtocolError) as exc:
            QMessageBox.warning(self, "参数无效", str(exc))
            return
        self._edit_spec = spec
        self._edit_queue = [
            _DelJob(tag="", cmd=protocol.cmd_point_list(True), kind="list_c")
        ]
        self._edit_index = 0
        self._editing = True
        self._edit_current = None
        self._edit_set_cmds = set_cmds
        self.update_textbrowser(f"[edit] {spec.id} → 候选（不会自动落盘）")
        self._send_next_edit()

    def _spec_from_source(self, src: source_set) -> AddPointResult:
        return AddPointResult(
            id=src.tag,
            name=src.name or src.tag,
            addr=int(src.slave_addr),
            fc=int(src.function_code or 3),
            reg=int(src.start_addr),
            qty=int(src.data_len or 1),
            dtype=src.data_type or "int16",
            scale=self._point_from_source(src).scale,
            formula=src.formula or "1",
            unit=src.unit or "",
            cmp=src.cmp or "",
            warn=src.warn,
            crit=src.crit,
        )

    def _point_from_spec(self, spec: AddPointResult) -> Point:
        return Point(
            id=spec.id,
            name=spec.name,
            addr=spec.addr,
            fc=spec.fc,
            reg=spec.reg,
            qty=spec.qty,
            dtype=spec.dtype,
            scale=spec.scale,
            unit=spec.unit,
            cmp=spec.cmp,
            warn=spec.warn,
            crit=spec.crit,
        )

    def _send_next_edit(self) -> None:
        if not self._editing:
            return
        if self._edit_index >= len(self._edit_queue):
            self._finish_edit(ok=True)
            return
        job = self._edit_queue[self._edit_index]
        self._edit_current = job
        if job.kind == "list_c":
            note = "查看候选表"
        elif job.kind == "abort":
            note = "丢掉空候选，以便从已确认表复制"
        elif job.kind == "add":
            note = f"补进候选 {job.tag}"
        else:
            note = f"set {job.tag}"
        self.update_textbrowser(f"[edit] {note}")
        self.send_nsh(job.cmd, kind=job.kind, timeout_s=15)
        self.page_points.set_busy(True, note)

    def _on_edit_reply(self, command: str, response: str) -> None:
        if not self._editing or self._edit_current is None:
            return
        job = self._edit_current
        if command != job.cmd:
            return
        st = protocol.parse_vgpoint_status(response)
        if job.kind == "list_c":
            if not self._plan_edit_after_probe(response):
                self._abort_edit("无法规划编辑队列")
                return
        elif job.kind == "abort":
            if not (st and st.ok):
                code = st.code if st else "no_status"
                self._abort_edit(f"无法准备候选表 {code}")
                return
        elif job.kind == "add":
            if not (st and (st.ok or st.code == "dup_id")):
                code = st.code if st else "no_status"
                self._abort_edit(f"补候选失败 {job.tag} {code}")
                return
        elif job.kind == "set":
            if st and st.ok:
                self._apply_edit_local()
            else:
                code = st.code if st else "no_status"
                self.update_textbrowser(f"[edit] FAIL {job.tag} {code}")
                self._abort_edit(f"set 失败 {code}")
                return
        self._edit_index += 1
        self._send_next_edit()

    def _on_edit_transport_fail(self, command: str, error: str) -> None:
        if not self._editing or self._edit_current is None:
            return
        job = self._edit_current
        if command != job.cmd:
            return
        self._abort_edit(error)

    def _plan_edit_after_probe(self, response: str) -> bool:
        spec = self._edit_spec
        if spec is None:
            return False
        cand_ids = {p.id for p in protocol.parse_vgpoint_points(response)}
        st = protocol.parse_vgpoint_status(response)
        cand_n = st.n if st is not None else len(cand_ids)
        extra: list[_DelJob] = []
        set_jobs = [
            _DelJob(tag=spec.id, cmd=cmd, kind="set") for cmd in self._edit_set_cmds
        ]
        if spec.id in cand_ids:
            extra.extend(set_jobs)
        elif cand_n == 0:
            self.update_textbrowser(
                "[edit] 候选为空，先 abort 再从已确认表复制后 set"
            )
            extra.append(
                _DelJob(tag="", cmd=protocol.cmd_point_abort(), kind="abort")
            )
            extra.extend(set_jobs)
        else:
            self.update_textbrowser("[edit] 候选里没有该点，先 add 再 set")
            wanted = spec.id
            for src in self.all_sources:
                if src.tag in cand_ids or src.pending_delete:
                    continue
                if src.was_committed or src.tag == wanted:
                    job = self._make_add_job(src)
                    if job is None:
                        return False
                    extra.append(job)
            extra.extend(set_jobs)
        if not extra:
            return False
        self._edit_queue.extend(extra)
        return True

    def _apply_edit_local(self) -> None:
        spec = self._edit_spec
        if spec is None:
            return
        old = next((s for s in self.all_sources if s.tag == spec.id), None)
        was_committed = bool(old.was_committed) if old else False
        src = self._upsert_source(
            source_set(
                name=spec.name,
                tag=spec.id,
                slave_addr=spec.addr,
                function_code=spec.fc,
                start_addr=spec.reg,
                data_len=spec.qty,
                data_type=spec.dtype,
                formula=spec.formula,
                unit=spec.unit,
                candidate=True,
                was_committed=was_committed,
                cmp=spec.cmp,
                warn=spec.warn,
                crit=spec.crit,
            )
        )
        src.card_widget = self.page_points.upsert(
            spec.id, unit=spec.unit, candidate=True, name=spec.name
        )
        self._refresh_session()

    def _finish_edit(self, ok: bool) -> None:
        tag = self._edit_spec.id if self._edit_spec else ""
        self._editing = False
        self._edit_current = None
        self._edit_queue = []
        self._edit_spec = None
        self._edit_set_cmds = []
        if ok:
            self.update_textbrowser(
                f"[edit] 已写入候选 {tag}。请「试读候选」后再「确认落盘」。"
            )

    def _abort_edit(self, reason: str) -> None:
        if not self._editing:
            return
        self.update_textbrowser(f"[edit] 中止：{reason}")
        self._editing = False
        self._edit_current = None
        self._edit_queue = []
        self._edit_spec = None
        self._edit_set_cmds = []

    def open_import_dialog(self):
        if not self._require_online():
            return
        busy = self._queue_busy()
        if busy:
            self.update_textbrowser(f"[import] {busy}进行中，请稍后再导入")
            return
        start = Path(__file__).resolve().parent / "examples"
        if not start.is_dir():
            start = Path(__file__).resolve().parent
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入点表 JSON",
            str(start),
            "JSON (*.json);;所有文件 (*.*)",
        )
        if not path:
            return
        rows, err = load_import_rows(path)
        if err:
            QMessageBox.warning(self, "无法导入", err)
            return
        dialog = ImportPointsDialog(path, rows, self)
        if dialog.exec_() != dialog.Accepted:
            self.update_textbrowser("[import] 已取消")
            return
        self._import_queue = [
            _ImportJob(
                point=row.point,
                cmd=row.add_cmd,
                kind="add",
                set_name_cmd=row.set_name_cmd,
            )
            for row in rows
            if row.ok and row.add_cmd
        ]
        if not self._import_queue:
            self.update_textbrowser("[import] 没有可导入的点")
            return
        self._import_index = 0
        self._import_ok = 0
        self._import_fail = 0
        self._importing = True
        self._import_current = None
        self.update_textbrowser(
            f"[import] 开始导入 {len(self._import_queue)} 点 → 候选（不会自动落盘）"
        )
        self._send_next_import()

    def _send_next_import(self) -> None:
        if not self._importing:
            return
        if self._import_index >= len(self._import_queue):
            self._finish_import()
            return
        job = self._import_queue[self._import_index]
        self._import_current = job
        n = len(self._import_queue)
        self.update_textbrowser(
            f"[import] {self._import_index + 1}/{n} {job.kind} {job.point.id}"
        )
        self.send_nsh(job.cmd, kind="import", timeout_s=15)
        self.page_points.set_busy(
            True, f"导入中 {self._import_index + 1}/{n} {job.point.id}"
        )

    def _on_import_reply(self, command: str, response: str) -> None:
        if not self._importing or self._import_current is None:
            return
        job = self._import_current
        if command != job.cmd:
            return
        st = protocol.parse_vgpoint_status(response)
        if (
            st
            and not st.ok
            and st.code == "dup_id"
            and job.kind == "add"
            and not job.retried_set
        ):
            job.retried_set = True
            job.kind = "set"
            job.cmd = protocol.cmd_point_set_from_point(job.point)
            self.update_textbrowser(f"[import] {job.point.id} 已存在，改 set")
            self.send_nsh(job.cmd, kind="import", timeout_s=15)
            return
        if st and st.ok:
            if job.set_name_cmd and job.kind != "set_name":
                job.kind = "set_name"
                job.cmd = job.set_name_cmd
                job.set_name_cmd = ""
                self.update_textbrowser(f"[import] {job.point.id} 补写 name")
                self.send_nsh(job.cmd, kind="import", timeout_s=15)
                return
            self._import_ok += 1
            self._upsert_imported_point(job.point)
        else:
            self._import_fail += 1
            code = st.code if st else "no_status"
            self.update_textbrowser(f"[import] FAIL {job.point.id} {code}")
        self._import_index += 1
        self._send_next_import()

    def _on_import_transport_fail(self, command: str, error: str) -> None:
        if not self._importing or self._import_current is None:
            return
        job = self._import_current
        if command != job.cmd:
            return
        self._import_fail += 1
        self.update_textbrowser(f"[import] FAIL {job.point.id} {error}")
        self._import_index += 1
        self._send_next_import()

    def _upsert_imported_point(self, point: Point) -> None:
        src = self._upsert_source(
            source_set(
                name=point.name or point.id,
                tag=point.id,
                slave_addr=point.addr,
                function_code=point.fc,
                start_addr=point.reg,
                data_len=point.qty,
                data_type=point.dtype,
                formula=str(point.scale),
                unit=point.unit,
                candidate=True,
                cmp=point.cmp,
                warn=point.warn,
                crit=point.crit,
            )
        )
        src.card_widget = self.page_points.upsert(
            point.id, unit=point.unit, candidate=True, name=point.name or point.id
        )
        self._refresh_session()

    def _finish_import(self) -> None:
        total = len(self._import_queue)
        ok_n = self._import_ok
        fail_n = self._import_fail
        self._importing = False
        self._import_current = None
        self._import_queue = []
        self.update_textbrowser(
            f"[import] 完成 ok={ok_n} fail={fail_n} / {total}。"
            "请「试读候选」确认后再「确认落盘」。"
        )

    def _abort_import(self, reason: str) -> None:
        if not self._importing:
            return
        self.update_textbrowser(f"[import] 中止：{reason}")
        self._importing = False
        self._import_current = None
        self._import_queue = []

    def _queue_busy(self) -> str:
        if self._importing:
            return "导入"
        if self._deleting:
            return "删除"
        if self._editing:
            return "编辑"
        return ""

    def run_point_test(self):
        if not self._require_online():
            return
        self.update_textbrowser("[host] 试读候选（test 成功后请人工确认再落盘）")
        self.send_nsh(protocol.cmd_point_test(), kind="test", timeout_s=45)

    def confirm_apply(self):
        if not self._require_online():
            return
        pending = [s.tag for s in self.all_sources if s.pending_delete]
        remain = [
            s.tag
            for s in self.all_sources
            if not s.pending_delete
        ]
        extra = ""
        if pending and not remain:
            extra = "\n\n当前候选会被写成空表，已确认表将清空（首页无点）。"
        ret = QMessageBox.question(
            self,
            "确认落盘",
            "将执行：\n\n  vgpoint apply --confirm\n\n"
            "把候选表写入已确认点表并刷新采集。"
            f"{extra}\n确定？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            self.update_textbrowser("[host] 已取消落盘")
            return
        self.send_nsh(protocol.cmd_point_apply(True), kind="apply", timeout_s=20)

    def abort_candidate(self):
        if not self._require_online():
            return
        ret = QMessageBox.question(
            self,
            "放弃候选",
            "执行 vgpoint abort 丢弃候选表？\n（不影响已确认表）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            return
        self.send_nsh(protocol.cmd_point_abort(), kind="abort", timeout_s=15)

    def delete_point(self, tag: str) -> None:
        self.delete_points([tag])

    def delete_points(self, tags) -> None:
        seen: set[str] = set()
        unique: list[str] = []
        for raw in tags or []:
            tag = (raw or "").strip()
            if not tag or tag in seen:
                continue
            seen.add(tag)
            unique.append(tag)
        if not unique:
            QMessageBox.information(
                self,
                "批量删除",
                "请先勾选实时数据卡片，或在参数设置点表中多选行。",
            )
            return
        if not self._require_online():
            return
        busy = self._queue_busy()
        if busy:
            self.update_textbrowser(f"[del] {busy}进行中，请稍后再删除")
            return
        preview = "\n".join(f"  vgpoint del {tag}" for tag in unique[:12])
        extra = "" if len(unique) <= 12 else f"\n  … 共 {len(unique)} 个"
        remain = [
            s.tag
            for s in self.all_sources
            if s.tag not in unique and not s.pending_delete
        ]
        empty_note = ""
        if not remain:
            empty_note = (
                "\n\n删光后候选为空。确认落盘会把已确认表写成空表（首页无点）。"
            )
        ret = QMessageBox.question(
            self,
            "删除点位",
            "将从候选表删除：\n\n"
            f"{preview}{extra}\n\n"
            "已确认点若还不在候选里，会先同步进候选再删。\n"
            "已确认表要等「确认落盘」才会少这些点。\n"
            "「放弃候选」可撤销未落盘的删除。"
            f"{empty_note}\n确定？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            shown = unique[0] if len(unique) == 1 else f"{len(unique)} 点"
            self.update_textbrowser(f"[host] 已取消删除 {shown}")
            return
        self.page_points.clear_selection(unique)
        self._del_targets = unique
        self._del_queue = [
            _DelJob(tag="", cmd=protocol.cmd_point_list(True), kind="list_c")
        ]
        self._del_index = 0
        self._del_ok = 0
        self._del_fail = 0
        self._deleting = True
        self._del_current = None
        self.update_textbrowser(
            f"[del] 开始删除 {len(unique)} 点 → 候选（不会自动落盘）"
        )
        self._send_next_del()

    def _send_next_del(self) -> None:
        if not self._deleting:
            return
        if self._del_index >= len(self._del_queue):
            self._finish_delete()
            return
        job = self._del_queue[self._del_index]
        self._del_current = job
        n_del = sum(1 for j in self._del_queue if j.kind == "del")
        i_del = sum(1 for j in self._del_queue[: self._del_index] if j.kind == "del")
        if job.kind == "list_c":
            note = "查看候选表"
        elif job.kind == "abort":
            note = "丢掉空候选，以便从已确认表复制"
        elif job.kind == "add":
            note = f"补进候选 {job.tag}"
        else:
            note = f"{i_del + 1}/{n_del} {job.tag}"
        self.update_textbrowser(f"[del] {note}")
        self.send_nsh(job.cmd, kind=job.kind, timeout_s=15)
        self.page_points.set_busy(True, note)

    def _on_del_reply(self, command: str, response: str) -> None:
        if not self._deleting or self._del_current is None:
            return
        job = self._del_current
        if command != job.cmd:
            return
        st = protocol.parse_vgpoint_status(response)
        if job.kind == "list_c":
            if not self._plan_delete_after_probe(response):
                self._abort_delete("无法规划删除队列")
                return
        elif job.kind == "abort":
            if not (st and st.ok):
                code = st.code if st else "no_status"
                self._abort_delete(f"无法准备候选表 {code}")
                return
        elif job.kind == "add":
            if not (st and (st.ok or st.code == "dup_id")):
                self._del_fail += 1
                code = st.code if st else "no_status"
                self.update_textbrowser(f"[del] 补候选 FAIL {job.tag} {code}")
            else:
                src = next((s for s in self.all_sources if s.tag == job.tag), None)
                if src is not None:
                    src.candidate = True
                    self.page_points.upsert(
                        src.tag, unit=src.unit, candidate=True, name=src.name or src.tag
                    )
        elif job.kind == "del":
            if st and st.ok:
                self._del_ok += 1
            else:
                self._del_fail += 1
                code = st.code if st else "no_status"
                self.update_textbrowser(f"[del] FAIL {job.tag} {code}")
        self._del_index += 1
        self._send_next_del()

    def _on_del_transport_fail(self, command: str, error: str) -> None:
        if not self._deleting or self._del_current is None:
            return
        job = self._del_current
        if command != job.cmd:
            return
        if job.kind in ("list_c", "abort"):
            self._abort_delete(error)
            return
        self._del_fail += 1
        self.update_textbrowser(f"[del] FAIL {job.tag or job.kind} {error}")
        self._del_index += 1
        self._send_next_del()

    def _make_del_jobs(self, tags: list[str]) -> Optional[list[_DelJob]]:
        jobs: list[_DelJob] = []
        for tag in tags:
            try:
                jobs.append(_DelJob(tag=tag, cmd=protocol.cmd_point_del(tag), kind="del"))
            except protocol.ProtocolError as exc:
                QMessageBox.warning(self, "参数无效", f"{tag}: {exc}")
                return None
        return jobs

    def _make_add_job(self, src: source_set) -> Optional[_DelJob]:
        try:
            point = self._point_from_source(src)
            return _DelJob(
                tag=src.tag,
                cmd=protocol.cmd_point_add_from_point(point),
                kind="add",
            )
        except (protocol.ProtocolError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "参数无效", f"{src.tag}: {exc}")
            return None

    def _plan_delete_after_probe(self, response: str) -> bool:
        targets = list(self._del_targets)
        cand_tags = {p.id for p in protocol.parse_vgpoint_points(response)}
        st = protocol.parse_vgpoint_status(response)
        cand_n = st.n if st is not None else len(cand_tags)
        extra: list[_DelJob] = []
        if targets and all(tag in cand_tags for tag in targets):
            extra = self._make_del_jobs(targets) or []
            if len(extra) != len(targets):
                return False
        elif cand_n == 0:
            self.update_textbrowser(
                "[del] 候选为空，先 abort 再从已确认表复制后删除"
            )
            extra.append(
                _DelJob(tag="", cmd=protocol.cmd_point_abort(), kind="abort")
            )
            dels = self._make_del_jobs(targets)
            if dels is None:
                return False
            extra.extend(dels)
        else:
            self.update_textbrowser(
                "[del] 候选里缺已确认点，先 add 补齐再删，避免落盘时误删其它点"
            )
            wanted = set(targets)
            for src in self.all_sources:
                if src.tag in cand_tags or src.pending_delete:
                    continue
                if src.was_committed or src.tag in wanted:
                    job = self._make_add_job(src)
                    if job is None:
                        return False
                    extra.append(job)
            dels = self._make_del_jobs(targets)
            if dels is None:
                return False
            extra.extend(dels)
        if not extra:
            return False
        self._del_queue.extend(extra)
        return True

    def _point_from_source(self, src: source_set) -> Point:
        try:
            scale = float(src.formula) if src.formula else 1.0
        except (TypeError, ValueError):
            scale = 1.0
        return Point(
            id=src.tag,
            name=src.name or src.tag,
            addr=int(src.slave_addr),
            fc=int(src.function_code or 3),
            reg=int(src.start_addr),
            qty=int(src.data_len or 1),
            dtype=src.data_type or "int16",
            scale=scale,
            unit=src.unit or "",
            cmp=src.cmp or "",
            warn=src.warn,
            crit=src.crit,
        )

    def _finish_delete(self) -> None:
        total = sum(1 for j in self._del_queue if j.kind == "del")
        ok_n = self._del_ok
        fail_n = self._del_fail
        self._deleting = False
        self._del_current = None
        self._del_queue = []
        self._del_targets = []
        self.update_textbrowser(
            f"[del] 完成 ok={ok_n} fail={fail_n} / {total}。"
            "已确认点需「确认落盘」后才会从已确认表去掉。"
        )

    def _abort_delete(self, reason: str) -> None:
        if not self._deleting:
            return
        self.update_textbrowser(f"[del] 中止：{reason}")
        self._deleting = False
        self._del_current = None
        self._del_queue = []
        self._del_targets = []

    def _mark_deleted(self, tag: str) -> None:
        src = next((s for s in self.all_sources if s.tag == tag), None)
        if src is None:
            self.page_points.remove_tags([tag])
            self._refresh_session()
            return
        if not src.was_committed:
            self.all_sources = [s for s in self.all_sources if s.tag != tag]
            self.page_points.remove_tags([tag])
        else:
            src.pending_delete = True
            src.candidate = True
            self.page_points.mark_pending_delete(tag)
        self._refresh_session()

    def _clear_points(self) -> None:
        self.all_sources = []
        self.page_points.remove_tags(list(self.page_points.tags()))
        self._refresh_session()

    def _replace_committed_points(self, points: list[Point]) -> None:
        listed = {p.id for p in points}
        stale: list[str] = []
        kept: list[source_set] = []
        for src in self.all_sources:
            if src.tag in listed:
                src.pending_delete = False
                kept.append(src)
            elif src.candidate and not src.was_committed and not src.pending_delete:
                kept.append(src)
            else:
                stale.append(src.tag)
        self.all_sources = kept
        if stale:
            self.page_points.remove_tags(stale)
        self._sync_cards_from_points(points, candidate=False)
        self._refresh_session()

    def _upsert_source(self, src: source_set) -> source_set:
        for i, old in enumerate(self.all_sources):
            if old.tag == src.tag:
                src.card_widget = old.card_widget
                src.last_value = old.last_value
                src.last_ok = old.last_ok
                if old.pending_delete:
                    src.pending_delete = True
                    src.candidate = True
                if old.was_committed and not src.was_committed:
                    src.was_committed = True
                self.all_sources[i] = src
                return src
        self.all_sources.append(src)
        return src

    def _sync_cards_from_points(self, points: list[Point], candidate: bool) -> None:
        label = "候选" if candidate else "已确认"
        self.update_textbrowser(f"[parse] {label}点数={len(points)}")
        for p in points:
            src = self._upsert_source(
                source_set(
                    name=p.name or p.id,
                    tag=p.id,
                    slave_addr=p.addr,
                    function_code=p.fc,
                    start_addr=p.reg,
                    data_len=p.qty,
                    data_type=p.dtype,
                    formula=str(p.scale),
                    unit=p.unit,
                    candidate=candidate,
                    was_committed=not candidate,
                    cmp=p.cmp,
                    warn=p.warn,
                    crit=p.crit,
                )
            )
            src.card_widget = self.page_points.upsert(
                p.id,
                unit=p.unit,
                candidate=src.candidate,
                value=src.last_value,
                ok=src.last_ok,
                name=p.name or p.id,
            )
            if src.pending_delete:
                self.page_points.mark_pending_delete(p.id)
        self._refresh_session()

    def _apply_reads(self, reads) -> None:
        by_id = {r.id: r for r in reads}
        for src in self.all_sources:
            r = by_id.get(src.tag or src.name)
            if r is None:
                continue
            if not r.ok or r.value is None:
                src.last_value = "FAIL"
                src.last_ok = False
            else:
                src.last_value = f"{r.value:g}"
                src.last_ok = True
            self.page_points.apply_read(src.tag, src.last_value, src.last_ok)
        ok_n = sum(1 for r in reads if r.ok)
        self.update_textbrowser(f"[parse] READ ok={ok_n}/{len(reads)}")

    def _refresh_session(self) -> None:
        cand = sum(1 for s in self.all_sources if s.candidate or s.pending_delete)
        self.page_session.set_counts(len(self.all_sources), cand)
        rows = []
        for s in self.all_sources:
            if s.pending_delete:
                status = "待删除"
            elif s.candidate:
                status = "候选"
            else:
                status = "已确认"
            rows.append(
                (
                    s.tag,
                    s.name or s.tag,
                    s.slave_addr,
                    s.function_code,
                    s.start_addr,
                    s.data_len,
                    s.formula,
                    s.unit,
                    status,
                )
            )
        self.page_session.set_rows(rows)

    def update_textbrowser(self, text):
        self.textBrowser.append(text if text.endswith("\n") else text.rstrip("\n"))

    def _header_drag_hit(self, pos: QPoint) -> bool:
        header = self.frame_4.rect()
        header.moveTopLeft(self.frame_4.mapTo(self, header.topLeft()))
        if not header.contains(pos):
            return False
        for w in (
            self.pushButton_serial,
            self.comboBox_serial,
            self.pushButton_4,
            self.pushButton_5,
        ):
            r = w.rect()
            r.moveTopLeft(w.mapTo(self, r.topLeft()))
            if r.contains(pos):
                return False
        return True

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton and self._header_drag_hit(event.pos()):
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            return
        self._drag_offset = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):  # noqa: N802
        try:
            self.ctl.shutdown()
        except Exception:
            pass
        super().closeEvent(event)


if __name__ == "__main__":
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    apply_theme(app)
    win = mainUI()
    win.show()
    sys.exit(app.exec_())
