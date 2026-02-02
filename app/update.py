"""
Auto-update functionality for the Green API Helper application.
"""

import json
import urllib.request
import urllib.error
from typing import Dict, Any
from PySide6 import QtCore, QtWidgets
from app.version import __version__


class UpdateManager(QtCore.QObject):
    """Manages automatic updates for the application."""

    update_available = QtCore.Signal(dict)  # Emits update info when new version found
    update_error = QtCore.Signal(str)  # Emits error message if update check fails

    def __init__(self, parent=None):
        super().__init__(parent)
        self.version_url = "https://raw.githubusercontent.com/Umar-Rehman/greenapi-helper/main/version.json"
        self.check_interval_hours = 24  # Check once per day

    def check_for_updates(self) -> None:
        """Check for updates in a background thread."""
        # Run the check in a separate thread to avoid blocking UI
        QtCore.QThreadPool.globalInstance().start(QtCore.QRunnable.create(self._perform_update_check))

    def _perform_update_check(self) -> None:
        """Perform the actual update check."""
        try:
            with urllib.request.urlopen(self.version_url, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            remote_version = data.get('version', '0.0.0')
            if self._is_newer_version(remote_version, __version__):
                self.update_available.emit(data)
            # If versions are the same or local is newer, do nothing

        except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
            self.update_error.emit(f"Failed to check for updates: {str(e)}")
        except Exception as e:
            self.update_error.emit(f"Unexpected error during update check: {str(e)}")

    def _is_newer_version(self, remote: str, local: str) -> bool:
        """Compare version strings to determine if remote is newer than local."""
        try:
            remote_parts = [int(x) for x in remote.split('.')]
            local_parts = [int(x) for x in local.split('.')]

            # Pad shorter version with zeros
            max_len = max(len(remote_parts), len(local_parts))
            remote_parts.extend([0] * (max_len - len(remote_parts)))
            local_parts.extend([0] * (max_len - len(local_parts)))

            return remote_parts > local_parts
        except ValueError:
            # If version parsing fails, assume no update available
            return False

    def show_update_dialog(self, update_info: Dict[str, Any], parent: QtWidgets.QWidget) -> None:
        """Show a dialog informing the user about available updates."""
        version = update_info.get('version', 'Unknown')
        notes = update_info.get('notes', 'No release notes available')
        download_url = update_info.get('download_url', '')
        changelog_url = update_info.get('changelog_url', '')

        msg_box = QtWidgets.QMessageBox(parent)
        msg_box.setWindowTitle("Update Available")
        msg_box.setIcon(QtWidgets.QMessageBox.Information)
        msg_box.setText(f"A new version ({version}) is available!")
        msg_box.setInformativeText(f"Current version: {__version__}\n\n{notes}")

        # Add buttons
        download_button = msg_box.addButton("Download", QtWidgets.QMessageBox.AcceptRole)
        changelog_button = msg_box.addButton("View Changelog", QtWidgets.QMessageBox.HelpRole)
        msg_box.addButton("Later", QtWidgets.QMessageBox.RejectRole)

        msg_box.exec()

        clicked_button = msg_box.clickedButton()

        if clicked_button == download_button and download_url:
            QtWidgets.QDesktopServices.openUrl(QtCore.QUrl(download_url))
        elif clicked_button == changelog_button and changelog_url:
            QtWidgets.QDesktopServices.openUrl(QtCore.QUrl(changelog_url))
        # If "Later" is clicked, just close the dialog


def get_update_manager() -> UpdateManager:
    """Get or create the global update manager instance."""
    if not hasattr(get_update_manager, '_instance'):
        get_update_manager._instance = UpdateManager()
    return get_update_manager._instance
