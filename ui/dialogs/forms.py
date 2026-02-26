from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QCheckBox,
    QDialogButtonBox,
    QMessageBox,
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


@dataclass
class BoolField:
    key: str
    label: str
    default: bool = False
    required: bool = False


FieldSpec = TextField | IntField | BoolField


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
            elif isinstance(spec, BoolField):
                w = QCheckBox()
                w.setChecked(spec.default)
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
                # Show validation message to the user and keep dialog open
                QMessageBox.warning(self, "Validation error", msg)
                # focus first widget to help user correct input
                try:
                    first_key = next(iter(self._widgets))
                    self._widgets[first_key].setFocus()
                except Exception:
                    pass
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
            elif isinstance(spec, BoolField):
                out[spec.key] = bool(w.isChecked())
        return out


def validate_phone_number(v: str) -> str | None:
    """Validate a plain phone number string (digits only, 11-16 chars).

    Returns an error message string on validation failure, or None if valid.
    """
    if not isinstance(v, str) or not v.strip():
        return "Phone number is required."
    v = v.strip()
    if not v.isdigit():
        return "Phone number must contain digits only (no spaces or symbols)."
    if not (11 <= len(v) <= 16):
        return "Phone number must be between 11 and 16 digits (include country code)."
    return None


# Convenience functions


def ask_chat_history(parent: QWidget, *, chat_id_default: str = "", count_default: int = 10):
    dlg = FormDialog(
        "Get Chat History",
        fields=[
            TextField(
                key="chatId",
                label="chatId:",
                default=chat_id_default,
                placeholder="e.g. 7987...@c.us, 1203...@g.us (WhatsApp) or 10000000, -10000000000000 (MAX)",
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
                placeholder="e.g. 7987...@c.us, 1203...@g.us (WhatsApp) or 10000000, -10000000000000 (MAX)",
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


def ask_check_whatsapp(parent: QWidget, *, phone_default: str | None = None):
    """Ask for plain phone number (same look as Get Contact Info) and return the number string.

    Returns None if cancelled, otherwise returns digits-only phone number string.
    """

    def _validator(values: dict[str, Any]) -> str | None:
        return validate_phone_number(values.get("phoneNumber", ""))

    dlg = FormDialog(
        "Check Whatsapp Availability",
        fields=[
            TextField(
                key="phoneNumber",
                label="Phone number:",
                default=str(phone_default or ""),
                placeholder="e.g. 79876543210 (include country code)",
                required=True,
                min_width=420,
            )
        ],
        parent=parent,
        first_focus_key="phoneNumber",
        min_width=480,
        fusion=False,
        validator=_validator,
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()["phoneNumber"]


def ask_get_contact_info(parent: QWidget, *, chat_id_default: str = "", instance_type: str = "whatsapp"):
    """Ask for chatId based on instance type.

    For WhatsApp: asks for phone number and returns '79876543210@c.us'
    For MAX: asks for numeric chatId and returns '10000000' or '-10000000000000'

    Returns None if cancelled, otherwise returns chatId string.
    """
    is_max = instance_type == "max"

    if is_max:
        # MAX: numeric chatId (can be negative for groups)
        def _validator(values: dict[str, Any]) -> str | None:
            v = values.get("chatId", "")
            if not isinstance(v, str) or not v.strip():
                return "Chat ID is required."
            v = v.strip()
            # Allow negative sign for group chats
            if v.startswith("-"):
                digits = v[1:]
            else:
                digits = v
            if not digits.isdigit():
                return "Chat ID must be numeric (e.g. 10000000 for individual, -10000000000000 for group)."
            if not (1 <= len(digits) <= 16):
                return "Chat ID must be between 1 and 16 digits."
            return None

        dlg = FormDialog(
            "Get Contact Info - MAX",
            fields=[
                TextField(
                    key="chatId",
                    label="Chat ID:",
                    default=chat_id_default,
                    placeholder="e.g. 10000000 (individual) or -10000000000000 (group)",
                    required=True,
                    min_width=420,
                )
            ],
            parent=parent,
            first_focus_key="chatId",
            min_width=480,
            fusion=False,
            validator=_validator,
        )
        if dlg.exec() != QDialog.Accepted:
            return None
        return dlg.values()["chatId"]
    else:
        # WhatsApp: phone number with @c.us suffix
        def _validator(values: dict[str, Any]) -> str | None:
            return validate_phone_number(values.get("phoneNumber", ""))

        dlg = FormDialog(
            "Get Contact Info - WhatsApp",
            fields=[
                TextField(
                    key="phoneNumber",
                    label="Phone number:",
                    default=chat_id_default,
                    placeholder="e.g. 79876543210 (include country code)",
                    required=True,
                    min_width=420,
                )
            ],
            parent=parent,
            first_focus_key="phoneNumber",
            min_width=480,
            fusion=False,
            validator=_validator,
        )
        if dlg.exec() != QDialog.Accepted:
            return None
        phone = dlg.values()["phoneNumber"]
        return f"{phone}@c.us"


def ask_check_max(parent: QWidget, *, phone_default: str | None = None):
    """Ask for phone number and force flag for Check MAX Availability.

    Returns None if cancelled, otherwise returns tuple (phone: str, force: bool).
    """

    def _validator(values: dict[str, Any]) -> str | None:
        return validate_phone_number(values.get("phoneNumber", ""))

    dlg = FormDialog(
        "Check MAX Availability",
        fields=[
            TextField(
                key="phoneNumber",
                label="Phone number:",
                default=str(phone_default or ""),
                placeholder="e.g. 79876543210 (include country code)",
                required=True,
                min_width=420,
            ),
            BoolField(
                key="force",
                label="Ignore cache (force):",
                default=False,
            ),
        ],
        parent=parent,
        first_focus_key="phoneNumber",
        min_width=480,
        fusion=False,
        validator=_validator,
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    return vals["phoneNumber"], vals["force"]


# Telegram Authentication dialog helpers


def ask_start_authorization(parent: QWidget, *, phone_default: str | None = None):
    """Ask for phone number to start Telegram authorization.

    Returns None if cancelled, otherwise returns phone number string.
    """

    def _validator(values: dict[str, Any]) -> str | None:
        return validate_phone_number(values.get("phoneNumber", ""))

    dlg = FormDialog(
        "Start Telegram Authorization",
        fields=[
            TextField(
                key="phoneNumber",
                label="Phone number:",
                default=str(phone_default or ""),
                placeholder="e.g. 79876543210 (include country code)",
                required=True,
                min_width=420,
            )
        ],
        parent=parent,
        first_focus_key="phoneNumber",
        min_width=480,
        fusion=False,
        validator=_validator,
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()["phoneNumber"]


def ask_send_authorization_code(parent: QWidget):
    """Ask for Telegram authorization code and optional 2FA password.

    Returns None if cancelled, otherwise returns tuple (code: str, password: str | None).
    """

    def _validator(values: dict[str, Any]) -> str | None:
        code = values.get("code", "").strip()
        if not code:
            return "Authorization code is required."
        if not code.isdigit():
            return "Authorization code must contain only digits."
        return None

    dlg = FormDialog(
        "Send Authorization Code",
        fields=[
            TextField(
                key="code",
                label="Verification code:",
                default="",
                placeholder="e.g. 12345",
                required=True,
                min_width=320,
            ),
            TextField(
                key="password",
                label="2FA password (optional):",
                default="",
                placeholder="Leave empty if 2FA not enabled",
                required=False,
                min_width=320,
            ),
        ],
        parent=parent,
        first_focus_key="code",
        min_width=480,
        fusion=False,
        validator=_validator,
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    password = vals.get("password", "").strip() or None
    return vals["code"], password


def ask_send_authorization_password(parent: QWidget):
    """Ask for Telegram 2FA password.

    Returns None if cancelled, otherwise returns password string.
    """

    def _validator(values: dict[str, Any]) -> str | None:
        password = values.get("password", "").strip()
        if not password:
            return "2FA password is required."
        return None

    dlg = FormDialog(
        "Send 2FA Password",
        fields=[
            TextField(
                key="password",
                label="2FA password:",
                default="",
                placeholder="Enter your two-factor authentication password",
                required=True,
                min_width=420,
            )
        ],
        parent=parent,
        first_focus_key="password",
        min_width=480,
        fusion=False,
        validator=_validator,
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()["password"]


# Group dialog helpers


def ask_create_group(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for new group details.

    Returns None if cancelled, otherwise returns (group_name, chat_ids_list).
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "Comma-separated (e.g. 10000000, 10000001)"
        if is_max
        else "Comma-separated (e.g. 79001234568@c.us, 79001234569@c.us)"
    )

    dlg = FormDialog(
        "Create Group",
        fields=[
            TextField(
                key="groupName",
                label="Group Name:",
                placeholder="Name for the new group",
                required=True,
            ),
            TextField(
                key="chatIds",
                label="Participant Chat IDs:",
                placeholder=chat_placeholder,
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="groupName",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    # Parse comma-separated chat IDs
    chat_ids = [cid.strip() for cid in vals["chatIds"].split(",") if cid.strip()]
    return vals["groupName"], chat_ids


def ask_group_id(parent: QWidget, *, title: str = "Group ID", instance_type: str = "whatsapp"):
    """Ask for a group ID.

    Returns None if cancelled, otherwise returns group ID string.
    """
    is_max = instance_type == "max"
    group_placeholder = (
        "Group Chat ID (e.g. -10000000000000)"
        if is_max
        else "Group Chat ID (e.g. 120363123456789012 or 120363123456789012@g.us)"
    )

    dlg = FormDialog(
        title,
        fields=[
            TextField(
                key="groupId",
                label="Group Chat ID:",
                placeholder=group_placeholder,
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="groupId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()["groupId"]


def ask_update_group_name(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for group ID and new name.

    Returns None if cancelled, otherwise returns (group_id, group_name).
    """
    is_max = instance_type == "max"
    group_placeholder = (
        "Group Chat ID (e.g. -10000000000000)"
        if is_max
        else "Group Chat ID (e.g. 120363123456789012 or 120363123456789012@g.us)"
    )

    dlg = FormDialog(
        "Update Group Name",
        fields=[
            TextField(
                key="groupId",
                label="Group Chat ID:",
                placeholder=group_placeholder,
                required=True,
            ),
            TextField(
                key="groupName",
                label="New Group Name:",
                placeholder="New name for the group",
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="groupId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    return vals["groupId"], vals["groupName"]


def ask_group_participant(parent: QWidget, *, title: str = "Group Participant", instance_type: str = "whatsapp"):
    """Ask for group ID and participant chat ID.

    Returns None if cancelled, otherwise returns (group_id, participant_chat_id).
    """
    is_max = instance_type == "max"
    group_placeholder = (
        "Group Chat ID (e.g. -10000000000000)"
        if is_max
        else "Group Chat ID (e.g. 120363123456789012 or 120363123456789012@g.us)"
    )
    participant_placeholder = (
        "Participant Chat ID (e.g. 10000000)" if is_max else "Participant Chat ID (e.g. 79001234568@c.us)"
    )

    dlg = FormDialog(
        title,
        fields=[
            TextField(
                key="groupId",
                label="Group Chat ID:",
                placeholder=group_placeholder,
                required=True,
            ),
            TextField(
                key="participantChatId",
                label="Participant Chat ID:",
                placeholder=participant_placeholder,
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="groupId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    return vals["groupId"], vals["participantChatId"]


def ask_group_settings(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for group ID and settings.

    Returns None if cancelled, otherwise returns (group_id, allow_edit, allow_send).
    """
    is_max = instance_type == "max"
    group_placeholder = (
        "Group Chat ID (e.g. -10000000000000)"
        if is_max
        else "Group Chat ID (e.g. 120363123456789012 or 120363123456789012@g.us)"
    )

    dlg = FormDialog(
        "Update Group Settings",
        fields=[
            TextField(
                key="groupId",
                label="Group Chat ID:",
                placeholder=group_placeholder,
                required=True,
            ),
            BoolField(
                key="allowParticipantsEditGroupSettings",
                label="Allow participants to edit group settings:",
                default=False,
            ),
            BoolField(
                key="allowParticipantsSendMessages",
                label="Allow participants to send messages:",
                default=True,
            ),
        ],
        parent=parent,
        first_focus_key="groupId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    return vals["groupId"], vals["allowParticipantsEditGroupSettings"], vals["allowParticipantsSendMessages"]


# Service method dialog helpers


def ask_chat_id_simple(parent: QWidget, *, title: str = "Chat ID", instance_type: str = "whatsapp"):
    """Ask for a chat ID.

    Returns None if cancelled, otherwise returns chat ID string.
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 (individual) or -10000000000000 (group)"
        if is_max
        else "e.g. 79001234568@c.us or 120363123456789012@g.us"
    )

    dlg = FormDialog(
        title,
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()["chatId"]


def ask_edit_message(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for chat ID, message ID, and new message text.

    Returns None if cancelled, otherwise returns (chat_id, id_message, message).
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 or -10000000000000" if is_max else "e.g. 79001234568@c.us or 120363123456789012@g.us"
    )

    dlg = FormDialog(
        "Edit Message",
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="idMessage",
                label="Message ID:",
                placeholder="e.g. BAE5367237E13A87",
                required=True,
            ),
            TextField(
                key="message",
                label="New Message Text:",
                placeholder="Updated message content",
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    return vals["chatId"], vals["idMessage"], vals["message"]


def ask_delete_message(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for chat ID, message ID, and delete option.

    Returns None if cancelled, otherwise returns (chat_id, id_message, only_sender_delete).
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 or -10000000000000" if is_max else "e.g. 79001234568@c.us or 120363123456789012@g.us"
    )

    dlg = FormDialog(
        "Delete Message",
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="idMessage",
                label="Message ID:",
                placeholder="e.g. BAE5F4886F6F2D05",
                required=True,
            ),
            BoolField(
                key="onlySenderDelete",
                label="Delete only for me (not for everyone):",
                default=False,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    return vals["chatId"], vals["idMessage"], vals["onlySenderDelete"]


def ask_disappearing_chat(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for chat ID and disappearing message expiration.

    Returns None if cancelled, otherwise returns (chat_id, ephemeral_expiration).
    """
    is_max = instance_type == "max"
    chat_placeholder = "e.g. 10000000" if is_max else "e.g. 79001234568@c.us"

    dlg = FormDialog(
        "Set Disappearing Messages",
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            IntField(
                key="ephemeralExpiration",
                label="Expiration (seconds):",
                default=0,
                min_value=0,
                max_value=7776000,
                step=1,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    # Add helper text
    expiration = vals["ephemeralExpiration"]
    if expiration not in [0, 86400, 604800, 7776000]:
        from PySide6.QtWidgets import QMessageBox

        message_text = (
            "Common values are:\n"
            "0 = Off\n"
            "86400 = 1 day\n"
            "604800 = 7 days\n"
            "7776000 = 90 days\n\n"
            f"You entered: {expiration}\nContinue?"
        )
        reply = QMessageBox.question(
            parent,
            "Confirm Value",
            message_text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return None
    return vals["chatId"], expiration


def ask_mark_message_as_read(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for chat ID and message ID to mark as read.

    Returns None if cancelled, otherwise returns (chat_id, id_message).
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 or -10000000000000" if is_max else "e.g. 79001234568@c.us or 120363123456789012@g.us"
    )

    dlg = FormDialog(
        "Mark Message as Read",
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="idMessage",
                label="Message ID:",
                placeholder="e.g. BAE5367237E13A87",
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    return vals["chatId"], vals["idMessage"]


# Sending dialog helpers


def ask_send_message(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for chat ID and message text.

    Returns None if cancelled, otherwise returns (chat_id, message, quoted_message_id).
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 or -10000000000000" if is_max else "e.g. 79001234568@c.us or 120363123456789012@g.us"
    )

    dlg = FormDialog(
        "Send Text Message",
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="message",
                label="Message:",
                placeholder="Your message text",
                required=True,
            ),
            TextField(
                key="quotedMessageId",
                label="Quote Message ID (optional):",
                placeholder="e.g. BAE587FA1CECF760 (leave empty for no quote)",
                required=False,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    quoted = vals.get("quotedMessageId", "").strip() or None
    return vals["chatId"], vals["message"], quoted


def ask_send_file_by_url(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for chat ID, file URL, filename, and caption.

    Returns None if cancelled, otherwise returns (chat_id, url_file, file_name, caption).
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 or -10000000000000" if is_max else "e.g. 79001234568@c.us or 120363123456789012@g.us"
    )

    return FormDialog(
        "Send File by URL",
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="urlFile",
                label="File URL:",
                placeholder="https://example.com/file.jpg",
                required=True,
            ),
            TextField(
                key="fileName",
                label="File Name:",
                placeholder="file.jpg",
                required=True,
            ),
            TextField(
                key="caption",
                label="Caption (optional):",
                placeholder="Optional caption for the file",
                required=False,
            ),
        ],
        title="Send File by URL",
        icon=QMessageBox.Icon.Information,
    )


def ask_send_text_status(parent: QWidget):
    """Ask for text status parameters.

    Returns None if cancelled, otherwise returns dict with message, backgroundColor, font, participants.
    """
    dlg = FormDialog(
        "Send Text Status",
        fields=[
            TextField(
                key="message",
                label="Status Message:",
                placeholder="Your status message",
                required=True,
            ),
            TextField(
                key="backgroundColor",
                label="Background Color (hex):",
                placeholder="#228B22 (optional)",
                required=False,
            ),
            TextField(
                key="font",
                label="Font:",
                placeholder="SERIF (optional)",
                required=False,
            ),
            TextField(
                key="participants",
                label="Participants (comma-separated):",
                placeholder="70000001234@c.us, 440000001234@c.us (optional)",
                required=False,
            ),
        ],
        parent=parent,
        first_focus_key="message",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()


def ask_send_voice_status(parent: QWidget):
    """Ask for voice status parameters.

    Returns None if cancelled, otherwise returns dict with urlFile, fileName, backgroundColor, participants.
    """
    dlg = FormDialog(
        "Send Voice Status",
        fields=[
            TextField(
                key="urlFile",
                label="Voice File URL:",
                placeholder="https://example.com/audio.mp3",
                required=True,
            ),
            TextField(
                key="fileName",
                label="File Name:",
                placeholder="audio.mp3",
                required=True,
            ),
            TextField(
                key="backgroundColor",
                label="Background Color (hex):",
                placeholder="#228B22 (optional)",
                required=False,
            ),
            TextField(
                key="participants",
                label="Participants (comma-separated):",
                placeholder="70000001234@c.us, 440000001234@c.us (optional)",
                required=False,
            ),
        ],
        parent=parent,
        first_focus_key="urlFile",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()


def ask_send_media_status(parent: QWidget):
    """Ask for media status parameters.

    Returns None if cancelled, otherwise returns dict with urlFile, fileName, caption, participants.
    """
    dlg = FormDialog(
        "Send Media Status",
        fields=[
            TextField(
                key="urlFile",
                label="Media File URL:",
                placeholder="https://example.com/image.jpg",
                required=True,
            ),
            TextField(
                key="fileName",
                label="File Name:",
                placeholder="image.jpg",
                required=True,
            ),
            TextField(
                key="caption",
                label="Caption:",
                placeholder="Optional caption",
                required=False,
            ),
            TextField(
                key="participants",
                label="Participants (comma-separated):",
                placeholder="70000001234@c.us, 440000001234@c.us (optional)",
                required=False,
            ),
        ],
        parent=parent,
        first_focus_key="urlFile",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()


def ask_delete_status(parent: QWidget):
    """Ask for status message ID to delete.

    Returns None if cancelled, otherwise returns dict with idMessage.
    """
    dlg = FormDialog(
        "Delete Status",
        fields=[
            TextField(
                key="idMessage",
                label="Status Message ID:",
                placeholder="e.g. BAE51DE78D6E986B",
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    return vals["chatId"], vals["urlFile"], vals["fileName"], vals.get("caption", "")


def ask_send_poll(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for chat ID, poll question, and options.

    Returns None if cancelled, otherwise returns (chat_id, message, options, multiple_answers).
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 or -10000000000000" if is_max else "e.g. 79001234568@c.us or 120363123456789012@g.us"
    )

    dlg = FormDialog(
        "Send Poll",
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="message",
                label="Poll Question:",
                placeholder="What's your favorite color?",
                required=True,
            ),
            TextField(
                key="options",
                label="Options (comma-separated):",
                placeholder="Red, Green, Blue",
                required=True,
            ),
            BoolField(
                key="multipleAnswers",
                label="Allow multiple selections:",
                default=False,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    # Parse comma-separated options
    options = [opt.strip() for opt in vals["options"].split(",") if opt.strip()]
    return vals["chatId"], vals["message"], options, vals["multipleAnswers"]


def ask_send_location(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for chat ID and location details.

    Returns None if cancelled, otherwise returns (chat_id, latitude, longitude, name_location, address).
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 or -10000000000000" if is_max else "e.g. 79001234568@c.us or 120363123456789012@g.us"
    )

    dlg = FormDialog(
        "Send Location",
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="latitude",
                label="Latitude:",
                placeholder="e.g. 12.3456789",
                required=True,
            ),
            TextField(
                key="longitude",
                label="Longitude:",
                placeholder="e.g. 10.1112131",
                required=True,
            ),
            TextField(
                key="nameLocation",
                label="Location Name (optional):",
                placeholder="e.g. Restaurant",
                required=False,
            ),
            TextField(
                key="address",
                label="Address (optional):",
                placeholder="e.g. 123 Main St, City",
                required=False,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    try:
        latitude = float(vals["latitude"])
        longitude = float(vals["longitude"])
    except ValueError:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(parent, "Invalid Input", "Latitude and Longitude must be valid numbers.")
        return None

    return vals["chatId"], latitude, longitude, vals.get("nameLocation", ""), vals.get("address", "")


def ask_send_contact(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for chat ID and contact details.

    Returns None if cancelled, otherwise returns (chat_id, phone_contact, first_name, middle_name, last_name, company).
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 or -10000000000000" if is_max else "e.g. 79001234568@c.us or 120363123456789012@g.us"
    )

    dlg = FormDialog(
        "Send Contact",
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="phoneContact",
                label="Contact Phone:",
                placeholder="e.g. 79001234568",
                required=True,
            ),
            TextField(
                key="firstName",
                label="First Name:",
                placeholder="John",
                required=True,
            ),
            TextField(
                key="middleName",
                label="Middle Name (optional):",
                placeholder="",
                required=False,
            ),
            TextField(
                key="lastName",
                label="Last Name (optional):",
                placeholder="Doe",
                required=False,
            ),
            TextField(
                key="company",
                label="Company (optional):",
                placeholder="Acme Corp",
                required=False,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    try:
        phone_contact = int(vals["phoneContact"])
    except ValueError:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(parent, "Invalid Input", "Contact phone must be a valid number.")
        return None

    return (
        vals["chatId"],
        phone_contact,
        vals["firstName"],
        vals.get("middleName", ""),
        vals.get("lastName", ""),
        vals.get("company", ""),
    )


def ask_forward_messages(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for source and destination chat IDs and message IDs.

    Returns None if cancelled, otherwise returns (chat_id, chat_id_from, messages).
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 or -10000000000000" if is_max else "e.g. 79001234568@c.us or 120363123456789012@g.us"
    )

    dlg = FormDialog(
        "Forward Messages",
        fields=[
            TextField(
                key="chatIdFrom",
                label="From Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="chatId",
                label="To Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="messages",
                label="Message IDs (comma-separated):",
                placeholder="e.g. BAE587FA1CECF760, BAE5608BC86F2B59",
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="chatIdFrom",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    vals = dlg.values()
    # Parse comma-separated message IDs
    messages = [msg.strip() for msg in vals["messages"].split(",") if msg.strip()]
    return vals["chatId"], vals["chatIdFrom"], messages


def ask_receive_notification(parent: QWidget):
    """Ask for receive timeout.

    Returns None if cancelled, otherwise returns dict with receiveTimeout.
    """
    dlg = FormDialog(
        "Receive Notification",
        fields=[
            TextField(
                key="receiveTimeout",
                label="Receive Timeout (seconds):",
                placeholder="5",
                required=False,
            ),
        ],
        parent=parent,
        first_focus_key="receiveTimeout",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()


def ask_delete_notification(parent: QWidget):
    """Ask for receipt ID.

    Returns None if cancelled, otherwise returns dict with receiptId.
    """
    dlg = FormDialog(
        "Delete Notification",
        fields=[
            TextField(
                key="receiptId",
                label="Receipt ID:",
                placeholder="e.g. 1234567890",
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="receiptId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()


def ask_download_file(parent: QWidget, *, instance_type: str = "whatsapp"):
    """Ask for chat ID and message ID to download file.

    Returns None if cancelled, otherwise returns dict with chatId and idMessage.
    """
    is_max = instance_type == "max"
    chat_placeholder = (
        "e.g. 10000000 or -10000000000000" if is_max else "e.g. 712345678910@c.us or 120363123456789012@g.us"
    )

    dlg = FormDialog(
        "Download File from Message",
        fields=[
            TextField(
                key="chatId",
                label="Chat ID:",
                placeholder=chat_placeholder,
                required=True,
            ),
            TextField(
                key="idMessage",
                label="Message ID:",
                placeholder="e.g. BE1DC86343987976E39B5FF354D7FF12",
                required=True,
            ),
        ],
        parent=parent,
        first_focus_key="chatId",
    )
    if dlg.exec() != QDialog.Accepted:
        return None
    return dlg.values()
