"""
Simple auto-update functionality for the Green API Helper application.
"""

import json
import os
import sys
import tempfile
import subprocess
import urllib.request
import traceback
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
        print("[UPDATE] Starting perform_simple_update")
        try:
            # Check if running as executable
            if not getattr(sys, "frozen", False):
                print("[UPDATE] Not running as frozen executable")
                QtWidgets.QMessageBox.information(
                    parent_widget,
                    "Update Not Available",
                    "Self-update only works with the installed executable.\n\n"
                    "Please download manually from GitHub releases.",
                )
                return

            print(f"[UPDATE] Running as frozen executable: {sys.executable}")
            print(f"[UPDATE] Download URL: {download_url}")

            # Show progress dialog
            progress = QtWidgets.QProgressDialog("Downloading update...", None, 0, 0, parent_widget)
            progress.setWindowModality(QtCore.Qt.WindowModal)
            progress.show()
            QtWidgets.QApplication.processEvents()

            # Download to temp file
            print("[UPDATE] Starting download...")
            temp_path = self._simple_download(download_url, progress)
            if not temp_path:
                print("[UPDATE] Download failed - temp_path is None")
                progress.close()
                QtWidgets.QMessageBox.critical(parent_widget, "Download Failed", "Failed to download update.")
                return

            print(f"[UPDATE] Download successful to: {temp_path}")
            progress.close()

            # Replace and restart
            print("[UPDATE] Starting replacement and restart...")
            self._replace_and_restart(temp_path, parent_widget)

        except Exception as e:
            print(f"[UPDATE] Exception in perform_simple_update: {type(e).__name__}: {str(e)}")
            print(traceback.format_exc())
            QtWidgets.QMessageBox.critical(parent_widget, "Update Failed", f"Update failed: {str(e)}")

    def _simple_download(self, url: str, progress: QtWidgets.QProgressDialog) -> Optional[str]:
        """Download file to temp location."""
        try:
            print(f"[DOWNLOAD] Starting download from: {url}")
            with urllib.request.urlopen(url, timeout=30) as response:
                temp_fd, temp_path = tempfile.mkstemp(suffix=".exe")
                os.close(temp_fd)
                print(f"[DOWNLOAD] Created temp file: {temp_path}")

                with open(temp_path, "wb") as f:
                    downloaded = 0
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                    print(f"[DOWNLOAD] Downloaded {downloaded} bytes")

                return temp_path
        except Exception as e:
            print(f"[DOWNLOAD] Download failed: {type(e).__name__}: {str(e)}")
            print(traceback.format_exc())
            return None

    def _replace_and_restart(self, new_exe_path: str, parent_widget: QtWidgets.QWidget) -> None:
        """Replace current exe with new one and restart."""
        print(f"[REPLACE] Starting replacement: {new_exe_path}")
        try:
            current_exe = sys.executable
            print(f"[REPLACE] Current executable: {current_exe}")
            print(f"[REPLACE] New executable path: {new_exe_path}")

            # Create a simple batch script to handle the update
            import shutil

            # Copy new exe to a temporary location with a different name
            updated_exe = current_exe + ".updated"
            print(f"[REPLACE] Copying to: {updated_exe}")
            shutil.copy2(new_exe_path, updated_exe)
            print("[REPLACE] Copy successful")

            # Create a batch script to replace the file after we exit
            batch_script = current_exe + ".updater.bat"
            batch_content = f"""@echo off
echo Updating Green API Helper...
timeout /t 2 /nobreak > nul
move /Y "{updated_exe}" "{current_exe}"
echo Update complete! Starting application...
start "" "{current_exe}"
del "%~f0"
"""

            with open(batch_script, "w") as f:
                f.write(batch_content)
            print(f"[REPLACE] Batch script created: {batch_script}")

            # Start the new version
            print(f"[REPLACE] Starting new version: {updated_exe}")
            subprocess.Popen([updated_exe])
            print("[REPLACE] New version started")

            # Show message and exit
            QtWidgets.QMessageBox.information(
                parent_widget,
                "Update Started",
                "Update downloaded successfully!\n\n"
                "The new version is starting now.\n"
                "Please close this window when the new version appears.",
            )

            print("[REPLACE] Exiting application")
            QtWidgets.QApplication.quit()

        except Exception as e:
            print(f"[REPLACE] Exception in _replace_and_restart: {type(e).__name__}: {str(e)}")
            print(traceback.format_exc())
            QtWidgets.QMessageBox.critical(
                parent_widget,
                "Update Failed",
                f"Update downloaded but installation failed: {str(e)}\n\n"
                f"New executable is at: {new_exe_path}\n\n"
                "Please manually replace the executable and restart the application.",
            )


def get_update_manager() -> UpdateManager:
    """Get or create the global update manager instance."""
    if not hasattr(get_update_manager, "_instance"):
        get_update_manager._instance = UpdateManager()
    return get_update_manager._instance
