"""Preview and confirm a JSON point-table import (candidate only)."""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QBrush, QColor, QDesktopServices, QFont
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from velaguard_host import protocol
from velaguard_host.protocol import ImportRow


def point_table_spec_path() -> Path:
    return Path(__file__).resolve().parents[1] / "docs" / "POINT_TABLE_JSON.md"


def point_table_spec_text() -> str:
    path = point_table_spec_path()
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return (
            "点表导入为 UTF-8 JSON。必填：id / addr / reg。\n"
            "外形：{schema_version, bus?, points:[...]}，或 {points}，或顶层数组。\n"
            "id 仅 [A-Za-z0-9_]{1,23}；name 可中文（≤47 字节）；fc 为 3 或 4；最多 32 点。\n"
            f"完整规范文件：{path}"
        )


class FormatSpecDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("点表导入文件格式规范")
        self.setMinimumSize(720, 520)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        title = QLabel("点表导入 JSON 格式")
        title.setObjectName("PageTitle")
        hint = QLabel(
            "导入只写入候选表（add / 已存在则 set），不会自动试读或 apply --confirm。"
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setFont(QFont("JetBrains Mono", 10))
        view.setPlainText(point_table_spec_text())
        root.addWidget(view, 1)
        row = QHBoxLayout()
        open_btn = QPushButton("打开规范文件")
        open_btn.setProperty("kind", "ghost")
        open_btn.setCursor(Qt.PointingHandCursor)
        open_btn.clicked.connect(self._open_file)
        close_btn = QPushButton("关闭")
        close_btn.setProperty("kind", "primary")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        row.addWidget(open_btn)
        row.addStretch(1)
        row.addWidget(close_btn)
        root.addLayout(row)

    def _open_file(self) -> None:
        path = point_table_spec_path()
        if not path.is_file():
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def show_point_table_spec(parent=None) -> None:
    FormatSpecDialog(parent).exec_()


_COLS = (
    "id",
    "name",
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
                p.id,
                p.name,
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
        spec_btn = buttons.addButton("格式说明", QDialogButtonBox.HelpRole)
        spec_btn.setProperty("kind", "ghost")
        spec_btn.setCursor(Qt.PointingHandCursor)
        spec_btn.clicked.connect(lambda: show_point_table_spec(self))
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
        return [], (
            "不是有效的点表 JSON（需要 points 数组或点对象数组）。"
            "格式见 docs/POINT_TABLE_JSON.md"
        )
    if not table.points:
        return [], "文件里没有点位"
    return protocol.prepare_import_rows(table.points), ""
