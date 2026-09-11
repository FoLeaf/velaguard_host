"""Middle pages: points grid, session info, NSH command console."""

from __future__ import annotations

from typing import Iterable, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from velaguard_host import protocol

from .point_card import PointCard


def _kind(btn: QPushButton, kind: str) -> QPushButton:
    btn.setProperty("kind", kind)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


class InfoCard(QFrame):
    def __init__(self, caption: str, value: str = "—", parent=None):
        super().__init__(parent)
        self.setObjectName("InfoCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        self.caption = QLabel(caption)
        self.caption.setObjectName("InfoCaption")
        self.value = QLabel(value)
        self.value.setObjectName("InfoValue")
        self.value.setWordWrap(True)
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.caption)
        lay.addWidget(self.value)

    def set_value(self, text: str) -> None:
        self.value.setText(text or "—")


class PointsPage(QWidget):
    add_requested = pyqtSignal()
    test_requested = pyqtSignal()
    apply_requested = pyqtSignal()
    abort_requested = pyqtSignal()
    delete_requested = pyqtSignal(str)
    batch_delete_requested = pyqtSignal(list)
    edit_requested = pyqtSignal(str)
    import_requested = pyqtSignal()
    format_spec_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter = "all"
        self._cards: dict[str, PointCard] = {}
        self._meta: dict[str, dict] = {}
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("实时数据")
        title.setObjectName("PageTitle")
        hint = QLabel("新增 / 导入 / 编辑 / 删除 → 试读候选 → 确认落盘")
        hint.setObjectName("PageHint")
        head.addWidget(title)
        head.addSpacing(12)
        head.addWidget(hint, 1)
        self.status = QLabel("")
        self.status.setObjectName("PageHint")
        self.status.setMinimumWidth(120)
        head.addWidget(self.status)

        self.btn_add = _kind(QPushButton("新增点位"), "primary")
        self.btn_import = _kind(QPushButton("导入点表"), "ghost")
        self.btn_test = _kind(QPushButton("试读候选"), "ghost")
        self.btn_apply = _kind(QPushButton("确认落盘"), "danger")
        self.btn_abort = _kind(QPushButton("放弃候选"), "ghost")
        self.btn_add.clicked.connect(self.add_requested.emit)
        self.btn_import.clicked.connect(self.import_requested.emit)
        self.btn_test.clicked.connect(self.test_requested.emit)
        self.btn_apply.clicked.connect(self.apply_requested.emit)
        self.btn_abort.clicked.connect(self.abort_requested.emit)
        for b in (self.btn_add, self.btn_import, self.btn_test, self.btn_apply, self.btn_abort):
            head.addWidget(b)
        root.addLayout(head)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        self._chip_btns: dict[str, QPushButton] = {}
        for key, label in (
            ("all", "全部"),
            ("committed", "已确认"),
            ("candidate", "候选"),
            ("fail", "失败"),
        ):
            btn = _kind(QPushButton(label), "chip")
            btn.setCheckable(True)
            self._chip_group.addButton(btn)
            self._chip_btns[key] = btn
            btn.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            chips.addWidget(btn)
        self._chip_btns["all"].setChecked(True)
        chips.addStretch(1)
        self.btn_select_all = _kind(QPushButton("全选可见"), "ghost")
        self.btn_batch_del = _kind(QPushButton("批量删除"), "ghost")
        self.btn_format = _kind(QPushButton("点表格式"), "ghost")
        self.btn_select_all.setToolTip("勾选当前筛选下的点位；再点一次取消")
        self.btn_batch_del.setToolTip("对勾选点位逐条 vgpoint del，不自动落盘")
        self.btn_format.setToolTip("查看导入 JSON 格式规范")
        self.btn_select_all.clicked.connect(self._toggle_select_visible)
        self.btn_batch_del.clicked.connect(self._emit_batch_delete)
        self.btn_format.clicked.connect(self.format_spec_requested.emit)
        chips.addWidget(self.btn_select_all)
        chips.addWidget(self.btn_batch_del)
        chips.addWidget(self.btn_format)
        root.addLayout(chips)

        self.empty = QLabel("打开串口后会列出点表\n也可「新增点位」写入候选")
        self.empty.setObjectName("EmptyHint")
        self.empty.setAlignment(Qt.AlignCenter)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        host = QWidget()
        self.grid = QGridLayout(host)
        self.grid.setContentsMargins(0, 4, 8, 4)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid.setColumnStretch(3, 1)
        self.scroll.setWidget(host)

        root.addWidget(self.empty, 1)
        root.addWidget(self.scroll, 1)
        self.scroll.hide()

    def _set_filter(self, key: str) -> None:
        self._filter = key
        self._relayout()

    def set_busy(self, busy: bool, command: str = "") -> None:
        """Show in-flight NSH status; do not disable workflow buttons."""
        if busy:
            shown = command.strip() or "NSH"
            if len(shown) > 36:
                shown = shown[:33] + "…"
            self.status.setText(f"执行中 · {shown}")
            self.status.setStyleSheet("color: #2EC4B6;")
        else:
            self.status.setText("")
            self.status.setStyleSheet("")

    def set_online(self, online: bool) -> None:
        if not online:
            return
        self.empty.setText("暂无点位\n点「新增点位」写入候选，或等待 list 同步")

    def upsert(
        self,
        tag: str,
        unit: str = "",
        candidate: bool = False,
        value: Optional[str] = None,
        ok: Optional[bool] = None,
        name: str = "",
    ) -> PointCard:
        meta = self._meta.get(tag, {})
        meta.update({"unit": unit, "candidate": candidate, "name": name or tag})
        if value is not None:
            meta["value"] = value
        if ok is not None:
            meta["ok"] = ok
        self._meta[tag] = meta
        card = self._cards.get(tag)
        display = name or meta.get("name") or tag
        if card is None:
            card = PointCard(tag, unit=unit, candidate=candidate, name=display)
            card.delete_requested.connect(self.delete_requested.emit)
            card.edit_requested.connect(self.edit_requested.emit)
            self._cards[tag] = card
        else:
            card.set_meta(tag, unit, candidate, name=display)
        if value is not None:
            card.set_value_text(value, ok)
        self._relayout()
        return card

    def apply_read(self, tag: str, text: str, ok: bool) -> None:
        if tag not in self._cards:
            self.upsert(tag, value=text, ok=ok)
            return
        self._meta.setdefault(tag, {})
        self._meta[tag]["value"] = text
        self._meta[tag]["ok"] = ok
        self._cards[tag].set_value_text(text, ok)
        self._relayout()

    def mark_pending_delete(self, tag: str) -> None:
        meta = self._meta.setdefault(tag, {})
        meta["pending_delete"] = True
        meta["candidate"] = True
        card = self._cards.get(tag)
        if card:
            card.set_pending_delete(True)
        self._relayout()

    def clear_pending_deletes(self) -> None:
        for tag, meta in self._meta.items():
            if not meta.get("pending_delete"):
                continue
            meta["pending_delete"] = False
            card = self._cards.get(tag)
            if card:
                card.set_pending_delete(False)
        self._relayout()

    def remove_tags(self, tags: Iterable[str]) -> None:
        for tag in list(tags):
            card = self._cards.pop(tag, None)
            self._meta.pop(tag, None)
            if card is not None:
                card.hide()
                card.setParent(None)
                card.deleteLater()
        self._relayout()

    def mark_all_committed(self) -> None:
        pending = [tag for tag, meta in self._meta.items() if meta.get("pending_delete")]
        self.remove_tags(pending)
        for tag, meta in self._meta.items():
            meta["candidate"] = False
            card = self._cards.get(tag)
            if card:
                card.set_candidate(False)
        self._relayout()

    def _visible_tags(self) -> list[str]:
        tags = []
        for tag, card in self._cards.items():
            meta = self._meta.get(tag, {})
            cand = bool(meta.get("candidate", card.candidate))
            pending = bool(meta.get("pending_delete", card.pending_delete))
            failed = card.last_ok is False
            if self._filter == "committed" and (cand or pending):
                continue
            if self._filter == "candidate" and not cand and not pending:
                continue
            if self._filter == "fail" and not failed:
                continue
            tags.append(tag)
        return tags

    def _relayout(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
        for card in self._cards.values():
            card.hide()
        tags = self._visible_tags()
        empty = len(self._cards) == 0 or len(tags) == 0
        self.empty.setVisible(empty and len(self._cards) == 0)
        if len(self._cards) == 0:
            self.empty.setText("打开串口后会列出点表\n也可「新增点位」写入候选")
            self.empty.show()
            self.scroll.hide()
            return
        if len(tags) == 0:
            self.empty.setText("当前筛选下没有点位")
            self.empty.show()
            self.scroll.hide()
            return
        self.empty.hide()
        self.scroll.show()
        cols = 3
        for i, tag in enumerate(tags):
            card = self._cards[tag]
            card.show()
            self.grid.addWidget(card, i // cols, i % cols)

    def card_for(self, tag: str) -> Optional[PointCard]:
        return self._cards.get(tag)

    def tags(self) -> Iterable[str]:
        return self._cards.keys()

    def selected_tags(self) -> list[str]:
        tags = []
        for tag in self._visible_tags():
            card = self._cards[tag]
            if card.pending_delete:
                continue
            if card.is_selected():
                tags.append(tag)
        return tags

    def clear_selection(self, tags: Optional[Iterable[str]] = None) -> None:
        targets = list(tags) if tags is not None else list(self._cards)
        for tag in targets:
            card = self._cards.get(tag)
            if card is not None:
                card.set_selected(False)

    def _toggle_select_visible(self) -> None:
        tags = [
            tag
            for tag in self._visible_tags()
            if not self._cards[tag].pending_delete
        ]
        if not tags:
            return
        all_on = all(self._cards[tag].is_selected() for tag in tags)
        for tag in tags:
            self._cards[tag].set_selected(not all_on)

    def _emit_batch_delete(self) -> None:
        self.batch_delete_requested.emit(self.selected_tags())


class SessionPage(QWidget):
    delete_requested = pyqtSignal(list)
    edit_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        title = QLabel("参数设置")
        title.setObjectName("PageTitle")
        hint = QLabel(
            "会话信息 · 点表可编辑或 Ctrl/Shift 多选删除。"
            "编辑/删除只改候选，需确认落盘才写入已确认表。"
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.card_proto = InfoCard("协议", "vgpoint")
        self.card_port = InfoCard("串口", "未连接")
        self.card_baud = InfoCard("波特率", "115200")
        self.card_prompt = InfoCard("提示符", "nsh>")
        self.card_apply = InfoCard("落盘命令", protocol.SAFE_APPLY_CMD)
        self.card_cand = InfoCard("候选路径", protocol.CANDIDATE_PATH)
        self.card_live = InfoCard("已确认路径", protocol.POINTS_PATH)
        self.card_count = InfoCard("点数", "0")
        cards = [
            self.card_proto,
            self.card_port,
            self.card_baud,
            self.card_prompt,
            self.card_apply,
            self.card_cand,
            self.card_live,
            self.card_count,
        ]
        for i, card in enumerate(cards):
            grid.addWidget(card, i // 4, i % 4)
        root.addLayout(grid)

        table_head = QHBoxLayout()
        table_lab = QLabel("点表")
        table_lab.setObjectName("PageHint")
        self.btn_edit_row = _kind(QPushButton("编辑选中"), "ghost")
        self.btn_edit_row.setToolTip("编辑当前行，字段与新增相同（id 不能改，name 可改）")
        self.btn_edit_row.clicked.connect(self._emit_selected_edit)
        self.btn_del_row = _kind(QPushButton("删除选中"), "ghost")
        self.btn_del_row.setToolTip("删除选中的一行或多行；只改候选，不自动落盘")
        self.btn_del_row.clicked.connect(self._emit_selected_delete)
        table_head.addWidget(table_lab)
        table_head.addStretch(1)
        table_head.addWidget(self.btn_edit_row)
        table_head.addWidget(self.btn_del_row)
        root.addLayout(table_head)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["id", "name", "addr", "fc", "reg", "qty", "scale", "unit", "状态"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(lambda row, _col: self._edit_row(row))
        root.addWidget(self.table, 1)

    def _emit_selected_edit(self) -> None:
        self._edit_row(self.table.currentRow())

    def _edit_row(self, row: int) -> None:
        if row < 0:
            return
        item = self.table.item(row, 0)
        if item is None:
            return
        tag = item.text().strip()
        if tag:
            self.edit_requested.emit(tag)

    def _emit_selected_delete(self) -> None:
        tags: list[str] = []
        seen: set[str] = set()
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        for row in rows:
            item = self.table.item(row, 0)
            if item is None:
                continue
            tag = item.text().strip()
            if tag and tag not in seen:
                seen.add(tag)
                tags.append(tag)
        if tags:
            self.delete_requested.emit(tags)

    def set_port(self, port: str, online: bool) -> None:
        if online and port:
            self.card_port.set_value(f"{port} · 已连接")
        elif port:
            self.card_port.set_value(f"{port} · 未连接")
        else:
            self.card_port.set_value("未连接")

    def set_counts(self, total: int, candidate: int) -> None:
        self.card_count.set_value(f"{total}（候选 {candidate}）")

    def set_rows(self, rows: list[tuple]) -> None:
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(r, c, item)


class ConsolePage(QWidget):
    command_submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)
        title = QLabel("控制台")
        title.setObjectName("PageTitle")
        hint = QLabel("向板端 NSH 发送一行命令。回显在窗口底部日志。apply 请用实时数据页的确认落盘。")
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)

        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("例如 vgpoint list  ·  Enter 发送")
        self.edit.returnPressed.connect(self._submit)
        self.btn_send = _kind(QPushButton("发送"), "primary")
        self.btn_send.clicked.connect(self._submit)
        row.addWidget(self.edit, 1)
        row.addWidget(self.btn_send)
        root.addLayout(row)

        chips = QHBoxLayout()
        chips.setSpacing(8)
        for cmd in ("?", "vgpoint list", "vgpoint list -c"):
            btn = _kind(QPushButton(cmd), "chip")
            btn.clicked.connect(lambda _=False, c=cmd: self.command_submitted.emit(c))
            chips.addWidget(btn)
        chips.addStretch(1)
        root.addLayout(chips)
        root.addStretch(1)

    def _submit(self) -> None:
        text = self.edit.text().strip()
        if not text:
            return
        self.command_submitted.emit(text)
        self.edit.clear()

    def set_online(self, online: bool) -> None:
        self.edit.setPlaceholderText(
            "例如 vgpoint list  ·  Enter 发送" if online else "请先打开串口"
        )
