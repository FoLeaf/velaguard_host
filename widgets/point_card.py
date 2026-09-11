"""Value-first point card — keeps sensor.png, matches board home tiles."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout

import sourcecard_src_rc  # noqa: F401


def _polish(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class PointCard(QFrame):
    delete_requested = pyqtSignal(str)

    def __init__(self, tag: str, unit: str = "", candidate: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("PointCard")
        self.setProperty("status", "idle")
        self.tag = tag
        self.unit = unit or ""
        self.candidate = candidate
        self.pending_delete = False
        self.last_ok: Optional[bool] = None

        self.setMinimumSize(200, 128)
        self.setMaximumWidth(280)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(6)

        top = QHBoxLayout()
        top.setSpacing(8)
        icon = QLabel()
        pix = QPixmap(":/新前缀/sensor.png")
        if not pix.isNull():
            icon.setPixmap(pix.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon.setFixedSize(22, 22)
        self.tag_label = QLabel(tag)
        self.tag_label.setObjectName("CardTag")
        self.badge = QLabel("候选" if candidate else "")
        self.badge.setObjectName("CardBadge")
        self.badge.setVisible(candidate)
        self.btn_del = QPushButton("×")
        self.btn_del.setObjectName("CardDelete")
        self.btn_del.setFixedSize(22, 22)
        self.btn_del.setCursor(Qt.PointingHandCursor)
        self.btn_del.setToolTip("从候选表删除，落盘后才从已确认表去掉")
        self.btn_del.clicked.connect(lambda: self.delete_requested.emit(self.tag))
        top.addWidget(icon)
        top.addWidget(self.tag_label, 1)
        top.addWidget(self.badge)
        top.addWidget(self.btn_del)
        root.addLayout(top)

        self.value_label = QLabel("--")
        self.value_label.setObjectName("CardValue")
        self.value_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(self.value_label)

        self.unit_label = QLabel(self.unit)
        self.unit_label.setObjectName("CardUnit")
        root.addWidget(self.unit_label)
        root.addStretch(1)

    def set_meta(self, tag: str, unit: str, candidate: bool) -> None:
        self.tag = tag
        self.unit = unit or ""
        self.tag_label.setText(tag)
        self.unit_label.setText(self.unit)
        self.set_candidate(candidate)

    def set_candidate(self, candidate: bool) -> None:
        self.candidate = candidate
        if self.pending_delete:
            return
        self.badge.setText("候选" if candidate else "")
        self.badge.setVisible(bool(candidate))

    def set_pending_delete(self, pending: bool) -> None:
        self.pending_delete = pending
        if pending:
            self.badge.setText("待删除")
            self.badge.setVisible(True)
            self.setProperty("status", "pending")
            self.value_label.setStyleSheet("color: #6C757D;")
        else:
            status = "idle" if self.last_ok is None else ("ok" if self.last_ok else "fail")
            self.setProperty("status", status)
            self.set_candidate(self.candidate)
            if self.last_ok is False:
                self.value_label.setStyleSheet("color: #E03131;")
            else:
                self.value_label.setStyleSheet("")
        _polish(self)

    def set_value_text(self, text: str, ok: Optional[bool] = None) -> None:
        self.value_label.setText(text if text else "--")
        if self.pending_delete:
            self.last_ok = False if (ok is False or (text or "").upper() == "FAIL") else ok
            self.value_label.setStyleSheet("color: #6C757D;")
            return
        if ok is False or (text or "").upper() == "FAIL":
            self.last_ok = False
            self.setProperty("status", "fail")
            self.value_label.setStyleSheet("color: #E03131;")
        elif ok is True:
            self.last_ok = True
            self.setProperty("status", "ok")
            self.value_label.setStyleSheet("")
        else:
            self.last_ok = None
            self.setProperty("status", "idle")
            self.value_label.setStyleSheet("")
        _polish(self)
