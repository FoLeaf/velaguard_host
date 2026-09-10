"""VelaGuard host main window (PyQt5, built in code)."""

from __future__ import annotations

import traceback

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import protocol
from .models import PointTable
from .nsh_session import NshSession
from .worker import SerialController

DEFAULT_BAUD = 115200


class VelaGuardHost(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VelaGuard Host — NSH 配置上位机")
        self.resize(1100, 760)
        self._ctl = SerialController()
        self._ctl.log.connect(self._on_log)
        self._ctl.connected.connect(self._on_connected)
        self._ctl.disconnected.connect(self._on_disconnected)
        self._ctl.command_done.connect(self._on_command_done)
        self._ctl.command_failed.connect(self._on_command_failed)

        self._pending = ""  # last command for dispatch
        self._table_live = PointTable()
        self._table_cand = PointTable()
        self._monitor_timer = QTimer(self)
        self._monitor_timer.timeout.connect(self._monitor_tick)

        self._build_ui()
        self._refresh_ports()

    # ---- UI ----
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # Connection bar
        conn = QGroupBox("串口连接（ST-LINK VCP / NSH）")
        form = QHBoxLayout(conn)
        self.port_combo = QComboBox()
        self.baud_spin = QSpinBox()
        self.baud_spin.setRange(1200, 921600)
        self.baud_spin.setValue(DEFAULT_BAUD)
        self.btn_refresh = QPushButton("刷新")
        self.btn_connect = QPushButton("连接")
        self.btn_disconnect = QPushButton("断开")
        self.btn_disconnect.setEnabled(False)
        self.lbl_status = QLabel("未连接")
        self.lbl_status.setStyleSheet("color:#a00; font-weight:bold;")
        form.addWidget(QLabel("端口"))
        form.addWidget(self.port_combo, 1)
        form.addWidget(QLabel("波特率"))
        form.addWidget(self.baud_spin)
        form.addWidget(self.btn_refresh)
        form.addWidget(self.btn_connect)
        form.addWidget(self.btn_disconnect)
        form.addWidget(self.lbl_status, 1)
        root.addWidget(conn)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 3)

        self.tabs.addTab(self._build_discover_tab(), "总线探查")
        self.tabs.addTab(self._build_points_tab(), "点表")
        self.tabs.addTab(self._build_monitor_tab(), "监视")
        self.tabs.addTab(self._build_console_tab(), "终端")

        # Log
        log_box = QGroupBox("主机日志")
        lv = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        self.log_view.setFont(QFont("Consolas", 10))
        lv.addWidget(self.log_view)
        root.addWidget(log_box, 2)

        self.btn_refresh.clicked.connect(self._refresh_ports)
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)

    def _build_discover_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        g = QGroupBox("vgdiscover 工作流（候选 → 试读 → 确认落盘）")
        grid = QGridLayout(g)

        self.addr_min = QSpinBox()
        self.addr_min.setRange(1, 247)
        self.addr_min.setValue(1)
        self.addr_max = QSpinBox()
        self.addr_max.setRange(1, 247)
        self.addr_max.setValue(32)
        self.probe_addr = QSpinBox()
        self.probe_addr.setRange(1, 247)
        self.probe_addr.setValue(1)
        self.tr_addr = QSpinBox()
        self.tr_addr.setRange(1, 247)
        self.tr_addr.setValue(1)
        self.tr_reg = QSpinBox()
        self.tr_reg.setRange(0, 65535)
        self.tr_qty = QSpinBox()
        self.tr_qty.setRange(1, 16)
        self.tr_qty.setValue(2)

        self.btn_scan = QPushButton("扫描地址")
        self.btn_probe = QPushButton("探测寄存器")
        self.btn_dump = QPushButton("导出候选点表")
        self.btn_test_read = QPushButton("试读一次")
        self.btn_apply_dry = QPushButton("预检 apply（不落盘）")
        self.btn_apply = QPushButton("确认落盘 apply --confirm")
        self.btn_apply.setStyleSheet("background:#b33; color:white; font-weight:bold;")

        grid.addWidget(QLabel("扫描范围"), 0, 0)
        grid.addWidget(self.addr_min, 0, 1)
        grid.addWidget(QLabel("—"), 0, 2)
        grid.addWidget(self.addr_max, 0, 3)
        grid.addWidget(self.btn_scan, 0, 4)

        grid.addWidget(QLabel("探测从站"), 1, 0)
        grid.addWidget(self.probe_addr, 1, 1)
        grid.addWidget(self.btn_probe, 1, 4)

        grid.addWidget(self.btn_dump, 2, 0, 1, 2)
        grid.addWidget(QLabel("试读从站/寄存器/数量"), 3, 0)
        grid.addWidget(self.tr_addr, 3, 1)
        grid.addWidget(self.tr_reg, 3, 2)
        grid.addWidget(self.tr_qty, 3, 3)
        grid.addWidget(self.btn_test_read, 3, 4)

        grid.addWidget(self.btn_apply_dry, 4, 0, 1, 2)
        grid.addWidget(self.btn_apply, 4, 2, 1, 3)
        v.addWidget(g)

        hint = QLabel(
            "安全约定：落盘必须单独点击「确认落盘」；未确认时 live 采集仍用旧点表。"
            "上位机不占用 RS485。"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#555;")
        v.addWidget(hint)

        self.discover_out = QPlainTextEdit()
        self.discover_out.setReadOnly(True)
        self.discover_out.setFont(QFont("Consolas", 10))
        v.addWidget(self.discover_out, 1)

        self.btn_scan.clicked.connect(self._do_scan)
        self.btn_probe.clicked.connect(self._do_probe)
        self.btn_dump.clicked.connect(self._do_dump)
        self.btn_test_read.clicked.connect(self._do_test_read)
        self.btn_apply_dry.clicked.connect(lambda: self._do_apply(False))
        self.btn_apply.clicked.connect(lambda: self._do_apply(True))
        return w

    def _build_points_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        bar = QHBoxLayout()
        self.btn_load_live = QPushButton("读取 live points.json")
        self.btn_load_cand = QPushButton("读取 candidate")
        self.btn_cfg = QPushButton("vgcfg dump")
        self.btn_stats = QPushButton("vgstats dump")
        bar.addWidget(self.btn_load_live)
        bar.addWidget(self.btn_load_cand)
        bar.addWidget(self.btn_cfg)
        bar.addWidget(self.btn_stats)
        bar.addStretch(1)
        v.addLayout(bar)

        self.point_table = QTableWidget(0, 8)
        self.point_table.setHorizontalHeaderLabels(
            ["tag", "addr", "fc", "reg", "qty", "dtype", "scale", "unit"]
        )
        self.point_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        v.addWidget(self.point_table, 2)

        self.points_meta = QLabel("未加载点表")
        v.addWidget(self.points_meta)

        self.cfg_out = QPlainTextEdit()
        self.cfg_out.setReadOnly(True)
        self.cfg_out.setMaximumHeight(140)
        self.cfg_out.setFont(QFont("Consolas", 10))
        v.addWidget(self.cfg_out)

        self.btn_load_live.clicked.connect(lambda: self._do_load_points(protocol.POINTS_PATH, True))
        self.btn_load_cand.clicked.connect(
            lambda: self._do_load_points(protocol.CANDIDATE_PATH, False)
        )
        self.btn_cfg.clicked.connect(lambda: self._send(protocol.cmd_cfg_dump(), 10))
        self.btn_stats.clicked.connect(lambda: self._send(protocol.cmd_stats_dump(), 10))
        return w

    def _build_monitor_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        form = QFormLayout()
        self.mon_addr = QSpinBox()
        self.mon_addr.setRange(1, 247)
        self.mon_addr.setValue(1)
        self.mon_reg = QSpinBox()
        self.mon_reg.setRange(0, 65535)
        self.mon_qty = QSpinBox()
        self.mon_qty.setRange(1, 16)
        self.mon_qty.setValue(2)
        self.mon_period = QSpinBox()
        self.mon_period.setRange(500, 60000)
        self.mon_period.setValue(2000)
        self.mon_period.setSuffix(" ms")
        self.btn_mon_toggle = QPushButton("开始监视")
        form.addRow("从站", self.mon_addr)
        form.addRow("起始寄存器", self.mon_reg)
        form.addRow("数量", self.mon_qty)
        form.addRow("周期", self.mon_period)
        form.addRow("", self.btn_mon_toggle)
        v.addLayout(form)

        self.mon_out = QPlainTextEdit()
        self.mon_out.setReadOnly(True)
        self.mon_out.setFont(QFont("Consolas", 10))
        v.addWidget(self.mon_out, 1)
        self.btn_mon_toggle.clicked.connect(self._toggle_monitor)
        return w

    def _build_console_tab(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        self.console_in = QLineEdit()
        self.console_in.setPlaceholderText("输入 NSH 命令，回车发送，例如 vgcfg dump")
        self.console_in.returnPressed.connect(self._send_console)
        self.btn_send = QPushButton("发送")
        row.addWidget(self.console_in, 1)
        row.addWidget(self.btn_send)
        v.addLayout(row)
        self.console_out = QPlainTextEdit()
        self.console_out.setReadOnly(True)
        self.console_out.setFont(QFont("Consolas", 10))
        v.addWidget(self.console_out, 1)
        self.btn_send.clicked.connect(self._send_console)
        return w

    # ---- connection ----
    def _refresh_ports(self) -> None:
        self.port_combo.clear()
        ports = NshSession.list_ports()
        self.port_combo.addItems(ports)
        for i, p in enumerate(ports):
            if p.upper().startswith("COM3") or "STLink" in p or "ST-LINK" in p.upper():
                self.port_combo.setCurrentIndex(i)
                break

    def _on_connect_clicked(self) -> None:
        port = self.port_combo.currentText().strip()
        if not port:
            QMessageBox.warning(self, "连接", "请选择串口")
            return
        self.lbl_status.setText(f"连接中 {port}…")
        self._ctl.open(port, self.baud_spin.value())

    def _on_disconnect_clicked(self) -> None:
        self._monitor_timer.stop()
        self.btn_mon_toggle.setText("开始监视")
        self._ctl.close()

    def _on_connected(self, port: str) -> None:
        self.lbl_status.setText(f"已连接 {port}")
        self.lbl_status.setStyleSheet("color:#070; font-weight:bold;")
        self.btn_connect.setEnabled(False)
        self.btn_disconnect.setEnabled(True)
        self.port_combo.setEnabled(False)
        self.baud_spin.setEnabled(False)

    def _on_disconnected(self) -> None:
        self.lbl_status.setText("未连接")
        self.lbl_status.setStyleSheet("color:#a00; font-weight:bold;")
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.port_combo.setEnabled(True)
        self.baud_spin.setEnabled(True)
        self._monitor_timer.stop()
        self.btn_mon_toggle.setText("开始监视")

    # ---- command helpers ----
    def _send(self, command: str, timeout_s: float = 20.0) -> None:
        self._pending = command
        self._append_log(f"$ {command}\n")
        self._ctl.send(command, timeout_s=timeout_s)

    def _require_connect(self) -> bool:
        if self.btn_disconnect.isEnabled():
            return True
        QMessageBox.information(self, "VelaGuard", "请先连接串口")
        return False

    def _do_scan(self) -> None:
        if not self._require_connect():
            return
        self._send(
            protocol.cmd_scan(self.addr_min.value(), self.addr_max.value()),
            timeout_s=60,
        )

    def _do_probe(self) -> None:
        if not self._require_connect():
            return
        self._send(protocol.cmd_probe(self.probe_addr.value()), timeout_s=60)

    def _do_dump(self) -> None:
        if not self._require_connect():
            return
        self._send(protocol.cmd_dump(), timeout_s=20)

    def _do_test_read(self) -> None:
        if not self._require_connect():
            return
        self._send(
            protocol.cmd_test_read(
                self.tr_addr.value(), self.tr_reg.value(), self.tr_qty.value()
            ),
            timeout_s=20,
        )

    def _do_apply(self, confirm: bool) -> None:
        if not self._require_connect():
            return
        if confirm:
            ret = QMessageBox.question(
                self,
                "确认落盘",
                "将执行 vgdiscover apply --confirm，写入 /data/velaguard/config/points.json 并刷新配置槽。\n确定？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ret != QMessageBox.Yes:
                return
        self._send(protocol.cmd_apply(confirm=confirm), timeout_s=20)

    def _do_load_points(self, path: str, live: bool) -> None:
        if not self._require_connect():
            return
        self._send(protocol.cmd_cat_points(path), timeout_s=15)
        self._pending_points_live = live

    def _send_console(self) -> None:
        if not self._require_connect():
            return
        cmd = self.console_in.text().strip()
        if not cmd:
            return
        self.console_in.clear()
        self._send(cmd, timeout_s=30)

    def _toggle_monitor(self) -> None:
        if self._monitor_timer.isActive():
            self._monitor_timer.stop()
            self.btn_mon_toggle.setText("开始监视")
            return
        if not self._require_connect():
            return
        self._monitor_timer.start(self.mon_period.value())
        self.btn_mon_toggle.setText("停止监视")

    def _monitor_tick(self) -> None:
        cmd = protocol.cmd_test_read(
            self.mon_addr.value(), self.mon_reg.value(), self.mon_qty.value()
        )
        # Long-running monitor should not collide with other work; skip if pending.
        if self._pending:
            return
        self._send(cmd, timeout_s=8)

    # ---- responses ----
    def _on_log(self, text: str) -> None:
        self._append_log(text if text.endswith("\n") else text + "\n")
        self.console_out.moveCursor(QTextCursor.End)
        self.console_out.insertPlainText(text if text.endswith("\n") else text + "\n")
        self.console_out.moveCursor(QTextCursor.End)

    def _on_command_done(self, command: str, response: str) -> None:
        self._append_log(f"< {command}\n{response}\n")
        page = self.tabs.currentWidget()
        # Always mirror to console / discover panes.
        self.console_out.appendPlainText(response)
        if self.tabs.currentIndex() == 0:
            self.discover_out.appendPlainText(f"$ {command}\n{response}")
        try:
            self._dispatch(command, response)
        except Exception:
            self._append_log("[host] parse error:\n" + traceback.format_exc())
        self._pending = ""

    def _on_command_failed(self, command: str, error: str) -> None:
        self._append_log(f"! {command}: {error}\n")
        self._pending = ""
        if command == "<connect>":
            self.lbl_status.setText(error)
            self.lbl_status.setStyleSheet("color:#a00; font-weight:bold;")

    def _dispatch(self, command: str, response: str) -> None:
        if command.startswith("vgdiscover scan"):
            hits = protocol.parse_scan(response)
            self.discover_out.appendPlainText(
                f"[parse] found {len(hits)} slave(s): "
                + ",".join(str(h.addr) for h in hits)
            )
        elif command.startswith("vgdiscover probe"):
            addr, blocks = protocol.parse_probe(response)
            self.discover_out.appendPlainText(f"[parse] probe addr={addr} blocks={len(blocks)}")
        elif command.startswith("vgdiscover test-read"):
            r = protocol.parse_test_read(response)
            if r:
                parts = [f"[{s.reg}]={s.raw}" for s in r.samples]
                self.discover_out.appendPlainText(
                    f"[parse] test-read addr={r.addr} reg={r.reg} " + " ".join(parts)
                )
            if self.tabs.currentIndex() == 2:
                self.mon_out.appendPlainText(response.strip())
        elif command.startswith("vgdiscover apply"):
            info = protocol.parse_apply(response)
            self.discover_out.appendPlainText(f"[parse] apply {info}")
        elif command.startswith("vgcfg dump"):
            info = protocol.parse_cfg_dump(response)
            self.cfg_out.setPlainText(
                f"{info.source} seq={info.seq} schema={info.schema} "
                f"committed={info.committed} name={info.name}\n{info.raw.strip()}"
            )
        elif command.startswith("vgstats dump"):
            stats = protocol.parse_stats_dump(response)
            lines = [
                f"slave={s.slave} total={s.total} ok={s.ok} crc={s.crc} "
                f"timeout={s.timeout} err={s.error_rate:.1%} lat_avg={s.lat_avg_ms}ms"
                for s in stats
            ]
            self.cfg_out.setPlainText("\n".join(lines) if lines else response.strip())
        elif command.startswith("cat "):
            table = protocol.parse_point_table_json(response, path=command.split(" ", 1)[1])
            if table:
                live = getattr(self, "_pending_points_live", True)
                if live:
                    self._table_live = table
                else:
                    self._table_cand = table
                self._fill_points_table(table)

    def _fill_points_table(self, table: PointTable) -> None:
        self.point_table.setRowCount(len(table.points))
        for row, p in enumerate(table.points):
            vals = [
                p.tag,
                str(p.addr),
                str(p.fc),
                str(p.reg),
                str(p.qty),
                p.dtype,
                f"{p.scale:g}",
                p.unit,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.point_table.setItem(row, col, item)
        self.points_meta.setText(
            f"schema={table.schema_version} bus={table.device}@{table.baud} "
            f"hits={table.hits} points={len(table.points)} path={table.path}"
        )

    def _append_log(self, text: str) -> None:
        self.log_view.moveCursor(QTextCursor.End)
        self.log_view.insertPlainText(text)
        self.log_view.moveCursor(QTextCursor.End)

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self._ctl.shutdown()
        except Exception:
            pass
        super().closeEvent(event)


def run() -> int:
    import sys

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    win = VelaGuardHost()
    win.show()
    return app.exec_()
