import sys, json
import time

from PyQt5.QtWidgets import QWidget, QApplication, QLabel, QCheckBox, QGridLayout, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer, QThread, QObject, pyqtSignal
from window import *
from config import *
import serial
import serial.tools.list_ports
from sourcecard_ui import *
from dataclasses import dataclass

from crc import Calculator, Configuration

CRC32_POLY = 0x04C11DB7
# Standard initial value
CRC32_INIT = 0xFFFFFFFF

# 创建一个自定义的 CRC 配置
# This configuration matches the default settings of MX_CRC_Init()
stm32_config = Configuration(
    width=32,
    polynomial=CRC32_POLY,
    init_value=CRC32_INIT,
    final_xor_value=0x00000000,  # Corresponds to final XOR with 0
    reverse_input=False,  # Corresponds to CRC_INPUTDATA_INVERSION_NONE (RefIn=False)
    reverse_output=False,  # Corresponds to CRC_OUTPUTDATA_INVERSION_DISABLE (RefOut=False)
)

# 使用上面的配置创建一个计算器实例
stm32_crc_calculator = Calculator(stm32_config)
FRAME_HEADER = b'\xeb\x90'  # b'' 前缀表示这是一个 bytes 对象
FRAME_TAIL = b'\xed'


def calculate_stm32_crc_accurate(data: bytes) -> int:
    """
    精确模拟STM32硬件CRC计算单元的行为。
    1. 数据按4字节对齐（不足补0）
    2. 每个4字节块内的字节顺序反转（模拟小端硬件处理）
    3. 使用指定的CRC32参数进行计算
    """
    # 1. 确保数据长度是4的倍数，不足则用0补齐
    original_len = len(data)
    padding_len = (4 - (original_len % 4)) % 4
    padded_data = data + b'\x00' * padding_len

    # 2. 模拟小端模式下，硬件对字节流的32位字解析：反转每个4字节块内的字节顺序
    swapped_data = bytearray()
    for i in range(0, len(padded_data), 4):
        chunk = padded_data[i:i + 4]
        swapped_chunk = chunk[::-1]
        swapped_data.extend(swapped_chunk)

    # 3. 使用我们精确配置的计算器来计算 CRC
    crc_result = stm32_crc_calculator.checksum(swapped_data)

    return crc_result


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
    card_widget: any = None


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
        if (self.dir):
            self.label_source_value = QLabel("N/A")
            self.label_source_value.setStyleSheet("""font: 12pt "小米兰亭";""")
            self.label_source_value.setAlignment(Qt.AlignCenter)
            self.frame_source_viewer.layout().addWidget(self.label_source_value)
        else:
            self.checkbox_source_controller = QCheckBox("关闭")
            self.checkbox_source_controller.setStyleSheet("""font: 12pt "小米兰亭";""")
            self.frame_source_viewer.layout().addWidget(self.checkbox_source_controller)
        self.label_source_name.setText(self.name)


class serialWorker(QObject):
    print_signal = pyqtSignal(str)
    decode_signal = pyqtSignal(str)

    def __init__(self, port, baudrate, rts, dtr):
        super().__init__()
        # 使用inter_byte_timeout参数实现空闲中断
        self.ser = serial.Serial(port, baudrate, dsrdtr=dtr, rtscts=rts, timeout=None, inter_byte_timeout=0.003)
        # 一个全局变量，使其他进程可以操作串口接收启停
        self.isLoop = True

    def run(self):
        if not self.ser.is_open:
            return

        while self.isLoop:
            try:
                # 设置了inter_byte_timout，当有空闲时会提前返回
                data = self.ser.read(4096)
                if data:
                    try:
                        self.print_signal.emit(data.decode('utf-8'))
                    except UnicodeDecodeError:
                        # 解码错误，输出原始字节流
                        self.print_signal.emit(repr(data))

            except serial.SerialException:
                # 串口读取失败等等，停止串口读取
                print('serial read ending..')
                self.isLoop = False

    def stop(self):
        self.isLoop = False
        if self.ser and self.ser.is_open:
            self.ser.close()


class mainUI(QWidget, Ui_Form):
    all_sources = []

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.mainUI_custom()
        self.thread = None

    def mainUI_custom(self):
        # --- High DPI Scaling ---
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 信号与槽连接
        self.pushButton_configuration.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(0))
        self.pushButton_realtimedata.clicked.connect(lambda: self.stackedWidget.setCurrentIndex(1))
        self.pushButton_serial.clicked.connect(lambda: self.serial_toggle(self.comboBox_serial.currentText()))
        self.pushButton_addsource.clicked.connect(self.open_add_source_dialog)  # Connect the button
        # 关闭textbrowser的自动换行
        self.textBrowser.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        # 初始化列出当前电脑可用端口
        self.serial_port_list_init()

        #   overview界面
        self.overview_layout = QGridLayout()
        self.frame_source_overview.setLayout(self.overview_layout)
        self.start_overview_update()

    def open_add_source_dialog(self):
        # 创建一个对话框
        dialog = QtWidgets.QDialog(self)
        # 调用设计师的类
        ui = Ui_Dialog()
        # 绘制UI到刚刚创建的对话框类
        ui.setupUi(dialog)
        # 连接OK，cancel的信号到对应的槽
        ui.buttonBox.accepted.connect(dialog.accept)
        ui.buttonBox.rejected.connect(dialog.reject)

        # 接收对话框退出时返回的事件
        result = dialog.exec_()
        # 判断是应用还是取消
        if result == QtWidgets.QDialog.Accepted:
            # 返回文本框中内容
            name = ui.lineEdit_source_name.text()
            id = ui.lineEdit_source_id.text()
            slave_addr = int(ui.lineEdit_slave_addr.text(), 16)
            func_code = int(ui.comboBox_function_code.currentText()[:2])
            start_addr = int(ui.lineEdit_start_addr.text(), 16)
            data_length = int(ui.lineEdit_data_length.text())
            data_type = int(ui.comboBox_data_type.currentIndex())
            formula = ui.lineEdit_formula.text()
            unit = ui.lineEdit_unit.text()
            if (ui.radioButton_io.isChecked()):
                dir = 0
            else:
                dir = 1
            self.create_new_source(name, id, slave_addr, func_code, start_addr, data_length, data_type, formula, dir,
                                   unit)
            self.textBrowser.append(f"新增数据源: 从机地址={slave_addr}, 功能码={func_code},起始地址{start_addr}")
        else:
            self.textBrowser.append("取消新增数据源。")

    def overview_update(self):
        for i, source in enumerate(self.all_sources):
            if source.card_widget is None:
                source.card_widget = source_card(source.name, source.dir)
                self.frame_source_overview.layout().addWidget(source.card_widget, int(i / 4), i % 4)

    def start_overview_update(self):
        self.overview_update_timer = QTimer()
        self.overview_update_timer.timeout.connect(self.overview_update)
        self.overview_update_timer.start(1000)

    def serial_toggle(self, port):
        # 判断当前线程是否存在
        if self.thread == None or not self.thread.isRunning():
            try:
                self.thread = QThread()
                self.serial_worker = serialWorker(port, 115200, False, False)

                self.serial_worker.moveToThread(self.thread)
                self.thread.started.connect(self.serial_worker.run)
                self.serial_worker.print_signal.connect(self.update_textbrowser)
                self.serial_worker.decode_signal.connect(self.decode_task)
                self.thread.finished.connect(self.thread.deleteLater)
                self.thread.finished.connect(self.serial_worker.deleteLater)

                self.thread.start()
            except serial.SerialException as e:
                self.textBrowser.append(f"错误：无法打开串口{port}:{e}")
            self.pushButton_serial.setText("关闭串口")
            self.comboBox_serial.setEnabled(False)
        else:
            if self.serial_worker:
                self.serial_worker.stop()
            if self.thread:
                self.thread.quit()
                self.thread.wait()
            self.serial_worker = None
            self.thread = None

            self.pushButton_serial.setText('打开串口')
            self.comboBox_serial.setEnabled(True)

    def serial_port_list_init(self):
        self.comboBox_serial.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.comboBox_serial.addItem(port.device)

    def decode_task(self):
        pass

    def update_textbrowser(self, text):
        self.textBrowser.append(text)
        # cursor = self.textBrowser.textCursor()
        # cursor.movePosition(QtGui.QTextCursor.End)
        # cursor.insertText(text)
        # self.textBrowser.ensureCursorVisible()

    def create_new_source(self, name, id, slave_addr, func_code, start_addr, data_length, data_type, formula, dir,
                          unit):
        source = source_set(name=name, id=id, slave_addr=slave_addr, function_code=func_code, start_addr=start_addr,
                            data_len=data_length, data_type=data_type, formula=formula, dir=dir, unit=unit)
        self.all_sources.append(source)
        self.serial_worker.ser.write(self.construct_frame_addsensor(source))

    def construct_frame_addsensor(self, source: source_set):
        """
        构建添加传感器的JSON命令帧

        Args:
            source: source_set数据类实例，包含传感器的所有配置信息

        Returns:
            dict: 包含传感器配置信息的JSON结构
        """
        command_json = {
            "command": "ADD_SENSOR",
            "payload": {
                "id": source.id,
                "name": source.name,
                "slave_addr": source.slave_addr,
                "start_addr": source.start_addr,
                "func_code": source.function_code,
                "data_len": source.data_len,
                "data_type": source.data_type,
                "formula": source.formula,
                "unit": source.unit,
                "dir": source.dir,
                "is_enabled": source.is_enabled,
            }
        }
        text = json.dumps(command_json)
        frame = self.frame_completion(text)
        return frame

    def frame_completion(self, payload):
        payload_len = len(payload)
        payload_len_bytes = payload_len.to_bytes(2, 'little')
        payload_bytes = payload.encode('utf-8')
        payload_crc = calculate_stm32_crc_accurate(payload_bytes)
        payload_crc_bytes = payload_crc.to_bytes(4, "little")

        frame = (
                FRAME_HEADER +
                payload_len_bytes +
                payload_bytes +
                payload_crc_bytes +
                FRAME_TAIL
        )

        return frame


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    win = mainUI()
    win.show()
    sys.exit(app.exec_())
