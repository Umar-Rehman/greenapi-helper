"""
Auto-update functionality with visible logging for debugging.
"""

import json
import os
import sys
import tempfile
import subprocess
import urllib.request
import traceback
import logging
from datetime import datetime
from typing import Optional
from PySide6 import QtCore, QtWidgets

# Setup file logging
log_dir = os.path.join(tempfile.gettempdir(), "greenapi-helper")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def get_current_version() -> str:
    """Get the current application version from version.json."""
    try:
        version_file = os.path.join(os.path.dirname(__file__), "..", "version.json")
        with open(version_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("version", "0.0.0")
    except FileNotFoundError, json.JSONDecodeError, KeyError:
        return "0.0.0"


class UpdateProgressDialog(QtWidgets.QDialog):
    """Dialog that shows update progress with detailed logs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update Progress")
        self.setMinimumSize(600, 400)
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)

        # Status label
        self.status_label = QtWidgets.QLabel("Initializing update...")
        layout.addWidget(self.status_label)

        # Log text area
        self.log_text = QtWidgets.QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: Consolas, monospace; font-size: 10pt;")
        layout.addWidget(self.log_text)

        # Progress bar
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)

        # Close button (initially hidden)
        self.close_button = QtWidgets.QPushButton("Close")
        self.close_button.clicked.connect(self.accept)
        self.close_button.hide()
        layout.addWidget(self.close_button)

        logger.info(f"Update log file: {log_file}")
        self.log(f"Update log file: {log_file}")

    def log(self, message: str):
        """Add a log message to the dialog."""
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
        QtWidgets.QApplication.processEvents()

    def set_status(self, status: str):
        """Update the status label."""
        self.status_label.setText(status)
        QtWidgets.QApplication.processEvents()

    def set_progress(self, value: int):
        """Update progress bar."""
        self.progress.setValue(value)
        QtWidgets.QApplication.processEvents()

    def show_error(self, error: str):
        """Show an error and enable closing."""
        self.set_status("Update Failed")
        self.log(f"ERROR: {error}")
        self.close_button.show()

    def finish_success(self):
        """Mark update as successful."""
        self.set_status("Update Complete - Application will restart")
        self.set_progress(100)


class UpdateManager(QtCore.QObject):
    """Update manager with visible progress and logging."""

    update_available = QtCore.Signal(dict)
    update_error = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.version_url = "https://api.github.com/repos/Umar-Rehman/greenapi-helper/releases/latest"
        logger.info("UpdateManager initialized")

    def check_for_updates(self) -> None:
        """Check for updates in a background thread."""
        logger.info("Starting update check")
        QtCore.QThreadPool.globalInstance().start(QtCore.QRunnable.create(self._perform_update_check))

    def _perform_update_check(self) -> None:
        """Perform the actual update check."""
        try:
            logger.info(f"Fetching latest release from: {self.version_url}")
            with urllib.request.urlopen(self.version_url, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))

            remote_version = data.get("tag_name", "").lstrip("v")
            logger.info(f"Remote version: {remote_version}")
            if not remote_version:
                logger.warning("No remote version found")
                return

            current = get_current_version()
            logger.info(f"Current version: {current}")

            if self._is_newer_version(remote_version, current):
                update_info = {
                    "version": remote_version,
                    "download_url": self._get_download_url(data),
                    "changelog_url": data.get("html_url", ""),
                    "notes": data.get("body", "New version available"),
                }
                logger.info(f"Update available: {remote_version}")
                self.update_available.emit(update_info)
            else:
                logger.info("No update needed")

        except Exception as e:
            logger.error(f"Update check failed: {e}")
            logger.error(traceback.format_exc())
            self.update_error.emit(f"Update check failed: {str(e)}")

    def _get_download_url(self, release_data: dict) -> str:
        """Extract download URL from release assets."""
        assets = release_data.get("assets", [])
        for asset in assets:
            if asset.get("name") == "greenapi-helper.exe":
                url = asset.get("browser_download_url", "")
                logger.info(f"Found asset URL: {url}")
                return url
        fallback = f"https://github.com/Umar-Rehman/greenapi-helper/releases/download/v{release_data.get('tag_name', '')}/greenapi-helper.exe"
        logger.info(f"Using fallback URL: {fallback}")
        return fallback

    def _is_newer_version(self, remote: str, local: str) -> bool:
        """Compare version strings."""
        try:
            remote_parts = [int(x) for x in remote.split(".")]
            local_parts = [int(x) for x in local.split(".")]
            is_newer = remote_parts > local_parts
            logger.debug(f"Version comparison: {remote} > {local} = {is_newer}")
            return is_newer
        except ValueError as e:
            logger.error(f"Version parsing error: {e}")
            return False

    def perform_simple_update(self, download_url: str, parent_widget: QtWidgets.QWidget) -> None:
        """Perform update with visible progress dialog."""
        logger.info("=== Starting Update Process ===")
        logger.info(f"Download URL: {download_url}")
        logger.info(f"Python executable: {sys.executable}")
        logger.info(f"Frozen: {getattr(sys, 'frozen', False)}")

        # Check if running as executable
        if not getattr(sys, "frozen", False):
            logger.warning("Not running as frozen executable")
            QtWidgets.QMessageBox.information(
                parent_widget,
                "Update Not Available",
                "Self-update only works with the installed executable.\n\n"
                "Please download manually from GitHub releases.",
            )
            return

        # Create and show progress dialog
        progress_dialog = UpdateProgressDialog(parent_widget)
        progress_dialog.show()

        try:
            # Step 1: Download
            progress_dialog.set_status("Downloading update...")
            progress_dialog.log(f"Downloading from: {download_url}")
            progress_dialog.set_progress(10)

            temp_path = self._download_with_progress(download_url, progress_dialog)
            if not temp_path:
                progress_dialog.show_error("Download failed - check log for details")
                return

            progress_dialog.log(f"Downloaded to: {temp_path}")
            progress_dialog.set_progress(60)

            # Step 2: Prepare replacement
            progress_dialog.set_status("Preparing update...")
            progress_dialog.log("Creating update files...")

            success = self._prepare_and_restart(temp_path, progress_dialog)
            if success:
                progress_dialog.finish_success()
                progress_dialog.log("Application will restart in 2 seconds...")
                QtCore.QTimer.singleShot(2000, QtWidgets.QApplication.quit)
            else:
                progress_dialog.show_error("Failed to prepare update")

        except Exception as e:
            logger.error(f"Update failed: {e}")
            logger.error(traceback.format_exc())
            progress_dialog.show_error(f"{type(e).__name__}: {str(e)}")

    def _download_with_progress(self, url: str, dialog: UpdateProgressDialog) -> Optional[str]:
        """Download file with progress updates."""
        try:
            logger.info(f"Starting download: {url}")
            dialog.log("Opening connection...")

            with urllib.request.urlopen(url, timeout=30) as response:
                total_size = int(response.headers.get("content-length", 0))
                logger.info(f"Download size: {total_size} bytes ({total_size / 1024 / 1024:.2f} MB)")
                dialog.log(f"Download size: {total_size / 1024 / 1024:.2f} MB")

                temp_fd, temp_path = tempfile.mkstemp(suffix=".exe")
                os.close(temp_fd)
                logger.info(f"Temp file: {temp_path}")
                dialog.log(f"Saving to: {temp_path}")

                downloaded = 0
                with open(temp_path, "wb") as f:
                    while True:
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            percent = int((downloaded / total_size) * 50) + 10  # 10-60%
                            dialog.set_progress(percent)

                            if downloaded % (1024 * 1024 * 10) == 0:  # Log every 10MB
                                dialog.log(f"Downloaded: {downloaded / 1024 / 1024:.1f} MB")

                logger.info(f"Download complete: {downloaded} bytes")
                dialog.log(f"Download complete: {downloaded / 1024 / 1024:.2f} MB")
                return temp_path

        except Exception as e:
            logger.error(f"Download failed: {e}")
            logger.error(traceback.format_exc())
            dialog.log(f"Download error: {e}")
            return None

    def _prepare_and_restart(self, new_exe_path: str, dialog: UpdateProgressDialog) -> bool:
        """Prepare update files and restart application."""
        try:
            import shutil

            current_exe = sys.executable
            logger.info(f"Current exe: {current_exe}")
            dialog.log(f"Current exe: {current_exe}")

            # Verify downloaded file exists and has size
            if not os.path.exists(new_exe_path):
                logger.error(f"Downloaded file doesn't exist: {new_exe_path}")
                dialog.log("ERROR: Downloaded file not found!")
                return False

            file_size = os.path.getsize(new_exe_path)
            logger.info(f"Downloaded file size: {file_size} bytes")
            dialog.log(f"Downloaded file size: {file_size / 1024 / 1024:.2f} MB")

            if file_size < 1000000:  # Less than 1MB is suspicious
                logger.error(f"Downloaded file too small: {file_size} bytes")
                dialog.log("ERROR: Downloaded file seems corrupted (too small)")
                return False

            # Copy to .updated file
            updated_exe = current_exe + ".updated"
            logger.info(f"Copying to: {updated_exe}")
            dialog.log(f"Creating: {updated_exe}")
            dialog.set_progress(70)

            shutil.copy2(new_exe_path, updated_exe)
            logger.info("Copy successful")
            dialog.log("Copy successful")
            dialog.set_progress(80)

            # Create batch script
            batch_script = current_exe + ".updater.bat"
            batch_content = f"""@echo off
echo Updating Green API Helper...
echo Waiting for main application to close...
timeout /t 3 /nobreak > nul

echo Replacing executable...
move /Y "{updated_exe}" "{current_exe}"
if errorlevel 1 (
    echo ERROR: Failed to replace executable
    pause
    exit /b 1
)

echo Starting updated application...
start "" "{current_exe}"

echo Cleaning up...
timeout /t 2 /nobreak > nul
del "%~f0"
"""

            with open(batch_script, "w") as f:
                f.write(batch_content)
            logger.info(f"Batch script created: {batch_script}")
            dialog.log(f"Update script created: {batch_script}")
            dialog.set_progress(90)

            # Start the batch script in background
            logger.info("Starting update script...")
            dialog.log("Starting update script...")
            subprocess.Popen(
                [batch_script],
                shell=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
            )

            logger.info("Update prepared successfully")
            dialog.set_progress(100)
            return True

        except Exception as e:
            logger.error(f"Prepare failed: {e}")
            logger.error(traceback.format_exc())
            dialog.log(f"ERROR: {e}")
            return False


def get_update_manager() -> UpdateManager:
    """Get or create the global update manager instance."""
    if not hasattr(get_update_manager, "_instance"):
        get_update_manager._instance = UpdateManager()
    return get_update_manager._instance
