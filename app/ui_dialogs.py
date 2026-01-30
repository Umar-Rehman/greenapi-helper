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
    QGridLayout,
    QScrollArea,
    QFrame,
    QToolButton,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, QSize
from app.ui_utils import pixmap_from_base64_png
from app.widgets import ToggleSwitch
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

_YESNO_FIELDS = [
    ("markIncomingMessagesReaded", "Mark incoming messages as read"),
    ("markIncomingMessagesReadedOnReply", "Mark incoming messages read on reply"),
    ("outgoingWebhook", "Receive webhooks on sent messages statuses"),
    ("outgoingMessageWebhook", "Receive webhooks on messages sent from phone"),
    ("outgoingAPIMessageWebhook", "Receive webhooks on messages sent from API"),
    ("stateWebhook", "Receive notifications about auth state change"),
    ("incomingWebhook", "Receive webhooks on incoming messages and files"),
    ("keepOnlineStatus", "Keep 'online' status"),
    ("pollMessageWebhook", "Get notifications about surveys (polls)"),
    ("incomingCallWebhook", "Get notifications about calls"),
    ("editedMessageWebhook", "Get notifications about edited messages"),
    ("deletedMessageWebhook", "Get notifications about deleted messages"),
    ("incomingBlockWebhook", "Get notifications about incoming chat blocks"),
]

def _to_yesno(value) -> str:
    """Normalize any truthy-ish value to yes/no."""
    if isinstance(value, str):
        return "yes" if value.strip().lower() == "yes" else "no"
    return "yes" if bool(value) else "no"

_FIELD_INFO: dict[str, str] = {
    "webhookUrl": (
        "Parameter: webhookUrl\n"
        "URL for sending notifications.\n"
        "Set empty string \"\" to disable.\n"
        "If using HTTP API notifications, this field must be empty."
    ),
    "webhookUrlToken": (
        "Parameter: webhookUrlToken\n"
        "Token/header value to access your notification server.\n"
        "If not required, set empty string \"\"."
    ),
    "delaySendMessagesMilliseconds": (
        "Parameter: delaySendMessagesMilliseconds\n"
        "Message sending delay from the queue (ms).\n"
        "Min: 500, Max: 600000. Recommended <= 300000."
    ),
    "markIncomingMessagesReaded": (
        "Parameter: markIncomingMessagesReaded\n"
        "Mark incoming messages as read.\n"
        "Ignored if markIncomingMessagesReadedOnReply is 'yes'."
    ),
    "markIncomingMessagesReadedOnReply": (
        "Parameter: markIncomingMessagesReadedOnReply\n"
        "Mark incoming messages read on reply from API.\n"
        "If 'yes', markIncomingMessagesReaded is ignored."
    ),
    "outgoingWebhook": (
        "Parameter: outgoingWebhook\n"
        "Receive webhooks on sent message statuses.\n"
        "noAccount and failed cannot be disabled."
    ),
    "outgoingMessageWebhook": (
        "Parameter: outgoingMessageWebhook\n"
        "Receive webhooks on messages sent from phone."
    ),
    "outgoingAPIMessageWebhook": (
        "Parameter: outgoingAPIMessageWebhook\n"
        "Receive webhooks on messages sent from API.\n"
        "If sending to non-existing WhatsApp, notification will not come."
    ),
    "stateWebhook": (
        "Parameter: stateWebhook\n"
        "Receive notifications about instance authorization state change."
    ),
    "incomingWebhook": (
        "Parameter: incomingWebhook\n"
        "Receive webhooks on incoming messages and files."
    ),
    "keepOnlineStatus": (
        "Parameter: keepOnlineStatus\n"
        "Keep 'online' status."
    ),
    "pollMessageWebhook": (
        "Parameter: pollMessageWebhook\n"
        "Receive notifications about polls."
    ),
    "incomingCallWebhook": (
        "Parameter: incomingCallWebhook\n"
        "Receive notifications about incoming calls."
    ),
    "editedMessageWebhook": (
        "Parameter: editedMessageWebhook\n"
        "Receive notifications about edited messages."
    ),
    "deletedMessageWebhook": (
        "Parameter: deletedMessageWebhook\n"
        "Receive notifications about deleted messages."
    ),
    "incomingBlockWebhook": (
        "Parameter: incomingBlockWebhook\n"
        "Receive notifications about incoming chat blocks."
    ),
}

class InstanceSettingsDialog(QDialog):
    """
    Popup for setSettings payload.
    - ToggleSwitch maps to yes/no strings
    - delay is int milliseconds
    """

    def __init__(self, parent: QWidget | None = None, current: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Instance Settings (setSettings)")

        # 1) Minimum size so rows never squash
        self.setMinimumSize(700, 560)

        current = current or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Scroll area so you don’t get ridiculous row stretching
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        root.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)

        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)

        # 2) Keep spacing consistent (and avoid huge middle gap)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(0)
        grid.setAlignment(Qt.AlignTop)  # rows stick to top; extra height goes below

        # Columns:
        # 0 = label + info button
        # 1 = control widget (expands)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        # light row separators via stylesheet (simple, looks clean)
        content.setStyleSheet("""
            QLabel#settingLabel {
                padding: 10px 6px;
            }
            QWidget#controlCell {
                padding: 6px 6px;
            }
            QFrame#rowSep {
                border: none;
                border-bottom: 1px solid rgba(0, 0, 0, 40);
            }
            QToolButton#infoBtn {
                margin-left: 4px;
                color: rgba(0,0,0,140);
            }
            QLineEdit, QSpinBox {
                min-height: 30px;
            }
        """)

        def add_separator(row: int):
            sep = QFrame()
            sep.setObjectName("rowSep")
            sep.setFrameShape(QFrame.HLine)
            sep.setFrameShadow(QFrame.Plain)
            grid.addWidget(sep, row, 0, 1, 2)

        def make_label_cell(text: str, info_key: str | None) -> QWidget:
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(6)

            lbl = QLabel(text)
            lbl.setObjectName("settingLabel")
            # 3) Prevent label column from becoming a giant gap maker
            lbl.setMaximumWidth(360)
            lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            lay.addWidget(lbl)

            if info_key:
                info = QToolButton()
                info.setObjectName("infoBtn")
                info.setAutoRaise(True)
                info.setToolTip(_FIELD_INFO.get(info_key, f"Parameter: {info_key}"))

                # Use a clean native “information” icon (circle-i style)
                info.setIcon(self.style().standardIcon(
                    self.style().StandardPixmap.SP_FileDialogInfoView
                ))
                info.setIconSize(QSize(14, 14))

                lay.addWidget(info)

            lay.addStretch(1)
            return w

        def make_control_cell(widget: QWidget, *, right_align: bool = False) -> QWidget:
            w = QWidget()
            w.setObjectName("controlCell")
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)

            if right_align:
                # old behavior (kept for cases you might still want it)
                lay.addStretch(1)
                lay.addWidget(widget, 0, Qt.AlignRight)
            else:
                # NEW: left-aligned, no empty space
                lay.addWidget(widget, 0, Qt.AlignLeft)

            return w

        r = 0

        # --- webhookUrl ---
        self.webhookUrl = QLineEdit(str(current.get("webhookUrl", "")) or "")
        self.webhookUrl.setPlaceholderText("https://mysite.com/webhook/green-api/   (empty to disable)")
        self.webhookUrl.setMinimumWidth(320)
        self.webhookUrl.setMaximumWidth(600)

        self.webhookUrl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        grid.addWidget(make_label_cell("Webhook Url", "webhookUrl"), r, 0)
        grid.addWidget(make_control_cell(self.webhookUrl), r, 1)
        r += 1
        add_separator(r); r += 1

        # --- webhookUrlToken ---
        self.webhookUrlToken = QLineEdit(str(current.get("webhookUrlToken", "")) or "")
        self.webhookUrlToken.setPlaceholderText("(optional) token header value, or empty")
        self.webhookUrlToken.setMinimumWidth(320)
        self.webhookUrlToken.setMaximumWidth(600)

        self.webhookUrlToken.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        grid.addWidget(make_label_cell("Webhook authorization header", "webhookUrlToken"), r, 0)
        grid.addWidget(make_control_cell(self.webhookUrlToken), r, 1)
        r += 1
        add_separator(r); r += 1

        # --- delay ---
        self.delaySendMessagesMilliseconds = QSpinBox()
        self.delaySendMessagesMilliseconds.setRange(500, 600000)
        self.delaySendMessagesMilliseconds.setSingleStep(500)
        try:
            self.delaySendMessagesMilliseconds.setValue(int(current.get("delaySendMessagesMilliseconds", 5000)))
        except Exception:
            self.delaySendMessagesMilliseconds.setValue(5000)
        # Keep it compact, not huge
        self.delaySendMessagesMilliseconds.setFixedWidth(140)

        grid.addWidget(make_label_cell("Queue send delay (ms)", "delaySendMessagesMilliseconds"), r, 0)
        grid.addWidget(make_control_cell(self.delaySendMessagesMilliseconds), r, 1)
        r += 1
        add_separator(r); r += 1

        # --- Yes/No fields (ToggleSwitch) ---
        self._checks: dict[str, ToggleSwitch] = {}

        for key, human_label in _YESNO_FIELDS:
            sw = ToggleSwitch()
            sw.setChecked(_to_yesno(current.get(key, "no")) == "yes")
            # Make switch not influence row sizing
            sw.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

            self._checks[key] = sw

            grid.addWidget(make_label_cell(human_label, key), r, 0)
            grid.addWidget(make_control_cell(sw), r, 1)
            r += 1
            add_separator(r); r += 1

        # enforce the "on reply" rule in UI
        on_reply = self._checks["markIncomingMessagesReadedOnReply"]
        if hasattr(on_reply, "toggled"):
            on_reply.toggled.connect(self._sync_read_rule)
        else:
            on_reply.stateChanged.connect(self._sync_read_rule)

        self._sync_read_rule()

        # Buttons
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons, 0)

    def _sync_read_rule(self):
        on_reply = self._checks["markIncomingMessagesReadedOnReply"].isChecked()
        base_sw = self._checks["markIncomingMessagesReaded"]
        base_sw.setEnabled(not on_reply)
        if on_reply:
            base_sw.setChecked(False)

    def payload(self) -> dict:
        data: dict[str, object] = {
            "webhookUrl": self.webhookUrl.text().strip(),
            "webhookUrlToken": self.webhookUrlToken.text().strip(),
            "delaySendMessagesMilliseconds": int(self.delaySendMessagesMilliseconds.value()),
        }
        for key, _label in _YESNO_FIELDS:
            data[key] = "yes" if self._checks[key].isChecked() else "no"

        if data.get("markIncomingMessagesReadedOnReply") == "yes":
            data["markIncomingMessagesReaded"] = "no"

        return data

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

