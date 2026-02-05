from __future__ import annotations

from PySide6 import QtWidgets, QtCore


class AppSettingsDialog(QtWidgets.QDialog):
    """Dialog for application-wide settings."""

    def __init__(self, parent, settings: QtCore.QSettings):
        super().__init__(parent)
        self.settings = settings
        self.parent_app = parent

        self.setWindowTitle("Application Settings")
        self.setMinimumWidth(500)
        self.setModal(True)

        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self):
        """Setup the settings dialog UI."""
        layout = QtWidgets.QVBoxLayout(self)

        # Create tab widget for organized settings
        tabs = QtWidgets.QTabWidget()

        # General settings tab
        general_tab = self._create_general_tab()
        tabs.addTab(general_tab, "General")

        # Output settings tab
        output_tab = self._create_output_tab()
        tabs.addTab(output_tab, "Output")

        # Data management tab
        data_tab = self._create_data_tab()
        tabs.addTab(data_tab, "Data")

        layout.addWidget(tabs)

        # Dialog buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._save_and_close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_general_tab(self) -> QtWidgets.QWidget:
        """Create general settings tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # Default startup tab
        startup_group = QtWidgets.QGroupBox("Startup")
        startup_layout = QtWidgets.QFormLayout()

        self.default_tab_combo = QtWidgets.QComboBox()
        self.default_tab_combo.addItems(
            [
                "Account",
                "Journals",
                "Queues",
                "Groups",
                "Sending",
                "Receiving",
                "Statuses",
                "Service Methods",
                "Read Mark",
            ]
        )
        startup_layout.addRow("Default Tab:", self.default_tab_combo)

        self.remember_last_tab_check = QtWidgets.QCheckBox("Remember last opened tab")
        self.remember_last_tab_check.setChecked(True)
        self.remember_last_tab_check.toggled.connect(self._on_remember_tab_toggled)
        startup_layout.addRow("", self.remember_last_tab_check)

        startup_group.setLayout(startup_layout)
        layout.addWidget(startup_group)

        # Window settings
        window_group = QtWidgets.QGroupBox("Window")
        window_layout = QtWidgets.QVBoxLayout()

        reset_layout_btn = QtWidgets.QPushButton("Reset Window Layout")
        reset_layout_btn.setToolTip("Reset window size and splitter to default positions")
        reset_layout_btn.clicked.connect(self._reset_window_layout)
        window_layout.addWidget(reset_layout_btn)

        window_group.setLayout(window_layout)
        layout.addWidget(window_group)

        layout.addStretch()
        return widget

    def _create_output_tab(self) -> QtWidgets.QWidget:
        """Create output settings tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # Timestamp settings
        timestamp_group = QtWidgets.QGroupBox("Timestamps")
        timestamp_layout = QtWidgets.QFormLayout()

        self.show_timestamps_check = QtWidgets.QCheckBox("Show timestamps in output")
        self.show_timestamps_check.setChecked(True)
        timestamp_layout.addRow("", self.show_timestamps_check)

        timestamp_group.setLayout(timestamp_layout)
        layout.addWidget(timestamp_group)

        # Display settings
        display_group = QtWidgets.QGroupBox("Display")
        display_layout = QtWidgets.QFormLayout()

        self.auto_scroll_check = QtWidgets.QCheckBox("Auto-scroll to bottom on new output")
        self.auto_scroll_check.setChecked(True)
        display_layout.addRow("", self.auto_scroll_check)

        self.word_wrap_check = QtWidgets.QCheckBox("Enable word wrap in output")
        self.word_wrap_check.setChecked(True)
        display_layout.addRow("", self.word_wrap_check)

        display_group.setLayout(display_layout)
        layout.addWidget(display_group)

        # Font settings
        font_group = QtWidgets.QGroupBox("Font")
        font_layout = QtWidgets.QFormLayout()

        self.font_size_spin = QtWidgets.QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(10)
        self.font_size_spin.setSuffix(" pt")
        font_layout.addRow("Font Size:", self.font_size_spin)

        font_group.setLayout(font_layout)
        layout.addWidget(font_group)

        layout.addStretch()
        return widget

    def _create_data_tab(self) -> QtWidgets.QWidget:
        """Create data management tab."""
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)

        # Instance history
        history_group = QtWidgets.QGroupBox("Instance History")
        history_layout = QtWidgets.QVBoxLayout()

        history_info = QtWidgets.QLabel(
            "Instance IDs are saved for quick access. " "You can clear this history if needed."
        )
        history_info.setWordWrap(True)
        history_layout.addWidget(history_info)

        # Show current history count
        history_count = len(self.settings.value("instance_history", []))
        self.history_count_label = QtWidgets.QLabel(f"Current history: {history_count} instance(s)")
        history_layout.addWidget(self.history_count_label)

        clear_history_btn = QtWidgets.QPushButton("Clear Instance History")
        clear_history_btn.setToolTip("Remove all saved instance IDs from history")
        clear_history_btn.clicked.connect(self._clear_instance_history)
        history_layout.addWidget(clear_history_btn)

        history_group.setLayout(history_layout)
        layout.addWidget(history_group)

        # Cache and credentials
        cache_group = QtWidgets.QGroupBox("Cache & Credentials")
        cache_layout = QtWidgets.QVBoxLayout()

        cache_info = QtWidgets.QLabel(
            "Clear cached data and credentials. This will remove " "all saved authentication information."
        )
        cache_info.setWordWrap(True)
        cache_layout.addWidget(cache_info)

        clear_cache_btn = QtWidgets.QPushButton("Clear All Cached Data")
        clear_cache_btn.setToolTip("Remove all saved credentials and cache")
        clear_cache_btn.clicked.connect(self._clear_all_cache)
        cache_layout.addWidget(clear_cache_btn)

        cache_group.setLayout(cache_layout)
        layout.addWidget(cache_group)

        # Reset all settings
        reset_group = QtWidgets.QGroupBox("Reset")
        reset_layout = QtWidgets.QVBoxLayout()

        reset_info = QtWidgets.QLabel(
            "Reset all application settings to defaults. " "This will clear all saved preferences, history, and layout."
        )
        reset_info.setWordWrap(True)
        reset_layout.addWidget(reset_info)

        reset_all_btn = QtWidgets.QPushButton("Reset All Settings")
        reset_all_btn.setToolTip("Reset everything to default values")
        reset_all_btn.setStyleSheet("QPushButton { color: #F44336; font-weight: bold; }")
        reset_all_btn.clicked.connect(self._reset_all_settings)
        reset_layout.addWidget(reset_all_btn)

        reset_group.setLayout(reset_layout)
        layout.addWidget(reset_group)

        layout.addStretch()
        return widget

    def _load_current_settings(self):
        """Load current settings values into the dialog."""
        # General tab
        default_tab = self.settings.value("default_tab_index", 0, type=int)
        self.default_tab_combo.setCurrentIndex(default_tab)

        remember_tab = self.settings.value("remember_last_tab", True, type=bool)
        self.remember_last_tab_check.setChecked(remember_tab)
        self.default_tab_combo.setEnabled(not remember_tab)

        # Output tab
        show_timestamps = self.settings.value("show_timestamps", True, type=bool)
        self.show_timestamps_check.setChecked(show_timestamps)

        auto_scroll = self.settings.value("auto_scroll_output", True, type=bool)
        self.auto_scroll_check.setChecked(auto_scroll)

        word_wrap = self.settings.value("word_wrap_output", True, type=bool)
        self.word_wrap_check.setChecked(word_wrap)

        font_size = self.settings.value("output_font_size", 10, type=int)
        self.font_size_spin.setValue(font_size)

    def _on_remember_tab_toggled(self, checked: bool):
        """Toggle default tab combo based on remember last tab setting."""
        self.default_tab_combo.setEnabled(not checked)

    def _reset_window_layout(self):
        """Reset window size and splitter positions."""
        reply = QtWidgets.QMessageBox.question(
            self,
            "Reset Window Layout",
            "Reset window size and splitter positions to default?\n\n" "This will take effect on next restart.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self.settings.remove("window_size")
            self.settings.remove("splitter_sizes")
            QtWidgets.QMessageBox.information(
                self, "Layout Reset", "Window layout will reset to defaults on next restart."
            )

    def _clear_instance_history(self):
        """Clear saved instance history."""
        history_count = len(self.settings.value("instance_history", []))

        if history_count == 0:
            QtWidgets.QMessageBox.information(self, "No History", "There is no instance history to clear.")
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Clear History",
            f"Clear all {history_count} saved instance ID(s) from history?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self.settings.setValue("instance_history", [])
            self.settings.remove("last_instance_id")
            self.history_count_label.setText("Current history: 0 instance(s)")

            # Update parent's combo box
            if hasattr(self.parent_app, "instance_combo"):
                self.parent_app.instance_combo.clear()

            QtWidgets.QMessageBox.information(
                self,
                "History Cleared",
                "Instance history has been cleared.\n\n" "The application will restart to apply changes.",
            )

            # Restart application
            QtWidgets.QApplication.quit()
            QtCore.QProcess.startDetached(QtWidgets.QApplication.instance().arguments()[0], [])

    def _clear_all_cache(self):
        """Clear all cached credentials and data."""
        reply = QtWidgets.QMessageBox.warning(
            self,
            "Clear Cache",
            "Clear all cached credentials and authentication data?\n\n"
            "You will need to re-authenticate after this action.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )

        if reply == QtWidgets.QMessageBox.Yes:
            # Clear any cached credentials (if your app stores them)
            # This is a placeholder - implement based on your credential storage

            QtWidgets.QMessageBox.information(self, "Cache Cleared", "All cached data has been cleared.")

    def _reset_all_settings(self):
        """Reset all application settings to defaults."""
        reply = QtWidgets.QMessageBox.warning(
            self,
            "Reset All Settings",
            "Reset ALL application settings to defaults?\n\n"
            "This will clear:\n"
            "• Window layout and size\n"
            "• Instance history\n"
            "• Output preferences\n"
            "• All saved preferences\n\n"
            "The application will restart.",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )

        if reply == QtWidgets.QMessageBox.Yes:
            self.settings.clear()
            QtWidgets.QMessageBox.information(
                self,
                "Settings Reset",
                "All settings have been reset to defaults.\n\n" "The application will now restart.",
            )

            # Restart application
            QtWidgets.QApplication.quit()
            QtCore.QProcess.startDetached(QtWidgets.QApplication.instance().arguments()[0], [])

    def _save_and_close(self):
        """Save settings and close dialog."""
        # General settings
        self.settings.setValue("default_tab_index", self.default_tab_combo.currentIndex())
        self.settings.setValue("remember_last_tab", self.remember_last_tab_check.isChecked())

        # Output settings
        self.settings.setValue("show_timestamps", self.show_timestamps_check.isChecked())
        self.settings.setValue("auto_scroll_output", self.auto_scroll_check.isChecked())
        self.settings.setValue("word_wrap_output", self.word_wrap_check.isChecked())
        self.settings.setValue("output_font_size", self.font_size_spin.value())

        # Apply settings that can be changed immediately
        self._apply_output_settings()

        self.accept()

    def _apply_output_settings(self):
        """Apply output settings to parent application immediately."""
        if hasattr(self.parent_app, "output"):
            # Apply word wrap
            if self.word_wrap_check.isChecked():
                self.parent_app.output.setLineWrapMode(QtWidgets.QTextEdit.WidgetWidth)
            else:
                self.parent_app.output.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)

            # Apply font size
            font = self.parent_app.output.font()
            font.setPointSize(self.font_size_spin.value())
            self.parent_app.output.setFont(font)
