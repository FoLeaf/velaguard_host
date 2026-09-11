"""Preview and confirm a JSON point-table import (candidate only)."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from velaguard_host import protocol
from velaguard_host.protocol import ImportRow


_COLS = (
    "tag",
    "addr",
    "fc",
    "reg",
    "qty",
    "dtype",
    "scale",
    "unit",
    "cmp",
    "warn",
    "crit",
    "校验",
)


class ImportPointsDialog(QDialog):
    def __init__(self, path: str, rows: list[ImportRow], parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入点表")
        self.setMinimumSize(840, 420)
        self._rows = rows
        self._build(path)

    def _build(self, path: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel("导入点表预览")
        title.setObjectName("PageTitle")
        hint = QLabel(
            f"文件：{path}\n"
            "将逐条发送 vgpoint add（已存在则 set）写入候选表。"
            "不会自动试读，也不会 apply --confirm。"
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)

        table = QTableWidget(len(self._rows), len(_COLS))
        table.setHorizontalHeaderLabels(_COLS)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        err_bg = QBrush(QColor("#3A1E1E"))
        err_fg = QBrush(QColor("#E03131"))
        for r, row in enumerate(self._rows):
            p = row.point
            vals = [
                p.tag,
                p.addr,
                p.fc,
                p.reg,
                p.qty,
                p.dtype,
                p.scale,
                p.unit,
                p.cmp,
                "" if p.warn is None else p.warn,
                "" if p.crit is None else p.crit,
                row.error or "OK",
            ]
            for c, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                if row.error:
                    item.setBackground(err_bg)
                    item.setForeground(err_fg)
                table.setItem(r, c, item)
        root.addWidget(table, 1)

        n_ok = sum(1 for row in self._rows if row.ok)
        n_bad = len(self._rows) - n_ok
        summary = QLabel(
            f"共 {len(self._rows)} 条，可导入 {n_ok}，错误 {n_bad}。"
            f" 上限 {protocol.MAX_POINTS} 点。"
        )
        summary.setObjectName("PageHint")
        if n_bad:
            summary.setStyleSheet("color: #E03131;")
        root.addWidget(summary)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("开始导入")
        buttons.button(QDialogButtonBox.Ok).setProperty("kind", "primary")
        ok_btn = buttons.button(QDialogButtonBox.Ok)
        ok_btn.setEnabled(n_ok > 0 and n_bad == 0)
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def rows(self) -> list[ImportRow]:
        return self._rows


def load_import_rows(path: str) -> tuple[list[ImportRow], str]:
    """Return (rows, error). error is set when the file cannot be parsed at all."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return [], f"无法读取文件：{exc}"
    table = protocol.parse_point_table_json(text, path=path)
    if table is None:
        return [], "不是有效的点表 JSON（需要 points 数组或点对象数组）"
    if not table.points:
        return [], "文件里没有点位"
    return protocol.prepare_import_rows(table.points), ""
