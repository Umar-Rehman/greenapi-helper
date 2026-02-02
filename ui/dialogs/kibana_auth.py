"""Dialog for Kibana authentication."""

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


class KibanaAuthDialog(QDialog):
    """Dialog to collect Kibana authentication credentials."""

    def __init__(self, parent: QWidget | None = None, *, prefill_cookie: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Kibana Authentication")
        self.setStyle(QStyleFactory.create("Fusion"))
        self.setMinimumWidth(500)

        self._kibana_cookie = ""

        self._setup_ui(prefill_cookie)

    def _setup_ui(self, prefill_cookie: str):
        """Setup the user interface."""
        layout = QVBoxLayout(self)

        # Info label
        info_label = QLabel(
            "To retrieve API tokens from Kibana, please provide your Kibana session cookie.\n\n"
            "You can obtain this from your browser:\n"
            "1. Log into Kibana\n"
            "2. Open Developer Tools (F12)\n"
            "3. Go to Application/Storage → Cookies\n"
            "4. Copy the cookie value (usually named 'sid' or similar)"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # Form
        form = QFormLayout()

        self.cookie_input = QLineEdit(prefill_cookie)
        self.cookie_input.setPlaceholderText("Paste Kibana cookie here...")
        self.cookie_input.setMinimumWidth(400)
        self.cookie_input.setEchoMode(QLineEdit.Password)
        form.addRow("Kibana Cookie:", self.cookie_input)

        layout.addLayout(form)

        # Show/Hide password toggle
        show_btn = QPushButton("Show")
        show_btn.setCheckable(True)
        show_btn.toggled.connect(self._toggle_cookie_visibility)
        form.addRow("", show_btn)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.cookie_input.setFocus()

    def _toggle_cookie_visibility(self, checked: bool):
        """Toggle cookie visibility."""
        if checked:
            self.cookie_input.setEchoMode(QLineEdit.Normal)
        else:
            self.cookie_input.setEchoMode(QLineEdit.Password)

    def _on_accept(self):
        """Handle OK button click."""
        cookie = self.cookie_input.text().strip()

        if not cookie:
            QMessageBox.warning(
                self, "Missing Cookie", "Please provide a Kibana cookie."
            )
            self.cookie_input.setFocus()
            return

        self._kibana_cookie = cookie
        self.accept()

    def get_credentials(self) -> str:
        """
        Get the entered Kibana cookie.

        Returns:
            The Kibana cookie string.
        """
        return self._kibana_cookie
