"""
Auto-update functionality for the Green API Helper application.
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


def get_current_version() -> str:
    """Get the current application version from version.json."""
    try:
        # Try to read from version.json in the same directory as this module
        version_file = os.path.join(os.path.dirname(__file__), "..", "version.json")
        with open(version_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("version", "0.0.0")
    except FileNotFoundError, json.JSONDecodeError, KeyError:
        # Fallback version if file can't be read
        return "0.0.0"


class UpdateManager(QtCore.QObject):
    """Manages automatic updates for the application."""

    update_available = QtCore.Signal(dict)  # Emits update info when new version found
    update_error = QtCore.Signal(str)  # Emits error message if update check fails

    def __init__(self, parent=None):
        super().__init__(parent)
        # GitHub API for public repository (no token required)
        self.version_url = "https://api.github.com/repos/Umar-Rehman/greenapi-helper/releases/latest"
        self.github_token = os.environ.get("GITHUB_TOKEN")  # Optional for private repos
        self.check_interval_hours = 24  # Check once per day

    def check_for_updates(self) -> None:
        """Check for updates in a background thread."""
        # Run the check in a separate thread to avoid blocking UI
        QtCore.QThreadPool.globalInstance().start(QtCore.QRunnable.create(self._perform_update_check))

    def _perform_update_check(self) -> None:
        """Perform the actual update check."""
        try:
            # Create request (works with public repos, token optional for private)
            req = urllib.request.Request(self.version_url)
            if self.github_token:
                req.add_header("Authorization", f"token {self.github_token}")
                req.add_header("Accept", "application/vnd.github.v3+json")
            else:
                # For public repos, we can make unauthenticated requests
                req.add_header("Accept", "application/vnd.github.v3+json")

            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            # Parse GitHub release format
            remote_version = data.get("tag_name", "").lstrip("v")  # Remove 'v' prefix if present
            if not remote_version:
                self.update_error.emit("Could not parse version from GitHub release")
                return

            if self._is_newer_version(remote_version, get_current_version()):
                # Convert GitHub release format to our expected format
                update_info = {
                    "version": remote_version,
                    "download_url": self._get_download_url_from_release(data),
                    "changelog_url": data.get("html_url", ""),
                    "minimum_version": "1.0.0",  # You can set this in release body or tags
                    "release_date": data.get("published_at", ""),
                    "notes": data.get("body", "New version available"),
                }
                self.update_available.emit(update_info)
            # If versions are the same or local is newer, do nothing

        except (urllib.error.URLError, json.JSONDecodeError, KeyError) as e:
            self.update_error.emit(f"Failed to check for updates: {str(e)}")
        except Exception as e:
            self.update_error.emit(f"Unexpected error during update check: {str(e)}")

    def _get_download_url_from_release(self, release_data: dict) -> str:
        """Extract the download URL for the executable from GitHub release assets."""
        assets = release_data.get("assets", [])
        for asset in assets:
            if asset.get("name") == "greenapi-helper.exe":
                return asset.get("browser_download_url", "")

        # Fallback: construct URL from release info
        tag_name = release_data.get("tag_name", "")
        return f"https://github.com/Umar-Rehman/greenapi-helper/releases/download/{tag_name}/greenapi-helper.exe"

    def _is_newer_version(self, remote: str, local: str) -> bool:
        """Compare version strings to determine if remote is newer than local."""
        try:
            remote_parts = [int(x) for x in remote.split(".")]
            local_parts = [int(x) for x in local.split(".")]

            # Pad shorter version with zeros
            max_len = max(len(remote_parts), len(local_parts))
            remote_parts.extend([0] * (max_len - len(remote_parts)))
            local_parts.extend([0] * (max_len - len(local_parts)))

            return remote_parts > local_parts
        except ValueError:
            # If version parsing fails, assume no update available
            return False

    def perform_self_update(self, download_url: str, parent_widget: QtWidgets.QWidget) -> bool:
        """Download and install update automatically with progress feedback."""
        try:
            # Check if running from source - self-update only works with frozen executables
            if not getattr(sys, "frozen", False):
                QtWidgets.QMessageBox.information(
                    parent_widget,
                    "Update Not Available",
                    "Self-update is only available when running the installed executable.\n\n"
                    "Please download the update manually from the GitHub releases page."
                )
                return False

            # Create progress dialog
            progress_dialog = QtWidgets.QProgressDialog("Preparing update...", "Cancel", 0, 100, parent_widget)
            progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
            progress_dialog.setAutoClose(False)
            progress_dialog.setAutoReset(False)
            progress_dialog.show()

            # Download the update
            progress_dialog.setLabelText("Downloading update...")
            temp_path = self._download_update_with_progress(download_url, progress_dialog)
            if not temp_path:
                progress_dialog.close()
                return False

            # Create and run updater script
            progress_dialog.setLabelText("Preparing installation...")
            progress_dialog.setValue(90)
            updater_script = self._create_updater_script(temp_path)
            if not updater_script:
                progress_dialog.close()
                return False

            # Show completion message
            progress_dialog.setLabelText("Update ready! Application will restart...")
            progress_dialog.setValue(100)
            progress_dialog.setCancelButtonText("Close")

            # Wait a moment to show completion
            QtCore.QTimer.singleShot(1500, progress_dialog.close)

            # Launch updater and exit current app
            QtCore.QTimer.singleShot(2000, lambda: subprocess.Popen([updater_script], shell=True))
            QtCore.QTimer.singleShot(2500, QtWidgets.QApplication.quit)  # Give time for updater to start
            return True

        except Exception as e:
            QtWidgets.QMessageBox.critical(parent_widget, "Update Failed", f"Failed to perform update: {str(e)}")
            return False

    def _download_update_with_progress(
        self, download_url: str, progress_dialog: QtWidgets.QProgressDialog
    ) -> Optional[str]:
        """Download the update executable to a temporary location with progress feedback."""
        try:
            print(f"DEBUG: Starting download from URL: {download_url}")  # Debug logging

            # Create temp file
            temp_fd, temp_path = tempfile.mkstemp(suffix=".exe")
            os.close(temp_fd)  # Close the file descriptor
            print(f"DEBUG: Created temp file: {temp_path}")  # Debug logging

            # Download the file with progress
            with urllib.request.urlopen(download_url, timeout=30) as response:
                total_size = int(response.headers.get("content-length", 0))
                downloaded = 0
                print(f"DEBUG: Total size: {total_size} bytes")  # Debug logging

                with open(temp_path, "wb") as f:
                    while True:
                        if progress_dialog.wasCanceled():
                            print("DEBUG: Download cancelled by user")  # Debug logging
                            os.unlink(temp_path)
                            return None

                        chunk = response.read(8192)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            progress = int((downloaded / total_size) * 80)  # 80% for download
                            progress_dialog.setValue(progress)
                            print(f"DEBUG: Downloaded {downloaded}/{total_size} bytes ({progress}%)")  # Debug logging

            progress_dialog.setValue(80)  # Ensure we show 80% completion
            print(f"DEBUG: Download completed successfully")  # Debug logging
            return temp_path

        except Exception as e:
            print(f"DEBUG: Download failed with error: {str(e)}")  # Debug logging
            progress_dialog.close()
            raise e

    def _create_updater_script(self, new_exe_path: str) -> Optional[str]:
        """Create a batch script that will replace the current executable and restart."""
        try:
            # Get current executable path
            if getattr(sys, "frozen", False):
                # Running as PyInstaller executable
                current_exe = sys.executable
                print(f"DEBUG: Running as frozen executable: {current_exe}")  # Debug logging
            else:
                # Running from source - try to find the executable in dist folder
                app_dir = os.path.dirname(os.path.dirname(__file__))
                current_exe = os.path.join(app_dir, "dist", "greenapi-helper.exe")
                print(f"DEBUG: Running from source, looking for executable: {current_exe}")  # Debug logging
                if not os.path.exists(current_exe):
                    # If dist doesn't exist, we can't self-update from source
                    print(f"DEBUG: Executable not found at: {current_exe}")  # Debug logging
                    self.update_error.emit(
                        "Cannot perform self-update when running from source. Please use manual download."
                    )
                    return None

            print(f"DEBUG: Current executable: {current_exe}")  # Debug logging
            print(f"DEBUG: New executable temp path: {new_exe_path}")  # Debug logging

            # Create updater batch script
            updater_script = os.path.join(tempfile.gettempdir(), "greenapi_updater.bat")
            print(f"DEBUG: Updater script path: {updater_script}")  # Debug logging

            script_content = f"""@echo off
echo Updating Green API Helper...
echo Please wait while the update is installed...
timeout /t 2 /nobreak > nul

REM Wait for main application to fully exit
timeout /t 1 /nobreak > nul

REM Replace the old executable with the new one
move /Y "{new_exe_path}" "{current_exe}"

REM Launch the updated application
start "" "{current_exe}"

REM Clean up this script
del "%~f0"
"""

            with open(updater_script, "w") as f:
                f.write(script_content)

            print(f"DEBUG: Updater script created successfully")  # Debug logging
            return updater_script

        except Exception as e:
            print(f"DEBUG: Failed to create updater script: {str(e)}")  # Debug logging
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
            # Add buttons for frozen executable
            msg_box.addButton("Update Now", QtWidgets.QMessageBox.AcceptRole)
            msg_box.addButton("Download Manually", QtWidgets.QMessageBox.ActionRole)
            msg_box.addButton("View Changelog", QtWidgets.QMessageBox.HelpRole)
            msg_box.addButton("Later", QtWidgets.QMessageBox.RejectRole)
        else:
            # Add buttons for source/development version
            msg_box.addButton("Download Manually", QtWidgets.QMessageBox.AcceptRole)
            msg_box.addButton("View Changelog", QtWidgets.QMessageBox.ActionRole)
            msg_box.addButton("Later", QtWidgets.QMessageBox.RejectRole)

        # Execute dialog and get result
        result = msg_box.exec()

        # Handle button clicks based on return value
        if can_self_update and result == QtWidgets.QMessageBox.AcceptRole and download_url:
            # Update Now button clicked (only available for frozen executables)
            success = self.perform_self_update(download_url, parent)
            if success:
                # Progress dialog will handle the user feedback
                pass
        elif (not can_self_update and result == QtWidgets.QMessageBox.AcceptRole and download_url) or \
             (can_self_update and result == QtWidgets.QMessageBox.ActionRole and download_url):
            # Download Manually button clicked
            QtWidgets.QDesktopServices.openUrl(QtCore.QUrl(download_url))
        elif (can_self_update and result == QtWidgets.QMessageBox.HelpRole and changelog_url) or \
             (not can_self_update and result == QtWidgets.QMessageBox.ActionRole and changelog_url):
            # View Changelog button clicked
            QtWidgets.QDesktopServices.openUrl(QtCore.QUrl(changelog_url))
        # RejectRole (Later) or other cases - just close dialog


def get_update_manager() -> UpdateManager:
    """Get or create the global update manager instance."""
    if not hasattr(get_update_manager, "_instance"):
        get_update_manager._instance = UpdateManager()
    return get_update_manager._instance
