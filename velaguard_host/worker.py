"""Qt worker + controller for NSH serial (thread-safe via queued signals)."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

from .nsh_session import NshError, NshSession


class SerialWorker(QObject):
    log = pyqtSignal(str)
    connected = pyqtSignal(str)
    disconnected = pyqtSignal()
    command_done = pyqtSignal(str, str)
    command_failed = pyqtSignal(str, str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._session: Optional[NshSession] = None

    def _close_session(self) -> None:
        if self._session:
            try:
                self._session.close()
            except Exception:
                pass
        self._session = None

    @pyqtSlot(str, int)
    def open_port(self, port: str, baud: int) -> None:
        self._close_session()
        try:
            session = NshSession(port, baud)
            session.open()
            boot = session.wait_boot_prompt(timeout_s=8.0)
            if boot:
                self.log.emit(boot)
            self._session = session
            self.connected.emit(port)
            self.log.emit(f"[host] connected {port} @ {baud}\n")
        except NshError as exc:
            self._session = None
            self.command_failed.emit("<connect>", str(exc))

    @pyqtSlot()
    def close_port(self) -> None:
        self._close_session()
        self.disconnected.emit()
        self.log.emit("[host] disconnected\n")

    @pyqtSlot(str, float)
    def run_command(self, command: str, timeout_s: float) -> None:
        if not self._session or not self._session.is_open:
            self.command_failed.emit(command, "串口未打开")
            return
        try:
            response = self._session.send_command(command, timeout_s=timeout_s)
        except NshError as exc:
            self.command_failed.emit(command, str(exc))
            return
        if not response:
            self.command_failed.emit(command, f"超时无响应（>{timeout_s}s）")
            return
        self.command_done.emit(command, response)


class SerialController(QObject):
    log = pyqtSignal(str)
    connected = pyqtSignal(str)
    disconnected = pyqtSignal()
    command_done = pyqtSignal(str, str)
    command_failed = pyqtSignal(str, str)
    _open_req = pyqtSignal(str, int)
    _close_req = pyqtSignal()
    _cmd_req = pyqtSignal(str, float)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._worker = SerialWorker()
        self._worker.moveToThread(self._thread)
        self._thread.start()

        self._open_req.connect(self._worker.open_port)
        self._close_req.connect(self._worker.close_port)
        self._cmd_req.connect(self._worker.run_command)

        self._worker.log.connect(self.log)
        self._worker.connected.connect(self.connected)
        self._worker.disconnected.connect(self.disconnected)
        self._worker.command_done.connect(self.command_done)
        self._worker.command_failed.connect(self.command_failed)

    def open(self, port: str, baud: int = 115200) -> None:
        self._open_req.emit(port, int(baud))

    def close(self) -> None:
        self._close_req.emit()

    def send(self, command: str, timeout_s: float = 20.0) -> None:
        self._cmd_req.emit(command, float(timeout_s))

    def shutdown(self) -> None:
        self._close_req.emit()
        self._thread.quit()
        self._thread.wait(2000)
