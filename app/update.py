"""
Auto-update functionality for the Green API Helper application.
"""

import json
import os
import sys
import tempfile
import shutil
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
        # For private repos, use GitHub API with personal access token
        self.version_url = "https://api.github.com/repos/Umar-Rehman/greenapi-helper/releases/latest"
        self.github_token = os.environ.get("GITHUB_TOKEN")  # Get from environment variable
        self.check_interval_hours = 24  # Check once per day

    def check_for_updates(self) -> None:
        """Check for updates in a background thread."""
        # Run the check in a separate thread to avoid blocking UI
        QtCore.QThreadPool.globalInstance().start(QtCore.QRunnable.create(self._perform_update_check))

    def _perform_update_check(self) -> None:
        """Perform the actual update check."""
        try:
            # Create request with authentication if token is provided
            req = urllib.request.Request(self.version_url)
            if self.github_token:
                req.add_header("Authorization", f"token {self.github_token}")
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

    def perform_self_update(self, download_url: str) -> bool:
        """Download and install update automatically."""
        try:
            # Download the update
            temp_path = self._download_update(download_url)
            if not temp_path:
                return False

            # Create and run updater script
            updater_script = self._create_updater_script(temp_path)
            if not updater_script:
                return False

            # Launch updater and exit current app
            subprocess.Popen([updater_script], shell=True)
            QtCore.QTimer.singleShot(1000, QtWidgets.QApplication.quit)  # Give time for updater to start
            return True

        except Exception as e:
            self.update_error.emit(f"Failed to perform self-update: {str(e)}")
            return False

    def _download_update(self, download_url: str) -> Optional[str]:
        """Download the update executable to a temporary location."""
        try:
            # Create temp file
            temp_fd, temp_path = tempfile.mkstemp(suffix=".exe")
            os.close(temp_fd)  # Close the file descriptor

            # Download the file
            with urllib.request.urlopen(download_url, timeout=30) as response:
                with open(temp_path, "wb") as f:
                    shutil.copyfileobj(response, f)

            return temp_path

        except Exception as e:
            self.update_error.emit(f"Failed to download update: {str(e)}")
            return None

    def _create_updater_script(self, new_exe_path: str) -> Optional[str]:
        """Create a batch script that will replace the current executable and restart."""
        try:
            # Get current executable path
            if getattr(sys, "frozen", False):
                # Running as PyInstaller executable
                current_exe = sys.executable
            else:
                # Running from source - try to find the executable in dist folder
                app_dir = os.path.dirname(os.path.dirname(__file__))
                current_exe = os.path.join(app_dir, "dist", "greenapi-helper.exe")
                if not os.path.exists(current_exe):
                    # If dist doesn't exist, we can't self-update from source
                    self.update_error.emit(
                        "Cannot perform self-update when running from source. Please use manual download."
                    )
                    return None

            # Create updater batch script
            updater_script = os.path.join(tempfile.gettempdir(), "greenapi_updater.bat")

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

            return updater_script

        except Exception as e:
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

        # Add buttons
        update_now_button = msg_box.addButton("Update Now", QtWidgets.QMessageBox.AcceptRole)
        download_button = msg_box.addButton("Download Manually", QtWidgets.QMessageBox.ActionRole)
        changelog_button = msg_box.addButton("View Changelog", QtWidgets.QMessageBox.HelpRole)
        msg_box.addButton("Later", QtWidgets.QMessageBox.RejectRole)

        msg_box.exec()

        clicked_button = msg_box.clickedButton()

        if clicked_button == update_now_button and download_url:
            # Perform automatic self-update
            success = self.perform_self_update(download_url)
            if success:
                QtWidgets.QMessageBox.information(
                    parent,
                    "Update Started",
                    "The application will now update and restart automatically.\n" "This may take a few moments...",
                )
        elif clicked_button == download_button and download_url:
            QtWidgets.QDesktopServices.openUrl(QtCore.QUrl(download_url))
        elif clicked_button == changelog_button and changelog_url:
            QtWidgets.QDesktopServices.openUrl(QtCore.QUrl(changelog_url))
        # If "Later" is clicked, just close the dialog


def get_update_manager() -> UpdateManager:
    """Get or create the global update manager instance."""
    if not hasattr(get_update_manager, "_instance"):
        get_update_manager._instance = UpdateManager()
    return get_update_manager._instance
