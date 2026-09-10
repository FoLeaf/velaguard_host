"""Blocking NSH serial session (no Qt). Safe to use from a worker thread."""

from __future__ import annotations

import re
import time
from typing import Optional

import serial
import serial.tools.list_ports

from .protocol import PROMPT_RE


class NshError(Exception):
    pass


class NshSession:
    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        read_timeout: float = 0.05,
    ) -> None:
        self.port_name = port
        self.baudrate = baudrate
        self._ser: Optional[serial.Serial] = None
        self._read_timeout = read_timeout
        self._rx = ""

    @property
    def is_open(self) -> bool:
        return bool(self._ser and self._ser.is_open)

    @staticmethod
    def list_ports() -> list[str]:
        return [p.device for p in serial.tools.list_ports.comports()]

    def open(self) -> None:
        if self.is_open:
            return
        try:
            self._ser = serial.Serial(
                port=self.port_name,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self._read_timeout,
                write_timeout=2.0,
                dsrdtr=False,
                rtscts=False,
            )
        except serial.SerialException as exc:
            self._ser = None
            raise NshError(f"无法打开串口 {self.port_name}: {exc}") from exc
        # Avoid auto-reset on ST-LINK / STM32 CDC.
        try:
            self._ser.dtr = False
            self._ser.rts = False
        except (serial.SerialException, OSError):
            pass
        self._rx = ""

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except serial.SerialException:
                pass
        self._ser = None
        self._rx = ""

    def drain(self, settle_s: float = 0.05) -> str:
        if not self.is_open or self._ser is None:
            return ""
        end = time.time() + settle_s
        chunks: list[str] = []
        while time.time() < end:
            data = self._ser.read(4096)
            if data:
                chunks.append(data.decode("utf-8", errors="replace"))
            else:
                time.sleep(0.01)
        self._rx += "".join(chunks)
        return "".join(chunks)

    def send_command(
        self,
        command: str,
        timeout_s: float = 20.0,
        settle_ms: int = 800,
    ) -> str:
        """Write one NSH line and wait until prompt returns."""
        if not self.is_open or self._ser is None:
            raise NshError("串口未打开")
        cmd = command.rstrip("\r\n")
        self._rx = ""
        self._ser.reset_input_buffer()
        payload = (cmd + "\n").encode("ascii", errors="ignore")
        try:
            self._ser.write(payload)
            self._ser.flush()
        except serial.SerialException as exc:
            raise NshError(f"写串口失败: {exc}") from exc

        time.sleep(settle_ms / 1000.0)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                data = self._ser.read(4096)
            except serial.SerialException as exc:
                raise NshError(f"读串口失败: {exc}") from exc
            if data:
                self._rx += data.decode("utf-8", errors="replace")
                if PROMPT_RE.search(self._rx):
                    return self._rx
            else:
                time.sleep(0.02)
        # Timeout: return whatever we got; caller decides.
        return self._rx

    def wait_boot_prompt(self, timeout_s: float = 25.0) -> str:
        if not self.is_open or self._ser is None:
            raise NshError("串口未打开")
        deadline = time.time() + timeout_s
        self._rx = ""
        while time.time() < deadline:
            try:
                data = self._ser.read(4096)
            except serial.SerialException as exc:
                raise NshError(f"读串口失败: {exc}") from exc
            if data:
                self._rx += data.decode("utf-8", errors="replace")
                if re.search(r"(nsh>|vela>|AI Agent ready)", self._rx):
                    return self._rx
            else:
                time.sleep(0.05)
        return self._rx
