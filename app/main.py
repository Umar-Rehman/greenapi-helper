import time
import json
import traceback
import os
import sys
from PySide6 import QtGui, QtCore, QtWidgets
from app.resources import resource_path
from app.update import get_update_manager, get_current_version
from ui.dialogs import forms, instance_settings, qr
from ui.dialogs.cert_selector import CertificateSelectorDialog
from ui.dialogs.kibana_login import KibanaLoginDialog
from greenapi.elk_auth import get_api_token, get_kibana_session_cookie_with_password
from greenapi.api_url_resolver import resolve_api_url
from greenapi.credentials import get_credential_manager
import greenapi.client as ga


class Worker(QtCore.QObject):
    finished = QtCore.Signal()
    result = QtCore.Signal(object)
    error = QtCore.Signal(str)

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @QtCore.Slot()
    def run(self):
        try:
            out = self.fn()
            self.result.emit(out)
        except Exception:
            self.error.emit(traceback.format_exc())
        finally:
            self.finished.emit()


class App(QtWidgets.QWidget):
    """Main application window for the Green API Helper tool.

    Provides a GUI interface to interact with Green API WhatsApp instances,
    including account management, message handling, and settings configuration.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"The Helper ({get_current_version()})")
        self._ctx = None  # {"instance_id": str, "api_url": str, "api_token": str, "ts": float}
        self._ctx_ttl_seconds = 10 * 60
        self._last_chat_id = None

        # Initialize update manager
        self.update_manager = get_update_manager()
        self.update_manager.update_available.connect(self._on_update_available)
        self.update_manager.update_error.connect(self._on_update_error)

        self._setup_ui()

        # Check for updates after UI is set up
        QtCore.QTimer.singleShot(1000, self.update_manager.check_for_updates)  # Check after 1 second

    def _add_button(self, layout, text, handler, action_type=None):
        """Add a QPushButton to the given layout with specified text and handler.

        Args:
            layout: The QLayout to add the button to.
            text: The button's display text.
            handler: The function to connect to the button's clicked signal.
            action_type: Optional property to set on the button (e.g., 'danger').

        Returns:
            The created QPushButton instance.
        """
        button = QtWidgets.QPushButton(text)
        button.clicked.connect(handler)
        if action_type:
            button.setProperty("actionType", action_type)
        layout.addWidget(button)
        return button

    def _run_simple_api_call(self, status_text, api_func):
        """Run a simple API call asynchronously with status feedback.

        Args:
            status_text: Text to display as the operation status.
            api_func: The API function to call (should take api_url, instance_id, api_token).
        """
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread before async work
        if not self._ensure_authentication():
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: api_func(api_url, instance_id, api_token),
            )

        self._run_async(status_text, work)

    def _confirm_action(self, title, message, cancel_message=None):
        """Show a confirmation dialog and return True if user confirms.

        Args:
            title: Dialog window title.
            message: Confirmation message text.
            cancel_message: Optional message to display in output if cancelled.

        Returns:
            True if user clicks Yes, False otherwise.
        """
        reply = QtWidgets.QMessageBox.question(
            self, title, message, QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            if cancel_message:
                self.output.setPlainText(cancel_message)
            return False
        return True

    def _setup_ui(self):
        # API method mappings for automatic method generation
        # Format: (status_text, api_func, needs_auth)
        self._api_method_mappings = {
            "run_get_instance_state": ("Fetching Instance State...", ga.get_instance_state, False),
            "run_get_instance_settings": ("Fetching Instance Settings...", ga.get_instance_settings, False),
            "run_get_qr_code": ("Fetching QR code...", ga.get_qr_code, False),
            "run_get_msg_queue_count": ("Fetching Message Queue Count...", ga.get_msg_queue_count, False),
            "run_get_msg_queue": ("Fetching Messages Queue...", ga.get_msg_queue, False),
            "run_get_webhook_count": ("Fetching Webhook Queue Count...", ga.get_webhook_count, False),
            "run_get_incoming_statuses": (
                "Fetching Incoming Statuses...",
                lambda u, i, t: ga.get_incoming_statuses(u, i, t, minutes=1440),
                True,
            ),
            "run_get_outgoing_statuses": (
                "Fetching Outgoing Statuses...",
                lambda u, i, t: ga.get_outgoing_statuses(u, i, t, minutes=1440),
                True,
            ),
            "run_get_incoming_msgs_journal": (
                "Fetching Incoming Messages Journal...",
                lambda u, i, t: ga.get_incoming_msgs_journal(u, i, t, minutes=1440),
                True,
            ),
            "run_get_outgoing_msgs_journal": (
                "Fetching Outgoing Messages Journal...",
                lambda u, i, t: ga.get_outgoing_msgs_journal(u, i, t, minutes=1440),
                True,
            ),
            "run_get_contacts": ("Fetching Contacts...", ga.get_contacts, False),
        }

        root = QtWidgets.QVBoxLayout()
        self._create_instance_input(root)
        self._create_reauthenticate_button(root)
        self._create_tabs(root)
        self._create_progress_area(root)
        self._create_output_area(root)
        self.setLayout(root)

    def _run_mapped_api_call(self, method_name: str):
        """Generic handler for API calls using the mapping.

        Consolidated method that handles both simple and authenticated API calls
        through the mapping table, avoiding duplicate authentication checks.
        """
        if method_name not in self._api_method_mappings:
            raise ValueError(f"Unknown API method: {method_name}")

        status_text, api_func, needs_auth = self._api_method_mappings[method_name]

        # _run_simple_api_call already handles auth, so just call it
        # The needs_auth flag is kept in mapping for documentation purposes
        self._run_simple_api_call(status_text, api_func)

    def _create_instance_input(self, root):
        root.addWidget(QtWidgets.QLabel("Instance ID:"))
        self.instance_input = QtWidgets.QLineEdit()
        root.addWidget(self.instance_input)

    def _create_reauthenticate_button(self, root):
        reauth_btn = QtWidgets.QPushButton("Re-authenticate Kibana Session")
        reauth_btn.clicked.connect(self._reauthenticate_kibana)
        reauth_btn.setToolTip("Clear all credentials and allow certificate re-selection")
        root.addWidget(reauth_btn)

    def _create_tabs(self, root):
        tabs = QtWidgets.QTabWidget()
        self._create_account_tab(tabs)
        self._create_journals_tab(tabs)
        self._create_queues_tab(tabs)
        self._create_groups_tab(tabs)
        self._create_sending_tab(tabs)
        self._create_receiving_tab(tabs)
        self._create_statuses_tab(tabs)
        self._create_read_mark_tab(tabs)
        self._create_service_methods_tab(tabs)
        root.addWidget(tabs)

    def _create_account_tab(self, tabs):
        account_tab = QtWidgets.QWidget()
        account_layout = QtWidgets.QVBoxLayout(account_tab)
        self.button = self._add_button(
            account_layout,
            "Get Instance Information (API Token / URL)",
            self.run_get_api_token,
        )
        self.state_button = self._add_button(account_layout, "Get Instance State", self.run_get_instance_state)
        self.settings_button = self._add_button(account_layout, "Get Instance Settings", self.run_get_instance_settings)
        self.set_settings_button = self._add_button(
            account_layout,
            "Set Instance Settings",
            self.run_set_instance_settings,
            "post",
        )
        self.get_account_settings_button = self._add_button(
            account_layout, "Get Account Settings", self.run_get_account_settings
        )
        self.get_qr_button = self._add_button(account_layout, "Get QR Code", self.run_get_qr_code)
        self.get_auth_code_button = self._add_button(
            account_layout, "Get Authorization Code", self.run_get_authorization_code
        )
        self.update_token_button = self._add_button(
            account_layout, "Update API Token", self.run_update_api_token, "danger"
        )
        self.logout_button = self._add_button(account_layout, "Logout Instance", self.run_logout_instance, "danger")
        self.reboot_button = self._add_button(account_layout, "Reboot Instance", self.run_reboot_instance, "danger")
        account_layout.addStretch(1)
        tabs.addTab(account_tab, "Account")

    def _create_journals_tab(self, tabs):
        journals_tab = QtWidgets.QWidget()
        journals_layout = QtWidgets.QVBoxLayout(journals_tab)
        self.journal_button = self._add_button(
            journals_layout,
            "Get Incoming Messages Journal",
            self.run_get_incoming_msgs_journal,
        )
        self.outgoing_journal_button = self._add_button(
            journals_layout,
            "Get Outgoing Messages Journal",
            self.run_get_outgoing_msgs_journal,
        )
        self.chat_history_button = self._add_button(
            journals_layout, "Get Chat History", self.run_get_chat_history, "post"
        )
        self.get_message_button = self._add_button(journals_layout, "Get Message", self.run_get_message, "post")
        journals_layout.addStretch(1)
        tabs.addTab(journals_tab, "Journals")

    def _create_queues_tab(self, tabs):
        queue_tab = QtWidgets.QWidget()
        queue_layout = QtWidgets.QVBoxLayout(queue_tab)
        self.msg_count_button = self._add_button(queue_layout, "Get Message Queue Count", self.run_get_msg_queue_count)
        self.msg_queue_button = self._add_button(queue_layout, "Get Messages Queued to Send", self.run_get_msg_queue)
        self.clear_queue_button = self._add_button(
            queue_layout,
            "Clear Message Queue to Send",
            self.run_clear_msg_queue,
            "post",
        )
        self.webhook_count_button = self._add_button(queue_layout, "Get Webhook Count", self.run_get_webhook_count)
        self.webhook_delete_button = self._add_button(
            queue_layout, "Delete Incoming Webhooks", self.run_clear_webhooks, "danger"
        )
        queue_layout.addStretch(1)
        tabs.addTab(queue_tab, "Queues")

    def _create_groups_tab(self, tabs):
        groups_tab = QtWidgets.QWidget()
        groups_layout = QtWidgets.QVBoxLayout(groups_tab)
        self.create_group_button = self._add_button(groups_layout, "Create Group", self.run_create_group, "post")
        self.update_group_name_button = self._add_button(
            groups_layout, "Update Group Name", self.run_update_group_name, "post"
        )
        self.get_group_data_button = self._add_button(groups_layout, "Get Group Data", self.run_get_group_data)
        self.add_participant_button = self._add_button(
            groups_layout, "Add Group Participant", self.run_add_group_participant, "post"
        )
        self.remove_participant_button = self._add_button(
            groups_layout, "Remove Group Participant", self.run_remove_group_participant, "post"
        )
        self.set_admin_button = self._add_button(groups_layout, "Set Group Admin", self.run_set_group_admin, "post")
        self.remove_admin_button = self._add_button(
            groups_layout, "Remove Group Admin", self.run_remove_group_admin, "post"
        )
        self.leave_group_button = self._add_button(groups_layout, "Leave Group", self.run_leave_group, "danger")
        self.update_group_settings_button = self._add_button(
            groups_layout, "Update Group Settings", self.run_update_group_settings, "post"
        )
        groups_layout.addStretch(1)
        tabs.addTab(groups_tab, "Groups")

    def _create_sending_tab(self, tabs):
        sending_tab = QtWidgets.QWidget()
        sending_layout = QtWidgets.QVBoxLayout(sending_tab)
        self.send_message_button = self._add_button(sending_layout, "Send Text Message", self.run_send_message, "post")
        self.send_file_url_button = self._add_button(
            sending_layout, "Send File by URL", self.run_send_file_by_url, "post"
        )
        self.send_poll_button = self._add_button(sending_layout, "Send Poll", self.run_send_poll, "post")
        self.send_location_button = self._add_button(sending_layout, "Send Location", self.run_send_location, "post")
        self.send_contact_button = self._add_button(sending_layout, "Send Contact", self.run_send_contact, "post")
        self.forward_messages_button = self._add_button(
            sending_layout, "Forward Messages", self.run_forward_messages, "post"
        )
        sending_layout.addStretch(1)
        tabs.addTab(sending_tab, "Sending")

    def _create_receiving_tab(self, tabs):
        receiving_tab = QtWidgets.QWidget()
        receiving_layout = QtWidgets.QVBoxLayout(receiving_tab)
        self.receive_notification_button = self._add_button(
            receiving_layout, "Receive Notification", self.run_receive_notification
        )
        self.delete_notification_button = self._add_button(
            receiving_layout, "Delete Notification", self.run_delete_notification, "danger"
        )
        self.download_file_button = self._add_button(
            receiving_layout, "Download File from Message", self.run_download_file, "post"
        )
        receiving_layout.addStretch(1)
        tabs.addTab(receiving_tab, "Receiving")

    def _create_statuses_tab(self, tabs):
        status_tab = QtWidgets.QWidget()
        status_layout = QtWidgets.QVBoxLayout(status_tab)
        self.send_text_status_button = self._add_button(
            status_layout, "Send Text Status", self.run_send_text_status, "post"
        )
        self.send_voice_status_button = self._add_button(
            status_layout, "Send Voice Status", self.run_send_voice_status, "post"
        )
        self.send_media_status_button = self._add_button(
            status_layout, "Send Media Status", self.run_send_media_status, "post"
        )
        self.delete_status_button = self._add_button(status_layout, "Delete Status", self.run_delete_status, "danger")
        self.incoming_status_button = self._add_button(
            status_layout, "Get Incoming Statuses", self.run_get_incoming_statuses
        )
        self.outgoing_status_button = self._add_button(
            status_layout, "Get Outgoing Statuses", self.run_get_outgoing_statuses
        )
        self.status_stat_button = self._add_button(status_layout, "Get Status Statistic", self.run_get_status_statistic)
        status_layout.addStretch(1)
        tabs.addTab(status_tab, "Statuses")

    def _create_service_methods_tab(self, tabs):
        service_tab = QtWidgets.QWidget()
        service_layout = QtWidgets.QVBoxLayout(service_tab)
        self.get_contacts_button = self._add_button(service_layout, "Get Contacts", self.run_get_contacts)
        self.check_whatsapp_button = self._add_button(
            service_layout, "Check Whatsapp Availability", self.run_check_whatsapp
        )
        self.check_max_button = self._add_button(service_layout, "Check MAX Availability", self.run_check_max)
        self.get_contact_info_button = self._add_button(service_layout, "Get Contact Info", self.run_get_contact_info)
        self.get_avatar_button = self._add_button(service_layout, "Get Avatar", self.run_get_avatar)
        self.edit_message_button = self._add_button(service_layout, "Edit Message", self.run_edit_message, "post")
        self.delete_message_button = self._add_button(
            service_layout, "Delete Message", self.run_delete_message, "danger"
        )
        self.archive_chat_button = self._add_button(service_layout, "Archive Chat", self.run_archive_chat, "post")
        self.unarchive_chat_button = self._add_button(service_layout, "Unarchive Chat", self.run_unarchive_chat, "post")
        self.disappearing_chat_button = self._add_button(
            service_layout, "Set Disappearing Messages", self.run_set_disappearing_chat, "post"
        )
        service_layout.addStretch(1)
        tabs.addTab(service_tab, "Service Methods")

    def _create_read_mark_tab(self, tabs):
        read_mark_tab = QtWidgets.QWidget()
        read_mark_layout = QtWidgets.QVBoxLayout(read_mark_tab)
        self.mark_message_read_button = self._add_button(
            read_mark_layout, "Mark Message as Read", self.run_mark_message_as_read, "post"
        )
        self.mark_chat_read_button = self._add_button(
            read_mark_layout, "Mark Chat as Read", self.run_mark_chat_as_read, "post"
        )
        read_mark_layout.addStretch(1)
        tabs.addTab(read_mark_tab, "Read Mark")

    def _create_progress_area(self, root):
        """Create the progress bar area for showing loading states."""
        # Status label
        self.status_label = QtWidgets.QLabel("Ready")
        self.status_label.setStyleSheet("font-weight: bold; color: #666;")
        root.addWidget(self.status_label)

        # Progress bar
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.setVisible(False)  # Hidden by default
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 3px;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 3px;
            }
        """)
        root.addWidget(self.progress_bar)

    def _create_output_area(self, root):
        self.output = QtWidgets.QTextEdit()
        self.output.setReadOnly(True)
        root.addWidget(self.output)

    # Worker handlers

    @QtCore.Slot(object)
    def _on_worker_result(self, payload, worker=None, button=None):
        # Update status to show success
        self.status_label.setText("Operation completed")
        self.status_label.setStyleSheet("font-weight: bold; color: #4CAF50;")

        # Schedule status reset after a short delay
        QtCore.QTimer.singleShot(2000, lambda: self._reset_status_label())

        if not (isinstance(payload, dict) and "ctx" in payload):
            self.output.setPlainText(self._pretty_print(payload))
            return

        self._ctx = payload["ctx"]

        if "error" in payload:
            self.output.setPlainText(str(payload["error"]))
            return

        result = payload.get("result", "")

        # Open settings dialog flow
        if isinstance(payload, dict) and payload.get("_ui_action") == "open_settings_dialog":
            # Parse the settings JSON (API often returns a JSON string)
            raw = payload.get("result", {})
            try:
                settings_dict = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                settings_dict = {}

            # Detect instance type from API URL
            api_url = self._ctx.get("api_url", "")
            instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

            # Allow user to retry settings if confirmation is cancelled
            while True:
                dlg = instance_settings.InstanceSettingsDialog(self, current=settings_dict, instance_type=instance_type)
                if dlg.exec() != QtWidgets.QDialog.Accepted:
                    self.output.setPlainText("Set settings cancelled.")
                    return

                new_settings = dlg.payload()

                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Confirm Settings",
                    "Apply these settings to the instance?\n\n"
                    + json.dumps(new_settings, indent=2, ensure_ascii=False),
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                )
                if reply == QtWidgets.QMessageBox.Yes:
                    break  # Proceed to apply settings

                # If cancelled, loop back to show dialog again

            instance_id = self._ctx.get("instance_id", "")

            def work_apply():
                payload = self._with_ctx(
                    self._ctx.get("instance_id", ""),
                    lambda api_url, api_token: ga.set_instance_settings(api_url, instance_id, api_token, new_settings),
                )

                # Normalize success response
                result = payload.get("result")

                try:
                    data = json.loads(result) if isinstance(result, str) else result
                except Exception:
                    data = None

                if isinstance(data, dict) and data.get("saveSettings") is True:
                    payload["result"] = "Settings applied successfully."

                return payload

            self._run_async("Applying settings…", work_apply)
            return

        # Try to parse JSON strings
        data = result
        if isinstance(result, str) and (result.strip().startswith(("{", "["))):
            try:
                data = json.loads(result.strip())
            except Exception:
                self.output.setPlainText(self._pretty_print(result))
                return

        # Handle QR response types
        if isinstance(data, dict) and (t := data.get("type")) in {
            "alreadyLogged",
            "error",
            "qrCode",
        }:
            instance_id = self._ctx.get("instance_id", "")
            api_token = self._ctx.get("api_token", "")
            api_url = self._ctx.get("api_url", "")
            # Add /v3 suffix for MAX instances
            v3_suffix = "/v3" if ga.is_max_instance(api_url) else ""
            qr_link = f"https://qr.green-api.com/wainstance{instance_id}/{api_token}{v3_suffix}"
            if t == "alreadyLogged":
                self.output.setPlainText(
                    f"Instance is already authorised.\nTo get a new QR code, first run Logout.\n\nQR link:\n{qr_link}"
                )
            elif t == "error":
                self.output.setPlainText(f"QR error:\n{data.get('message', '')}\n\nQR link:\n{qr_link}")
            else:  # qrCode
                qr.QrCodeDialog(link=qr_link, qr_base64=data.get("message", ""), parent=self).exec()
                self.output.setPlainText(f"QR ready.\n\n{qr_link}")
            return

        self.output.setPlainText(self._pretty_print(data))

    def _reset_status_label(self):
        """Reset status label to default state."""
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("")

    def _handle_api_error(self, error: str) -> str:
        """Parse and display user-friendly error messages for API failures."""
        error_lower = error.lower()

        # HTTP status code mapping
        http_errors = {
            "http 400": "Bad Request (400): Invalid request parameters. Please check your input.",
            "http 401": "Authentication Failed (401): Invalid API token or credentials.",
            "http 403": "Access Denied (403): Insufficient permissions for this operation.",
            "http 404": "Not Found (404): The requested resource doesn't exist.",
            "http 429": "Rate Limited (429): Too many requests. Please wait and try again.",
            "http 500": "Server Error (500): Green API server error. Please try again later.",
            "http 502": "Bad Gateway (502): Server temporarily unavailable. Please try again.",
            "http 503": "Service Unavailable (503): Server is temporarily down. Please try again later.",
        }

        # Check HTTP status codes first
        for code, message in http_errors.items():
            if code in error_lower:
                return message

        # Certificate errors
        if "ssl certificate error" in error_lower or ("certificate" in error_lower and "error" in error_lower):
            return "Certificate Error: Please verify your certificate is properly configured."

        # Network errors
        if "timeout" in error_lower or "timed out" in error_lower:
            return "Request Timeout: The server took too long to respond. Please try again."
        if "connection" in error_lower and ("refused" in error_lower or "failed" in error_lower):
            return "Connection Error: Unable to connect to Green API. Check your internet connection."
        if "dns" in error_lower or "name resolution" in error_lower:
            return "DNS Error: Unable to resolve server address. Check your network settings."

        # API-specific errors
        if "invalid" in error_lower and "token" in error_lower:
            return "Invalid API Token: Please check your API token and try again."
        if "instance" in error_lower and ("not found" in error_lower or "invalid" in error_lower):
            return "Invalid Instance ID: Please verify your Instance ID is correct."

        # Extract useful information from error
        if "request error:" in error_lower:
            return f"Network Error: {error.split(':', 1)[1].strip() if ':' in error else error}"

        lines = error.split("\n")
        for line in lines:
            if "HTTP" in line or "Error:" in line:
                return f"API Error: {line.strip()}"

        return f"An error occurred. Please try again.\n\nDetails: {error[:200]}..."

    @QtCore.Slot(str)
    def _on_worker_error(self, err: str, worker=None, button=None):
        """Handle errors from background worker threads."""
        # Update status to show error
        self.status_label.setText("Operation failed")
        self.status_label.setStyleSheet("font-weight: bold; color: #f44336;")

        # Schedule status reset after a delay
        QtCore.QTimer.singleShot(3000, self._hide_progress)

        user_friendly_error = self._handle_api_error(err)
        self.output.setPlainText(user_friendly_error)

    @QtCore.Slot()
    def _on_worker_finished(self, worker, button=None):
        """Handle worker completion and cleanup."""
        # Re-enable button
        if button is not None:
            button.setEnabled(True)

        # Remove from workers list
        if hasattr(self, "_workers") and worker in self._workers:
            self._workers.remove(worker)

        # Decrement active operations count
        if hasattr(self, "_active_operations"):
            self._active_operations -= 1

        # Hide progress when no active operations
        if self._active_operations <= 0:
            self._hide_progress()

    def _run_async(self, status_text: str, fn):
        """Run function asynchronously using thread pool."""
        self._set_status(status_text)
        self._show_progress(status_text)

        if not hasattr(self, "_active_operations"):
            self._active_operations = 0
        self._active_operations += 1

        # Disable the clicked button (only if this call was triggered by a QPushButton)
        sender = self.sender()
        btn = sender if isinstance(sender, QtWidgets.QPushButton) else None
        if btn is not None:
            btn.setEnabled(False)

        # Create worker and run in thread pool
        worker = Worker(fn)

        def on_result(result):
            self._on_worker_result(result, worker, btn)

        def on_error(error):
            self._on_worker_error(error, worker, btn)

        def on_finished():
            self._on_worker_finished(worker, btn)

        worker.result.connect(on_result, QtCore.Qt.QueuedConnection)
        worker.error.connect(on_error, QtCore.Qt.QueuedConnection)
        worker.finished.connect(on_finished, QtCore.Qt.QueuedConnection)

        # Store reference to prevent garbage collection
        worker._btn = btn
        if not hasattr(self, "_workers"):
            self._workers = []
        self._workers.append(worker)

        # Start in global thread pool
        QtCore.QThreadPool.globalInstance().start(QtCore.QRunnable.create(worker.run))

    # Helpers

    def _pretty_print(self, value) -> str:
        try:
            if isinstance(value, (dict, list)):
                return json.dumps(value, indent=2, ensure_ascii=False)
            if isinstance(value, (bytes, bytearray)):
                value = value.decode("utf-8", errors="replace")
            if isinstance(value, str):
                return json.dumps(json.loads(value), indent=2, ensure_ascii=False)
        except Exception:
            pass
        return str(value)

    def _get_instance_id_or_warn(self) -> str | None:
        """Get the instance ID from the input field, or show a warning if empty/invalid.

        Returns:
            The instance ID string if valid, None otherwise.
        """
        instance_id = self.instance_input.text().strip()
        if not instance_id:
            self.output.setPlainText("Please enter an Instance ID.")
            self.instance_input.setFocus()
            return None

        # Validate format: at least 4 digits, contains only numbers
        if len(instance_id) < 4 or not instance_id.isdigit():
            self.output.setPlainText("Invalid Instance ID format. Must be at least 4 digits and contain only numbers.")
            self.instance_input.setFocus()
            return None
        return instance_id

    def _set_status(self, msg: str):
        self.output.setPlainText(msg)

    def _show_progress(self, status_text: str):
        """Show progress bar and update status label."""
        self.status_label.setText(f"⏳ {status_text}...")
        self.status_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        self.progress_bar.setVisible(True)

    def _hide_progress(self):
        """Hide progress bar and reset status label."""
        self.status_label.setText("Ready")
        self.status_label.setStyleSheet("font-weight: bold; color: #666;")
        self.progress_bar.setVisible(False)

    def _ctx_is_valid(self, instance_id: str) -> bool:
        """Check if cached context is valid for the given instance."""
        if not self._ctx or self._ctx.get("instance_id") != instance_id:
            return False
        if time.time() - float(self._ctx.get("ts", 0)) > self._ctx_ttl_seconds:
            return False
        tok = (self._ctx.get("api_token") or "").strip()
        return bool(tok and tok != "apiToken not found" and not tok.startswith("HTTP ") and self._ctx.get("api_url"))

    def _reauthenticate_kibana(self):
        """Force re-authentication with Kibana by clearing all credentials and starting fresh."""
        cred_mgr = get_credential_manager()
        cred_mgr.clear()  # Clear all certificates and cookies
        self.output.setPlainText("Clearing all credentials...")
        if not self._ensure_authentication():
            self.output.setPlainText("Re-authentication cancelled.")

    def _authenticate_kibana(self) -> bool:
        """
        Authenticate with Kibana using username/password.
        Tries environment credentials first, then prompts user with retry on failure.

        Returns:
            True if authentication succeeded, False if authentication failed or was cancelled
        """
        cred_mgr = get_credential_manager()
        env_username = os.getenv("KIBANA_USER")
        env_password = os.getenv("KIBANA_PASS")

        # Show initial status
        self.output.setPlainText("Starting Kibana authentication...")

        # Try environment credentials first
        if env_username and env_password:
            # Show progress dialog for authentication
            progress = QtWidgets.QProgressDialog("Authenticating with Kibana...", "Please wait...", 0, 0, self)
            progress.setWindowModality(QtCore.Qt.WindowModal)
            progress.setWindowTitle("Kibana Authentication")
            progress.setCancelButton(None)  # No cancel button
            progress.setMinimumDuration(0)  # Show immediately
            progress.setLabelText(f"Authenticating with {env_username} using certificate...")
            progress.show()

            try:
                cookie = get_kibana_session_cookie_with_password(
                    env_username, env_password, cred_mgr.get_certificate_files()
                )
                if cookie:
                    cred_mgr.set_kibana_cookie(cookie)
                    self.output.setPlainText("Certificate and Kibana session configured!")
                    return True
                else:
                    self.output.setPlainText(
                        "Warning: Automatic login with environment credentials failed.\n"
                        "Please enter your credentials manually..."
                    )
            finally:
                progress.close()

        # Prompt for credentials with retry loop
        prefill_username = env_username or ""
        while True:
            login_dialog = KibanaLoginDialog(self, prefill_username=prefill_username)
            if login_dialog.exec() != QtWidgets.QDialog.Accepted:
                self.output.setPlainText("Kibana authentication cancelled.")
                return False  # Authentication failed, don't proceed with API calls

            username, password = login_dialog.get_credentials()
            prefill_username = username  # Remember username for retry

            # Show authentication message in output area
            self.output.setPlainText(
                f"Authenticating as {username} with Kibana...\n\n"
                "Please wait while we establish a secure connection using your certificate."
            )
            QtWidgets.QApplication.processEvents()  # Force UI update

            try:
                cookie = get_kibana_session_cookie_with_password(username, password, cred_mgr.get_certificate_files())

                if cookie:
                    cred_mgr.set_kibana_cookie(cookie)
                    self.output.setPlainText("Certificate and Kibana session configured!")
                    return True
                else:
                    # Authentication failed - show message and allow retry
                    self.output.setPlainText(
                        "Kibana authentication failed. This could be due to:\n"
                        "• Incorrect username or password\n"
                        "• Network issues\n"
                        "• Certificate problems\n\n"
                        "You can try again by entering different credentials, or cancel to skip Kibana authentication."
                    )
                    # Loop continues to allow retry
            except Exception as e:
                # Handle authentication exceptions
                self.output.setPlainText(
                    f"Authentication error: {str(e)}\n\n"
                    "You can try again by entering different credentials, or cancel to skip Kibana authentication."
                )
                # Loop continues to allow retry

    def _ensure_authentication(self) -> bool:
        """
        Ensure the user is authenticated with certificate.
        Certificate selection automatically triggers Kibana session establishment.
        Falls back to manual Kibana cookie entry if automatic authentication fails.

        Returns:
            True if authentication is successful (or user chooses to continue), False if user cancelled
        """
        cred_mgr = get_credential_manager()

        # Check if certificate is configured
        if not cred_mgr.has_certificate():
            cert_dialog = CertificateSelectorDialog(self)
            if cert_dialog.exec() != QtWidgets.QDialog.Accepted:
                self.output.setPlainText("Certificate selection cancelled.")
                return False

            cert_result = cert_dialog.get_selected_certificate()
            if not cert_result:
                self.output.setPlainText("Failed to export certificate.")
                cert_dialog.close()
                return False

            cert_pem, cert_context = cert_result
            if not cred_mgr.set_certificate(cert_pem, cert_context):
                self.output.setPlainText("Failed to configure certificate.")
                cert_dialog.close()
                return False

            # Explicitly close the certificate dialog
            cert_dialog.close()

            # Give feedback about Kibana session status
            self.output.setPlainText("Authenticating with Kibana...")

            if not cred_mgr.has_kibana_cookie() and not self._authenticate_kibana():
                return False
            if cred_mgr.has_kibana_cookie():
                self.output.setPlainText("Certificate and Kibana session configured!")

        # Update client.py to use the configured certificates
        if cert_files := cred_mgr.get_certificate_files():
            ga.set_certificate_files(cert_files[0], cert_files[1])
        return True

    def _fetch_ctx(self, instance_id: str) -> dict:
        """Fetch context (API token and URL) for the given instance."""
        # Authentication should already be done on main thread before this is called
        cred_mgr = get_credential_manager()
        cert_files = cred_mgr.get_certificate_files()
        kibana_cookie = cred_mgr.get_kibana_cookie()

        if not cert_files:
            return {
                "instance_id": instance_id,
                "api_url": "",
                "api_token": "Certificate authentication not configured",
                "ts": time.time(),
            }

        # Note: kibana_cookie may be None if user skipped manual auth and automatic failed
        # Try to get token anyway - it may still work depending on server configuration
        token = get_api_token(instance_id, kibana_cookie=kibana_cookie, cert_files=cert_files)
        url = resolve_api_url(instance_id)
        return {
            "instance_id": instance_id,
            "api_url": url,
            "api_token": token,
            "ts": time.time(),
        }

    def _with_ctx(self, instance_id: str, call_fn):
        """Runs call_fn(api_url, api_token) with cached context if fresh."""
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        ctx = self._ctx
        token = ctx.get("api_token", "")
        if not token or token == "apiToken not found" or token.startswith("HTTP "):
            return {"ctx": ctx, "error": f"Failed to get apiToken: {token}"}
        if not ctx.get("api_url"):
            return {"ctx": ctx, "error": "Failed to resolve apiUrl"}
        return {"ctx": ctx, "result": call_fn(ctx["api_url"], token)}

    # API Methods

    def run_get_api_token(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread before async work
        if not self._ensure_authentication():
            return

        def work():
            ctx = self._fetch_ctx(instance_id)
            return {
                "ctx": ctx,
                "result": (
                    f"API URL:\n{ctx['api_url']}\n\n"
                    f"Instance ID:\n{instance_id}\n\n"
                    f"API Token:\n{ctx['api_token']}\n"
                ),
            }

        self._run_async("Fetching information...", work)

    def run_get_instance_state(self):
        self._run_mapped_api_call("run_get_instance_state")

    def run_get_instance_settings(self):
        self._run_mapped_api_call("run_get_instance_settings")

    def run_set_instance_settings(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        # Fetch current settings first (async)
        def work_fetch():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.get_instance_settings(api_url, instance_id, api_token),
            )

        # we reuse the worker system, but we need to "tag" this result
        def work_fetch_tagged():
            payload = work_fetch()
            payload["_ui_action"] = "open_settings_dialog"
            return payload

        self._run_async("Loading current settings…", work_fetch_tagged)

    def run_logout_instance(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id or not self._ensure_authentication():
            return
        if not self._confirm_action(
            "Confirm Logout",
            f"Are you sure you want to logout instance {instance_id}?\n\nThis will disconnect the WhatsApp session.",
            "Logout cancelled.",
        ):
            return

        def work():
            payload = self._with_ctx(instance_id, lambda u, t: ga.logout_instance(u, instance_id, t))
            if payload.get("result") == '{"isLogout":true}':
                payload["result"] = "Logout successful."
            return payload

        self._run_async("Logging out instance...", work)

    def run_reboot_instance(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id or not self._ensure_authentication():
            return
        if not self._confirm_action(
            "Confirm Reboot",
            f"Are you sure you want to reboot instance {instance_id}?\n\nThis may interrupt message processing.",
            "Reboot cancelled.",
        ):
            return

        def work():
            payload = self._with_ctx(instance_id, lambda u, t: ga.reboot_instance(u, instance_id, t))
            if payload.get("result") == '{"isReboot":true}':
                payload["result"] = "Reboot successful."
            return payload

        self._run_async("Rebooting instance...", work)

    def run_get_qr_code(self):
        self._run_mapped_api_call("run_get_qr_code")

    def run_get_authorization_code(self):
        """Prompt for phone number and get authorization code (WhatsApp only)."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Validate instance type - MAX instances don't support this
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Get Authorization Code is not available for MAX instances.\n"
                "This endpoint is only supported by WhatsApp instances."
            )
            return

        phone = forms.ask_check_whatsapp(self)
        if phone is None:
            self.output.setPlainText("Get Authorization Code cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.get_authorization_code(api_url, instance_id, api_token, phone),
            )

        self._run_async(f"Getting authorization code for {phone}...", work)

    def run_update_api_token(self):
        """Regenerate API token for this instance (WhatsApp only)."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Validate instance type - MAX instances don't support this
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Update API Token is not available for MAX instances.\n"
                "This endpoint is only supported by WhatsApp instances."
            )
            return

        if not self._confirm_action(
            "Confirm Update API Token",
            f"Are you sure you want to regenerate the API token for instance {instance_id}?\n\n"
            "WARNING: The old API token will be invalidated immediately. You will need to update all integrations.",
            "Update API Token cancelled.",
        ):
            return

        def work():
            return self._with_ctx(
                instance_id, lambda api_url, api_token: ga.update_api_token(api_url, instance_id, api_token)
            )

        self._run_async("Updating API token...", work)

    def run_get_account_settings(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id or not self._ensure_authentication():
            return

        def work():
            return self._with_ctx(instance_id, lambda u, t: ga.get_account_settings(u, instance_id, t))

        self._run_async("Fetching account settings...", work)

    # Journal API methods

    def run_get_incoming_msgs_journal(self):
        self._run_mapped_api_call("run_get_incoming_msgs_journal")

    def run_get_outgoing_msgs_journal(self):
        self._run_mapped_api_call("run_get_outgoing_msgs_journal")

    def run_get_chat_history(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return
        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return
        params = forms.ask_chat_history(
            self,
            chat_id_default=(self._last_chat_id or ""),
            count_default=10,
        )
        if not params:
            self.output.setPlainText("Get Chat History cancelled.")
            return

        chat_id, count = params

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.get_chat_history(api_url, instance_id, api_token, chat_id, count),
            )

        self._last_chat_id = chat_id
        self._run_async(f"Fetching Chat History for {chat_id}...", work)

    def run_get_message(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return
        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return
        params = forms.ask_get_message(
            self,
            chat_id_default=(self._last_chat_id or ""),
        )
        if not params:
            self.output.setPlainText("Get Message cancelled.")
            return

        chat_id, id_message = params

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.get_message(api_url, instance_id, api_token, chat_id, id_message),
            )

        self._last_chat_id = chat_id
        self._run_async(f"Fetching Message {id_message}...", work)

    # Queue API methods

    def run_get_msg_queue_count(self):
        self._run_mapped_api_call("run_get_msg_queue_count")

    def run_get_msg_queue(self):
        self._run_mapped_api_call("run_get_msg_queue")

    def run_clear_msg_queue(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Clear Message Queue",
            f"Are you sure you want to clear the message queue to send for instance {instance_id}?\n\n"
            "This will delete ALL queued messages.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            self.output.setPlainText("Clearing message queue cancelled.")
            return

        def work():
            payload = self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.clear_msg_queue_to_send(api_url, instance_id, api_token),
            )
            if isinstance(payload, dict) and payload.get("result") == '{"isCleared":true}':
                payload["result"] = "Message queue cleared successfully."
            return payload

        self._run_async("Clearing Message Queue to Send...", work)

    def run_get_webhook_count(self):
        self._run_mapped_api_call("run_get_webhook_count")

    def run_clear_webhooks(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        if not self._confirm_action(
            "Confirm Clear Webhooks Queue",
            f"Are you sure you want to clear the incoming webhooks queue for instance {instance_id}?\n\n"
            "This will delete ALL queued incoming webhooks.",
            "Clearing webhooks queue cancelled.",
        ):
            return

        def work():
            payload = self._with_ctx(instance_id, lambda u, t: ga.clear_webhooks_queue(u, instance_id, t))
            if not isinstance(payload, dict) or "result" not in payload:
                return payload

            raw = payload["result"]
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except Exception:
                    pass

            if isinstance(raw, dict):
                payload["result"] = (
                    "Webhook queue cleared successfully."
                    if raw.get("isCleared")
                    else f"Webhook queue could not be cleared.\n\n{raw.get('reason', '')}"
                )
            return payload

        self._run_async("Clearing Incoming Webhook Queue...", work)

    # Status API methods

    def run_get_incoming_statuses(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Validate instance type - MAX instances don't have status endpoints
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Status endpoints are not available for MAX instances.\n"
                "MAX instances use the /v3 API and do not support status tracking."
            )
            return

        self._run_mapped_api_call("run_get_incoming_statuses")

    def run_get_outgoing_statuses(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Validate instance type - MAX instances don't have status endpoints
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Status endpoints are not available for MAX instances.\n"
                "MAX instances use the /v3 API and do not support status tracking."
            )
            return

        self._run_mapped_api_call("run_get_outgoing_statuses")

    def run_get_status_statistic(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        # Validate instance type - MAX instances don't have status endpoints
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Status endpoints are not available for MAX instances.\n"
                "MAX instances use the /v3 API and do not support status tracking."
            )
            return

        id_message = forms.ask_status_statistic(self)
        if not id_message:
            self.output.setPlainText("Get Status Statistic cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.get_status_statistic(api_url, instance_id, api_token, id_message),
            )

        self._run_async(f"Fetching Status Statistic for {id_message}...", work)

    def run_send_text_status(self):
        """Send a text status."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        # Validate instance type - MAX instances don't have status endpoints
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Status endpoints are not available for MAX instances.\n"
                "MAX instances use the /v3 API and do not support status tracking."
            )
            return

        result = forms.ask_send_text_status(self)
        if result is None:
            self.output.setPlainText("Send Text Status cancelled.")
            return

        # Parse participants if provided
        participants = None
        if result.get("participants"):
            participants = [p.strip() for p in result["participants"].split(",") if p.strip()]

        # Build kwargs
        kwargs = {"message": result["message"]}
        if result.get("backgroundColor"):
            kwargs["background_color"] = result["backgroundColor"]
        if result.get("font"):
            kwargs["font"] = result["font"]
        if participants:
            kwargs["participants"] = participants

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.send_text_status(api_url, instance_id, api_token, **kwargs),
            )

        self._run_async("Sending text status...", work)

    def run_send_voice_status(self):
        """Send a voice status."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        # Validate instance type - MAX instances don't have status endpoints
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Status endpoints are not available for MAX instances.\n"
                "MAX instances use the /v3 API and do not support status tracking."
            )
            return

        result = forms.ask_send_voice_status(self)
        if result is None:
            self.output.setPlainText("Send Voice Status cancelled.")
            return

        # Parse participants if provided
        participants = None
        if result.get("participants"):
            participants = [p.strip() for p in result["participants"].split(",") if p.strip()]

        # Build kwargs
        kwargs = {
            "url_file": result["urlFile"],
            "file_name": result["fileName"],
        }
        if result.get("backgroundColor"):
            kwargs["background_color"] = result["backgroundColor"]
        if participants:
            kwargs["participants"] = participants

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.send_voice_status(api_url, instance_id, api_token, **kwargs),
            )

        self._run_async("Sending voice status...", work)

    def run_send_media_status(self):
        """Send a media (image/video) status."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        # Validate instance type - MAX instances don't have status endpoints
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Status endpoints are not available for MAX instances.\n"
                "MAX instances use the /v3 API and do not support status tracking."
            )
            return

        result = forms.ask_send_media_status(self)
        if result is None:
            self.output.setPlainText("Send Media Status cancelled.")
            return

        # Parse participants if provided
        participants = None
        if result.get("participants"):
            participants = [p.strip() for p in result["participants"].split(",") if p.strip()]

        # Build kwargs
        kwargs = {
            "url_file": result["urlFile"],
            "file_name": result["fileName"],
        }
        if result.get("caption"):
            kwargs["caption"] = result["caption"]
        if participants:
            kwargs["participants"] = participants

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.send_media_status(api_url, instance_id, api_token, **kwargs),
            )

        self._run_async("Sending media status...", work)

    def run_delete_status(self):
        """Delete a status."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        # Validate instance type - MAX instances don't have status endpoints
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Status endpoints are not available for MAX instances.\n"
                "MAX instances use the /v3 API and do not support status tracking."
            )
            return

        result = forms.ask_delete_status(self)
        if result is None:
            self.output.setPlainText("Delete Status cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.delete_status(
                    api_url, instance_id, api_token, id_message=result["idMessage"]
                ),
            )

        self._run_async("Deleting status...", work)

    def run_get_contacts(self):
        """Run the getContacts API call and show results."""
        self._run_mapped_api_call("run_get_contacts")

    def run_check_whatsapp(self):
        """Prompt for phone number and call checkWhatsapp API."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        # Validate instance type
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Check Whatsapp is not available for MAX instances.\n"
                "MAX instances use the /v3 API and should use 'Check MAX Availability' instead."
            )
            return

        # Prompt for phone number using shared form helper
        phone = forms.ask_check_whatsapp(self)
        if phone is None:
            self.output.setPlainText("Check Whatsapp cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id, lambda api_url, api_token: ga.check_whatsapp(api_url, instance_id, api_token, phone)
            )

        self._run_async(f"Checking Whatsapp for {phone}...", work)

    def run_check_max(self):
        """Prompt for phone number and force flag, then call checkAccount API (MAX only)."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Validate instance type
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        if not ga.is_max_instance(self._ctx.get("api_url", "")):
            self.output.setPlainText(
                "Error: Check MAX is only available for MAX instances.\n"
                "WhatsApp instances should use 'Check Whatsapp Availability' instead."
            )
            return

        result = forms.ask_check_max(self)
        if result is None:
            self.output.setPlainText("Check MAX cancelled.")
            return

        phone, force = result

        def work():
            return self._with_ctx(
                instance_id, lambda api_url, api_token: ga.check_max(api_url, instance_id, api_token, phone, force)
            )

        force_text = " (ignoring cache)" if force else ""
        self._run_async(f"Checking MAX for {phone}{force_text}...", work)

    def run_get_contact_info(self):
        """Prompt for chatId and call GetContactInfo API."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        # Prepare default based on instance type
        default_value = self._last_chat_id or ""
        # If switching instance types, clear the default to avoid confusion
        if instance_type == "whatsapp" and default_value and not default_value.endswith("@c.us"):
            default_value = ""
        elif instance_type == "max" and default_value.endswith("@c.us"):
            default_value = ""
        # For WhatsApp, strip @c.us suffix for input
        elif instance_type == "whatsapp" and default_value.endswith("@c.us"):
            default_value = default_value[:-5]

        chat_id = forms.ask_get_contact_info(self, chat_id_default=default_value, instance_type=instance_type)
        if chat_id is None:
            self.output.setPlainText("Get Contact Info cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id, lambda api_url, api_token: ga.get_contact_info(api_url, instance_id, api_token, chat_id)
            )

        self._last_chat_id = chat_id
        self._run_async(f"Fetching Contact Info for {chat_id}...", work)

    # Group handler methods

    def run_create_group(self):
        """Prompt for group details and create a new group."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_create_group(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Create Group cancelled.")
            return

        group_name, chat_ids = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.create_group(api_url, instance_id, api_token, group_name, chat_ids),
            )

        self._run_async(f"Creating group '{group_name}' with {len(chat_ids)} participants...", work)

    def run_update_group_name(self):
        """Prompt for group ID and new name, then update the group."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_update_group_name(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Update Group Name cancelled.")
            return

        group_id, group_name = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.update_group_name(api_url, instance_id, api_token, group_id, group_name),
            )

        self._run_async(f"Updating group name to '{group_name}'...", work)

    def run_get_group_data(self):
        """Prompt for group ID and get group information."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        group_id = forms.ask_group_id(self, title="Get Group Data", instance_type=instance_type)
        if group_id is None:
            self.output.setPlainText("Get Group Data cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.get_group_data(api_url, instance_id, api_token, group_id),
            )

        self._run_async(f"Fetching group data for {group_id}...", work)

    def run_add_group_participant(self):
        """Prompt for group ID and participant, then add participant to group."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_group_participant(self, title="Add Group Participant", instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Add Group Participant cancelled.")
            return

        group_id, participant_chat_id = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.add_group_participant(
                    api_url, instance_id, api_token, group_id, participant_chat_id
                ),
            )

        self._run_async(f"Adding participant {participant_chat_id} to group...", work)

    def run_remove_group_participant(self):
        """Prompt for group ID and participant, then remove participant from group."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_group_participant(self, title="Remove Group Participant", instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Remove Group Participant cancelled.")
            return

        group_id, participant_chat_id = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.remove_group_participant(
                    api_url, instance_id, api_token, group_id, participant_chat_id
                ),
            )

        self._run_async(f"Removing participant {participant_chat_id} from group...", work)

    def run_set_group_admin(self):
        """Prompt for group ID and participant, then grant admin rights."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_group_participant(self, title="Set Group Admin", instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Set Group Admin cancelled.")
            return

        group_id, participant_chat_id = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.set_group_admin(
                    api_url, instance_id, api_token, group_id, participant_chat_id
                ),
            )

        self._run_async(f"Setting {participant_chat_id} as group admin...", work)

    def run_remove_group_admin(self):
        """Prompt for group ID and participant, then remove admin rights."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_group_participant(self, title="Remove Group Admin", instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Remove Group Admin cancelled.")
            return

        group_id, participant_chat_id = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.remove_group_admin(
                    api_url, instance_id, api_token, group_id, participant_chat_id
                ),
            )

        self._run_async(f"Removing admin rights from {participant_chat_id}...", work)

    def run_leave_group(self):
        """Prompt for group ID and leave the group."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        group_id = forms.ask_group_id(self, title="Leave Group", instance_type=instance_type)
        if group_id is None:
            self.output.setPlainText("Leave Group cancelled.")
            return

        # Confirmation dialog
        reply = QtWidgets.QMessageBox.question(
            self,
            "Confirm Leave Group",
            f"Are you sure you want to leave group {group_id}?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            self.output.setPlainText("Leave Group cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.leave_group(api_url, instance_id, api_token, group_id),
            )

        self._run_async(f"Leaving group {group_id}...", work)

    def run_update_group_settings(self):
        """Prompt for group settings and update them."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_group_settings(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Update Group Settings cancelled.")
            return

        group_id, allow_edit, allow_send = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.update_group_settings(
                    api_url, instance_id, api_token, group_id, allow_edit, allow_send
                ),
            )

        self._run_async(f"Updating group settings for {group_id}...", work)

    # Additional service method handlers

    def run_get_avatar(self):
        """Prompt for chat ID and get avatar."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        chat_id = forms.ask_chat_id_simple(self, title="Get Avatar", instance_type=instance_type)
        if chat_id is None:
            self.output.setPlainText("Get Avatar cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.get_avatar(api_url, instance_id, api_token, chat_id),
            )

        self._run_async(f"Fetching avatar for {chat_id}...", work)

    def run_edit_message(self):
        """Prompt for chat ID, message ID, and new text, then edit the message."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_edit_message(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Edit Message cancelled.")
            return

        chat_id, id_message, message = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.edit_message(
                    api_url, instance_id, api_token, chat_id, id_message, message
                ),
            )

        self._run_async(f"Editing message {id_message}...", work)

    def run_delete_message(self):
        """Prompt for chat ID, message ID, and delete option, then delete the message."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_delete_message(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Delete Message cancelled.")
            return

        chat_id, id_message, only_sender_delete = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.delete_message(
                    api_url, instance_id, api_token, chat_id, id_message, only_sender_delete
                ),
            )

        delete_type = "for me" if only_sender_delete else "for everyone"
        self._run_async(f"Deleting message {id_message} ({delete_type})...", work)

    def run_archive_chat(self):
        """Prompt for chat ID and archive the chat."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        chat_id = forms.ask_chat_id_simple(self, title="Archive Chat", instance_type=instance_type)
        if chat_id is None:
            self.output.setPlainText("Archive Chat cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.archive_chat(api_url, instance_id, api_token, chat_id),
            )

        self._run_async(f"Archiving chat {chat_id}...", work)

    def run_unarchive_chat(self):
        """Prompt for chat ID and unarchive the chat."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        chat_id = forms.ask_chat_id_simple(self, title="Unarchive Chat", instance_type=instance_type)
        if chat_id is None:
            self.output.setPlainText("Unarchive Chat cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.unarchive_chat(api_url, instance_id, api_token, chat_id),
            )

        self._run_async(f"Unarchiving chat {chat_id}...", work)

    def run_set_disappearing_chat(self):
        """Prompt for chat ID and expiration, then set disappearing messages."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_disappearing_chat(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Set Disappearing Messages cancelled.")
            return

        chat_id, ephemeral_expiration = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.set_disappearing_chat(
                    api_url, instance_id, api_token, chat_id, ephemeral_expiration
                ),
            )

        self._run_async(f"Setting disappearing messages for {chat_id} to {ephemeral_expiration}s...", work)

    def run_mark_message_as_read(self):
        """Prompt for chat ID and message ID, then mark as read."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_mark_message_as_read(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Mark Message as Read cancelled.")
            return

        chat_id, id_message = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.mark_message_as_read(
                    api_url, instance_id, api_token, chat_id, id_message
                ),
            )

        self._run_async(f"Marking message {id_message} as read...", work)

    def run_mark_chat_as_read(self):
        """Prompt for chat ID and mark all messages as read."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        chat_id = forms.ask_chat_id_simple(self, title="Mark Chat as Read", instance_type=instance_type)
        if chat_id is None:
            self.output.setPlainText("Mark Chat as Read cancelled.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.mark_chat_as_read(api_url, instance_id, api_token, chat_id),
            )

        self._run_async(f"Marking all messages in {chat_id} as read...", work)

    # Sending handler methods

    def run_send_message(self):
        """Prompt for chat ID and message, then send text message."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_send_message(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Send Message cancelled.")
            return

        chat_id, message, quoted_message_id = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.send_message(
                    api_url, instance_id, api_token, chat_id, message, quoted_message_id
                ),
            )

        self._run_async(f"Sending message to {chat_id}...", work)

    def run_send_file_by_url(self):
        """Prompt for file details and send file by URL."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_send_file_by_url(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Send File by URL cancelled.")
            return

        chat_id, url_file, file_name, caption = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.send_file_by_url(
                    api_url, instance_id, api_token, chat_id, url_file, file_name, caption
                ),
            )

        self._run_async(f"Sending file to {chat_id}...", work)

    def run_send_poll(self):
        """Prompt for poll details and send poll."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_send_poll(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Send Poll cancelled.")
            return

        chat_id, message, options, multiple_answers = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.send_poll(
                    api_url, instance_id, api_token, chat_id, message, options, multiple_answers
                ),
            )

        self._run_async(f"Sending poll to {chat_id}...", work)

    def run_send_location(self):
        """Prompt for location details and send location."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_send_location(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Send Location cancelled.")
            return

        chat_id, latitude, longitude, name_location, address = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.send_location(
                    api_url, instance_id, api_token, chat_id, latitude, longitude, name_location, address
                ),
            )

        self._run_async(f"Sending location to {chat_id}...", work)

    def run_send_contact(self):
        """Prompt for contact details and send contact."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_send_contact(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Send Contact cancelled.")
            return

        chat_id, phone_contact, first_name, middle_name, last_name, company = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.send_contact(
                    api_url, instance_id, api_token, chat_id, phone_contact, first_name, middle_name, last_name, company
                ),
            )

        self._run_async(f"Sending contact to {chat_id}...", work)

    def run_forward_messages(self):
        """Prompt for forward details and forward messages."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        if not self._ensure_authentication():
            return

        # Detect instance type for appropriate placeholders
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        api_url = self._ctx.get("api_url", "")
        instance_type = "max" if ga.is_max_instance(api_url) else "whatsapp"

        result = forms.ask_forward_messages(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Forward Messages cancelled.")
            return

        chat_id, chat_id_from, messages = result

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.forward_messages(
                    api_url, instance_id, api_token, chat_id, chat_id_from, messages
                ),
            )

        self._run_async(f"Forwarding {len(messages)} message(s) from {chat_id_from} to {chat_id}...", work)

    def run_receive_notification(self):
        """Receive incoming notification from the queue with countdown timer."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        result = forms.ask_receive_notification(self)
        if result is None:
            self.output.setPlainText("Receive Notification cancelled.")
            return

        # Get timeout value or default to 5
        timeout = 5
        if result.get("receiveTimeout"):
            try:
                timeout = int(result["receiveTimeout"])
            except ValueError:
                timeout = 5

        # Show initial message in output
        self.output.setPlainText(
            f"Awaiting notifications...\n\nListening for incoming messages or events (timeout: {timeout}s)"
        )

        # Initialize active operations counter
        if not hasattr(self, "_active_operations"):
            self._active_operations = 0
        self._active_operations += 1

        # Create countdown timer
        self._show_progress(f"Receiving notification (timeout: {timeout}s)...")
        remaining_time = [timeout]  # Use list to allow mutation in closure

        # Create timer for countdown updates
        countdown_timer = QtCore.QTimer(self)

        def update_countdown():
            remaining_time[0] -= 1
            if remaining_time[0] > 0:
                self.status_label.setText(f"Receiving notification (timeout: {remaining_time[0]}s)...")

        countdown_timer.timeout.connect(update_countdown)
        countdown_timer.start(1000)  # Update every second

        # Disable button
        sender = self.sender()
        btn = sender if isinstance(sender, QtWidgets.QPushButton) else None
        if btn is not None:
            btn.setEnabled(False)

        # Initialize workers list if needed
        if not hasattr(self, "_workers"):
            self._workers = []

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.receive_notification(
                    api_url, instance_id, api_token, receive_timeout=timeout
                ),
            )

        worker = Worker(work)

        def on_result(result):
            countdown_timer.stop()
            # Handle null response explicitly - check for null string, None, or empty
            result_str = str(result).strip() if result is not None else ""
            if result is None or result_str.lower() in ("null", "none", ""):
                self.status_label.setText("No notification received")
                self.status_label.setStyleSheet("font-weight: bold; color: #FF9800;")
                self.output.setPlainText(
                    f"No notification received within {timeout} seconds.\n\n"
                    "This means no incoming messages or events were detected in the queue.\n"
                    "Try again or increase the timeout value."
                )
                # Re-enable button
                if btn is not None:
                    btn.setEnabled(True)
                QtCore.QTimer.singleShot(3000, self._hide_progress)
            else:
                # Successfully received notification
                self._on_worker_result(result, worker, btn)
                # The worker_finished will be called separately to handle cleanup

        def on_error(error):
            countdown_timer.stop()
            self._on_worker_error(error, worker, btn)

        def on_finished():
            countdown_timer.stop()
            self._on_worker_finished(worker, btn)

        worker.result.connect(on_result, QtCore.Qt.QueuedConnection)
        worker.error.connect(on_error, QtCore.Qt.QueuedConnection)
        worker.finished.connect(on_finished, QtCore.Qt.QueuedConnection)

        # Store reference to prevent garbage collection
        worker._btn = btn
        worker._countdown_timer = countdown_timer
        self._workers.append(worker)

        # Start in global thread pool
        QtCore.QThreadPool.globalInstance().start(QtCore.QRunnable.create(worker.run))

    def run_delete_notification(self):
        """Delete received notification from the queue."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        result = forms.ask_delete_notification(self)
        if result is None:
            self.output.setPlainText("Delete Notification cancelled.")
            return

        try:
            receipt_id = int(result["receiptId"])
        except ValueError:
            self.output.setPlainText("Error: Receipt ID must be a number.")
            return

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.delete_notification(
                    api_url, instance_id, api_token, receipt_id=receipt_id
                ),
            )

        self._run_async(f"Deleting notification (receipt ID: {receipt_id})...", work)

    def run_download_file(self):
        """Download file from incoming message."""
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return

        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        # Detect instance type for placeholder
        if not self._ctx_is_valid(instance_id):
            self._ctx = self._fetch_ctx(instance_id)

        instance_type = "max" if ga.is_max_instance(self._ctx.get("api_url", "")) else "whatsapp"

        result = forms.ask_download_file(self, instance_type=instance_type)
        if result is None:
            self.output.setPlainText("Download File cancelled.")
            return

        chat_id = result["chatId"]
        id_message = result["idMessage"]

        def work():
            return self._with_ctx(
                instance_id,
                lambda api_url, api_token: ga.download_file(api_url, instance_id, api_token, chat_id, id_message),
            )

        self._run_async(f"Downloading file from {chat_id} (message: {id_message})...", work)

    @QtCore.Slot(dict)
    def _on_update_available(self, update_info: dict):
        """Handle when a new update is available."""
        # Show update notification in a non-blocking way
        QtCore.QTimer.singleShot(100, lambda: self._show_simple_update_dialog(update_info))

    def _show_simple_update_dialog(self, update_info: dict):
        """Show a simple update dialog."""
        version = update_info.get("version", "Unknown")
        notes = update_info.get("notes", "New version available")
        download_url = update_info.get("download_url", "")
        changelog_url = update_info.get("changelog_url", "")

        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle("Update Available")
        msg_box.setIcon(QtWidgets.QMessageBox.Information)
        msg_box.setText(f"A new version ({version}) is available!")
        msg_box.setInformativeText(f"Current version: {get_current_version()}\n\n{notes}")

        # Check if self-update is available
        can_self_update = getattr(sys, "frozen", False)

        if can_self_update:
            update_btn = msg_box.addButton("Update Now", QtWidgets.QMessageBox.AcceptRole)
            manual_btn = msg_box.addButton("Download Manually", QtWidgets.QMessageBox.ActionRole)
            msg_box.addButton("Later", QtWidgets.QMessageBox.RejectRole)
        else:
            manual_btn = msg_box.addButton("Download Manually", QtWidgets.QMessageBox.AcceptRole)
            msg_box.addButton("Later", QtWidgets.QMessageBox.RejectRole)

        msg_box.exec()
        clicked_btn = msg_box.clickedButton()

        if can_self_update and clicked_btn == update_btn and download_url:
            # Update Now clicked - perform automatic update
            self.update_manager.perform_self_update(download_url, self)
        elif clicked_btn == manual_btn:
            # Download Manually clicked - open GitHub release page
            url_to_open = changelog_url if changelog_url else download_url
            if url_to_open:
                QtGui.QDesktopServices.openUrl(QtCore.QUrl(url_to_open))

    @QtCore.Slot(str)
    def _on_update_error(self, error_msg: str):
        """Handle update check errors (silently ignore for now)."""
        # Could log to console or show subtle notification if needed
        print(f"Update check failed: {error_msg}")


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    with open(resource_path("ui/styles.qss"), "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())
    app.setWindowIcon(QtGui.QIcon(resource_path("ui/greenapiicon.ico")))
    w = App()
    w.setMinimumSize(600, 400)
    w.resize(750, 600)
    w.show()
    app.exec()
