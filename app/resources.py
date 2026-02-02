import sys
from pathlib import Path


def resource_path(relative_path: str) -> str:
    # Check if running in PyInstaller bundle
    if getattr(sys, "frozen", False):
        # Running as bundled executable
        base = Path(sys._MEIPASS)
    else:
        # Running as script
        base = Path(__file__).resolve().parent.parent  # Go up from app/ to project root
    return str(base / relative_path)
