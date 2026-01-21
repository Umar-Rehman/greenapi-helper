import sys
from pathlib import Path
import json
import traceback
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import (
    Qt,
    QObject,
    Signal,
    Slot,
    QThread,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QMessageBox,
    QTabWidget,
)
from elk_queries import (
    resolve_api_url,
    get_api_token,
    get_instance_settings,
    set_instance_settings,
    get_instance_state,
    get_incoming_msgs_journal,
    get_outgoing_msgs_journal,
    get_msg_queue_count,
    get_msg_queue,
    clear_msg_queue_to_send,
    get_webhook_count,
    reboot_instance,
    logout_instance,
)

# ---------- Resource Path Helper ---------- #
def resource_path(relative_path: str) -> str:
    # When running as a PyInstaller onefile exe, files live under sys._MEIPASS
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / relative_path)

class Worker(QObject):
    finished = Signal()
    result = Signal(str)
    error = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @Slot()
    def run(self):
        try:
            out = self.fn()
            # ensure we always emit a string
            self.result.emit(out if isinstance(out, str) else str(out))
        except Exception:
            self.error.emit(traceback.format_exc())
        finally:
            self.finished.emit()

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("The Helper")

        root = QVBoxLayout()

        # Instance ID input
        root.addWidget(QLabel("Instance ID:"))
        self.instance_input = QLineEdit()
        root.addWidget(self.instance_input)

        # ---------------- Tabs ----------------
        tabs = QTabWidget()

        # ----- Account tab -----
        account_tab = QWidget()
        account_layout = QVBoxLayout(account_tab)

        self.button = QPushButton("Get Instance Information (API Token / URL)")
        self.button.clicked.connect(self.run_get_api_token)
        account_layout.addWidget(self.button)

        self.state_button = QPushButton("Get Instance State")
        self.state_button.clicked.connect(self.run_get_instance_state)
        account_layout.addWidget(self.state_button)

        self.settings_button = QPushButton("Get Instance Settings")
        self.settings_button.clicked.connect(self.run_get_instance_settings)
        account_layout.addWidget(self.settings_button)

        self.logout_button = QPushButton("Logout Instance")
        self.logout_button.clicked.connect(self.run_logout_instance)
        self.logout_button.setProperty("actionType", "danger")
        account_layout.addWidget(self.logout_button)

        self.reboot_button = QPushButton("Reboot Instance")
        self.reboot_button.clicked.connect(self.run_reboot_instance)
        self.reboot_button.setProperty("actionType", "danger")
        account_layout.addWidget(self.reboot_button)

        account_layout.addStretch(1)
        tabs.addTab(account_tab, "Account")

        # ----- Journals tab -----
        journals_tab = QWidget()
        journals_layout = QVBoxLayout(journals_tab)

        self.journal_button = QPushButton("Get Incoming Messages Journal")
        self.journal_button.clicked.connect(self.run_get_incoming_msgs_journal)
        journals_layout.addWidget(self.journal_button)

        self.outgoing_journal_button = QPushButton("Get Outgoing Messages Journal")
        self.outgoing_journal_button.clicked.connect(self.run_get_outgoing_msgs_journal)
        journals_layout.addWidget(self.outgoing_journal_button)

        journals_layout.addStretch(1)
        tabs.addTab(journals_tab, "Journals")

        # ----- Queue tab -----
        queue_tab = QWidget()
        queue_layout = QVBoxLayout(queue_tab)

        self.msg_count_button = QPushButton("Get Message Queue Count")
        self.msg_count_button.clicked.connect(self.run_get_msg_queue_count)
        queue_layout.addWidget(self.msg_count_button)

        self.msg_queue_button = QPushButton("Get Messages Queued to Send")
        self.msg_queue_button.clicked.connect(self.run_get_msg_queue)
        queue_layout.addWidget(self.msg_queue_button)

        self.clear_queue_button = QPushButton("Clear Message Queue to Send")
        self.clear_queue_button.clicked.connect(self.run_clear_msg_queue)
        self.clear_queue_button.setProperty("actionType", "post")
        queue_layout.addWidget(self.clear_queue_button)

        self.webhook_count_button = QPushButton("Get Webhook Count")
        self.webhook_count_button.clicked.connect(self.run_get_webhook_count)
        queue_layout.addWidget(self.webhook_count_button)

        queue_layout.addStretch(1)
        tabs.addTab(queue_tab, "Queue")

        root.addWidget(tabs)

        # Output area (shared across all tabs)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        root.addWidget(self.output)

        self.setLayout(root)

    @Slot(str)
    def _on_worker_result(self, text: str):
        self.output.setPlainText(self._pretty_print(text))

    @Slot(str)
    def _on_worker_error(self, err: str):
        self.output.setPlainText("❌ Error:\n" + err)

    def _run_async(self, status_text: str, fn):
        self._set_status(status_text)

        # Keep a list so multiple clicks don't overwrite previous threads
        if not hasattr(self, "_jobs"):
            self._jobs = []

        thread = QThread(self)
        worker = Worker(fn)
        worker.moveToThread(thread)

        job = {"thread": thread, "worker": worker}
        self._jobs.append(job)

        # --- signal wiring ---
        worker.result.connect(self._on_worker_result, Qt.QueuedConnection)
        worker.error.connect(self._on_worker_error, Qt.QueuedConnection)

        # When worker completes, ask the thread event loop to stop
        worker.finished.connect(thread.quit, Qt.QueuedConnection)

        # When thread actually stops, cleanup safely on the UI thread
        def cleanup():
            try:
                self._jobs.remove(job)
            except ValueError:
                pass
            worker.deleteLater()
            thread.deleteLater()

        thread.finished.connect(cleanup, Qt.QueuedConnection)

        thread.started.connect(worker.run)
        thread.start()

        btn = self.sender()
        btn.setEnabled(False)
        def reenable():
            btn.setEnabled(True)
        thread.finished.connect(reenable, Qt.QueuedConnection)


    # ---------- Helpers ---------- #

    def _pretty_print(self, text: str) -> str:
        """Pretty-print JSON if possible, else return original text."""
        try:
            parsed = json.loads(text)
            return json.dumps(parsed, indent=2, ensure_ascii=False)
        except Exception:
            return text

    def _get_instance_id_or_warn(self) -> str | None:
        instance_id = self.instance_input.text().strip()
        if not instance_id:
            self.output.setPlainText("Please enter an Instance ID.")
            return None
        return instance_id

    def _set_status(self, msg: str):
        self.output.setPlainText(msg)
        QApplication.processEvents()

    def apply_light_palette(app: QApplication):
        p = QPalette()

        # Window + general background
        p.setColor(QPalette.Window, QColor("#E8F6EE"))
        p.setColor(QPalette.Base, QColor("#FFFFFF"))          # QTextEdit/QLineEdit background
        p.setColor(QPalette.AlternateBase, QColor("#F3FBF6"))

        # Text colors
        p.setColor(QPalette.WindowText, Qt.black)
        p.setColor(QPalette.Text, Qt.black)
        p.setColor(QPalette.ButtonText, Qt.black)

        # Buttons
        p.setColor(QPalette.Button, QColor("#FFFFFF"))

        app.setPalette(p)

    # ---------- Account Calls Buttons ---------- #

    def run_get_api_token(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        self._set_status("Fetching information…")
        token = get_api_token(instance_id)
        url = resolve_api_url(instance_id)
        self.output.setPlainText(
            f"API URL:\n{url}\n\n"
            f"Instance ID:\n{instance_id}\n\n"
            f"API Token:\n{self._pretty_print(token)}\n\n"
        )

    def run_get_instance_state(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        self._run_async(
            "Fetching Instance State…",
            lambda: get_instance_state(instance_id)
        )

    def run_set_instance_settings(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        api_token = get_api_token(instance_id)
        if not api_token or api_token == "apiToken not found":
            self.output.setPlainText(f"Failed to get apiToken: {api_token}")
            return

        # For demonstration, we'll set empty settings (you can modify as needed)
        self._set_status("Setting Instance Settings…")
        result = set_instance_settings(instance_id, api_token)
        self.output.setPlainText(self._pretty_print(result))

    def run_get_instance_settings(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        self._set_status("Fetching Instance Settings…")
        settings = get_instance_settings(instance_id)
        self.output.setPlainText(self._pretty_print(settings))

    def run_reboot_instance(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Reboot",
            f"Are you sure you want to reboot instance {instance_id}?\n\nThis may interrupt message processing.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.output.setPlainText("Reboot cancelled.")
            return

        self._set_status("Rebooting instance…")

        api_token = get_api_token(instance_id)
        if not api_token or api_token == "apiToken not found":
            self.output.setPlainText(f"Failed to get apiToken: {api_token}")
            return

        result = reboot_instance(instance_id, api_token)
        if result == '{"isReboot":true}':
            result = "Reboot successful."
        self.output.setPlainText(result)

    def run_logout_instance(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Logout",
            f"Are you sure you want to logout instance {instance_id}?\n\nThis will disconnect the WhatsApp session.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.output.setPlainText("Logout cancelled.")
            return

        self._set_status("Logging out instance…")

        api_token = get_api_token(instance_id)
        if not api_token or api_token == "apiToken not found":
            self.output.setPlainText(f"Failed to get apiToken: {api_token}")
            return

        result = logout_instance(instance_id, api_token)
        if result == '{"isLogout":true}':
            result = "Logout successful."
        self.output.setPlainText(result)

    # ---------- Journals Calls Buttons ---------- #

    def run_get_incoming_msgs_journal(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        self._set_status("Fetching Incoming Messages Journal…")
        journal = get_incoming_msgs_journal(instance_id)
        self.output.setPlainText(self._pretty_print(journal))

    def run_get_outgoing_msgs_journal(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        self._set_status("Fetching Outgoing Messages Journal…")
        journal = get_outgoing_msgs_journal(instance_id)
        self.output.setPlainText(self._pretty_print(journal))

    # ---------- Queue Calls Buttons ---------- #

    def run_get_msg_queue_count(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        self._set_status("Fetching Message Queue Count…")
        count = get_msg_queue_count(instance_id)
        self.output.setPlainText(self._pretty_print(count))

    def run_get_msg_queue(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        self._set_status("Fetching Messages Queued to Send…")
        queued = get_msg_queue(instance_id)
        self.output.setPlainText(self._pretty_print(queued))

    def run_clear_msg_queue(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Clear Message Queue",
            f"Are you sure you want to clear the message queue to send for instance {instance_id}?\n\nThis will delete all queued messages.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.output.setPlainText("Clearing message queue cancelled.")
            return

        self._set_status("Clearing Message Queue to Send…")

        api_token = get_api_token(instance_id)
        if not api_token or api_token == "apiToken not found":
            self.output.setPlainText(f"Failed to get apiToken: {api_token}")
            return

        result = clear_msg_queue_to_send(instance_id, api_token)
        if result == '{"isCleared":true}':
            result = "Message queue cleared successfully."
        self.output.setPlainText(result)

    def run_get_webhook_count(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        self._set_status("Fetching Webhook Count…")
        webhook_count = get_webhook_count(instance_id)
        self.output.setPlainText(self._pretty_print(webhook_count))

if __name__ == "__main__":
    app = QApplication([])
    App.apply_light_palette(app)
    with open(resource_path("ui/styles.qss"), "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())
    w = App()
    w.resize(750, 600)
    w.show()
    app.exec()
