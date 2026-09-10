import sys
import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject, QPoint

from window import *  # 导入您用Qt Designer创建的UI类
from config import *  # 导入您用Qt Designer创建的UI类

# --- High DPI Scaling ---
# 这两行代码是为了让应用在高分屏上显示正常，属于推荐的标准化设置
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)


# ===================================================================
# 步骤1: 创建一个工作对象(Worker)，负责所有耗时的串口逻辑
# ===================================================================
class SerialWorker(QObject):
    """
    串口工作类
    - 继承自QObject，这样才能使用信号和槽机制。
    - 这个类的实例将被移动到一个独立的QThread线程中运行。
    """
    # pyqtSignal是一个信号定义。当我们需要从这个工作线程发送信息给主UI线程时，就会发射这个信号。
    # 我们定义它发送一个字符串（str）类型的数据。
    data_received = pyqtSignal(str)

    def __init__(self, port, baudrate):
        """
        初始化函数
        :param port: 要打开的串口号，例如 'COM3'
        :param baudrate: 波特率，例如 9600 或 115200
        """
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.serial_port = None  # pyserial的串口对象将保存在这里
        self._is_running = False  # 一个标志，用于控制后台循环是否继续运行

    # run() 是这个Worker的核心，它将在后台线程启动后被调用
    def run(self):
        """
        线程启动后，此函数将开始在一个独立的后台线程中执行。
        """
        self._is_running = True
        try:
            # 1. 创建pyserial的Serial对象，并尝试打开串口
            # timeout=1.0 表示如果1秒内没有读取到任何数据，read操作就会返回，而不是永久阻塞
            self.serial_port = serial.Serial(self.port, self.baudrate, timeout=1.0)

            # --- 关键修复：防止单片机自动复位 ---
            # 很多开发板（如Arduino）会利用RTS或DTR信号来自动复位。
            # 打开串口时，pyserial默认可能会改变这两个信号线的电平，导致单片机意外重启。
            # 我们在这里手动将它们都设置为False（低电平），以阻止这种情况发生。
            self.serial_port.rts = False
            self.serial_port.dtr = False
            # ---------------------------------------------------------

            # 检查串口是否真的成功打开
            if not self.serial_port.is_open:
                self.data_received.emit(f"错误：无法打开串口 {self.port}\n")
                return

            self.data_received.emit(f"成功打开串口 {self.port}\n")

            # 2. 进入主循环，持续监听串口数据
            while self._is_running:
                try:
                    # --- 健壮的数据读取方式 ---
                    # self.serial_port.in_waiting 会返回输入缓冲区中当前有多少字节的数据
                    if self.serial_port.in_waiting > 0:
                        # 读取所有可用的字节
                        data_bytes = self.serial_port.read(self.serial_port.in_waiting)
                        # 将读取到的字节串（bytes）解码成我们能看的字符串（str）。
                        # 使用'utf-8'编码，如果遇到无法解码的字节，则忽略（errors='ignore'）
                        text = data_bytes.decode('utf-8', errors='ignore')
                        # 发射信号，将解码后的字符串发送给主UI线程
                        self.data_received.emit(text)

                    # 短暂休眠50毫秒。这非常重要！
                    # 如果没有这行代码，这个while循环会一直空转，导致一个CPU核心被100%占用。
                    QThread.msleep(50)

                except serial.SerialException:
                    self.data_received.emit("错误：串口读取异常\n")
                    break  # 发生读取错误时，跳出循环

            # 3. 循环结束后，关闭串口
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
                self.data_received.emit(f"串口 {self.port} 已关闭\n")

        except serial.SerialException as e:
            # 如果在尝试打开串口时就发生错误（例如串口不存在或被占用），则会进入这里
            self.data_received.emit(f"错误：{str(e)}\n")

    def stop(self):
        """
        提供一个从外部（主UI线程）停止后台循环的方法。
        """
        self._is_running = False


# ===================================================================
# 步骤2: 修改您的主UI类，集成串口功能
# ===================================================================
class mainUI(QWidget, Ui_Form):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        # 设置无边框窗口和透明背景，这些是您之前的UI设置
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # --- 串口功能相关的成员变量 ---
        self.serial_thread = None  # 将用于管理后台任务的QThread对象
        self.serial_worker = None  # 上面定义的SerialWorker类的实例

        # --- 初始化流程 ---
        self.setup_serial_ui()  # 初始化UI中和串口相关的部分
        self.connect_signals()  # 连接所有按钮的点击事件

    def setup_serial_ui(self):
        """此函数负责初始化和串口相关的UI组件"""
        # 1. 使用pyserial的工具函数 serial.tools.list_ports.comports() 来查找电脑上所有可用的串口
        ports = serial.tools.list_ports.comports()
        self.comboBox_serial.clear()  # 清空下拉列表
        if ports:
            # 如果找到了串口，就将它们的设备名（如'COM3'）添加到下拉列表中
            for port in ports:
                self.comboBox_serial.addItem(port.device)
        else:
            # 如果没找到任何串口，则提示用户
            self.comboBox_serial.addItem("无可用串口")
            self.pushButton_serial.setEnabled(False)  # 并禁用“打开串口”按钮

    def connect_signals(self):
        """此函数集中管理所有信号和槽的连接"""
        # 将“打开串口”按钮的点击（clicked）信号，连接到 self.toggle_serial_port 这个函数上
        self.pushButton_serial.clicked.connect(self.toggle_serial_port)

    def toggle_serial_port(self):
        """这个函数是“打开/关闭串口”按钮的核心逻辑"""
        # 检查线程是否还未创建或已经结束运行
        if self.serial_thread is None or not self.serial_thread.isRunning():
            # --- 如果当前是关闭状态，则执行“打开串口”的逻辑 ---
            selected_port = self.comboBox_serial.currentText()  # 获取用户在下拉列表中选择的串口号
            if selected_port == "无可用串口":
                self.textBrowser.append("错误：没有选择有效的串口。")
                return

            # 1. 创建QThread和SerialWorker的实例
            self.serial_thread = QThread()
            self.serial_worker = SerialWorker(port=selected_port, baudrate=115200)  # 波特率可按需修改

            # 2. 将Worker移动到后台线程。这是QThread的标准用法，非常关键！
            self.serial_worker.moveToThread(self.serial_thread)

            # 3. 连接各种信号和槽
            #   - 当线程启动时(started)，调用worker的run()方法开始执行后台任务
            self.serial_thread.started.connect(self.serial_worker.run)
            #   - 当worker通过emit()发射data_received信号时，调用主UI的update_text_browser()方法来更新界面
            self.serial_worker.data_received.connect(self.update_text_browser)
            #   - 当线程结束时(finished)，自动清理相关的对象
            self.serial_thread.finished.connect(self.serial_thread.deleteLater)
            self.serial_thread.finished.connect(self.serial_worker.deleteLater)

            # 4. 启动线程。这会发射started信号，从而触发worker.run()
            self.serial_thread.start()

            # 5. 更新UI状态
            self.pushButton_serial.setText("关闭串口")
            self.comboBox_serial.setEnabled(False)  # 运行时不允许切换串口
        else:
            # --- 如果当前是打开状态，则执行“关闭串口”的逻辑 ---
            if self.serial_worker:
                self.serial_worker.stop()  # 1. 通知后台循环停止
            if self.serial_thread:
                self.serial_thread.quit()  # 2. 安全地退出线程的事件循环
                self.serial_thread.wait()  # 3. 等待线程完全终止

            # 4. 重置变量，为下次打开做准备
            self.serial_thread = None
            self.serial_worker = None

            # 5. 更新UI状态
            self.pushButton_serial.setText("打开串口")
            self.comboBox_serial.setEnabled(True)

    def update_text_browser(self, text):
        """这是一个槽函数，负责接收后台线程发来的数据并显示在UI上"""
        # self.textBrowser.append() 会自动将文本追加到末尾，并处理换行
        # text.strip() 用于移除字符串前后可能存在的空白字符
        self.textBrowser.append(text.strip())

    def closeEvent(self, event):
        """重写窗口关闭事件，确保在关闭主窗口时，后台线程和串口能被干净地关闭"""
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_worker.stop()
            self.serial_thread.quit()
            self.serial_thread.wait()
        event.accept()  # 确认关闭

    # --- 您之前的无边框窗口拖动代码 ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._tracking = True
            self._start_pos = event.pos()

    def mouseMoveEvent(self, event):
        if hasattr(self, '_tracking') and self._tracking:
            self.move(self.pos() + event.pos() - self._start_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._tracking = False


# ===================================================================
# 步骤3: Python程序的标准入口点
# ===================================================================
if __name__ == '__main__':
    app = QApplication(sys.argv)  # 创建应用实例
    win = mainUI()  # 创建我们主窗口的实例
    win.show()  # 显示窗口
    sys.exit(app.exec_())  # 启动Qt事件循环，并等待程序退出