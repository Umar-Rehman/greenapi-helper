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

        self._setup_ui(prefill_username)

    def _setup_ui(self, prefill_username: str):
        layout = QVBoxLayout(self)

        info_label = QLabel(
            "Kibana requires your username/password in addition to the certificate.\n"
            "Enter your credentials to authenticate automatically (no cookie copy)."
        )
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
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Missing Credentials", "Please enter both username and password.")
            return

        self._username = username
        self._password = password
        self.accept()

    def get_credentials(self) -> tuple[str, str]:
        return self._username, self._password
