from __future__ import annotations

from PySide6.QtCore import Property, QPropertyAnimation, QEasingCurve, Qt, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QCheckBox


class ToggleSwitch(QCheckBox):
    """
    iOS-style animated toggle switch.
    Usage: sw = ToggleSwitch(); sw.setChecked(True/False)
    Behaves like QCheckBox (isChecked(), toggled signal, etc).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

        self._offset = 0.0  # knob position 0..1
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self.setChecked(False)  # ensures offset matches initial state
        self.stateChanged.connect(self._start_anim)

        # Make it compact; you can tweak
        self._w = 42
        self._h = 22
        self.setMinimumSize(self._w, self._h)

    def sizeHint(self) -> QSize:
        return QSize(self._w, self._h)

    def _start_anim(self):
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if self.isChecked() else 0.0)
        self._anim.start()

    def hitButton(self, pos):
        # Whole widget clickable
        return self.rect().contains(pos)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        r = self.rect()
        margin = 2
        track = QRectF(margin, margin, r.width() - 2 * margin, r.height() - 2 * margin)
        radius = track.height() / 2.0

        # Colors (no QSS required)
        if self.isEnabled():
            track_on = QColor(52, 199, 89)
            track_off = QColor(200, 200, 200)
            knob = QColor(255, 255, 255)
            border = QColor(150, 150, 150)
        else:
            track_on = QColor(170, 220, 185)
            track_off = QColor(220, 220, 220)
            knob = QColor(245, 245, 245)
            border = QColor(190, 190, 190)

        # Track
        p.setPen(Qt.NoPen)
        p.setBrush(track_on if self.isChecked() else track_off)
        p.drawRoundedRect(track, radius, radius)

        # Optional border
        p.setPen(QPen(border, 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(track, radius, radius)

        # Knob
        knob_d = track.height() - 4
        x0 = track.left() + 2
        x1 = track.right() - 2 - knob_d
        x = x0 + (x1 - x0) * self._offset
        knob_rect = QRectF(x, track.top() + 2, knob_d, knob_d)

        p.setPen(Qt.NoPen)
        p.setBrush(knob)
        p.drawEllipse(knob_rect)

        p.end()

    # --- animated property ---
    def getOffset(self) -> float:
        return self._offset

    def setOffset(self, v: float):
        self._offset = float(v)
        self.update()

    offset = Property(float, getOffset, setOffset)
