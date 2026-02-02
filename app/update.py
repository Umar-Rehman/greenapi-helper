"""
Simple auto-update functionality for the Green API Helper application.
"""

import json
import os
import sys
import tempfile
import subprocess
import urllib.request
from typing import Optional
from PySide6 import QtCore, QtWidgets


def get_current_version() -> str:
    """Get the current application version from version.json."""
    try:
        version_file = os.path.join(os.path.dirname(__file__), "..", "version.json")
        with open(version_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("version", "0.0.0")
    except FileNotFoundError, json.JSONDecodeError, KeyError:
        return "0.0.0"


class UpdateManager(QtCore.QObject):
    """Simple update manager for the application."""

    update_available = QtCore.Signal(dict)
    update_error = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.version_url = "https://api.github.com/repos/Umar-Rehman/greenapi-helper/releases/latest"

    def check_for_updates(self) -> None:
        """Check for updates in a background thread."""
        QtCore.QThreadPool.globalInstance().start(QtCore.QRunnable.create(self._perform_update_check))

    def _perform_update_check(self) -> None:
        """Perform the actual update check."""
        try:
            with urllib.request.urlopen(self.version_url, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            remote_version = data.get("tag_name", "").lstrip("v")
            if not remote_version:
                return

            if self._is_newer_version(remote_version, get_current_version()):
                update_info = {
                    "version": remote_version,
                    "download_url": self._get_download_url(data),
                    "changelog_url": data.get("html_url", ""),
                    "notes": data.get("body", "New version available"),
                }
                self.update_available.emit(update_info)

        except Exception as e:
            self.update_error.emit(f"Update check failed: {str(e)}")

    def _get_download_url(self, release_data: dict) -> str:
        """Extract download URL from release assets."""
        assets = release_data.get("assets", [])
        for asset in assets:
            if asset.get("name") == "greenapi-helper.exe":
                return asset.get("browser_download_url", "")
        return (
            "https://github.com/Umar-Rehman/greenapi-helper/releases/download/"
            f"v{release_data.get('tag_name', '')}/greenapi-helper.exe"
        )

    def _is_newer_version(self, remote: str, local: str) -> bool:
        """Compare version strings."""
        try:
            remote_parts = [int(x) for x in remote.split(".")]
            local_parts = [int(x) for x in local.split(".")]
            return remote_parts > local_parts
        except ValueError:
            return False

    def perform_simple_update(self, download_url: str, parent_widget: QtWidgets.QWidget) -> None:
        """Simple update: download, replace, restart."""
        try:
            # Check if running as executable
            if not getattr(sys, "frozen", False):
                QtWidgets.QMessageBox.information(
                    parent_widget,
                    "Update Not Available",
                    "Self-update only works with the installed executable.\n\n"
                    "Please download manually from GitHub releases.",
                )
                return
                return

            # Show progress dialog
            progress = QtWidgets.QProgressDialog("Downloading update...", None, 0, 0, parent_widget)
            progress.setWindowModality(QtCore.Qt.WindowModal)
            progress.show()

            # Download to temp file
            temp_path = self._simple_download(download_url, progress)
            if not temp_path:
                progress.close()
                QtWidgets.QMessageBox.critical(parent_widget, "Download Failed", "Failed to download update.")
                return

            progress.close()

            # Replace and restart
            self._replace_and_restart(temp_path, parent_widget)

        except Exception as e:
            QtWidgets.QMessageBox.critical(parent_widget, "Update Failed", f"Update failed: {str(e)}")

    def _simple_download(self, url: str, progress: QtWidgets.QProgressDialog) -> Optional[str]:
        """Download file to temp location."""
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                temp_fd, temp_path = tempfile.mkstemp(suffix=".exe")
                os.close(temp_fd)

                with open(temp_path, "wb") as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)

                return temp_path
        except Exception:
            return None

    def _replace_and_restart(self, new_exe_path: str, parent_widget: QtWidgets.QWidget) -> None:
        """Replace current exe with new one and restart."""
        try:
            current_exe = sys.executable

            # Simple replacement - just move the file
            os.replace(new_exe_path, current_exe)

            # Restart the application
            subprocess.Popen([current_exe])
            QtWidgets.QApplication.quit()

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                parent_widget,
                "Restart Failed",
                f"Update downloaded but restart failed: {str(e)}\n\nPlease restart the application manually.",
            )


def get_update_manager() -> UpdateManager:
    """Get or create the global update manager instance."""
    if not hasattr(get_update_manager, "_instance"):
        get_update_manager._instance = UpdateManager()
    return get_update_manager._instance
