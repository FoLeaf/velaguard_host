"""VelaGuard Host — 基于原工程 UI（Designer + 图片资源）的 NSH 上位机入口。

保留 window.py / config.py / sourcecard_ui.py / res_rc.py 与 PNG 图标，
仅将主机通信改为 ST-LINK COM3 上的 openvela NSH 文本协议。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Optional

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication, QCheckBox, QGridLayout, QLabel, QVBoxLayout, QWidget

from window import *  # noqa: F401,F403 — Ui_Form + res_rc 图标资源
from config import *  # noqa: F401,F403 — Ui_Dialog 添加数据源对话框
from sourcecard_ui import *  # noqa: F401,F403 — Ui_sourcecard_ui 传感器卡片

from velaguard_host import protocol
from velaguard_host.worker import SerialController


@dataclass
class source_set:
    """实时数据页上的一个监视点（与原工程字段兼容）。"""

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


class source_card(QWidget, Ui_sourcecard_ui):
    def __init__(self, name, dir):
        super().__init__()
        self.setupUi(self)
        self.viewer_layout = QVBoxLayout()
        self.frame_source_viewer.setLayout(self.viewer_layout)
        self.dir = dir
        self.name = name
        self.source_card_init()

    def source_card_init(self):
        if self.dir:
            self.label_source_value = QLabel("N/A")
            self.label_source_value.setStyleSheet("""font: 12pt "小米兰亭";""")
            self.label_source_value.setAlignment(Qt.AlignCenter)
            self.frame_source_viewer.layout().addWidget(self.label_source_value)
        else:
            self.checkbox_source_controller = QCheckBox("关闭")
            self.checkbox_source_controller.setStyleSheet("""font: 12pt "小米兰亭";""")
            self.frame_source_viewer.layout().addWidget(self.checkbox_source_controller)
        self.label_source_name.setText(self.name)

    def set_value_text(self, text: str) -> None:
        if hasattr(self, "label_source_value"):
            self.label_source_value.setText(text)


class mainUI(QWidget, Ui_Form):
    all_sources = []

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
        self._poll_index = 0
        self.mainUI_custom()

    def mainUI_custom(self):
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # 原侧栏：控制台 / 实时数据 / 参数设置
        self.pushButton_console.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.pushButton_realtimedata.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        self.pushButton_configuration.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.pushButton_serial.clicked.connect(self.serial_toggle)
        self.pushButton_addsource.clicked.connect(self.open_add_source_dialog)
        self.pushButton_getsource.clicked.connect(self.toggle_poll_sources)

        self.textBrowser.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        self.serial_port_list_init()

        self.overview_layout = QGridLayout()
        self.frame_source_overview.setLayout(self.overview_layout)
        self.start_overview_update()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_one_source)
        self.poll_timer.setInterval(1500)
        self._polling = False

        self.update_textbrowser("[host] VelaGuard NSH 模式：COM3 文本协议，非 EB90 帧")
        self.update_textbrowser("[host] 确认落盘请在控制台手动执行 vgdiscover apply --confirm")

    # ---- 串口 / NSH ----
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
            self.poll_timer.stop()
            self._polling = False
            self.pushButton_getsource.setText("获取数据流")
            self.ctl.close()
            self.pushButton_serial.setText("打开串口")
            self.comboBox_serial.setEnabled(True)

    def serial_port_list_init(self):
        self.comboBox_serial.clear()
        from velaguard_host.nsh_session import NshSession

        for port in NshSession.list_ports():
            self.comboBox_serial.addItem(port)
        # 默认优先 ST-LINK 常见口
        for i in range(self.comboBox_serial.count()):
            if self.comboBox_serial.itemText(i).upper().startswith("COM3"):
                self.comboBox_serial.setCurrentIndex(i)
                break

    def _on_nsh_connected(self, port: str):
        self.update_textbrowser(f"已连接 {port} @ 115200（NSH）")
        self.send_nsh("?")

    def _on_nsh_disconnected(self):
        self.update_textbrowser("串口已断开")

    def send_nsh(self, command: str, timeout_s: float = 20.0) -> None:
        self._pending_cmd = command
        self.update_textbrowser(f"$ {command}")
        self.ctl.send(command, timeout_s=timeout_s)

    def _on_nsh_done(self, command: str, response: str) -> None:
        self.update_textbrowser(response)
        try:
            self._dispatch_nsh(command, response)
        except Exception as exc:  # 解析失败不影响日志
            self.update_textbrowser(f"[parse] {exc}")
        self._pending_cmd = ""

    def _on_nsh_failed(self, command: str, error: str) -> None:
        self.update_textbrowser(f"! {command}: {error}")
        if command == "<connect>":
            self.pushButton_serial.setText("打开串口")
            self.comboBox_serial.setEnabled(True)
        self._pending_cmd = ""

    def _dispatch_nsh(self, command: str, response: str) -> None:
        if command.startswith("vgdiscover test-read") or command.startswith("vgmodbus"):
            parsed = protocol.parse_test_read(response) or protocol.parse_vgmodbus_regs(response)
            if parsed and parsed.samples:
                text = " ".join(f"{s.reg}:{s.raw}" for s in parsed.samples)
                for src in self.all_sources:
                    if src.slave_addr != parsed.addr or src.card_widget is None:
                        continue
                    first = parsed.samples[0]
                    scale = 1.0
                    formula = str(src.formula or "")
                    if "/" in formula:
                        try:
                            denom = float(formula.split("/")[-1])
                            scale = 1.0 / denom if denom else 1.0
                        except ValueError:
                            scale = 1.0
                    else:
                        try:
                            scale = float(formula) if formula else 1.0
                        except ValueError:
                            scale = 1.0
                    unit = f" {src.unit}" if src.unit else ""
                    src.last_value = f"{first.raw * scale:g}{unit}"
                    src.card_widget.set_value_text(src.last_value)
                self.update_textbrowser(f"[parse] {text}")
        elif command.startswith("vgdiscover scan"):
            hits = protocol.parse_scan(response)
            self.update_textbrowser("[parse] slaves=" + ",".join(str(h.addr) for h in hits))
        elif command.startswith("vgdiscover apply"):
            info = protocol.parse_apply(response)
            self.update_textbrowser(f"[parse] apply {info}")
        elif command.startswith("cat "):
            table = protocol.parse_point_table_json(response)
            if table:
                self._sync_points_to_cards(table)

    # ---- 数据源 / 卡片 ----
    def open_add_source_dialog(self):
        dialog = QtWidgets.QDialog(self)
        ui = Ui_Dialog()
        ui.setupUi(dialog)
        ui.buttonBox.accepted.connect(dialog.accept)
        ui.buttonBox.rejected.connect(dialog.reject)

        result = dialog.exec_()
        if result == QtWidgets.QDialog.Accepted:
            name = ui.lineEdit_source_name.text()
            id_ = ui.lineEdit_source_id.text()
            try:
                slave_addr = int(ui.lineEdit_slave_addr.text() or "1", 16)
            except ValueError:
                slave_addr = int(ui.lineEdit_slave_addr.text() or "1")
            func_code = int(ui.comboBox_function_code.currentText()[:2], 16)
            try:
                start_addr = int(ui.lineEdit_start_addr.text() or "0", 16)
            except ValueError:
                start_addr = int(ui.lineEdit_start_addr.text() or "0")
            data_length = int(ui.lineEdit_data_length.text() or "1")
            data_type = int(ui.comboBox_data_type.currentIndex())
            formula = ui.lineEdit_formula.text()
            unit = ui.lineEdit_unit.text()
            dir_ = 0 if ui.radioButton_io.isChecked() else 1
            self.create_new_source(
                name, id_, slave_addr, func_code, start_addr, data_length, data_type, formula, dir_, unit
            )
            self.update_textbrowser(
                f"新增数据源(本地监视点): 从机={slave_addr} 功能码={func_code} 起始={start_addr} 数量={data_length}"
            )
            self.update_textbrowser(
                "[host] 仅创建上位机监视卡片；板端点表请用 vgdiscover/apply --confirm，不在此写盘"
            )
        else:
            self.update_textbrowser("取消新增数据源。")

    def overview_update(self):
        for i, source in enumerate(self.all_sources):
            if source.card_widget is None:
                source.card_widget = source_card(source.name, source.dir)
                self.frame_source_overview.layout().addWidget(source.card_widget, int(i / 4), i % 4)
                if source.last_value:
                    source.card_widget.set_value_text(source.last_value)

    def start_overview_update(self):
        self.overview_update_timer = QTimer()
        self.overview_update_timer.timeout.connect(self.overview_update)
        self.overview_update_timer.start(1000)

    def create_new_source(
        self, name, id, slave_addr, func_code, start_addr, data_length, data_type, formula, dir, unit
    ):
        source = source_set(
            name=name or id or f"S{slave_addr}",
            id=id,
            slave_addr=slave_addr,
            function_code=func_code,
            start_addr=start_addr,
            data_len=data_length,
            data_type=data_type,
            formula=formula,
            dir=dir,
            unit=unit,
        )
        self.all_sources.append(source)
        # 不发送 EB90 帧；连接后由「获取数据流」轮询 test-read

    def toggle_poll_sources(self):
        if not self.all_sources:
            self.update_textbrowser("请先新增数据源")
            return
        if self._polling:
            self.poll_timer.stop()
            self._polling = False
            self.pushButton_getsource.setText("获取数据流")
            self.update_textbrowser("停止数据流")
            return
        if self.pushButton_serial.text() != "关闭串口":
            self.update_textbrowser("请先打开串口")
            return
        self._polling = True
        self.pushButton_getsource.setText("停止数据流")
        self.poll_timer.start()
        self.update_textbrowser("开始数据流（周期 test-read）")

    def poll_one_source(self):
        if not self.all_sources or self._pending_cmd:
            return
        src = self.all_sources[self._poll_index % len(self.all_sources)]
        self._poll_index += 1
        qty = max(1, min(16, int(src.data_len or 1)))
        try:
            cmd = protocol.cmd_test_read(src.slave_addr, src.start_addr, qty)
        except ValueError as exc:
            self.update_textbrowser(f"[poll] {exc}")
            return
        self.send_nsh(cmd, timeout_s=8)

    def _sync_points_to_cards(self, table) -> None:
        self.update_textbrowser(f"[parse] points={len(table.points)} baud={table.baud}")
        # 若板端点表与本地卡片不同，仅提示，不自动清空用户卡片
        tags = [p.tag for p in table.points]
        if tags:
            self.update_textbrowser("[parse] tags=" + ",".join(tags[:12]))

    # ---- 控制台日志 ----
    def update_textbrowser(self, text):
        self.textBrowser.append(text if text.endswith("\n") else text.rstrip("\n"))

    def closeEvent(self, event):  # noqa: N802
        try:
            self.poll_timer.stop()
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
