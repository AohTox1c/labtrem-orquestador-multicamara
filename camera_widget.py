"""
camera_widget.py
Widget que muestra el feed en vivo de una cámara y superpone la silueta.
"""
from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QSizePolicy, QWidget

from silhouette import draw_silhouette

_BG_DARK   = QColor("#16213e")
_TEXT_IDLE = QColor("#4a5568")
_OVERLAY_REC = QColor(220, 38, 38, 180)   # rojo semitransparente para indicador REC


class CameraWidget(QWidget):
    """
    Muestra el frame actual de una cámara escalado a la ventana,
    con la silueta de referencia superpuesta.
    """

    def __init__(self, silhouette_type: str = "adult", parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._silhouette_type = silhouette_type
        self._show_silhouette = True
        self._recording = False

        self.setMinimumSize(280, 200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #16213e; border-radius: 0px;")

    # ── Slots / mutadores ─────────────────────────────────────────────────────

    def update_frame(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def set_silhouette_type(self, silhouette_type: str) -> None:
        self._silhouette_type = silhouette_type
        self.update()

    def set_silhouette_visible(self, visible: bool) -> None:
        self._show_silhouette = visible
        self.update()

    def set_recording(self, recording: bool) -> None:
        self._recording = recording
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self._recording = False
        self.update()

    # ── Pintado ───────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        rect = self.rect()

        if self._pixmap and not self._pixmap.isNull():
            self._draw_frame(painter, rect)
        else:
            self._draw_idle(painter, rect)

        if self._show_silhouette:
            draw_silhouette(painter, QRectF(rect), self._silhouette_type)

        if self._recording:
            self._draw_rec_indicator(painter, rect)

        painter.end()

    def _draw_frame(self, painter: QPainter, rect) -> None:
        """Dibuja el frame de cámara centrado y con relación de aspecto preservada."""
        scaled = self._pixmap.scaled(
            rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        px = (rect.width()  - scaled.width())  // 2
        py = (rect.height() - scaled.height()) // 2

        # Recortar al rect del widget
        painter.setClipRect(rect)
        painter.drawPixmap(px, py, scaled)
        painter.setClipping(False)

    def _draw_idle(self, painter: QPainter, rect) -> None:
        """Fondo oscuro con mensaje cuando no hay cámara conectada."""
        painter.fillRect(rect, _BG_DARK)

        # Icono de cámara sencillo (texto Unicode)
        painter.setPen(QPen(_TEXT_IDLE))
        icon_font = QFont("Segoe UI", 28)
        painter.setFont(icon_font)
        painter.drawText(
            QRectF(rect).adjusted(0, -20, 0, 0),
            Qt.AlignHCenter | Qt.AlignVCenter,
            "📷",
        )
        msg_font = QFont("Segoe UI", 10)
        painter.setFont(msg_font)
        painter.drawText(
            QRectF(rect).adjusted(0, 44, 0, 0),
            Qt.AlignHCenter | Qt.AlignVCenter,
            "Sin señal de cámara",
        )

    def _draw_rec_indicator(self, painter: QPainter, rect) -> None:
        """Punto rojo REC en la esquina superior derecha."""
        painter.setBrush(QBrush(_OVERLAY_REC))
        painter.setPen(Qt.NoPen)
        r = 8
        margin = 10
        painter.drawEllipse(rect.right() - margin - r, rect.top() + margin, r * 2, r * 2)

        painter.setPen(QPen(QColor(255, 255, 255, 220)))
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)
        painter.drawText(
            rect.right() - margin - r * 2 - 32,
            rect.top() + margin,
            32,
            r * 2,
            Qt.AlignRight | Qt.AlignVCenter,
            "REC",
        )
