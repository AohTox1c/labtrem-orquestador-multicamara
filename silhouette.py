"""
silhouette.py
Dibuja siluetas de referencia de posicionamiento sobre el feed de cámara.

Tipos disponibles:
  'adult'     – adulto sentado, vista frontal  (monitor Cuidador)
  'child'     – niño sentado, vista frontal    (monitor Niño)
  'panoramic' – adulto + niño lado a lado      (monitor Panorámica)
  'none'      – sin silueta
"""
from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QPainter,
    QPainterPath,
    QPen,
)

# ── Paleta ────────────────────────────────────────────────────────────────────
_OUTLINE = QColor(255, 255, 255, 210)
_FILL    = QColor(255, 255, 255, 38)
_GUIDE   = QColor(255, 255, 255, 160)
_DOT     = QColor(255, 255, 255, 230)


# ── API pública ───────────────────────────────────────────────────────────────

def draw_silhouette(painter: QPainter, rect: QRectF, silhouette_type: str) -> None:
    """Punto de entrada: delega al dibujador correcto."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    if silhouette_type == "adult":
        _draw_figure(painter, rect, cx=0.50, top=0.28, scale=0.92, child=False)
    elif silhouette_type == "child":
        _draw_figure(painter, rect, cx=0.50, top=0.32, scale=0.68, child=True)
    elif silhouette_type == "panoramic":
        _draw_figure(painter, rect, cx=0.30, top=0.28, scale=0.72, child=False)
        _draw_figure(painter, rect, cx=0.70, top=0.34, scale=0.56, child=True)
    elif silhouette_type == "panoramic_flipped":
        _draw_figure(painter, rect, cx=0.30, top=0.34, scale=0.56, child=True)
        _draw_figure(painter, rect, cx=0.70, top=0.28, scale=0.72, child=False)
    painter.restore()


# ── Dibujador de figura ───────────────────────────────────────────────────────

def _draw_figure(
    painter: QPainter,
    rect: QRectF,
    cx: float,
    top: float,
    scale: float,
    child: bool,
) -> None:
    W  = rect.width()
    H  = rect.height()
    ox = rect.left()
    oy = rect.top()

    c  = ox + cx * W   # centro horizontal absoluto
    t  = oy + top * H  # borde superior de la figura
    sw = W * scale
    sh = H * scale

    # ── Cabeza ────────────────────────────────────────────────────────────────
    head_rw = 0.068 * sw
    head_rh = (0.100 if child else 0.088) * sh
    head_cy = t + head_rh + 0.010 * sh

    painter.setPen(QPen(_OUTLINE, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(QBrush(_FILL))
    painter.drawEllipse(QRectF(c - head_rw, head_cy - head_rh, head_rw * 2, head_rh * 2))

    # ── Puntos clave del cuerpo ───────────────────────────────────────────────
    neck_hw  = 0.024 * sw
    neck_top = head_cy + head_rh * 0.72
    neck_bot = neck_top + 0.050 * sh

    sh_y  = neck_bot + 0.006 * sh
    sh_hw = (0.155 if child else 0.175) * sw   # semi-ancho hombros

    # Brazo superior (apenas supera el ancho del hombro)
    ua_mid_y = sh_y + 0.105 * sh
    ua_out_x = sh_hw * 1.06

    # Codo (al nivel del ancho del hombro)
    el_y = sh_y + 0.215 * sh
    el_x = sh_hw * 1.00

    # Antebrazo (se acerca al centro → reposa en el regazo)
    fa_y = sh_y + (0.355 if child else 0.372) * sh
    fa_x = sh_hw * 0.76

    # Regazo / base
    lap_y  = sh_y + (0.425 if child else 0.442) * sh
    lap_hw = sh_hw * 0.86

    # ── Cuerpo (trayecto único cerrado) ───────────────────────────────────────
    body = QPainterPath()
    body.moveTo(c - neck_hw, neck_top)

    # Cuello izq → hombro izq
    body.cubicTo(
        c - neck_hw * 2.0, neck_top + (neck_bot - neck_top) * 0.4,
        c - sh_hw * 0.60,  sh_y - 0.008 * sh,
        c - sh_hw,         sh_y,
    )
    # Hombro izq → codo izq (suave arco exterior)
    body.cubicTo(
        c - sh_hw * 1.04,  sh_y + 0.030 * sh,
        c - ua_out_x,      ua_mid_y,
        c - el_x,          el_y,
    )
    # Codo izq → antebrazo izq (curva hacia adentro)
    body.cubicTo(
        c - el_x  * 0.97,  el_y + 0.042 * sh,
        c - fa_x  * 1.05,  fa_y - 0.022 * sh,
        c - fa_x,          fa_y,
    )
    # Antebrazo izq → regazo izq
    body.cubicTo(
        c - fa_x  * 0.92,  fa_y  + 0.018 * sh,
        c - lap_hw * 1.04, lap_y - 0.008 * sh,
        c - lap_hw,        lap_y,
    )
    # Base (regazo)
    body.lineTo(c + lap_hw, lap_y)

    # ── Lado derecho (espejo) ─────────────────────────────────────────────────
    body.cubicTo(
        c + lap_hw * 1.04, lap_y - 0.008 * sh,
        c + fa_x  * 0.92,  fa_y  + 0.018 * sh,
        c + fa_x,          fa_y,
    )
    body.cubicTo(
        c + fa_x  * 1.05,  fa_y - 0.022 * sh,
        c + el_x  * 0.97,  el_y + 0.042 * sh,
        c + el_x,          el_y,
    )
    body.cubicTo(
        c + ua_out_x,      ua_mid_y,
        c + sh_hw * 1.04,  sh_y + 0.030 * sh,
        c + sh_hw,         sh_y,
    )
    body.cubicTo(
        c + sh_hw * 0.60,  sh_y - 0.008 * sh,
        c + neck_hw * 2.0, neck_top + (neck_bot - neck_top) * 0.4,
        c + neck_hw,       neck_top,
    )
    body.closeSubpath()

    painter.setPen(QPen(_OUTLINE, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(QBrush(_FILL))
    painter.drawPath(body)

    # ── Guías de referencia ───────────────────────────────────────────────────
    guide_pen = QPen(_GUIDE, 1.3, Qt.DashLine)
    guide_pen.setDashPattern([6, 4])
    painter.setPen(guide_pen)
    painter.setBrush(Qt.NoBrush)

    spread = 0.38 * sw
    painter.drawLine(QPointF(c, oy + 0.01 * H), QPointF(c, oy + H * 0.98))
    painter.drawLine(QPointF(c - spread, sh_y),           QPointF(c + spread, sh_y))
    painter.drawLine(QPointF(c - spread * 0.78, lap_y),   QPointF(c + spread * 0.78, lap_y))

    # ── Keypoints ─────────────────────────────────────────────────────────────
    painter.setBrush(QBrush(_DOT))
    painter.setPen(Qt.NoPen)
    dr = max(3.0, 4.0 * scale)
    for pt in [
        QPointF(c,          head_cy - head_rh),
        QPointF(c,          head_cy),
        QPointF(c - sh_hw,  sh_y),
        QPointF(c + sh_hw,  sh_y),
        QPointF(c - el_x,   el_y),
        QPointF(c + el_x,   el_y),
        QPointF(c,         (sh_y + lap_y) * 0.5),
        QPointF(c - lap_hw, lap_y),
        QPointF(c + lap_hw, lap_y),
    ]:
        painter.drawEllipse(pt, dr, dr)
