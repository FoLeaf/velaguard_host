"""VelaGuard Host — 原工程 UI + 板端 vgpoint NSH 协议。

权威协议：
  contest2026_004_TeamFalcons/docs/velaguard-host-nsh-protocol.md
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QGridLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from window import *  # noqa: F401,F403
from config import *  # noqa: F401,F403
from sourcecard_ui import *  # noqa: F401,F403

from velaguard_host import protocol
from velaguard_host.models import Point
from velaguard_host.worker import SerialController


def sanitize_tag(name: str, fallback: str = "p1") -> str:
    raw = (name or fallback or "p1").strip()
    out = []
    for ch in raw:
        if (ch.isascii() and ch.isalnum()) or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    tag = "".join(out)[:23].strip("_") or fallback
    if tag[0].isdigit():
        tag = "t_" + tag
    return tag[:23]


@dataclass
class source_set:
    name: str
    id: str
    slave_addr: int
    function_code: int
    start_addr: int
    data_len: int
    data_type: int
    formula: str
    unit: str
    dir: int
    is_enabled: bool = True
    card_widget: Any = None
    last_value: Optional[str] = None
    tag: str = ""


class source_card(QWidget, Ui_sourcecard_ui):
    def __init__(self, name, dir):
        super().__init__()
        self.setupUi(self)
        self.viewer_layout = QVBoxLayout()
        self.frame_source_viewer.setLayout(self.viewer_layout)
        self.dir = dir
        self.name = name
        self._value_label: Optional[QLabel] = None
        self.source_card_init()

    def source_card_init(self):
        if self.dir:
            self._value_label = QLabel("N/A")
            self._value_label.setStyleSheet(
                'font: 12pt "小米兰亭"; color: #07234d; font-weight:600;'
            )
            self._value_label.setAlignment(Qt.AlignCenter)
            self.frame_source_viewer.layout().addWidget(self._value_label)
        else:
            self.checkbox_source_controller = QCheckBox("关闭")
            self.checkbox_source_controller.setStyleSheet('font: 12pt "小米兰亭";')
            self.frame_source_viewer.layout().addWidget(self.checkbox_source_controller)
        self.label_source_name.setText(self.name)

    def set_value_text(self, text: str) -> None:
        if self._value_label is not None:
            self._value_label.setText(text)


class mainUI(QWidget, Ui_Form):
    all_sources: list[source_set] = []

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.ctl = SerialController(self)
        self.ctl.log.connect(self.update_textbrowser)
        self.ctl.connected.connect(self._on_nsh_connected)
        self.ctl.disconnected.connect(self._on_nsh_disconnected)
        self.ctl.command_done.connect(self._on_nsh_done)
        self.ctl.command_failed.connect(self._on_nsh_failed)
        self._pending_cmd = ""
        self._pending_kind = ""  # add | test | apply | list | raw
        self.mainUI_custom()

    # ---- UI 装配（原壳 + 简单优化）----
    def mainUI_custom(self):
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 原侧栏导航
        self.pushButton_console.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.pushButton_realtimedata.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        self.pushButton_configuration.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.pushButton_serial.clicked.connect(self.serial_toggle)
        self.pushButton_addsource.clicked.connect(self.open_add_source_dialog)
        self.pushButton_getsource.clicked.connect(self.run_point_test)

        # 简单文案/语义优化（不改 Designer 结构）
        self.label_2.setText("VelaGuard Host")
        self.label_3.setText("NSH · vgpoint")
        self.pushButton_addsource.setText("新增点位")
        self.pushButton_getsource.setText("试读候选")
        self.pushButton_9.setText("确认落盘")
        self.pushButton_10.setText("放弃候选")
        self.pushButton_9.clicked.connect(self.confirm_apply)
        self.pushButton_10.clicked.connect(self.abort_candidate)
        self._retarget_config_page()

        self.textBrowser.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        self.textBrowser.setFont(QFont("JetBrains Mono", 11))
        self.serial_port_list_init()

        self.overview_layout = QGridLayout()
        self.frame_source_overview.setLayout(self.overview_layout)
        self.overview_timer = QTimer(self)
        self.overview_timer.timeout.connect(self.overview_update)
        self.overview_timer.start(800)

        self.update_textbrowser("[host] 协议: vgpoint NSH（板端 docs/velaguard-host-nsh-protocol.md）")
        self.update_textbrowser("[host] 流程: 新增点位 → 试读候选 → 人确认 → 确认落盘")
        self._set_online_chips(False)

    def _retarget_config_page(self):
        """把原 MQTT 参数页改标签为点表落盘说明（仅文案，布局不动）。"""
        mapping = {
            "label_5": "协议",
            "label_6": "串口",
            "label_7": "提示符",
            "label_8": "落盘命令",
            "label_9": "候选路径",
            "label_10": "已确认路径",
            "label_11": "点上限",
        }
        for obj, text in mapping.items():
            w = getattr(self, obj, None)
            if w is not None:
                w.setText(text)
        # 只读展示，避免误当 MQTT 配置
        placeholders = {
            "lineEdit": "vgpoint",
            "lineEdit_2": "COM3 @ 115200",
            "lineEdit_3": "nsh>",
            "lineEdit_4": "vgpoint apply --confirm",
            "lineEdit_5": protocol.CANDIDATE_PATH,
            "lineEdit_6": protocol.POINTS_PATH,
            "lineEdit_7": "32",
        }
        for obj, ph in placeholders.items():
            w = getattr(self, obj, None)
            if w is not None:
                w.setPlaceholderText(ph)
                if not w.text():
                    w.setText(ph)
                w.setReadOnly(True)

    def _set_online_chips(self, online: bool):
        color = "#0a7a3e" if online else "#a33"
        self.label.setStyleSheet(
            f'color: rgb(255,255,255); font: 12pt "小米兰亭"; border:1px solid {color};'
            f"border-radius:8px; background:{color}; padding:2px 6px;"
        )
        self.label.setText("  NSH 已连接" if online else "  NSH 未连接")

    # ---- 串口 ----
    def serial_toggle(self):
        if self.pushButton_serial.text() == "打开串口":
            port = self.comboBox_serial.currentText().strip()
            if not port:
                self.update_textbrowser("错误：请选择串口")
                return
            self.ctl.open(port, 115200)
            self.pushButton_serial.setText("关闭串口")
            self.comboBox_serial.setEnabled(False)
        else:
            self.ctl.close()
            self.pushButton_serial.setText("打开串口")
            self.comboBox_serial.setEnabled(True)
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
        self.update_textbrowser(f"$ {command}")
        self.ctl.send(command, timeout_s=timeout_s)

    def _on_nsh_connected(self, port: str):
        self.update_textbrowser(f"已连接 {port} @ 115200（NSH）")
        self._set_online_chips(True)
        self.send_nsh("?", kind="raw")
        self.send_nsh(protocol.cmd_point_list(False), kind="list", timeout_s=15)

    def _on_nsh_disconnected(self):
        self.update_textbrowser("串口已断开")
        self._set_online_chips(False)

    def _on_nsh_done(self, command: str, response: str) -> None:
        self.update_textbrowser(response)
        try:
            self._dispatch(command, response)
        except Exception as exc:
            self.update_textbrowser(f"[parse] {exc}")
        self._pending_cmd = ""
        self._pending_kind = ""

    def _on_nsh_failed(self, command: str, error: str) -> None:
        self.update_textbrowser(f"! {command}: {error}")
        if command == "<connect>":
            self.pushButton_serial.setText("打开串口")
            self.comboBox_serial.setEnabled(True)
            self._set_online_chips(False)
        self._pending_cmd = ""
        self._pending_kind = ""

    def _dispatch(self, command: str, response: str) -> None:
        if command.startswith("vgpoint"):
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
                if not st.ok and st.code == "need_confirm":
                    self.update_textbrowser("[host] apply 必须带 --confirm，已用确认对话框流程")

    # ---- 点位操作 ----
    def open_add_source_dialog(self):
        if not self._require_online():
            return
        dialog = QtWidgets.QDialog(self)
        ui = Ui_Dialog()
        ui.setupUi(dialog)
        ui.buttonBox.accepted.connect(dialog.accept)
        ui.buttonBox.rejected.connect(dialog.reject)
        # 对话框标签微调
        ui.lineEdit_source_name.setPlaceholderText("tag: temp / flood_1")
        ui.lineEdit_formula.setPlaceholderText("scale 如 0.1 或 1")
        ui.lineEdit_unit.setPlaceholderText("C / 空")

        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            self.update_textbrowser("取消新增点位。")
            return

        try:
            tag = sanitize_tag(ui.lineEdit_source_name.text(), fallback="p1")
            # 从机地址：支持 0x 十进制
            slave_txt = ui.lineEdit_slave_addr.text().strip() or "1"
            slave_addr = int(slave_txt, 16) if slave_txt.lower().startswith("0x") else int(slave_txt)
            func_code = int(ui.comboBox_function_code.currentText()[:2], 16)
            if func_code not in (3, 4):
                func_code = 3
            start_txt = ui.lineEdit_start_addr.text().strip() or "0"
            start_addr = int(start_txt, 16) if start_txt.lower().startswith("0x") else int(start_txt, 16)
            data_length = int(ui.lineEdit_data_length.text() or "1")
            formula = ui.lineEdit_formula.text().strip() or "1"
            try:
                scale = float(formula) if "/" not in formula else 1.0 / float(formula.split("/")[-1])
            except ValueError:
                scale = 1.0
            unit = ui.lineEdit_unit.text().strip()[:7]
            dtype = "uint16" if ui.comboBox_data_type.currentIndex() == 0 else "int16"
            # 对话框无阈值字段：先 add 基础点，阈值可用控制台 vgpoint set
            cmd = protocol.cmd_point_add(
                tag=tag,
                addr=slave_addr,
                reg=start_addr,
                fc=func_code,
                qty=max(1, min(4, data_length)),
                dtype=dtype,
                scale=scale,
                unit=unit,
            )
        except (ValueError, protocol.ProtocolError) as exc:
            QMessageBox.warning(self, "参数无效", str(exc))
            return

        src = source_set(
            name=ui.lineEdit_source_name.text() or tag,
            id=ui.lineEdit_source_id.text() or tag,
            slave_addr=slave_addr,
            function_code=func_code,
            start_addr=start_addr,
            data_len=data_length,
            data_type=ui.comboBox_data_type.currentIndex(),
            formula=formula,
            unit=unit,
            dir=1,
            tag=tag,
        )
        self.all_sources.append(src)
        self.send_nsh(cmd, kind="add", timeout_s=15)

    def overview_update(self):
        for i, source in enumerate(self.all_sources):
            if source.card_widget is None:
                source.card_widget = source_card(source.name or source.tag, True)
                self.frame_source_overview.layout().addWidget(
                    source.card_widget, int(i / 4), i % 4
                )
                if source.last_value:
                    source.card_widget.set_value_text(source.last_value)

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

    def _sync_cards_from_points(self, points: list[Point], candidate: bool) -> None:
        label = "候选" if candidate else "已确认"
        self.update_textbrowser(f"[parse] {label}点数={len(points)}")
        # 为板端点补齐卡片（不覆盖已有）
        known = {s.tag for s in self.all_sources}
        for p in points:
            if p.tag in known:
                continue
            self.all_sources.append(
                source_set(
                    name=p.tag,
                    id=p.tag,
                    slave_addr=p.addr,
                    function_code=p.fc,
                    start_addr=p.reg,
                    data_len=p.qty,
                    data_type=0,
                    formula=str(p.scale),
                    unit=p.unit,
                    dir=1,
                    tag=p.tag,
                )
            )

    def _apply_reads(self, reads) -> None:
        by_tag = {r.tag: r for r in reads}
        for src in self.all_sources:
            r = by_tag.get(src.tag or src.name)
            if r is None or src.card_widget is None:
                continue
            if not r.ok or r.value is None:
                src.last_value = "FAIL"
                src.card_widget.set_value_text("FAIL")
            else:
                unit = f" {src.unit}" if src.unit else ""
                src.last_value = f"{r.value:g}{unit}"
                src.card_widget.set_value_text(src.last_value)
        ok_n = sum(1 for r in reads if r.ok)
        self.update_textbrowser(f"[parse] READ ok={ok_n}/{len(reads)}")

    def update_textbrowser(self, text):
        self.textBrowser.append(text if text.endswith("\n") else text.rstrip("\n"))

    def closeEvent(self, event):  # noqa: N802
        try:
            self.ctl.shutdown()
        except Exception:
            pass
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    win = mainUI()
    win.show()
    sys.exit(app.exec_())
