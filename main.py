import sys
import time
from pathlib import Path
import json
import traceback
from PySide6.QtGui import QIcon
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
    QInputDialog,
    QTabWidget,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QStyleFactory,
)
from elk_auth import get_api_token
from api_url_resolver import resolve_api_url
from greenapi_client import (
    get_instance_settings,
    set_instance_settings,
    get_instance_state,
    get_incoming_msgs_journal,
    get_outgoing_msgs_journal,
    get_chat_history,
    get_message,
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
    result = Signal(object)
    error = Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @Slot()
    def run(self):
        try:
            out = self.fn()
            self.result.emit(out)
        except Exception:
            self.error.emit(traceback.format_exc())
        finally:
            self.finished.emit()

class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("The Helper")
        self._ctx = None  # {"instance_id": str, "api_url": str, "api_token": str, "ts": float}
        self._ctx_ttl_seconds = 10 * 60  # 10 minutes
        self._last_chat_id = None

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

        self.chat_history_button = QPushButton("Get Chat History")
        self.chat_history_button.clicked.connect(self.run_get_chat_history)
        self.chat_history_button.setProperty("actionType", "post")
        journals_layout.addWidget(self.chat_history_button)

        self.get_message_button = QPushButton("Get Message")
        self.get_message_button.clicked.connect(self.run_get_message)
        self.get_message_button.setProperty("actionType", "post")
        journals_layout.addWidget(self.get_message_button)

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

    # ---------- Worker handlers ---------- #

    @Slot(object)
    def _on_worker_result(self, payload):
        # payload can be a string OR dict {"ctx":..., "result":...} / {"ctx":..., "error":...}
        if isinstance(payload, dict) and "ctx" in payload:
            self._ctx = payload["ctx"]

            if "error" in payload:
                self.output.setPlainText(str(payload["error"]))
                return

            self.output.setPlainText(self._pretty_print(payload.get("result", "")))
            return

        # fallback: plain text
        self.output.setPlainText(self._pretty_print(str(payload)))

    @Slot(str)
    def _on_worker_error(self, err: str):
        self.output.setPlainText("Error:\n" + err)
    
    def _run_async(self, status_text: str, fn):
        self._set_status(status_text)

        if not hasattr(self, "_jobs"):
            self._jobs = []

        thread = QThread(self)
        worker = Worker(fn)
        worker.moveToThread(thread)

        job = {"thread": thread, "worker": worker}
        self._jobs.append(job)

        # Disable the clicked button
        btn = self.sender()
        if btn is not None:
            btn.setEnabled(False)

        # --- signal wiring ---
        worker.result.connect(self._on_worker_result, Qt.QueuedConnection)
        worker.error.connect(self._on_worker_error, Qt.QueuedConnection)

        # stop thread loop after worker finishes
        worker.finished.connect(thread.quit, Qt.QueuedConnection)

        def cleanup():
            # re-enable button
            if btn is not None:
                btn.setEnabled(True)

            # remove job and delete objects
            try:
                self._jobs.remove(job)
            except ValueError:
                pass
            worker.deleteLater()
            thread.deleteLater()

        # cleanup only when thread is fully stopped
        thread.finished.connect(cleanup, Qt.QueuedConnection)

        thread.started.connect(worker.run)
        thread.start()

    # ---------- Helpers ---------- #

    def _pretty_print(self, value) -> str:
        try:
            if isinstance(value, (dict, list)):
                return json.dumps(value, indent=2, ensure_ascii=False)

            if isinstance(value, (bytes, bytearray)):
                value = value.decode("utf-8", errors="replace")

            if isinstance(value, str):
                parsed = json.loads(value)  # will throw if not JSON
                return json.dumps(parsed, indent=2, ensure_ascii=False)

            return str(value)
        except Exception:
            return str(value)
    
    def _get_instance_id_or_warn(self) -> str | None:
        instance_id = self.instance_input.text().strip()
        if not instance_id:
            self.output.setPlainText("Please enter an Instance ID.")
            self.instance_input.setFocus()
            return None
        return instance_id

    def _set_status(self, msg: str):
        self.output.setPlainText(msg)

    def _ctx_is_valid(self, instance_id: str) -> bool:
        if not self._ctx:
            return False
        if self._ctx.get("instance_id") != instance_id:
            return False
        age = time.time() - float(self._ctx.get("ts", 0))
        if age > self._ctx_ttl_seconds:
            return False

        tok = (self._ctx.get("api_token") or "").strip()
        if not tok or tok == "apiToken not found" or tok.startswith("HTTP "):
            return False

        url = (self._ctx.get("api_url") or "").strip()
        if not url:
            return False

        return True

    def _fetch_ctx(self, instance_id: str) -> dict:
        # Runs in worker thread
        token = get_api_token(instance_id)
        url = resolve_api_url(instance_id)
        return {
            "instance_id": instance_id,
            "api_url": url,
            "api_token": token,
            "ts": time.time(),
        }

    def _with_ctx(self, instance_id: str, call_fn):
        """
        Runs call_fn(api_url, api_token) with cached context if fresh,
        otherwise refreshes token/url first. Returns dict payload.
        """
        if self._ctx_is_valid(instance_id):
            ctx = self._ctx
        else:
            ctx = self._fetch_ctx(instance_id)

        token = ctx.get("api_token", "")
        if not token or token == "apiToken not found" or str(token).startswith("HTTP "):
            return {"ctx": ctx, "error": f"Failed to get apiToken: {token}"}

        api_url = ctx.get("api_url", "")
        if not api_url:
            return {"ctx": ctx, "error": "Failed to resolve apiUrl"}

        result = call_fn(api_url, token)
        return {"ctx": ctx, "result": result}
    
    def _ask_chat_history_params(self, default_chat_id: str = "", default_count: int = 10):
        dlg = QDialog(self)
        dlg.setWindowTitle("Get Chat History")
        dlg.setStyle(QStyleFactory.create("Fusion"))

        form = QFormLayout(dlg)

        chat_edit = QLineEdit(default_chat_id)
        chat_edit.setMinimumWidth(300)

        chat_edit.setPlaceholderText("e.g. XXXXXXXXXXX@c.us or XXXXXXX...@g.us")

        count_spin = QSpinBox()
        count_spin.setRange(1, 1000)
        count_spin.setSingleStep(10)
        count_spin.setValue(default_count)

        form.addRow("chatId:", chat_edit)
        form.addRow("Count:", count_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        form.addRow(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        chat_edit.setFocus()

        if dlg.exec() != QDialog.Accepted:
            return None

        chat_id = chat_edit.text().strip()
        if not chat_id:
            return None

        return chat_id, int(count_spin.value())

    def _ask_get_message_params(self, default_chat_id: str = ""):
        dlg = QDialog(self)
        dlg.setWindowTitle("Get Message")

        form = QFormLayout(dlg)

        chat_edit = QLineEdit(default_chat_id)
        chat_edit.setMinimumWidth(300)
        chat_edit.setPlaceholderText("e.g. 79876543210@c.us or 1203630...@g.us")

        msg_edit = QLineEdit()
        msg_edit.setPlaceholderText("e.g. BAE5F4886F6F2D05")

        form.addRow("chatId:", chat_edit)
        form.addRow("idMessage:", msg_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        form.addRow(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        chat_edit.setFocus()

        if dlg.exec() != QDialog.Accepted:
            return None

        chat_id = chat_edit.text().strip()
        id_message = msg_edit.text().strip()

        if not chat_id or not id_message:
            return None

        return chat_id, id_message

    # ---------- Account Calls Buttons ---------- #

    def run_get_api_token(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        def work():
            # always fetch fresh for the "info" button, so it reflects reality
            ctx = self._fetch_ctx(instance_id)
            return {
                "ctx": ctx,
                "result": (
                    f"API URL:\n{ctx['api_url']}\n\n"
                    f"Instance ID:\n{instance_id}\n\n"
                    f"API Token:\n{ctx['api_token']}\n"
                ),
            }

        self._run_async("Fetching information…", work)

    def run_get_instance_state(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: get_instance_state(api_url, instance_id, api_token),
            )

        self._run_async("Fetching Instance State…", work)

    def run_set_instance_settings(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # TODO: replace this with settings taken from UI later
        settings = {"webhookUrl": ""}  # example payload

        reply = QMessageBox.question(
            self,
            "Confirm setSettings",
            f"Apply settings to instance {instance_id}?\n\nThis changes instance configuration.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            self.output.setPlainText("setSettings cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: set_instance_settings(api_url, instance_id, api_token, settings),
            )

        self._run_async("Applying Instance Settings…", work)

    def run_get_instance_settings(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: get_instance_settings(api_url, instance_id, api_token),
            )

        self._run_async("Fetching Instance Settings…", work)

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

        def work():
            payload = self._with_ctx(
                instance_id,
                lambda api_url, api_token: logout_instance(api_url, instance_id, api_token),
            )
            if isinstance(payload, dict) and payload.get("result") == '{"isLogout":true}':
                payload["result"] = "Logout successful."
            return payload

        self._run_async("Logging out instance…", work)

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

        def work():
            payload = self._with_ctx(
                instance_id,
                lambda api_url, api_token: reboot_instance(api_url, instance_id, api_token),
            )
            if isinstance(payload, dict) and payload.get("result") == '{"isReboot":true}':
                payload["result"] = "Reboot successful."
            return payload

        self._run_async("Rebooting instance…", work)

    # ---------- Journals Calls Buttons ---------- #

    def run_get_incoming_msgs_journal(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: get_incoming_msgs_journal(api_url, instance_id, api_token, minutes=1440),
            )

        self._run_async("Fetching Incoming Messages Journal…", work)

    def run_get_outgoing_msgs_journal(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: get_outgoing_msgs_journal(api_url, instance_id, api_token, minutes=1440),
            )

        self._run_async("Fetching Outgoing Messages Journal…", work)

    def run_get_chat_history(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        params = self._ask_chat_history_params(self._last_chat_id or "", default_count=10)
        if not params:
            self.output.setPlainText("Get Chat History cancelled.")
            return

        chat_id, count = params

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: get_chat_history(api_url, instance_id, api_token, chat_id, count),
            )

        self._last_chat_id = chat_id
        self._run_async(f"Fetching Chat History for {chat_id}…", work)

    def run_get_message(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        params = self._ask_get_message_params(self._last_chat_id or "")
        if not params:
            self.output.setPlainText("Get Message cancelled.")
            return

        chat_id, id_message = params

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: get_message(api_url, instance_id, api_token, chat_id, id_message),
            )

        self._last_chat_id = chat_id
        self._run_async(f"Fetching Message {id_message}…", work)

    # ---------- Queue Calls Buttons ---------- #

    def run_get_msg_queue_count(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: get_msg_queue_count(api_url, instance_id, api_token),
            )

        self._run_async("Fetching Message Queue Count…", work)

    def run_get_msg_queue(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: get_msg_queue(api_url, instance_id, api_token),
            )

        self._run_async("Fetching Messages Queued to Send…", work)

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

        def work():
            payload = self._with_ctx(
                instance_id,
                lambda api_url, api_token: clear_msg_queue_to_send(api_url, instance_id, api_token),
            )
            if isinstance(payload, dict) and payload.get("result") == '{"isCleared":true}':
                payload["result"] = "Message queue cleared successfully."
            return payload

        self._run_async("Clearing Message Queue to Send…", work)

    def run_get_webhook_count(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: get_webhook_count(api_url, instance_id, api_token),
            )

        self._run_async("Fetching Webhook Count…", work)

if __name__ == "__main__":
    app = QApplication([])
    with open(resource_path("ui/styles.qss"), "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())
    app.setWindowIcon(QIcon(resource_path("ui/greenapiicon.ico")))
    w = App()
    w.resize(750, 600)
    w.show()
    app.exec()
