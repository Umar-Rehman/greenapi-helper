"""Dialog for Kibana username/password login."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QCheckBox,
    QStyleFactory,
    QWidget,
    QMessageBox,
)


class KibanaLoginDialog(QDialog):
    """Dialog to collect Kibana username and password."""

    def __init__(self, parent: QWidget | None = None, *, prefill_username: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Kibana Login")
        self.setStyle(QStyleFactory.create("Fusion"))
        self.setMinimumWidth(500)

        self._username = ""
        self._password = ""
        self._remember_me = False

        self._setup_ui(prefill_username)

    def _setup_ui(self, prefill_username: str):
        layout = QVBoxLayout(self)

        info_label = QLabel("Enter your Kibana credentials to authenticate:")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        form = QFormLayout()

        self.username_input = QLineEdit(prefill_username)
        self.username_input.setPlaceholderText("username")
        form.addRow("Username:", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("password")
        self.password_input.setEchoMode(QLineEdit.Password)
        form.addRow("Password:", self.password_input)

        show_btn = QPushButton("Show")
        show_btn.setCheckable(True)
        show_btn.toggled.connect(self._toggle_password_visibility)
        form.addRow("", show_btn)

        layout.addLayout(form)

        # Add Remember Me checkbox
        self.remember_checkbox = QCheckBox("Remember my credentials (stored securely in Windows Credential Manager)")
        self.remember_checkbox.setChecked(False)
        layout.addWidget(self.remember_checkbox)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.username_input.setFocus()

    def _toggle_password_visibility(self, checked: bool):
        if checked:
            self.password_input.setEchoMode(QLineEdit.Normal)
        else:
            self.password_input.setEchoMode(QLineEdit.Password)

    def _on_accept(self):
        username = self.username_input.text()
        password = self.password_input.text()

        if not username.strip() or not password:
            QMessageBox.warning(self, "Missing Credentials", "Please enter both username and password.")
            return

        self._username = username.strip()
        self._password = password
        self._remember_me = self.remember_checkbox.isChecked()
        self.accept()

    def get_credentials(self) -> tuple[str, str, bool]:
        """Return username, password, and remember_me flag."""
        return self._username, self._password, self._remember_me
