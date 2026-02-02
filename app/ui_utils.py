import base64
from PySide6.QtGui import QPixmap


def pixmap_from_base64_png(b64: str) -> QPixmap | None:
    try:
        raw = base64.b64decode(b64)
        pix = QPixmap()
        if pix.loadFromData(raw, "PNG"):
            return pix
    except Exception:
        pass
    return None
