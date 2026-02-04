"""
Auto-update functionality for the Green API Helper application.
Simplified version without excessive logging.
"""

import json
import os
import sys
import tempfile
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from PySide6 import QtCore, QtWidgets


def _log_error(message: str) -> None:
    """Log errors to stderr for production debugging."""
    print(f"[UPDATE ERROR] {message}", file=sys.stderr)


def get_current_version() -> str:
    """Get the current application version from version.json."""
    try:
        version_file = os.path.join(os.path.dirname(__file__), "..", "version.json")
        with open(version_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("version", "0.0.0")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return "0.0.0"


class UpdateManager(QtCore.QObject):
    """Manages automatic updates for the application."""

    update_available = QtCore.Signal(dict)  # Emits update info when new version found
    update_error = QtCore.Signal(str)  # Emits error message if update check fails

    def __init__(self, parent=None):
        super().__init__(parent)
        self.version_url = "https://api.github.com/repos/Umar-Rehman/greenapi-helper/releases/latest"

    def check_for_updates(self) -> None:
        """Check for updates in a background thread."""
        QtCore.QThreadPool.globalInstance().start(QtCore.QRunnable.create(self._perform_update_check))

    def _perform_update_check(self) -> None:
        """Perform the actual update check."""
        try:
            req = urllib.request.Request(self.version_url)
            req.add_header("Accept", "application/vnd.github.v3+json")

            with urllib.request.urlopen(req, timeout=10) as response:
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

        except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
            _log_error(f"Update check failed: {type(e).__name__}: {str(e)}")
            self.update_error.emit(f"Failed to check for updates: {str(e)}")

    def _get_download_url(self, release_data: dict) -> str:
        """Extract download URL from release assets."""
        assets = release_data.get("assets", [])
        for asset in assets:
            if asset.get("name") == "greenapi-helper.exe":
                return asset.get("browser_download_url", "")

        # Fallback URL
        tag_name = release_data.get("tag_name", "")
        return f"https://github.com/Umar-Rehman/greenapi-helper/releases/download/{tag_name}/greenapi-helper.exe"

    def _is_newer_version(self, remote: str, local: str) -> bool:
        """Compare version strings."""
        try:
            remote_parts = [int(x) for x in remote.split(".")]
            local_parts = [int(x) for x in local.split(".")]
            max_len = max(len(remote_parts), len(local_parts))
            remote_parts.extend([0] * (max_len - len(remote_parts)))
            local_parts.extend([0] * (max_len - len(local_parts)))
            return remote_parts > local_parts
        except ValueError:
            return False

    def perform_self_update(self, download_url: str, parent_widget: QtWidgets.QWidget) -> bool:
        """Download and install update with progress feedback."""
        # Check if running as frozen executable
        if not getattr(sys, "frozen", False):
            QtWidgets.QMessageBox.information(
                parent_widget,
                "Update Not Available",
                "Self-update is only available when running the installed executable.\n\n"
                "Please download the update manually from the GitHub releases page.",
            )
            return False

        try:
            # Create progress dialog
            progress = QtWidgets.QProgressDialog("Getting latest release...", "Cancel", 0, 100, parent_widget)
            progress.setWindowModality(QtCore.Qt.WindowModal)
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.setMinimumWidth(400)
            progress.setMinimumDuration(0)
            progress.show()
            progress.setValue(5)

            # Download update
            progress.setLabelText("Downloading update...")
            progress.setValue(10)
            temp_path = self._download_update(download_url, progress)
            if not temp_path:
                progress.close()
                return False

            # Create updater script
            progress.setLabelText("Finalizing installation...")
            progress.setValue(90)
            updater_script = self._create_updater_script(temp_path)
            if not updater_script:
                progress.close()
                return False

            # Show completion
            progress.setLabelText("Update complete! Please restart the application.")
            progress.setValue(100)
            progress.setCancelButtonText("Close")

            # Launch updater and exit (no automatic restart)
            QtCore.QTimer.singleShot(1500, progress.close)
            QtCore.QTimer.singleShot(2000, lambda: subprocess.Popen([updater_script], shell=True))
            QtCore.QTimer.singleShot(2500, QtWidgets.QApplication.quit)
            return True

        except Exception as e:
            _log_error(f"Self-update failed: {type(e).__name__}: {str(e)}")
            QtWidgets.QMessageBox.critical(parent_widget, "Update Failed", f"Failed to perform update: {str(e)}")
            return False

    def _download_update(self, download_url: str, progress: QtWidgets.QProgressDialog) -> Optional[str]:
        """Download the update executable with progress feedback."""
        try:
            temp_fd, temp_path = tempfile.mkstemp(suffix=".exe")
            os.close(temp_fd)

            with urllib.request.urlopen(download_url, timeout=30) as response:
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0

                with open(temp_path, "wb") as f:
                    while True:
                        if progress.wasCanceled():
                            os.unlink(temp_path)
                            return None

                        chunk = response.read(8192)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = int((downloaded / total_size) * 75) + 10
                            mb_downloaded = downloaded / (1024 * 1024)
                            mb_total = total_size / (1024 * 1024)
                            progress.setLabelText(f"Downloading update... {mb_downloaded:.1f} MB / {mb_total:.1f} MB")
                            progress.setValue(percent)

            progress.setLabelText("Download complete, verifying...")
            progress.setValue(85)
            return temp_path

        except Exception as e:
            _log_error(f"Download failed: {type(e).__name__}: {str(e)}")
            progress.close()
            raise

    def _create_updater_script(self, new_exe_path: str) -> Optional[str]:
        """Create a batch script to replace the current executable and restart."""
        try:
            current_exe = sys.executable
            updater_script = os.path.join(tempfile.gettempdir(), "greenapi_updater.bat")

            script_content = f"""@echo off
echo Updating Green API Helper...
timeout /t 2 /nobreak > nul

REM Wait for application to exit
timeout /t 1 /nobreak > nul

REM Replace executable
move /Y "{new_exe_path}" "{current_exe}"

REM Show completion message
echo.
echo ====================================
echo Update completed successfully!
echo Please restart the application.
echo ====================================
echo.
pause

REM Clean up
del "%~f0"
"""

            with open(updater_script, "w") as f:
                f.write(script_content)

            return updater_script

        except Exception as e:
            _log_error(f"Updater script creation failed: {type(e).__name__}: {str(e)}")
            self.update_error.emit(f"Failed to create updater script: {str(e)}")
            return None

    def show_update_dialog(self, update_info: Dict[str, Any], parent: QtWidgets.QWidget) -> None:
        """Show a dialog informing the user about available updates."""
        version = update_info.get("version", "Unknown")
        notes = update_info.get("notes", "No release notes available")
        download_url = update_info.get("download_url", "")
        changelog_url = update_info.get("changelog_url", "")

        msg_box = QtWidgets.QMessageBox(parent)
        msg_box.setWindowTitle("Update Available")
        msg_box.setIcon(QtWidgets.QMessageBox.Information)
        msg_box.setText(f"A new version ({version}) is available!")
        msg_box.setInformativeText(f"Current version: {get_current_version()}\n\n{notes}")

        # Check if self-update is available
        can_self_update = getattr(sys, "frozen", False)

        if can_self_update:
            msg_box.addButton("Update Now", QtWidgets.QMessageBox.AcceptRole)
            msg_box.addButton("Download Manually", QtWidgets.QMessageBox.ActionRole)
            msg_box.addButton("View Changelog", QtWidgets.QMessageBox.HelpRole)
            msg_box.addButton("Later", QtWidgets.QMessageBox.RejectRole)
        else:
            msg_box.addButton("Download Manually", QtWidgets.QMessageBox.AcceptRole)
            msg_box.addButton("View Changelog", QtWidgets.QMessageBox.ActionRole)
            msg_box.addButton("Later", QtWidgets.QMessageBox.RejectRole)

        result = msg_box.exec()

        # Handle button clicks
        if can_self_update and result == QtWidgets.QMessageBox.AcceptRole:
            # Update Now button (frozen exe only)
            self.perform_self_update(download_url, parent)
        elif (can_self_update and result == QtWidgets.QMessageBox.ActionRole) or (
            not can_self_update and result == QtWidgets.QMessageBox.AcceptRole
        ):
            # Download Manually button - open GitHub release page
            url_to_open = changelog_url if changelog_url else download_url
            if url_to_open:
                QtWidgets.QDesktopServices.openUrl(QtCore.QUrl(url_to_open))
        elif result == QtWidgets.QMessageBox.HelpRole:
            # View Changelog button
            if changelog_url:
                QtWidgets.QDesktopServices.openUrl(QtCore.QUrl(changelog_url))


def get_update_manager() -> UpdateManager:
    """Get or create the global update manager instance."""
    if not hasattr(get_update_manager, "_instance"):
        get_update_manager._instance = UpdateManager()
    return get_update_manager._instance
