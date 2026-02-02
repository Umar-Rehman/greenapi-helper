from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QDialogButtonBox,
    QStyleFactory,
    QWidget,
)

# Field specifications


@dataclass
class TextField:
    key: str
    label: str
    default: str = ""
    placeholder: str = ""
    required: bool = True
    min_width: int = 320


@dataclass
class IntField:
    key: str
    label: str
    default: int = 0
    min_value: int = 0
    max_value: int = 10_000
    step: int = 1
    required: bool = True


FieldSpec = TextField | IntField


# Form dialog


class FormDialog(QDialog):
    """
    Generic form dialog.
    You pass a list of field specs (TextField / IntField),
    it builds widgets and returns values as dict.
    """

    def __init__(
        self,
        title: str,
        fields: list[FieldSpec],
        parent: QWidget | None = None,
        *,
        min_width: int = 420,
        fusion: bool = True,
        first_focus_key: str | None = None,
        validator: Callable[[dict[str, Any]], str | None] | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        if fusion:
            self.setStyle(QStyleFactory.create("Fusion"))
        self.setMinimumWidth(min_width)

        self._fields = fields
        self._widgets: dict[str, QWidget] = {}
        self._validator = validator

        layout = QFormLayout(self)

        for spec in fields:
            if isinstance(spec, TextField):
                w = QLineEdit(spec.default)
                w.setPlaceholderText(spec.placeholder)
                w.setMinimumWidth(spec.min_width)
                layout.addRow(spec.label, w)
                self._widgets[spec.key] = w
            elif isinstance(spec, IntField):
                w = QSpinBox()
                w.setRange(spec.min_value, spec.max_value)
                w.setSingleStep(spec.step)
                w.setValue(spec.default)
                layout.addRow(spec.label, w)
                self._widgets[spec.key] = w
            else:
                raise TypeError(f"Unknown field spec: {spec}")

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if first_focus_key and first_focus_key in self._widgets:
            self._widgets[first_focus_key].setFocus()
        elif fields:
            self._widgets[fields[0].key].setFocus()

    def _on_accept(self):
        values = self.values()

        for spec in self._fields:
            if not spec.required:
                continue
            v = values.get(spec.key)
            if isinstance(spec, TextField) and not str(v or "").strip():
                self._widgets[spec.key].setFocus()
                return

        if self._validator:
            msg = self._validator(values)
            if msg:
                return

        self.accept()

    def values(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for spec in self._fields:
            w = self._widgets[spec.key]
            if isinstance(spec, TextField):
                out[spec.key] = w.text().strip()
            elif isinstance(spec, IntField):
                out[spec.key] = int(w.value())
        return out


# Convenience functions


def ask_chat_history(
    parent: QWidget, *, chat_id_default: str = "", count_default: int = 10
):
    dlg = FormDialog(
        "Get Chat History",
        fields=[
            TextField(
                key="chatId",
                label="chatId:",
                default=chat_id_default,
                placeholder="e.g. 7987...@c.us or 1203...@g.us",
            ),
            IntField(
                key="count",
                label="count:",
                default=count_default,
                min_value=1,
                max_value=1000,
                step=10,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    v = dlg.values()
    return v["chatId"], v["count"]


def ask_get_message(parent: QWidget, *, chat_id_default: str = ""):
    dlg = FormDialog(
        "Get Message",
        fields=[
            TextField(
                key="chatId",
                label="chatId:",
                default=chat_id_default,
                placeholder="e.g. 7987...@c.us or 1203...@g.us",
            ),
            TextField(
                key="idMessage",
                label="idMessage:",
                placeholder="e.g. BAE5F4886F6F2D05",
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
        min_width=520,
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    v = dlg.values()
    return v["chatId"], v["idMessage"]


def ask_status_statistic(parent: QWidget, *, id_message_default: str = ""):
    dlg = FormDialog(
        "Get Status Statistic",
        fields=[
            TextField(
                key="idMessage",
                label="idMessage:",
                default=id_message_default,
                placeholder="e.g. BAE5F4886F6F2D05",
                min_width=360,
            )
        ],
        parent=parent,
        min_width=520,
        fusion=False,
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()["idMessage"]
