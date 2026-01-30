from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QScrollArea,
    QFrame,
    QDialogButtonBox,
    QSizePolicy,
)
from PySide6.QtCore import Qt

from app.widgets import ToggleSwitch

# Helpers

def _to_yesno(value) -> str:
    if isinstance(value, str):
        return "yes" if value.strip().lower() == "yes" else "no"
    return "yes" if bool(value) else "no"


# Metadata

_SETTINGS = [
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


class InstanceSettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, current: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Instance Settings (setSettings)")
        self.setMinimumSize(700, 560)

        current = current or {}
        root = QVBoxLayout(self)

        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        root.addWidget(scroll, 1)

        content = QWidget()
        scroll.setWidget(content)

        grid = QGridLayout(content)
        grid.setAlignment(Qt.AlignTop)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(0)

        def sep(r):
            f = QFrame(frameShape=QFrame.HLine)
            grid.addWidget(f, r, 0, 1, 2)

        def label_cell(text: str):
            w = QWidget()
            l = QHBoxLayout(w)
            lbl = QLabel(text)
            lbl.setMaximumWidth(360)
            lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
            l.addWidget(lbl)
            l.addStretch(1)
            return w

        def control_cell(w: QWidget):
            c = QWidget()
            l = QHBoxLayout(c)
            l.addWidget(w, 0, Qt.AlignLeft)
            return c

        r = 0

        self.webhookUrl = QLineEdit(current.get("webhookUrl", ""))
        self.webhookUrl.setPlaceholderText("https://xyz.com/webhook/green-api/  (empty to disable)")
        self.webhookUrl.setFixedWidth(320)
        grid.addWidget(label_cell("Webhook Url"), r, 0)
        grid.addWidget(control_cell(self.webhookUrl), r, 1)
        r += 1; sep(r); r += 1

        self.webhookUrlToken = QLineEdit(current.get("webhookUrlToken", ""))
        self.webhookUrlToken.setPlaceholderText("(optional) token header value, or empty")
        self.webhookUrlToken.setFixedWidth(320)
        grid.addWidget(label_cell("Webhook authorization header"), r, 0)
        grid.addWidget(control_cell(self.webhookUrlToken), r, 1)
        r += 1; sep(r); r += 1

        self.delaySendMessagesMilliseconds = QSpinBox()
        self.delaySendMessagesMilliseconds.setRange(500, 600000)
        self.delaySendMessagesMilliseconds.setValue(int(current.get("delaySendMessagesMilliseconds", 5000)))
        self.delaySendMessagesMilliseconds.setFixedWidth(140)
        grid.addWidget(label_cell("Queue send delay (ms)"), r, 0)
        grid.addWidget(control_cell(self.delaySendMessagesMilliseconds), r, 1)
        r += 1; sep(r); r += 1

        self._checks = {}
        for key, label in _SETTINGS:
            sw = ToggleSwitch()
            sw.setChecked(_to_yesno(current.get(key)) == "yes")
            self._checks[key] = sw
            grid.addWidget(label_cell(label), r, 0)
            grid.addWidget(control_cell(sw), r, 1)
            r += 1; sep(r); r += 1

        self._checks["markIncomingMessagesReadedOnReply"].toggled.connect(self._sync_rule)
        self._sync_rule()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _sync_rule(self):
        on_reply = self._checks["markIncomingMessagesReadedOnReply"].isChecked()
        base = self._checks["markIncomingMessagesReaded"]
        base.setEnabled(not on_reply)
        if on_reply:
            base.setChecked(False)

    def payload(self) -> dict:
        data = {
            "webhookUrl": self.webhookUrl.text().strip(),
            "webhookUrlToken": self.webhookUrlToken.text().strip(),
            "delaySendMessagesMilliseconds": int(self.delaySendMessagesMilliseconds.value()),
        }
        for k in self._checks:
            data[k] = "yes" if self._checks[k].isChecked() else "no"
        if data["markIncomingMessagesReadedOnReply"] == "yes":
            data["markIncomingMessagesReaded"] = "no"
        return data
