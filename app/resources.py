import sys
from pathlib import Path
def resource_path(relative_path: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent[1]))
    return str(base / relative_path)