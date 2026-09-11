"""Add-point dialog: FC 03/04, no password echo, optional thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


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


def parse_int_field(text: str, default: int = 0) -> int:
    raw = (text or "").strip() or str(default)
    if raw.lower().startswith("0x"):
        return int(raw, 16)
    return int(raw, 10)


def parse_scale(text: str) -> float:
    formula = (text or "1").strip() or "1"
    if "/" in formula:
        parts = formula.split("/")
        return 1.0 / float(parts[-1])
    return float(formula)


@dataclass
class AddPointResult:
    tag: str
    name: str
    addr: int
    fc: int
    reg: int
    qty: int
    dtype: str
    scale: float
    formula: str
    unit: str
    cmp: str
    warn: Optional[float]
    crit: Optional[float]


class AddPointDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新增点位")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        title = QLabel("新增点位")
        title.setObjectName("PageTitle")
        hint = QLabel("写入候选表（vgpoint add）。试读通过后再单独确认落盘。")
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("tag: temp / flood_1")
        self.edit_addr = QLineEdit()
        self.edit_addr.setPlaceholderText("1 或 0x01")
        self.edit_addr.setText("1")
        self.combo_fc = QComboBox()
        self.combo_fc.addItem("03  读保持寄存器", 3)
        self.combo_fc.addItem("04  读输入寄存器", 4)
        self.edit_reg = QLineEdit()
        self.edit_reg.setPlaceholderText("0 或 0x0000")
        self.edit_reg.setText("0")
        self.edit_qty = QLineEdit()
        self.edit_qty.setPlaceholderText("1–4")
        self.edit_qty.setText("1")
        self.combo_dtype = QComboBox()
        self.combo_dtype.addItem("int16", "int16")
        self.combo_dtype.addItem("uint16", "uint16")
        self.edit_scale = QLineEdit()
        self.edit_scale.setPlaceholderText("0.1 或 1 或 R/10")
        self.edit_scale.setText("1")
        self.edit_unit = QLineEdit()
        self.edit_unit.setPlaceholderText("C / 空，ASCII ≤7")

        form.addRow("名称 / tag", self.edit_name)
        form.addRow("从机地址", self.edit_addr)
        form.addRow("功能码", self.combo_fc)
        form.addRow("起始寄存器", self.edit_reg)
        form.addRow("数量", self.edit_qty)
        form.addRow("数据类型", self.combo_dtype)
        form.addRow("倍率", self.edit_scale)
        form.addRow("单位", self.edit_unit)
        root.addLayout(form)

        box = QGroupBox("告警阈值（可选）")
        box_form = QFormLayout(box)
        box_form.setHorizontalSpacing(12)
        box_form.setVerticalSpacing(8)
        self.combo_cmp = QComboBox()
        self.combo_cmp.addItem("不比较", "")
        self.combo_cmp.addItem("≥  ge", "ge")
        self.combo_cmp.addItem("≤  le", "le")
        self.combo_cmp.addItem("=  eq", "eq")
        self.edit_warn = QLineEdit()
        self.edit_warn.setPlaceholderText("预警值，可空")
        self.edit_crit = QLineEdit()
        self.edit_crit.setPlaceholderText("严重值，可空")
        box_form.addRow("比较", self.combo_cmp)
        box_form.addRow("预警 warn", self.edit_warn)
        box_form.addRow("严重 crit", self.edit_crit)
        root.addWidget(box)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        ok_btn.setText("加入候选")
        ok_btn.setProperty("kind", "primary")
        ok_btn.style().unpolish(ok_btn)
        ok_btn.style().polish(ok_btn)
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(buttons)
        root.addLayout(row)

    def result_values(self) -> AddPointResult:
        name = self.edit_name.text().strip()
        tag = sanitize_tag(name, fallback="p1")
        warn_txt = self.edit_warn.text().strip()
        crit_txt = self.edit_crit.text().strip()
        return AddPointResult(
            tag=tag,
            name=name or tag,
            addr=parse_int_field(self.edit_addr.text(), 1),
            fc=int(self.combo_fc.currentData()),
            reg=parse_int_field(self.edit_reg.text(), 0),
            qty=max(1, min(4, parse_int_field(self.edit_qty.text(), 1))),
            dtype=str(self.combo_dtype.currentData()),
            scale=parse_scale(self.edit_scale.text()),
            formula=self.edit_scale.text().strip() or "1",
            unit=self.edit_unit.text().strip()[:7],
            cmp=str(self.combo_cmp.currentData() or ""),
            warn=float(warn_txt) if warn_txt else None,
            crit=float(crit_txt) if crit_txt else None,
        )
