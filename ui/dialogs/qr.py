from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QHBoxLayout,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication

from app.ui_utils import pixmap_from_base64_png


class QrCodeDialog(QDialog):
    def __init__(self, *, link: str, qr_base64: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QR Code")
        self.setMinimumWidth(560)

        self._qr_base64 = qr_base64
        self._qr_visible = False
        self._pix_original = None

        root = QVBoxLayout(self)

        root.addWidget(QLabel("Open this link to view QR in browser:"))

        self.link_box = QTextEdit()
        self.link_box.setReadOnly(True)
        self.link_box.setPlainText(link)
        self.link_box.setFixedHeight(60)
        root.addWidget(self.link_box)

        self.preview = QLabel(alignment=Qt.AlignCenter)
        self.preview.hide()
        root.addWidget(self.preview)

        row = QHBoxLayout()

        self.btn_preview = QPushButton("Show QR image")
        self.btn_preview.clicked.connect(self._on_preview)
        row.addWidget(self.btn_preview)

        self.btn_copy = QPushButton("Copy QR image")
        self.btn_copy.clicked.connect(self._copy_qr)
        self.btn_copy.setEnabled(bool(qr_base64))
        row.addWidget(self.btn_copy)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_close)

        root.addLayout(row)

        if not qr_base64:
            self.btn_preview.setEnabled(False)
            self.btn_preview.setText("No image to preview")

    def _on_preview(self):
        if self._qr_visible:
            self.preview.hide()
            self.btn_preview.setText("Show QR image")
            self._qr_visible = False
            self.adjustSize()
            return

        pix = pixmap_from_base64_png(self._qr_base64)
        if not pix:
            return

        self.preview.setPixmap(pix.scaledToWidth(320, Qt.SmoothTransformation))
        self.preview.show()
        self.btn_preview.setText("Hide QR image")
        self._qr_visible = True
        self.adjustSize()

    def _copy_qr(self):
        if not self._pix_original:
            self._pix_original = pixmap_from_base64_png(self._qr_base64)
        if not self._pix_original:
            return

        QGuiApplication.clipboard().setPixmap(self._pix_original)
        self.btn_copy.setText("Copied!")
        self.btn_copy.setEnabled(False)
        QTimer.singleShot(1200, self._reset_copy)

    def _reset_copy(self):
        self.btn_copy.setText("Copy QR image")
        self.btn_copy.setEnabled(True)
