import time
import json
import traceback
import os
import sys
from datetime import datetime
from PySide6 import QtGui, QtCore, QtWidgets
from app.resources import resource_path
from app.update import get_update_manager, get_current_version
from app.tab_config import TAB_CONFIG
from ui.dialogs import forms, instance_settings, qr
from ui.dialogs.cert_selector import CertificateSelectorDialog
from ui.dialogs.kibana_login import KibanaLoginDialog
from ui.dialogs.app_settings import AppSettingsDialog
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

        # Initialize settings for persistence
        self.settings = QtCore.QSettings("GreenAPI", "Helper")

        # Set minimum window size to accommodate tabs better
        self.setMinimumSize(1200, 700)

        # Restore window size or set default
        saved_size = self.settings.value("window_size")
        if saved_size:
            self.resize(saved_size)
        else:
            self.resize(1400, 800)

        # Initialize update manager
        self.update_manager = get_update_manager()
        self.update_manager.update_available.connect(self._on_update_available)
        self.update_manager.update_error.connect(self._on_update_error)

        self._setup_ui()

        # Restore last used instance ID
        self._restore_last_instance()

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

        # Main layout
        main_layout = QtWidgets.QVBoxLayout()

        # Create horizontal splitter for left (controls) and right (output)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Left side - controls
        left_widget = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._create_instance_toolbar(left_layout)
        self._create_tabs(left_layout)
        self._create_history_panel(left_layout)

        # Right side - output area
        right_widget = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self._create_progress_area(right_layout)
        self._create_output_area(right_layout)

        # Add widgets to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)

        # Set minimum widths to prevent collapsing
        left_widget.setMinimumWidth(300)
        right_widget.setMinimumWidth(200)

        # Set initial sizes (give left side enough room to show all tabs without scroll buttons)
        # Left side: ~900px to fit all 9 tabs comfortably, Right side: ~500px for output
        splitter.setSizes([1070, 330])
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        # Make splitter handle more visible and easier to grab
        splitter.setHandleWidth(4)

        # Restore splitter position if saved
        saved_splitter = self.settings.value("splitter_sizes")
        if saved_splitter:
            splitter.restoreState(saved_splitter)

        # Save splitter state when changed
        splitter.splitterMoved.connect(lambda: self.settings.setValue("splitter_sizes", splitter.saveState()))

        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

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

    def _create_instance_toolbar(self, root):
        """Create horizontal toolbar with instance input, type indicator, and action buttons."""
        toolbar_layout = QtWidgets.QHBoxLayout()

        # Instance ID label and input
        toolbar_layout.addWidget(QtWidgets.QLabel("Instance ID:"))

        # Create editable combo box for instance ID with history
        self.instance_input = QtWidgets.QComboBox()
        self.instance_input.setEditable(True)
        self.instance_input.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.instance_input.setFixedWidth(180)
        self.instance_input.lineEdit().setPlaceholderText("Enter instance ID...")

        # Load instance history from settings
        self._load_instance_history()

        # Connect signal to detect instance type when text changes
        self.instance_input.currentTextChanged.connect(self._update_instance_type_indicator)

        toolbar_layout.addWidget(self.instance_input)

        # Add instance type indicator label (will show logo images)
        self.instance_type_label = QtWidgets.QLabel("")
        self.instance_type_label.setScaledContents(False)
        self.instance_type_label.setAlignment(QtCore.Qt.AlignCenter)
        self.instance_type_label.setFixedWidth(100)
        self.instance_type_label.setMaximumHeight(30)
        toolbar_layout.addWidget(self.instance_type_label)

        # Re-authenticate button
        reauth_btn = QtWidgets.QPushButton("Re-authenticate")
        reauth_btn.clicked.connect(self._reauthenticate_kibana)
        reauth_btn.setToolTip("Clear all credentials and allow certificate re-selection")
        reauth_btn.setFixedWidth(130)
        toolbar_layout.addWidget(reauth_btn)

        # Settings button
        settings_btn = QtWidgets.QPushButton("Settings")
        settings_btn.clicked.connect(self._open_settings)
        settings_btn.setToolTip("Application settings and preferences")
        settings_btn.setFixedWidth(90)
        toolbar_layout.addWidget(settings_btn)

        toolbar_layout.addStretch()

        root.addLayout(toolbar_layout)

    def _create_instance_input(self, root):
        # Create horizontal layout for instance ID with type indicator
        instance_layout = QtWidgets.QHBoxLayout()
        instance_layout.addWidget(QtWidgets.QLabel("Instance ID:"))

        # Create editable combo box for instance ID with history
        self.instance_input = QtWidgets.QComboBox()
        self.instance_input.setEditable(True)
        self.instance_input.setInsertPolicy(QtWidgets.QComboBox.NoInsert)
        self.instance_input.setMinimumWidth(200)
        self.instance_input.lineEdit().setPlaceholderText("Enter instance ID...")

        # Load instance history from settings
        self._load_instance_history()

        # Connect signal to detect instance type when text changes
        self.instance_input.currentTextChanged.connect(self._update_instance_type_indicator)

        instance_layout.addWidget(self.instance_input, stretch=1)

        # Add instance type indicator label (will show logo images)
        self.instance_type_label = QtWidgets.QLabel("")
        self.instance_type_label.setScaledContents(False)
        self.instance_type_label.setAlignment(QtCore.Qt.AlignCenter)
        self.instance_type_label.setMinimumWidth(100)
        self.instance_type_label.setMaximumHeight(30)
        instance_layout.addWidget(self.instance_type_label)

        root.addLayout(instance_layout)

    def _create_reauthenticate_button(self, root):
        reauth_btn = QtWidgets.QPushButton("Re-authenticate Kibana Session")
        reauth_btn.clicked.connect(self._reauthenticate_kibana)
        reauth_btn.setToolTip("Clear all credentials and allow certificate re-selection")
        root.addWidget(reauth_btn)

    def _create_tabs(self, root):
        tabs = QtWidgets.QTabWidget()

        # Create all tabs from configuration
        for tab_name in TAB_CONFIG.keys():
            self._create_tab_from_config(tabs, tab_name)

        # Store reference for tab management
        self.tabs = tabs

        # Connect signal to save tab changes
        tabs.currentChanged.connect(self._on_tab_changed)

        # Restore last active tab or use default
        remember_last_tab = self.settings.value("remember_last_tab", True, type=bool)
        if remember_last_tab:
            last_tab = self.settings.value("last_tab_index", 0, type=int)
        else:
            last_tab = self.settings.value("default_tab_index", 0, type=int)

        if 0 <= last_tab < tabs.count():
            tabs.setCurrentIndex(last_tab)

        root.addWidget(tabs)

    def _create_tab_from_config(self, tabs, tab_name):
        """Create a tab dynamically from configuration.

        Args:
            tabs: QTabWidget to add the tab to.
            tab_name: Name of the tab from TAB_CONFIG.
        """
        tab_widget = QtWidgets.QWidget()
        tab_layout = QtWidgets.QVBoxLayout(tab_widget)

        config = TAB_CONFIG[tab_name]

        for section in config["sections"]:
            # Create section group box
            group = QtWidgets.QGroupBox(section["title"])
            group_layout = QtWidgets.QVBoxLayout()

            # Add buttons to the section
            for button_config in section["buttons"]:
                handler_name = button_config["handler"]
                handler = getattr(self, handler_name)
                action_type = button_config.get("action_type")

                self._add_button(group_layout, button_config["text"], handler, action_type)

            group.setLayout(group_layout)
            tab_layout.addWidget(group)

        tab_layout.addStretch(1)
        tabs.addTab(tab_widget, tab_name)

    def _create_history_panel(self, root):
        """Create request history panel at bottom of left side."""
        # Create container
        history_container = QtWidgets.QGroupBox("Request History")
        history_layout = QtWidgets.QVBoxLayout(history_container)

        # Toolbar with clear button
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.addStretch()

        clear_history_btn = QtWidgets.QPushButton("Clear")
        clear_history_btn.setToolTip("Clear request history")
        clear_history_btn.clicked.connect(self._clear_request_history)
        clear_history_btn.setMaximumWidth(80)
        toolbar.addWidget(clear_history_btn)

        history_layout.addLayout(toolbar)

        # History list
        self.history_list = QtWidgets.QListWidget()
        self.history_list.setMaximumHeight(150)
        self.history_list.setAlternatingRowColors(True)
        self.history_list.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.history_list.customContextMenuRequested.connect(self._show_history_context_menu)
        history_layout.addWidget(self.history_list)

        # Initialize history storage
        self.request_history = []
        self._load_request_history()

        root.addWidget(history_container)

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
        # Create output container with toolbar
        output_container = QtWidgets.QVBoxLayout()

        # Create toolbar with Clear, Copy, and Export buttons
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.addWidget(QtWidgets.QLabel("Output:"))
        toolbar.addStretch()

        # Clear button
        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.setToolTip("Clear output area")
        clear_btn.clicked.connect(self._clear_output)
        clear_btn.setMaximumWidth(80)
        toolbar.addWidget(clear_btn)

        # Copy button
        copy_btn = QtWidgets.QPushButton("Copy")
        copy_btn.setToolTip("Copy output to clipboard")
        copy_btn.clicked.connect(self._copy_output)
        copy_btn.setMaximumWidth(80)
        toolbar.addWidget(copy_btn)

        # Export button
        export_btn = QtWidgets.QPushButton("Export")
        export_btn.setToolTip("Export output to file")
        export_btn.clicked.connect(self._export_output)
        export_btn.setMaximumWidth(80)
        toolbar.addWidget(export_btn)

        output_container.addLayout(toolbar)

        # Create search bar
        search_bar = QtWidgets.QHBoxLayout()
        search_bar.addWidget(QtWidgets.QLabel("Find:"))

        self.search_field = QtWidgets.QLineEdit()
        self.search_field.setPlaceholderText("Search in output...")
        self.search_field.textChanged.connect(self._on_search_text_changed)
        self.search_field.returnPressed.connect(self._find_next)
        search_bar.addWidget(self.search_field)

        # Match count label
        self.match_count_label = QtWidgets.QLabel("")
        self.match_count_label.setMinimumWidth(80)
        search_bar.addWidget(self.match_count_label)

        # Previous button
        prev_btn = QtWidgets.QPushButton("◀ Prev")
        prev_btn.setToolTip("Previous match")
        prev_btn.clicked.connect(self._find_previous)
        prev_btn.setMaximumWidth(80)
        search_bar.addWidget(prev_btn)

        # Next button
        next_btn = QtWidgets.QPushButton("Next ▶")
        next_btn.setToolTip("Next match")
        next_btn.clicked.connect(self._find_next)
        next_btn.setMaximumWidth(80)
        search_bar.addWidget(next_btn)

        output_container.addLayout(search_bar)

        # Create output text area
        self.output = QtWidgets.QTextEdit()
        self.output.setReadOnly(True)

        # Apply saved output settings
        word_wrap = self.settings.value("word_wrap_output", True, type=bool)
        if word_wrap:
            self.output.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
        else:
            self.output.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)

        font_size = self.settings.value("output_font_size", 10, type=int)
        font = self.output.font()
        font.setPointSize(font_size)
        self.output.setFont(font)

        # Initialize search tracking
        self.search_matches = []
        self.current_match_index = -1

        output_container.addWidget(self.output)

        root.addLayout(output_container)

    # Worker handlers

    @QtCore.Slot(object)
    def _on_worker_result(self, payload, worker=None, button=None):
        # Update status to show success
        self.status_label.setText("Operation completed")
        self.status_label.setStyleSheet("font-weight: bold; color: #4CAF50;")

        # Schedule status reset after a short delay
        QtCore.QTimer.singleShot(2000, lambda: self._reset_status_label())

        # Capture output for history
        output_text = ""
        if not (isinstance(payload, dict) and "ctx" in payload):
            output_text = self._pretty_print(payload)
            self.output.setPlainText(output_text)

        # Add to history with output
        if worker and hasattr(worker, "_operation_name"):
            self._add_to_history(
                method_name=worker._operation_name,
                instance_id=getattr(worker, "_instance_id", ""),
                success=True,
                output=output_text or self._pretty_print(payload),
            )

        if not (isinstance(payload, dict) and "ctx" in payload):
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

        # Add to history as failed with error output
        if worker and hasattr(worker, "_operation_name"):
            self._add_to_history(
                method_name=worker._operation_name,
                instance_id=getattr(worker, "_instance_id", ""),
                success=False,
                output=user_friendly_error,
            )

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

        # Store operation context for history tracking
        # Use button text if available, otherwise use status text
        if btn is not None and hasattr(btn, "text"):
            worker._operation_name = btn.text()
        else:
            worker._operation_name = status_text
        worker._instance_id = self.instance_input.currentText() if hasattr(self, "instance_input") else ""

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

    def _load_instance_history(self):
        """Load instance ID history from settings."""
        history = self.settings.value("instance_history", [])
        if not isinstance(history, list):
            history = []

        # Add items to combo box (most recent first)
        for instance_id in history[:10]:  # Limit to 10 most recent
            self.instance_input.addItem(str(instance_id))

    def _save_instance_to_history(self, instance_id: str):
        """Save instance ID to history.

        Args:
            instance_id: The instance ID to save
        """
        if not instance_id:
            return

        # Get current history
        history = self.settings.value("instance_history", [])
        if not isinstance(history, list):
            history = []

        # Remove if already exists (to move to top)
        if instance_id in history:
            history.remove(instance_id)

        # Add to beginning
        history.insert(0, instance_id)

        # Keep only last 10
        history = history[:10]

        # Save back to settings
        self.settings.setValue("instance_history", history)

        # Update combo box
        current_text = self.instance_input.currentText()
        self.instance_input.clear()
        self._load_instance_history()
        self.instance_input.setCurrentText(current_text)

    def _restore_last_instance(self):
        """Restore the last used instance ID."""
        last_instance = self.settings.value("last_instance_id", "")
        if last_instance:
            self.instance_input.setCurrentText(last_instance)
            self._update_instance_type_indicator(last_instance)

    def _update_instance_type_indicator(self, instance_id: str):
        """Update the instance type indicator label.

        Args:
            instance_id: The instance ID to check
        """
        if not instance_id or not instance_id.strip():
            self.instance_type_label.clear()
            self.instance_type_label.setPixmap(QtGui.QPixmap())
            self.instance_type_label.setStyleSheet("")
            return

        # Keep transparent until at least 10 digits entered
        if len(instance_id) < 10 or not instance_id.isdigit():
            self.instance_type_label.clear()
            self.instance_type_label.setPixmap(QtGui.QPixmap())
            self.instance_type_label.setStyleSheet("")
            return

        # Validate it's exactly 10 digits
        if len(instance_id) != 10:
            self.instance_type_label.setPixmap(QtGui.QPixmap())  # Clear any pixmap
            self.instance_type_label.setText("Invalid")
            self.instance_type_label.setStyleSheet(
                "font-weight: bold; padding: 2px 8px; " "background-color: #FF9800; color: white; border-radius: 3px;"
            )
            return

        # Extract pool prefix (first 2 digits)
        pool_prefix = instance_id[:2]

        # Known MAX prefixes (from api_url_resolver - those with /v3 path)
        max_prefixes = ("31", "35")

        # Known WhatsApp prefixes (from api_url_resolver - RULES_EXACT and RULES_PREFIX)
        whatsapp_prefixes = ("11", "22", "33", "55", "57", "71", "77", "99")

        if pool_prefix in max_prefixes:
            # MAX instance - show logo
            pixmap = QtGui.QPixmap(resource_path("ui/Max_logo.png"))
            if not pixmap.isNull():
                # Scale to fit height while maintaining aspect ratio
                scaled_pixmap = pixmap.scaledToHeight(28, QtCore.Qt.SmoothTransformation)
                self.instance_type_label.setPixmap(scaled_pixmap)
                self.instance_type_label.setStyleSheet(
                    "padding: 2px 8px; " "background-color: #2196F3; border-radius: 3px;"
                )
            else:
                self.instance_type_label.setText("MAX")
                self.instance_type_label.setStyleSheet(
                    "font-weight: bold; padding: 2px 8px; "
                    "background-color: #2196F3; color: white; border-radius: 3px;"
                )
        elif pool_prefix in whatsapp_prefixes:
            # WhatsApp instance - show logo
            pixmap = QtGui.QPixmap(resource_path("ui/WhatsApp_logo.png"))
            if not pixmap.isNull():
                # Scale to fit height while maintaining aspect ratio
                scaled_pixmap = pixmap.scaledToHeight(28, QtCore.Qt.SmoothTransformation)
                self.instance_type_label.setPixmap(scaled_pixmap)
                self.instance_type_label.setStyleSheet(
                    "padding: 2px 8px; " "background-color: #25D366; border-radius: 3px;"
                )
            else:
                self.instance_type_label.setText("WhatsApp")
                self.instance_type_label.setStyleSheet(
                    "font-weight: bold; padding: 2px 8px; "
                    "background-color: #25D366; color: white; border-radius: 3px;"
                )
        else:
            # Unknown prefix
            self.instance_type_label.setPixmap(QtGui.QPixmap())  # Clear any pixmap
            self.instance_type_label.setText("Unknown")
            self.instance_type_label.setStyleSheet(
                "font-weight: bold; padding: 2px 8px; " "background-color: #9E9E9E; color: white; border-radius: 3px;"
            )

    def _clear_output(self):
        """Clear the output area."""
        self.output.clear()
        self._clear_search_highlights()

    def _set_output(self, text: str):
        """Set output text and auto-scroll if enabled in settings."""
        self.output.setPlainText(text)

        # Auto-scroll to bottom if enabled
        auto_scroll = self.settings.value("auto_scroll_output", True, type=bool)
        if auto_scroll:
            scrollbar = self.output.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

        # Re-apply search if there's active search text
        if hasattr(self, "search_field") and self.search_field.text():
            self._on_search_text_changed()

    def _on_search_text_changed(self):
        """Handle search text changes - highlight all matches."""
        search_text = self.search_field.text()

        # Clear previous highlights
        self._clear_search_highlights()

        if not search_text:
            self.match_count_label.setText("")
            return

        # Get search flags (case insensitive by default)
        flags = QtGui.QTextDocument.FindFlags()

        # Find all matches and highlight them
        cursor = self.output.textCursor()
        cursor.setPosition(0)
        self.output.setTextCursor(cursor)

        self.search_matches = []
        match_format = QtGui.QTextCharFormat()
        match_format.setBackground(QtGui.QColor("#FFEB3B"))  # Yellow highlight

        # Search for all occurrences
        while True:
            cursor = self.output.document().find(search_text, cursor, flags)
            if cursor.isNull():
                break

            self.search_matches.append(cursor.position())

            # Apply highlight
            extra_selection = QtWidgets.QTextEdit.ExtraSelection()
            extra_selection.cursor = cursor
            extra_selection.format = match_format
            self.output.setExtraSelections(self.output.extraSelections() + [extra_selection])

        # Update match count
        if self.search_matches:
            self.current_match_index = 0
            self.match_count_label.setText(f"1 of {len(self.search_matches)}")
            self._highlight_current_match()
        else:
            self.current_match_index = -1
            self.match_count_label.setText("No matches")

    def _find_next(self):
        """Move to next search match."""
        if not self.search_matches:
            return

        self.current_match_index = (self.current_match_index + 1) % len(self.search_matches)
        self.match_count_label.setText(f"{self.current_match_index + 1} of {len(self.search_matches)}")
        self._highlight_current_match()

    def _find_previous(self):
        """Move to previous search match."""
        if not self.search_matches:
            return

        self.current_match_index = (self.current_match_index - 1) % len(self.search_matches)
        self.match_count_label.setText(f"{self.current_match_index + 1} of {len(self.search_matches)}")
        self._highlight_current_match()

    def _highlight_current_match(self):
        """Highlight the current match with a different color and scroll to it."""
        if self.current_match_index < 0 or self.current_match_index >= len(self.search_matches):
            return

        # Re-highlight all matches
        search_text = self.search_field.text()
        flags = QtGui.QTextDocument.FindFlags()

        selections = []
        cursor = self.output.textCursor()
        cursor.setPosition(0)

        match_index = 0
        while True:
            cursor = self.output.document().find(search_text, cursor, flags)
            if cursor.isNull():
                break

            extra_selection = QtWidgets.QTextEdit.ExtraSelection()
            extra_selection.cursor = cursor

            # Current match gets orange highlight, others get yellow
            if match_index == self.current_match_index:
                extra_selection.format.setBackground(QtGui.QColor("#FF9800"))  # Orange
                # Scroll to this match
                self.output.setTextCursor(cursor)
                self.output.ensureCursorVisible()
            else:
                extra_selection.format.setBackground(QtGui.QColor("#FFEB3B"))  # Yellow

            selections.append(extra_selection)
            match_index += 1

        self.output.setExtraSelections(selections)

    def _clear_search_highlights(self):
        """Clear all search highlights."""
        self.output.setExtraSelections([])
        self.search_matches = []
        self.current_match_index = -1
        if hasattr(self, "match_count_label"):
            self.match_count_label.setText("")

    def _load_request_history(self):
        """Load request history from settings."""
        history = self.settings.value("request_history", [])
        if not isinstance(history, list):
            history = []

        self.request_history = history[-50:]  # Keep last 50
        self._update_history_display()

    def _save_request_history(self):
        """Save request history to settings."""
        self.settings.setValue("request_history", self.request_history[-50:])

    def _add_to_history(
        self, method_name: str, instance_id: str, success: bool, params: dict = None, output: str = None
    ):
        """Add a request to history."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        status_icon = "✓" if success else "✗"

        # Create display text
        display_text = f"{status_icon} {timestamp} | {method_name}"
        if instance_id:
            display_text += f" | {instance_id}"

        # Store full details including output
        history_entry = {
            "timestamp": timestamp,
            "method": method_name,
            "instance_id": instance_id,
            "success": success,
            "params": params or {},
            "output": output or "",
        }

        self.request_history.append(history_entry)

        # Keep only last 50
        if len(self.request_history) > 50:
            self.request_history = self.request_history[-50:]

        self._save_request_history()
        self._update_history_display()

    def _update_history_display(self):
        """Update the history list widget."""
        self.history_list.clear()

        # Add items in reverse order (newest first)
        for entry in reversed(self.request_history):
            timestamp = entry.get("timestamp", "")
            method = entry.get("method", "Unknown")
            instance_id = entry.get("instance_id", "")
            success = entry.get("success", False)

            status_icon = "✓" if success else "✗"
            display_text = f"{status_icon} {timestamp} | {method}"
            if instance_id:
                display_text += f" | {instance_id}"

            item = QtWidgets.QListWidgetItem(display_text)

            # Color code by status
            if success:
                item.setForeground(QtGui.QColor("#4CAF50"))  # Green
            else:
                item.setForeground(QtGui.QColor("#F44336"))  # Red

            # Store full entry data
            item.setData(QtCore.Qt.UserRole, entry)

            self.history_list.addItem(item)

    def _show_history_context_menu(self, position):
        """Show context menu for history items."""
        item = self.history_list.itemAt(position)
        if not item:
            return

        entry = item.data(QtCore.Qt.UserRole)
        if not entry:
            return

        menu = QtWidgets.QMenu(self)

        # Add hover effect styling
        menu.setStyleSheet("""
            QMenu {
                background-color: white;
                border: 1px solid #ccc;
            }
            QMenu::item {
                padding: 5px 25px 5px 10px;
                border: 1px solid transparent;
            }
            QMenu::item:selected {
                background-color: #0078d4;
                color: white;
            }
            QMenu::item:hover {
                background-color: #0078d4;
                color: white;
            }
        """)

        # View output action
        view_action = menu.addAction("🔍 View Output")
        view_action.triggered.connect(lambda: self._view_history_output(entry))

        # Re-run action
        rerun_action = menu.addAction("⟳ Re-run Request")
        rerun_action.triggered.connect(lambda: self._rerun_from_history(entry))

        menu.addSeparator()

        # Delete action
        delete_action = menu.addAction("🗑 Delete")
        delete_action.triggered.connect(lambda: self._delete_history_item(item, entry))

        menu.exec(self.history_list.mapToGlobal(position))

    def _view_history_output(self, entry: dict):
        """View the output from a history entry."""
        output = entry.get("output", "")
        if output:
            self.output.setPlainText(output)
            self.status_label.setText(f"Viewing: {entry.get('method', 'Unknown')}")
        else:
            self.status_label.setText("No output available for this request")

    def _rerun_from_history(self, entry: dict):
        """Re-run a request from history."""
        method = entry.get("method", "")
        instance_id = entry.get("instance_id", "")

        # Set instance ID if available
        if instance_id and hasattr(self, "instance_input"):
            self.instance_input.setCurrentText(instance_id)

        # Ensure authentication before re-running
        if not self._ensure_authentication():
            self.status_label.setText("Authentication required to re-run request")
            return

        # Try to call the method directly if it exists
        if hasattr(self, method) and callable(getattr(self, method)):
            self.status_label.setText(f"Re-running: {method}")
            try:
                getattr(self, method)()
            except Exception as e:
                self.output.setPlainText(f"Error re-running {method}: {str(e)}")
            return

        # If no exact match, try finding by partial button text match
        for method_key in dir(self):
            if method_key.startswith("run_"):
                # Convert method key to readable text (e.g., "run_get_qr_code" -> "Get QR Code")
                readable_name = method_key.replace("run_", "").replace("_", " ").title()
                if readable_name.lower() in method.lower() or method.lower() in readable_name.lower():
                    self.status_label.setText(f"Re-running: {method}")
                    try:
                        getattr(self, method_key)()
                    except Exception as e:
                        self.output.setPlainText(f"Error re-running {method_key}: {str(e)}")
                    return

        self.status_label.setText(f"Cannot find matching method for: {method}")

    def _delete_history_item(self, item: QtWidgets.QListWidgetItem, entry: dict):
        """Delete a single history item."""
        # Remove from list widget
        row = self.history_list.row(item)
        self.history_list.takeItem(row)

        # Remove from history data
        if entry in self.request_history:
            self.request_history.remove(entry)
            self._save_request_history()

    def _clear_request_history(self):
        """Clear all request history."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Clear History",
            "Clear all request history?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self.request_history = []
            self._save_request_history()
            self._update_history_display()
            self.status_label.setText("History cleared")

    def _copy_output(self):
        """Copy output area content to clipboard."""
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(self.output.toPlainText())

        # Show brief confirmation in status
        original_text = self.status_label.text()
        original_style = self.status_label.styleSheet()
        self.status_label.setText("Copied to clipboard")
        self.status_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
        QtCore.QTimer.singleShot(
            1000, lambda: (self.status_label.setText(original_text), self.status_label.setStyleSheet(original_style))
        )

    def _export_output(self):
        """Export output area content to a file."""
        content = self.output.toPlainText()

        if not content.strip():
            self.status_label.setText("No output to export")
            self.status_label.setStyleSheet("font-weight: bold; color: #FF9800;")
            QtCore.QTimer.singleShot(2000, lambda: self._reset_status_label())
            return

        # Open file dialog
        file_path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Output", "", "JSON Files (*.json);;Text Files (*.txt);;All Files (*.*)"
        )

        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Show success confirmation
            original_text = self.status_label.text()
            original_style = self.status_label.styleSheet()
            self.status_label.setText(f"Exported to {os.path.basename(file_path)}")
            self.status_label.setStyleSheet("font-weight: bold; color: #4CAF50;")
            QtCore.QTimer.singleShot(
                2000,
                lambda: (self.status_label.setText(original_text), self.status_label.setStyleSheet(original_style)),
            )
        except Exception as e:
            self.status_label.setText(f"Export failed: {str(e)}")
            self.status_label.setStyleSheet("font-weight: bold; color: #F44336;")
            QtCore.QTimer.singleShot(3000, lambda: self._reset_status_label())

    def _pretty_print(self, value, add_timestamp=True) -> str:
        """Format value as pretty-printed JSON with optional timestamp.

        Args:
            value: The value to format (dict, list, str, bytes, or other)
            add_timestamp: If True, prepends timestamp to the output (if enabled in settings)

        Returns:
            Formatted string representation
        """
        formatted = ""
        try:
            if isinstance(value, (dict, list)):
                formatted = json.dumps(value, indent=2, ensure_ascii=False)
            elif isinstance(value, (bytes, bytearray)):
                value = value.decode("utf-8", errors="replace")
                formatted = json.dumps(json.loads(value), indent=2, ensure_ascii=False)
            elif isinstance(value, str):
                formatted = json.dumps(json.loads(value), indent=2, ensure_ascii=False)
            else:
                formatted = str(value)
        except Exception:
            formatted = str(value)

        # Add timestamp prefix if requested and enabled in settings
        show_timestamps = self.settings.value("show_timestamps", True, type=bool)
        if add_timestamp and show_timestamps:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted = f"[{timestamp}]\n{formatted}"

        return formatted

    def _get_instance_id_or_warn(self) -> str | None:
        """Get the instance ID from the input field, or show a warning if empty/invalid.

        Returns:
            The instance ID string if valid, None otherwise.
        """
        instance_id = self.instance_input.currentText().strip()
        if not instance_id:
            self.output.setPlainText("Please enter an Instance ID.")
            self.instance_input.setFocus()
            return None

        # Validate format: at least 4 digits, contains only numbers
        if len(instance_id) < 4 or not instance_id.isdigit():
            self.output.setPlainText("Invalid Instance ID format. Must be at least 4 digits and contain only numbers.")
            self.instance_input.setFocus()
            return None

        # Save to history and settings
        self._save_instance_to_history(instance_id)
        self.settings.setValue("last_instance_id", instance_id)

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
        cred_mgr.clear(clear_saved=True)  # Clear all certificates, cookies, and saved credentials
        self._ctx = None  # Invalidate cached API token
        self.output.setPlainText("Clearing all credentials...")

        # Force full authentication flow (certificate + Kibana credentials)
        if not self._ensure_authentication():
            self.output.setPlainText("Re-authentication cancelled.")

    def _open_settings(self):
        """Open the application settings dialog."""
        dlg = AppSettingsDialog(self, self.settings)
        dlg.exec()

    def _authenticate_kibana(self) -> bool:
        """
        Authenticate with Kibana using username/password.
        Tries saved credentials first, then environment, then prompts user with retry on failure.

        Returns:
            True if authentication succeeded, False if authentication failed or was cancelled
        """
        cred_mgr = get_credential_manager()

        # Show initial status
        self.output.setPlainText("Starting Kibana authentication...")

        # Try saved credentials first (from previous login)
        saved_creds = cred_mgr.get_saved_credentials()
        if saved_creds:
            saved_username, saved_password = saved_creds
            # Show progress dialog for authentication
            progress = QtWidgets.QProgressDialog(
                "Authenticating with saved credentials...", "Please wait...", 0, 0, self
            )
            progress.setWindowModality(QtCore.Qt.WindowModal)
            progress.setWindowTitle("Kibana Authentication")
            progress.setCancelButton(None)
            progress.setMinimumDuration(0)
            progress.setLabelText(f"Authenticating as {saved_username} using certificate...")
            progress.show()

            try:
                cookie = get_kibana_session_cookie_with_password(
                    saved_username, saved_password, cred_mgr.get_certificate_files()
                )
                if cookie:
                    cred_mgr.set_kibana_cookie(cookie)
                    self.output.setPlainText(f"Welcome back! Authenticated as {saved_username}")
                    return True
                else:
                    # Saved credentials failed - clear them and continue to prompt
                    self.output.setPlainText(
                        "Saved credentials are no longer valid.\n" "Please enter your credentials..."
                    )
                    cred_mgr.clear_saved_credentials()
            except Exception:
                # Saved credentials failed - clear them
                cred_mgr.clear_saved_credentials()
            finally:
                progress.close()

        # Try environment credentials
        env_username = os.getenv("KIBANA_USER")
        env_password = os.getenv("KIBANA_PASS")
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

            username, password, remember_me = login_dialog.get_credentials()
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
                    # Save credentials only if user opted in
                    if remember_me:
                        cred_mgr.save_credentials(username, password)
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

        # Check if Kibana authentication is needed (whether certificate is new or existing)
        if not cred_mgr.has_kibana_cookie():
            # Give feedback about Kibana session status
            self.output.setPlainText("Authenticating with Kibana...")

            if not self._authenticate_kibana():
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

    def closeEvent(self, event):
        """Save window size, splitter position, and current tab when closing."""
        self.settings.setValue("window_size", self.size())
        if hasattr(self, "tabs"):
            self.settings.setValue("last_tab_index", self.tabs.currentIndex())
        event.accept()

    def _on_tab_changed(self, index):
        """Save the current tab index when user switches tabs."""
        self.settings.setValue("last_tab_index", index)


if __name__ == "__main__":
    app = QtWidgets.QApplication([])
    with open(resource_path("ui/styles.qss"), "r", encoding="utf-8") as f:
        app.setStyleSheet(f.read())
    app.setWindowIcon(QtGui.QIcon(resource_path("ui/greenapiicon.ico")))
    w = App()
    # Window size is now set in __init__ based on saved settings or defaults
    w.show()
    app.exec()
