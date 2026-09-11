"""Value-first point card — keeps sensor.png, matches board home tiles."""

from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

import sourcecard_src_rc  # noqa: F401


def _polish(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class PointCard(QFrame):
    delete_requested = pyqtSignal(str)
    edit_requested = pyqtSignal(str)

    def __init__(
        self,
        tag: str,
        unit: str = "",
        candidate: bool = False,
        name: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("PointCard")
        self.setProperty("status", "idle")
        self.tag = tag
        self.name = name or tag
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
        self.check = QCheckBox()
        self.check.setObjectName("CardSelect")
        self.check.setCursor(Qt.PointingHandCursor)
        self.check.setToolTip("勾选后可批量删除")
        icon = QLabel()
        pix = QPixmap(":/新前缀/sensor.png")
        if not pix.isNull():
            icon.setPixmap(pix.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        icon.setFixedSize(22, 22)
        self.tag_label = QLabel(self.name)
        self.tag_label.setObjectName("CardTag")
        self.tag_label.setToolTip(f"id={tag}" if self.name != tag else "")
        self.badge = QLabel("候选" if candidate else "")
        self.badge.setObjectName("CardBadge")
        self.badge.setVisible(candidate)
        self.btn_edit = QPushButton("✎")
        self.btn_edit.setObjectName("CardEdit")
        self.btn_edit.setFixedSize(22, 22)
        self.btn_edit.setCursor(Qt.PointingHandCursor)
        self.btn_edit.setToolTip("编辑点位，写入候选表")
        self.btn_edit.clicked.connect(lambda: self.edit_requested.emit(self.tag))
        self.btn_del = QPushButton("×")
        self.btn_del.setObjectName("CardDelete")
        self.btn_del.setFixedSize(22, 22)
        self.btn_del.setCursor(Qt.PointingHandCursor)
        self.btn_del.setToolTip("从候选表删除，落盘后才从已确认表去掉")
        self.btn_del.clicked.connect(lambda: self.delete_requested.emit(self.tag))
        top.addWidget(self.check)
        top.addWidget(icon)
        top.addWidget(self.tag_label, 1)
        top.addWidget(self.badge)
        top.addWidget(self.btn_edit)
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

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        if not self.pending_delete:
            self.edit_requested.emit(self.tag)
        super().mouseDoubleClickEvent(event)

    def set_meta(self, tag: str, unit: str, candidate: bool, name: str = "") -> None:
        self.tag = tag
        self.name = name or tag
        self.unit = unit or ""
        self.tag_label.setText(self.name)
        self.tag_label.setToolTip(f"id={tag}" if self.name != tag else "")
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
        self.check.setEnabled(not pending)
        if pending:
            self.check.setChecked(False)
        self.btn_edit.setEnabled(not pending)
        _polish(self)

    def is_selected(self) -> bool:
        return self.check.isChecked()

    def set_selected(self, selected: bool) -> None:
        if self.pending_delete:
            self.check.setChecked(False)
            return
        self.check.setChecked(bool(selected))

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
