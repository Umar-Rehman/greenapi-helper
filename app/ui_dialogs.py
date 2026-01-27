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
    QVBoxLayout, 
    QLabel, 
    QPushButton, 
    QTextEdit,
    QHBoxLayout,
)
from PySide6.QtCore import Qt, QTimer
from app.ui_utils import pixmap_from_base64_png
from PySide6.QtGui import QGuiApplication

# ---------- Field specs ----------

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

# ---------- Generic form dialog ----------

class FormDialog(QDialog):
    """
    Generic form dialog.
    You pass a list of field specs (TextField / IntField), it builds widgets and returns values as dict.
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
        validator: Callable[[dict[str, Any]], str | None] | None = None,  # return error message or None
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

        # Build fields
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

        # Buttons
        self._buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        layout.addRow(self._buttons)

        # Focus
        focus_key = first_focus_key
        if focus_key and focus_key in self._widgets:
            self._widgets[focus_key].setFocus()
        else:
            # focus first widget
            if fields:
                self._widgets[fields[0].key].setFocus()

    def _on_accept(self):
        values = self.values()

        # required checks
        for spec in self._fields:
            if not getattr(spec, "required", False):
                continue
            v = values.get(spec.key)
            if isinstance(spec, TextField) and (v is None or str(v).strip() == ""):
                # mark focus and do not close
                self._widgets[spec.key].setFocus()
                return
            if isinstance(spec, IntField) and v is None:
                self._widgets[spec.key].setFocus()
                return

        # custom validator
        if self._validator:
            msg = self._validator(values)
            if msg:
                # simple: keep dialog open; caller can show error if desired
                # (If you want, we can add a QLabel for error text here.)
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

# ---------- QR Code Dialog ----------

class QrCodeDialog(QDialog):
    def __init__(self, *, link: str, qr_base64: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QR Code")
        self.setMinimumWidth(560)

        self._qr_base64 = qr_base64
        self._qr_visible = False
        self._pix_original = None  # cache decoded QR pixmap once
        self._collapsed_size = None  # remember size when image hidden

        root = QVBoxLayout(self)

        root.addWidget(QLabel("Open this link to view QR in browser:"))

        self.link_box = QTextEdit()
        self.link_box.setReadOnly(True)
        self.link_box.setPlainText(link)
        self.link_box.setFixedHeight(60)
        root.addWidget(self.link_box)

        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.hide()
        root.addWidget(self.preview)

        row = QHBoxLayout()

        self.btn_preview = QPushButton("Show QR image")
        self.btn_preview.clicked.connect(self._on_preview)
        row.addWidget(self.btn_preview)

        self.btn_copy = QPushButton("Copy QR image")
        self.btn_copy.clicked.connect(self._copy_qr_to_clipboard)
        self.btn_copy.setEnabled(bool(qr_base64))
        row.addWidget(self.btn_copy)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_close)

        root.addLayout(row)

        if not qr_base64:
            self.btn_preview.setEnabled(False)
            self.btn_preview.setText("No image to preview")
            self.btn_copy.setEnabled(False)

        # capture the "collapsed" size (image hidden) once the layout has settled
        QTimer.singleShot(0, self._capture_collapsed_size)

    def _capture_collapsed_size(self):
        # called once after the dialog is shown / layout is computed
        self.adjustSize()
        self._collapsed_size = self.size()

    def _ensure_pixmap(self):
        if self._pix_original is not None:
            return True
        if not self._qr_base64:
            return False

        pix = pixmap_from_base64_png(self._qr_base64)
        if not pix:
            return False

        self._pix_original = pix
        return True

    def _on_preview(self):
        if self._qr_visible:
            self.preview.hide()
            self.btn_preview.setText("Show QR image")
            self._qr_visible = False
            self.adjustSize()
            return

        # Show QR
        if not self._qr_base64:
            return

        pix = pixmap_from_base64_png(self._qr_base64)
        if not pix:
            self.btn_preview.setText("Failed to render QR")
            return

        self.preview.setPixmap(
            pix.scaledToWidth(320, Qt.SmoothTransformation)
        )
        self.preview.show()
        self.btn_preview.setText("Hide QR image")
        self._qr_visible = True
        self.adjustSize()

    def _copy_qr_to_clipboard(self):
        if not self._ensure_pixmap():
            return

        QGuiApplication.clipboard().setPixmap(self._pix_original)

        self.btn_copy.setText("Copied!")
        self.btn_copy.setEnabled(False)
        QTimer.singleShot(1200, self._reset_copy_button)

    def _reset_copy_button(self):
        self.btn_copy.setText("Copy QR image")
        self.btn_copy.setEnabled(True)

# ---------- Convenience wrappers ----------

def ask_chat_history(parent: QWidget, *, chat_id_default: str = "", count_default: int = 10):
    dlg = FormDialog(
        "Get Chat History",
        fields=[
            TextField(
                key="chatId",
                label="chatId:",
                default=chat_id_default,
                placeholder="e.g. 7987...@c.us or 1203...@g.us",
                required=True,
            ),
            IntField(
                key="count",
                label="count:",
                default=count_default,
                min_value=1,
                max_value=1000,
                step=10,
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
        min_width=420,
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
                required=True,
            ),
            TextField(
                key="idMessage",
                label="idMessage:",
                placeholder="e.g. BAE5F4886F6F2D05",
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
        min_width=520,  # wider for message id
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    else:
        v = dlg.values()
        return v["chatId"], v["idMessage"]

def ask_status_statistic(parent, *, id_message_default: str = ""):
    dlg = FormDialog(
        "Get Status Statistic",
        fields=[
            TextField(
                key="idMessage",
                label="idMessage:",
                default=id_message_default,
                placeholder="e.g. BAE5F4886F6F2D05",
                required=True,
                min_width=360,
            )
        ],
        parent=parent,
        min_width=520,
        first_focus_key="idMessage",
        fusion=False,
    )
    if dlg.exec() != QDialog.Accepted:
        return None

    v = dlg.values()
    return v["idMessage"]

