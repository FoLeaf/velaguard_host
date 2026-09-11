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
from widgets import AddPointDialog, ConsolePage, ImportPointsDialog, PointsPage, SessionPage
from widgets.import_points_dialog import load_import_rows


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
        self.update_textbrowser("[host] 流程: 新增/删除点位 → 试读候选 → 人确认 → 确认落盘")
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
        self.page_points.import_requested.connect(self.open_import_dialog)
        self.page_session.delete_requested.connect(self.delete_point)
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
        self._finish_inflight()

    def _on_nsh_failed(self, command: str, error: str) -> None:
        self.update_textbrowser(f"! {command}: {error}")
        if command == "<connect>":
            self.pushButton_serial.setText("打开串口")
            self.comboBox_serial.setEnabled(True)
            self._connecting = False
            self._inflight = 0
            self._connected_port = ""
            self._set_online_chips(False)
            self._set_busy(False)
        else:
            try:
                self._on_import_transport_fail(command, error)
            except Exception as exc:
                self.update_textbrowser(f"[import] {exc}")
            self._finish_inflight()

    def _dispatch(self, command: str, response: str) -> None:
        if not command.startswith("vgpoint"):
            return
        st = protocol.parse_vgpoint_status(response)
        points = protocol.parse_vgpoint_points(response)
        reads = protocol.parse_vgpoint_reads(response)
        if points and command.startswith("vgpoint list"):
            self._sync_cards_from_points(points, candidate=command.endswith("-c"))
        if reads:
            self._apply_reads(reads)
        if st:
            kind = "OK" if st.ok else f"ERR {st.code}"
            self.update_textbrowser(f"[parse] vgpoint {kind} cmd={st.cmd} n={st.n}")
            if st.ok and st.cmd == "apply":
                self.update_textbrowser("[host] 已确认表已更新；请再「试读候选」或 list 核对")
                self.all_sources = [s for s in self.all_sources if not s.pending_delete]
                for src in self.all_sources:
                    src.candidate = False
                    src.was_committed = True
                    src.pending_delete = False
                self.page_points.mark_all_committed()
                self._refresh_session()
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
                self.send_nsh(protocol.cmd_point_list(False), kind="list", timeout_s=5)
            if not st.ok and st.cmd == "del":
                self.update_textbrowser(f"[host] 删除失败 code={st.code}")
            if not st.ok and st.code == "need_confirm":
                self.update_textbrowser("[host] apply 必须带 --confirm，已用确认对话框流程")

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
                tag=spec.tag,
                addr=spec.addr,
                reg=spec.reg,
                fc=spec.fc,
                qty=spec.qty,
                dtype=spec.dtype,
                scale=spec.scale,
                unit=spec.unit,
                cmp=spec.cmp,
                warn=spec.warn,
                crit=spec.crit,
            )
        except (ValueError, protocol.ProtocolError) as exc:
            QMessageBox.warning(self, "参数无效", str(exc))
            return

        src = self._upsert_source(
            source_set(
                name=spec.name,
                tag=spec.tag,
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
            spec.tag, unit=spec.unit, candidate=True
        )
        self._refresh_session()
        self.send_nsh(cmd, kind="add", timeout_s=15)

    def open_import_dialog(self):
        if not self._require_online():
            return
        if self._importing:
            self.update_textbrowser("[import] 已有导入进行中")
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
            _ImportJob(point=row.point, cmd=row.add_cmd, kind="add")
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
            f"[import] {self._import_index + 1}/{n} {job.kind} {job.point.tag}"
        )
        self.send_nsh(job.cmd, kind="import", timeout_s=15)
        self.page_points.set_busy(
            True, f"导入中 {self._import_index + 1}/{n} {job.point.tag}"
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
            and st.code == "dup_tag"
            and job.kind == "add"
            and not job.retried_set
        ):
            job.retried_set = True
            job.kind = "set"
            job.cmd = protocol.cmd_point_set_from_point(job.point)
            self.update_textbrowser(f"[import] {job.point.tag} 已存在，改 set")
            self.send_nsh(job.cmd, kind="import", timeout_s=15)
            return
        if st and st.ok:
            self._import_ok += 1
            self._upsert_imported_point(job.point)
        else:
            self._import_fail += 1
            code = st.code if st else "no_status"
            self.update_textbrowser(f"[import] FAIL {job.point.tag} {code}")
        self._import_index += 1
        self._send_next_import()

    def _on_import_transport_fail(self, command: str, error: str) -> None:
        if not self._importing or self._import_current is None:
            return
        job = self._import_current
        if command != job.cmd:
            return
        self._import_fail += 1
        self.update_textbrowser(f"[import] FAIL {job.point.tag} {error}")
        self._import_index += 1
        self._send_next_import()

    def _upsert_imported_point(self, point: Point) -> None:
        src = self._upsert_source(
            source_set(
                name=point.tag,
                tag=point.tag,
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
            point.tag, unit=point.unit, candidate=True
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

    def run_point_test(self):
        if not self._require_online():
            return
        self.update_textbrowser("[host] 试读候选（test 成功后请人工确认再落盘）")
        self.send_nsh(protocol.cmd_point_test(), kind="test", timeout_s=45)

    def confirm_apply(self):
        if not self._require_online():
            return
        ret = QMessageBox.question(
            self,
            "确认落盘",
            "将执行：\n\n  vgpoint apply --confirm\n\n"
            "把候选表写入已确认点表并刷新采集。\n确定？",
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
        tag = (tag or "").strip()
        if not tag:
            return
        if not self._require_online():
            return
        ret = QMessageBox.question(
            self,
            "删除点位",
            f"将执行：\n\n  vgpoint del {tag}\n\n"
            "只从候选表删除。已确认表要等「确认落盘」才会少这个点。\n"
            "「放弃候选」可撤销未落盘的删除。\n确定？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ret != QMessageBox.Yes:
            self.update_textbrowser(f"[host] 已取消删除 {tag}")
            return
        try:
            cmd = protocol.cmd_point_del(tag)
        except protocol.ProtocolError as exc:
            QMessageBox.warning(self, "参数无效", str(exc))
            return
        self.send_nsh(cmd, kind="del", timeout_s=15)

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
                    name=p.tag,
                    tag=p.tag,
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
                p.tag,
                unit=p.unit,
                candidate=src.candidate,
                value=src.last_value,
                ok=src.last_ok,
            )
            if src.pending_delete:
                self.page_points.mark_pending_delete(p.tag)
        self._refresh_session()

    def _apply_reads(self, reads) -> None:
        by_tag = {r.tag: r for r in reads}
        for src in self.all_sources:
            r = by_tag.get(src.tag or src.name)
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
