import time, json, traceback, os
from PySide6 import QtGui, QtCore, QtWidgets
from app.version import __version__
from app.resources import resource_path
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
        self.setWindowTitle(f"The Helper ({__version__})")
        self._ctx = None  # {"instance_id": str, "api_url": str, "api_token": str, "ts": float}
        self._ctx_ttl_seconds = 10 * 60
        self._last_chat_id = None

        self._setup_ui()

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
            return self._with_ctx(instance_id, lambda api_url, api_token: api_func(api_url, instance_id, api_token))
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
        root = QtWidgets.QVBoxLayout()
        self._create_instance_input(root)
        self._create_reauthenticate_button(root)
        self._create_tabs(root)
        self._create_output_area(root)
        self.setLayout(root)

    def _create_instance_input(self, root):
        root.addWidget(QtWidgets.QLabel("Instance ID:"))
        self.instance_input = QtWidgets.QLineEdit()
        root.addWidget(self.instance_input)
    
    def _create_reauthenticate_button(self, root):
        reauth_btn = QtWidgets.QPushButton("🔑 Re-authenticate Kibana Session")
        reauth_btn.clicked.connect(self._reauthenticate_kibana)
        reauth_btn.setToolTip("Clear current session and re-authenticate with Kibana")
        root.addWidget(reauth_btn)

    def _create_tabs(self, root):
        tabs = QtWidgets.QTabWidget()
        self._create_account_tab(tabs)
        self._create_journals_tab(tabs)
        self._create_queues_tab(tabs)
        self._create_statuses_tab(tabs)
        root.addWidget(tabs)

    def _create_account_tab(self, tabs):
        account_tab = QtWidgets.QWidget()
        account_layout = QtWidgets.QVBoxLayout(account_tab)
        self.button = self._add_button(account_layout, "Get Instance Information (API Token / URL)", self.run_get_api_token)
        self.state_button = self._add_button(account_layout, "Get Instance State", self.run_get_instance_state)
        self.settings_button = self._add_button(account_layout, "Get Instance Settings", self.run_get_instance_settings)
        self.set_settings_button = self._add_button(account_layout, "Set Instance Settings", self.run_set_instance_settings, "post")
        self.get_wa_settings_button = self._add_button(account_layout, "Get WhatsApp Settings", self.run_get_wa_settings)
        self.get_qr_button = self._add_button(account_layout, "Get QR Code", self.run_get_qr_code)
        self.logout_button = self._add_button(account_layout, "Logout Instance", self.run_logout_instance, "danger")
        self.reboot_button = self._add_button(account_layout, "Reboot Instance", self.run_reboot_instance, "danger")
        account_layout.addStretch(1)
        tabs.addTab(account_tab, "Account")

    def _create_journals_tab(self, tabs):
        journals_tab = QtWidgets.QWidget()
        journals_layout = QtWidgets.QVBoxLayout(journals_tab)
        self.journal_button = self._add_button(journals_layout, "Get Incoming Messages Journal", self.run_get_incoming_msgs_journal)
        self.outgoing_journal_button = self._add_button(journals_layout, "Get Outgoing Messages Journal", self.run_get_outgoing_msgs_journal)
        self.chat_history_button = self._add_button(journals_layout, "Get Chat History", self.run_get_chat_history, "post")
        self.get_message_button = self._add_button(journals_layout, "Get Message", self.run_get_message, "post")
        journals_layout.addStretch(1)
        tabs.addTab(journals_tab, "Journals")

    def _create_queues_tab(self, tabs):
        queue_tab = QtWidgets.QWidget()
        queue_layout = QtWidgets.QVBoxLayout(queue_tab)
        self.msg_count_button = self._add_button(queue_layout, "Get Message Queue Count", self.run_get_msg_queue_count)
        self.msg_queue_button = self._add_button(queue_layout, "Get Messages Queued to Send", self.run_get_msg_queue)
        self.clear_queue_button = self._add_button(queue_layout, "Clear Message Queue to Send", self.run_clear_msg_queue, "post")
        self.webhook_count_button = self._add_button(queue_layout, "Get Webhook Count", self.run_get_webhook_count)
        self.webhook_delete_button = self._add_button(queue_layout, "Delete Incoming Webhooks", self.run_clear_webhooks, "danger")
        queue_layout.addStretch(1)
        tabs.addTab(queue_tab, "Queues")

    def _create_statuses_tab(self, tabs):
        status_tab = QtWidgets.QWidget()
        status_layout = QtWidgets.QVBoxLayout(status_tab)
        self.incoming_status_button = self._add_button(status_layout, "Get Incoming Statuses", self.run_get_incoming_statuses)
        self.outgoing_status_button = self._add_button(status_layout, "Get Outgoing Statuses", self.run_get_outgoing_statuses)
        self.status_stat_button = self._add_button(status_layout, "Get Status Statistic", self.run_get_status_statistic)
        status_layout.addStretch(1)
        tabs.addTab(status_tab, "Statuses")

    def _create_output_area(self, root):
        self.output = QtWidgets.QTextEdit()
        self.output.setReadOnly(True)
        root.addWidget(self.output)

    # Worker handlers

    @QtCore.Slot(object)
    def _on_worker_result(self, payload):
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

            # Allow user to retry settings if confirmation is cancelled
            while True:
                dlg = instance_settings.InstanceSettingsDialog(self, current=settings_dict)
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
                    lambda api_url, api_token: ga.set_instance_settings(
                        api_url, instance_id, api_token, new_settings
                    ),
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
        if isinstance(data, dict) and (t := data.get("type")) in {"alreadyLogged", "error", "qrCode"}:
            qr_link = f"https://qr.green-api.com/wainstance{self._ctx.get('instance_id', '')}/{self._ctx.get('api_token', '')}"
            if t == "alreadyLogged":
                self.output.setPlainText(f"Instance is already authorised.\nTo get a new QR code, first run Logout.\n\nQR link:\n{qr_link}")
            elif t == "error":
                self.output.setPlainText(f"QR error:\n{data.get('message', '')}\n\nQR link:\n{qr_link}")
            else:  # qrCode
                qr.QrCodeDialog(link=qr_link, qr_base64=data.get("message", ""), parent=self).exec()
                self.output.setPlainText(f"QR ready.\n\n{qr_link}")
            return

        self.output.setPlainText(self._pretty_print(data))

    @QtCore.Slot(str)
    def _on_worker_error(self, err: str):
        self.output.setPlainText("Error:\n" + err)

    def _run_async(self, status_text: str, fn):
        self._set_status(status_text)

        if not hasattr(self, "_jobs"):
            self._jobs = []

        thread = QtCore.QThread(self)
        worker = Worker(fn)
        worker.moveToThread(thread)

        job = {"thread": thread, "worker": worker}
        self._jobs.append(job)

        # Disable the clicked button (only if this call was triggered by a QPushButton)
        sender = self.sender()
        btn = sender if isinstance(sender, QtWidgets.QPushButton) else None
        if btn is not None:
            btn.setEnabled(False)

        # Signal connections
        worker.result.connect(self._on_worker_result, QtCore.Qt.QueuedConnection)
        worker.error.connect(self._on_worker_error, QtCore.Qt.QueuedConnection)

        # stop thread loop after worker finishes
        worker.finished.connect(thread.quit, QtCore.Qt.QueuedConnection)

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
        thread.finished.connect(cleanup, QtCore.Qt.QueuedConnection)

        thread.started.connect(worker.run)
        thread.start()

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
        """Get the instance ID from the input field, or show a warning if empty.

        Returns:
            The instance ID string if valid, None otherwise.
        """
        instance_id = self.instance_input.text().strip()
        if not instance_id:
            self.output.setPlainText("Please enter an Instance ID.")
            self.instance_input.setFocus()
            return None
        return instance_id

    def _set_status(self, msg: str):
        self.output.setPlainText(msg)

    def _ctx_is_valid(self, instance_id: str) -> bool:
        if not self._ctx or self._ctx.get("instance_id") != instance_id:
            return False
        if time.time() - float(self._ctx.get("ts", 0)) > self._ctx_ttl_seconds:
            return False
        tok = (self._ctx.get("api_token") or "").strip()
        return bool(tok and tok != "apiToken not found" and not tok.startswith("HTTP ") and self._ctx.get("api_url"))

    def _reauthenticate_kibana(self):
        """Force re-authentication with Kibana by clearing the current session."""
        cred_mgr = get_credential_manager()
        cred_mgr.set_kibana_cookie(None)
        self.output.setPlainText("Clearing current session...")
        if not self._authenticate_kibana():
            self.output.setPlainText("Re-authentication cancelled.")

    def _authenticate_kibana(self) -> bool:
        """
        Authenticate with Kibana using username/password.
        Tries environment credentials first, then prompts user with retry on failure.
        
        Returns:
            True if authentication succeeded or user cancelled, False should never happen
        """
        cred_mgr = get_credential_manager()
        env_username = os.getenv("KIBANA_USER")
        env_password = os.getenv("KIBANA_PASS")
        
        # Try environment credentials first
        if env_username and env_password:
            self.output.setPlainText("⚠ Certificate configured.\n"
                                   "Authenticating with credentials from environment...")
            cookie = get_kibana_session_cookie_with_password(
                env_username,
                env_password,
                cred_mgr.get_certificate_files()
            )
            if cookie:
                cred_mgr.set_kibana_cookie(cookie)
                self.output.setPlainText("✓ Certificate and Kibana session configured!")
                return True
            else:
                self.output.setPlainText("⚠ Automatic login with environment credentials failed.\n"
                                       "Please enter your credentials manually...")
        
        # Prompt for credentials with retry loop
        prefill_username = env_username or ""
        while True:
            login_dialog = KibanaLoginDialog(self, prefill_username=prefill_username)
            if login_dialog.exec() != QtWidgets.QDialog.Accepted:
                self.output.setPlainText("⚠ Kibana authentication cancelled.\n"
                                       "API calls may fail. You can try again later.")
                return True  # Allow user to continue without Kibana session
            
            username, password = login_dialog.get_credentials()
            prefill_username = username  # Remember username for retry
            
            self.output.setPlainText(f"Authenticating as {username}...")
            cookie = get_kibana_session_cookie_with_password(
                username,
                password,
                cred_mgr.get_certificate_files()
            )
            
            if cookie:
                cred_mgr.set_kibana_cookie(cookie)
                self.output.setPlainText("✓ Certificate and Kibana session configured!")
                return True
            else:
                # Authentication failed - ask if user wants to retry
                reply = QtWidgets.QMessageBox.question(
                    self,
                    "Authentication Failed",
                    "Kibana authentication failed. This could be due to:\n"
                    "• Incorrect username or password\n"
                    "• Network issues\n"
                    "• Certificate problems\n\n"
                    "Would you like to try again?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
                )
                
                if reply != QtWidgets.QMessageBox.Yes:
                    self.output.setPlainText("⚠ Kibana authentication skipped.\n"
                                           "API calls may fail. You can try again later.")
                    return True  # Allow user to continue without Kibana session
                # Loop continues to retry

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
                return False
            
            cert_pem, cert_context = cert_result
            if not cred_mgr.set_certificate(cert_pem, cert_context):
                self.output.setPlainText("Failed to configure certificate.")
                return False
            
            # Give feedback about Kibana session status
            if not cred_mgr.has_kibana_cookie() and not self._authenticate_kibana():
                return False
            if cred_mgr.has_kibana_cookie():
                self.output.setPlainText("✓ Certificate and Kibana session configured successfully!")
        
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
        ctx = self._ctx if self._ctx_is_valid(instance_id) else self._fetch_ctx(instance_id)
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
        self._run_simple_api_call("Fetching Instance State...", ga.get_instance_state)

    def run_get_instance_settings(self):
        self._run_simple_api_call("Fetching Instance Settings...", ga.get_instance_settings)

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
        if not self._confirm_action("Confirm Logout", f"Are you sure you want to logout instance {instance_id}?\n\nThis will disconnect the WhatsApp session.", "Logout cancelled."):
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
        if not self._confirm_action("Confirm Reboot", f"Are you sure you want to reboot instance {instance_id}?\n\nThis may interrupt message processing.", "Reboot cancelled."):
            return
        
        def work():
            payload = self._with_ctx(instance_id, lambda u, t: ga.reboot_instance(u, instance_id, t))
            if payload.get("result") == '{"isReboot":true}':
                payload["result"] = "Reboot successful."
            return payload
        
        self._run_async("Rebooting instance...", work)

    def run_get_qr_code(self):
        self._run_simple_api_call("Fetching QR code...", ga.get_qr_code)

    def run_get_wa_settings(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id or not self._ensure_authentication():
            return
        
        def work():
            output = self._with_ctx(instance_id, lambda u, t: ga.get_wa_settings(u, instance_id, t))
            if not isinstance(output, dict):
                output = "WhatsApp account not found. This instance may be for another service. You can check the typeInstance with the Get Instance Settings button." 
            return output
        
        self._run_async("Fetching WhatsApp settings...", work)

    # Journal API methods

    def run_get_incoming_msgs_journal(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return
        if not self._ensure_authentication():
            return
        self._run_async("Fetching Incoming Messages Journal...", 
                       lambda: self._with_ctx(instance_id, lambda u, t: ga.get_incoming_msgs_journal(u, instance_id, t, minutes=1440)))

    def run_get_outgoing_msgs_journal(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return
        if not self._ensure_authentication():
            return
        self._run_async("Fetching Outgoing Messages Journal...",
                       lambda: self._with_ctx(instance_id, lambda u, t: ga.get_outgoing_msgs_journal(u, instance_id, t, minutes=1440)))

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
                lambda api_url, api_token: ga.get_chat_history(
                    api_url, instance_id, api_token, chat_id, count
                ),
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
                lambda api_url, api_token: ga.get_message(
                    api_url, instance_id, api_token, chat_id, id_message
                ),
            )

        self._last_chat_id = chat_id
        self._run_async(f"Fetching Message {id_message}...", work)

    # Queue API methods

    def run_get_msg_queue_count(self):
        self._run_simple_api_call("Fetching Message Queue Count...", ga.get_msg_queue_count)

    def run_get_msg_queue(self):
        self._run_simple_api_call("Fetching Messages Queued to Send...", ga.get_msg_queue)

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
            f"Are you sure you want to clear the message queue to send for instance {instance_id}?\n\nThis will delete ALL queued messages.",
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
        self._run_simple_api_call("Fetching Webhook Count...", ga.get_webhook_count)

    def run_clear_webhooks(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return
        
        # Ensure authentication in main thread
        if not self._ensure_authentication():
            return

        if not self._confirm_action(
            "Confirm Clear Webhooks Queue",
            f"Are you sure you want to clear the incoming webhooks queue for instance {instance_id}?\n\nThis will delete ALL queued incoming webhooks.",
            "Clearing webhooks queue cancelled."
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
                payload["result"] = "Webhook queue cleared successfully." if raw.get("isCleared") else f"Webhook queue could not be cleared.\n\n{raw.get('reason', '')}"
            return payload

        self._run_async("Clearing Incoming Webhook Queue...", work)

    # Status API methods

    def run_get_incoming_statuses(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id or not self._ensure_authentication():
            return
        self._run_async("Fetching Incoming Statuses...",
                       lambda: self._with_ctx(instance_id, lambda u, t: ga.get_incoming_statuses(u, instance_id, t, minutes=1440)))

    def run_get_outgoing_statuses(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id or not self._ensure_authentication():
            return
        self._run_async("Fetching Outgoing Statuses...",
                       lambda: self._with_ctx(instance_id, lambda u, t: ga.get_outgoing_statuses(u, instance_id, t, minutes=1440)))

    def run_get_status_statistic(self):
        instance_id = self._get_instance_id_or_warn()
        if not instance_id:
            return
        
        # Ensure authentication in main thread
        if not self._ensure_authentication():
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

if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    with open(resource_path("../ui/styles.qss"), "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())
    app.setWindowIcon(QtGui.QIcon(resource_path("../ui/greenapiicon.ico")))
    w = App()
    w.setMinimumSize(600, 400)
    w.resize(750, 600)
    w.show()
    app.exec()
