"""
main_window.py
Ventana principal — LabTREM Orquestador Multicámara.
"""
import datetime
import os

from PyQt5.QtCore import QPropertyAnimation, QRectF, Qt, QTimer, pyqtProperty
from PyQt5.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPen, QPalette
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from camera_detector import detect_cameras
from camera_thread import CameraThread
from camera_widget import CameraWidget
from audio_recorder import AudioRecorder, mux_audio_into_video

# ── Roles de cámara ───────────────────────────────────────────────────────────
ROLES = [
    {
        "key": "cuidador",
        "label": "Cuidador",
        "color": "#3b82f6",
        "abbr": "C",
        "silhouette": "adult",
    },
    {
        "key": "nino",
        "label": "Niño",
        "color": "#10b981",
        "abbr": "N",
        "silhouette": "child",
    },
    {
        "key": "panoramica",
        "label": "Panorámica",
        "color": "#7c3aed",
        "abbr": "P",
        "silhouette": "panoramic",
    },
]


# ── Widget: logo LabTREM ─────────────────────────────────────────────────────

class _LabTremLogo(QWidget):
    def __init__(self, size: int = 56, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, _event):  # noqa: N802
        from PyQt5.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        s = float(self.width())

        # Clip al círculo para que nada sobresalga
        margin = 1.0
        circle_rect = QRectF(margin, margin, s - 2 * margin, s - 2 * margin)
        clip = QPainterPath()
        clip.addEllipse(circle_rect)
        p.setClipPath(clip)

        # Fondo oscuro
        p.setBrush(QBrush(QColor("#1c1008")))
        p.setPen(Qt.NoPen)
        p.drawEllipse(circle_rect)

        # ── "lab" pequeño en la esquina superior izquierda ────────────────
        f_lab = QFont("Arial Black", max(6, int(s * 0.16)), QFont.Bold)
        f_lab.setLetterSpacing(QFont.AbsoluteSpacing, -0.5)
        p.setFont(f_lab)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(s * 0.14, s * 0.11, s * 0.50, s * 0.28),
                   Qt.AlignLeft | Qt.AlignVCenter, "lab")

        # ── "TREM" grande, centrado, T·R blancos, E azul, M blanco ───────
        f_trem = QFont("Arial Black", max(9, int(s * 0.265)), QFont.Bold)
        p.setFont(f_trem)
        fm = p.fontMetrics()

        chars = [("T", "#ffffff"), ("R", "#ffffff"), ("E", "#9ec8e0"), ("M", "#ffffff")]
        total_w = sum(fm.horizontalAdvance(ch) for ch, _ in chars)

        base_x = (s - total_w) / 2.0
        base_y = s * 0.845

        for ch, color in chars:
            p.setPen(QColor(color))
            cw = fm.horizontalAdvance(ch)
            p.drawText(QRectF(base_x, base_y - fm.ascent(), cw + 1, fm.height()),
                       Qt.AlignLeft | Qt.AlignTop, ch)
            base_x += cw

        p.end()


# ── Widget auxiliar: punto de estado ─────────────────────────────────────────
class _StatusDot(QLabel):
    _ACTIVE   = "background:#22c55e;border-radius:6px;"
    _INACTIVE = "background:#cbd5e1;border-radius:6px;"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        self.setStyleSheet(self._ACTIVE if active else self._INACTIVE)

# ── Widget auxiliar: spinner de carga ─────────────────────────────────────────
class _Spinner(QLabel):
    """Animación de carga con caracteres rotativos."""
    _FRAMES = ("◜", "◝", "◞", "◟")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._idx = 0
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self.setStyleSheet("font-size:15px;color:#2563eb;")
        self.setFixedWidth(20)
        self.hide()

    def start(self) -> None:
        self._idx = 0
        self.setText(self._FRAMES[0])
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()
        self.setText("")

    def _tick(self) -> None:
        self._idx = (self._idx + 1) % len(self._FRAMES)
        self.setText(self._FRAMES[self._idx])


# ── Widget auxiliar: notificación flotante (toast) ────────────────────────
class _Toast(QWidget):
    """Notificación emergente que aparece y desaparece con una animación."""

    def __init__(self, parent: QWidget):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)

        self._lbl = QLabel()
        self._lbl.setWordWrap(True)
        self._lbl.setStyleSheet(
            "color:#ffffff;font-size:13px;font-weight:500;background:transparent;"
        )
        layout.addWidget(self._lbl)

        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)

        self._anim_in  = QPropertyAnimation(self._effect, b"opacity")
        self._anim_in.setDuration(300)
        self._anim_in.setStartValue(0.0)
        self._anim_in.setEndValue(1.0)

        self._anim_out = QPropertyAnimation(self._effect, b"opacity")
        self._anim_out.setDuration(400)
        self._anim_out.setStartValue(1.0)
        self._anim_out.setEndValue(0.0)
        self._anim_out.finished.connect(self.hide)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._anim_out.start)

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(30, 41, 59, 230)))   # slate-800 semi-transparente
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(self.rect(), 12, 12)
        p.end()

    def show_message(self, text: str, duration_ms: int = 4000) -> None:
        self._lbl.setText(text)
        self.adjustSize()
        self._reposition()
        self._anim_out.stop()
        self._hide_timer.stop()
        self._effect.setOpacity(0.0)
        self.show()
        self._anim_in.start()
        self._hide_timer.start(duration_ms)

    def _reposition(self) -> None:
        parent = self.parent()
        if parent:
            pr = parent.rect()
            self.move(
                pr.right() - self.width() - 24,
                pr.bottom() - self.height() - 48,
            )

# ── Ventana principal ─────────────────────────────────────────────────────────
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LabTREM — Orquestador Multicámara")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 820)

        # Estado interno
        self._threads:   dict[str, CameraThread]  = {}
        self._widgets:   dict[str, CameraWidget]  = {}
        self._combos:    dict[str, QComboBox]      = {}
        self._dots:      dict[str, _StatusDot]     = {}
        self._slabels:   dict[str, QLabel]         = {}
        self._cameras:   list[tuple[int, str]]     = []
        self._recording  = False
        self._rec_start: datetime.datetime | None  = None
        self._panoramic_flipped = False
        self._recording_paths: list[str] = []
        self._audio_recorder = AudioRecorder()
        self._spinners:  dict[str, _Spinner]   = {}
        # En Linux (Raspberry Pi) usa el disco externo; en Windows, carpeta Videos
        if os.name == "nt":
            self._output_dir = os.path.join(os.path.expanduser("~"), "Videos", "LabTREM")
        else:
            self._output_dir = "/mnt/disco1/Camarapp/Videos"

        # Timer para mostrar duración en la barra de estado
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(1000)
        self._rec_timer.timeout.connect(self._update_rec_status)

        self._toast = _Toast(self)

        self._build_ui()
        self._apply_stylesheet()
        self._refresh_cameras()

    # ═════════════════════════════════════════════════════════════════════════
    # Construcción de la UI
    # ═════════════════════════════════════════════════════════════════════════

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        layout.addWidget(self._build_header())
        layout.addWidget(self._build_connection_panel())
        layout.addWidget(self._build_views_panel(), stretch=1)
        layout.addWidget(self._build_controls())

        self._status_bar = QStatusBar()
        self._status_bar.setFixedHeight(26)
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Listo. Seleccione las cámaras y pulse Conectar.")

    # ── Encabezado ────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)

        # Logo LabTREM
        logo = _LabTremLogo(56)
        h.addWidget(logo)

        vbox_t = QVBoxLayout()
        vbox_t.setSpacing(0)
        vbox_t.setContentsMargins(6, 0, 0, 0)
        lbl_brand = QLabel("LabTREM")
        lbl_brand.setStyleSheet("font-size:9px;font-weight:700;color:#94a3b8;letter-spacing:3.5px;")
        lbl_name = QLabel("Orquestador Multicámara")
        lbl_name.setStyleSheet("font-size:17px;font-weight:700;color:#0f172a;letter-spacing:-0.3px;")
        vbox_t.addWidget(lbl_brand)
        vbox_t.addWidget(lbl_name)
        h.addLayout(vbox_t)

        h.addStretch()

        btn_open = QPushButton("Abrir carpeta")
        btn_open.setObjectName("btn_secondary")
        btn_open.clicked.connect(self._open_output_dir)
        h.addWidget(btn_open)

        self._btn_refresh = QPushButton("Actualizar cámaras")
        self._btn_refresh.setObjectName("btn_secondary")
        self._btn_refresh.clicked.connect(self._refresh_cameras)
        h.addWidget(self._btn_refresh)

        return w

    # ── Panel de conexión ─────────────────────────────────────────────────────

    def _build_connection_panel(self) -> QGroupBox:
        box = QGroupBox()
        box.setObjectName("connection_panel")
        vbox = QVBoxLayout(box)
        vbox.setContentsMargins(18, 12, 18, 12)
        vbox.setSpacing(6)

        # Título del panel
        title_row = QHBoxLayout()
        lbl_title = QLabel("Conexión de cámaras")
        lbl_title.setStyleSheet("font-size:13px;font-weight:700;color:#0f172a;letter-spacing:0.2px;")
        title_row.addWidget(lbl_title)
        title_row.addStretch()
        vbox.addLayout(title_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#e2e8f0;")
        vbox.addWidget(sep)

        for role in ROLES:
            vbox.addWidget(self._build_camera_row(role))

        return box

    def _build_camera_row(self, role: dict) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(4, 2, 4, 2)
        h.setSpacing(12)

        pill = QLabel(role["abbr"])
        pill.setFixedSize(26, 26)
        pill.setAlignment(Qt.AlignCenter)
        pill.setStyleSheet(
            f"background:{role['color']};color:#ffffff;font-size:11px;"
            "font-weight:700;border-radius:6px;"
        )
        h.addWidget(pill)

        lbl = QLabel(role["label"])
        lbl.setFixedWidth(92)
        lbl.setStyleSheet("font-size:13px;font-weight:600;color:#1e293b;")
        h.addWidget(lbl)

        combo = QComboBox()
        combo.setObjectName("camera_combo")
        combo.setMinimumWidth(260)
        self._combos[role["key"]] = combo
        combo.currentIndexChanged.connect(
            lambda _, k=role["key"]: self._on_camera_selected(k)
        )
        h.addWidget(combo)

        dot = _StatusDot()
        self._dots[role["key"]] = dot
        h.addWidget(dot)

        spinner = _Spinner()
        self._spinners[role["key"]] = spinner
        h.addWidget(spinner)

        slabel = QLabel("Desconectada")
        slabel.setStyleSheet("font-size:12px;color:#94a3b8;")
        slabel.setFixedWidth(100)
        self._slabels[role["key"]] = slabel
        h.addWidget(slabel)

        h.addStretch()
        return w

    # ── Panel de vistas de cámara ─────────────────────────────────────────────

    def _build_views_panel(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(10)
        for role in ROLES:
            h.addWidget(self._build_view_card(role), stretch=1)
        return w

    def _build_view_card(self, role: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("view_card")
        vbox = QVBoxLayout(card)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Cabecera de la tarjeta
        header = QWidget()
        header.setObjectName("view_card_header")
        header.setFixedHeight(36)
        hh = QHBoxLayout(header)
        hh.setContentsMargins(12, 0, 12, 0)
        hh.setSpacing(8)
        accent = QFrame()
        accent.setFixedSize(4, 18)
        accent.setStyleSheet(f"background:{role['color']};border-radius:2px;")
        hh.addWidget(accent)
        lbl = QLabel(role["label"])
        lbl.setStyleSheet("font-size:12px;font-weight:700;color:#334155;letter-spacing:0.2px;")
        hh.addWidget(lbl)
        hh.addStretch()

        # Botón invertir solo en Panorámica
        if role["key"] == "panoramica":
            self._btn_flip = QPushButton("Invertir")
            self._btn_flip.setObjectName("btn_flip")
            self._btn_flip.setFixedHeight(22)
            self._btn_flip.setToolTip("Intercambia la posición del adulto y el niño en la silueta")
            self._btn_flip.clicked.connect(self._toggle_panoramic_flip)
            hh.addWidget(self._btn_flip)

        vbox.addWidget(header)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#e2e8f0;")
        vbox.addWidget(sep)

        # Widget de cámara
        cam = CameraWidget(role["silhouette"])
        self._widgets[role["key"]] = cam
        vbox.addWidget(cam, stretch=1)

        return card

    # ── Barra de controles ────────────────────────────────────────────────────

    def _build_controls(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 4, 0, 0)
        h.setSpacing(12)

        self._chk_silhouette = QCheckBox("Mostrar silueta de referencia")
        self._chk_silhouette.setChecked(True)
        self._chk_silhouette.stateChanged.connect(self._toggle_silhouette)
        h.addWidget(self._chk_silhouette)

        # Contador de grabación visible
        self._lbl_timer = QLabel("REC  00:00")
        self._lbl_timer.setObjectName("rec_timer_label")
        self._lbl_timer.setFixedHeight(46)
        self._lbl_timer.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self._lbl_timer.hide()
        h.addWidget(self._lbl_timer)

        h.addStretch()

        self._btn_connect = QPushButton("Reconectar todo")
        self._btn_connect.setObjectName("btn_connect")
        self._btn_connect.setFixedHeight(46)
        self._btn_connect.setToolTip(
            "Desconecta y vuelve a conectar todas las cámaras seleccionadas.\n"
            "Las cámaras se conectan automáticamente al elegirlas en el desplegable."
        )
        self._btn_connect.clicked.connect(self._connect_cameras)
        h.addWidget(self._btn_connect)

        self._btn_record = QPushButton("Grabar")
        self._btn_record.setObjectName("btn_record")
        self._btn_record.setFixedHeight(46)
        self._btn_record.setEnabled(False)
        self._btn_record.clicked.connect(self._start_recording)
        h.addWidget(self._btn_record)

        self._btn_stop = QPushButton("Detener")
        self._btn_stop.setObjectName("btn_stop")
        self._btn_stop.setFixedHeight(46)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._stop_recording)
        h.addWidget(self._btn_stop)

        h.addStretch()
        return w

    # ═════════════════════════════════════════════════════════════════════════
    # Lógica de cámaras
    # ═════════════════════════════════════════════════════════════════════════

    def _refresh_cameras(self) -> None:
        """Detecta cámaras disponibles y llena los desplegables."""
        self._btn_refresh.setEnabled(False)
        self._btn_refresh.setText("Buscando...")
        self._status_bar.showMessage("Buscando cámaras...")
        # Procesar eventos para que el texto se actualice antes del bloqueo
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        self._cameras = detect_cameras()
        for role in ROLES:
            combo = self._combos[role["key"]]
            prev = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("— Seleccionar cámara —", userData=-1)
            for idx, name in self._cameras:
                combo.addItem(name, userData=idx)
            # Restaurar selección anterior si sigue disponible
            if prev is not None:
                for i in range(combo.count()):
                    if combo.itemData(i) == prev:
                        combo.setCurrentIndex(i)
                        break
            combo.blockSignals(False)

        n = len(self._cameras)
        self._status_bar.showMessage(
            f"{n} cámara(s) detectada(s). Selecciónelas en los desplegables para iniciar la vista previa."
        )        self._btn_refresh.setEnabled(True)
        self._btn_refresh.setText("Actualizar cámaras")
    def _on_camera_selected(self, key: str) -> None:
        """Conecta automáticamente la cámara elegida en el desplegable."""
        if key in self._threads:
            self._threads[key].stop()
            del self._threads[key]
            self._widgets[key].clear()
            self._dots[key].set_active(False)
            self._spinners[key].stop()
            self._slabels[key].setText("Desconectada")
            self._slabels[key].setStyleSheet("font-size:12px;color:#94a3b8;")

        idx = self._combos[key].currentData()
        if idx is None or idx < 0:
            self._btn_record.setEnabled(bool(self._threads))
            return

        self._start_thread(key, idx)
        self._status_bar.showMessage(f"Conectando {key}…")

    def _start_thread(self, key: str, idx: int) -> None:
        """Arranca un hilo de captura para el slot indicado."""
        self._spinners[key].start()
        self._slabels[key].setText("Conectando…")
        self._slabels[key].setStyleSheet("font-size:12px;color:#2563eb;")
        thread = CameraThread(idx, self)
        thread.frame_ready.connect(self._widgets[key].update_frame)
        thread.connected.connect(lambda ok, k=key: self._on_connected(k, ok))
        thread.error_occurred.connect(lambda msg, k=key: self._on_error(k, msg))
        thread.start()
        self._threads[key] = thread
        self._btn_record.setEnabled(True)

    def _connect_cameras(self) -> None:
        """Reconecta todas las cámaras seleccionadas."""
        self._disconnect_all()
        connected = 0
        for role in ROLES:
            idx = self._combos[role["key"]].currentData()
            if idx is None or idx < 0:
                continue
            self._start_thread(role["key"], idx)
            connected += 1

        if connected:
            self._status_bar.showMessage(f"{connected} cámara(s) reconectando…")
        else:
            self._status_bar.showMessage(
                "No se seleccionó ninguna cámara. Elija al menos una."
            )

    def _on_connected(self, key: str, ok: bool) -> None:
        self._spinners[key].stop()
        self._dots[key].set_active(ok)
        self._slabels[key].setText("Lista" if ok else "Error")
        self._slabels[key].setStyleSheet(
            f"font-size:12px;color:{'#22c55e' if ok else '#ef4444'};"
        )

    def _on_error(self, key: str, msg: str) -> None:
        self._spinners[key].stop()
        self._dots[key].set_active(False)
        self._slabels[key].setText("Error")
        self._slabels[key].setStyleSheet("font-size:12px;color:#ef4444;")
        self._status_bar.showMessage(f"Error [{key}]: {msg}")

    def _disconnect_all(self) -> None:
        for key, thread in self._threads.items():
            thread.stop()
            self._widgets[key].clear()
            self._dots[key].set_active(False)
            self._spinners[key].stop()
            self._slabels[key].setText("Desconectada")
            self._slabels[key].setStyleSheet("font-size:12px;color:#94a3b8;")
        self._threads.clear()
        self._btn_record.setEnabled(False)

    # ═════════════════════════════════════════════════════════════════════════
    # Grabación
    # ═════════════════════════════════════════════════════════════════════════

    def _start_recording(self) -> None:
        os.makedirs(self._output_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._recording_paths = []

        # Arrancar grabación en todos los hilos activos simultáneamente
        for key, thread in self._threads.items():
            path = os.path.join(self._output_dir, f"{key}_{ts}.mp4")
            self._recording_paths.append(path)
            thread.start_recording(path)

        # Iniciar grabación de audio (no-op si sounddevice no está instalado)
        self._audio_recorder.start()

        # Indicar REC en los widgets
        for key in self._threads:
            self._widgets[key].set_recording(True)

        self._recording = True
        self._rec_start = datetime.datetime.now()
        self._btn_record.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._btn_connect.setEnabled(False)
        self._lbl_timer.setText("REC  00:00")
        self._lbl_timer.show()
        self._rec_timer.start()
        self._status_bar.showMessage(f"REC — Grabando  |  Destino: {self._output_dir}")

    def _stop_recording(self) -> None:
        self._rec_timer.stop()

        for key, thread in self._threads.items():
            thread.stop_recording()
            self._widgets[key].set_recording(False)

        # Detener audio y mezclar con cada video si ffmpeg está disponible
        wav_path = self._audio_recorder.stop()
        if wav_path:
            for vpath in self._recording_paths:
                mux_audio_into_video(vpath, wav_path)
            try:
                import os as _os
                _os.remove(wav_path)
            except OSError:
                pass
        self._recording_paths = []

        elapsed = ""
        if self._rec_start:
            secs = int((datetime.datetime.now() - self._rec_start).total_seconds())
            m, s = divmod(secs, 60)
            elapsed = f"  ({m:02d}:{s:02d})"
            self._rec_start = None

        self._recording = False
        self._btn_record.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._btn_connect.setEnabled(True)
        self._lbl_timer.hide()
        self._status_bar.showMessage(
            f"Grabación finalizada{elapsed}.  Archivos en: {self._output_dir}"
        )

        n = len(self._recording_paths)
        self._toast.show_message(
            f"Grabación guardada correctamente\n"
            f"{n} archivo(s) en:\n{self._output_dir}",
            duration_ms=6000,
        )

    def _update_rec_status(self) -> None:
        if self._rec_start:
            secs = int((datetime.datetime.now() - self._rec_start).total_seconds())
            m, s = divmod(secs, 60)
            time_str = f"{m:02d}:{s:02d}"
            self._lbl_timer.setText(f"REC  {time_str}")
            self._status_bar.showMessage(
                f"REC — Grabando  {time_str}  |  Destino: {self._output_dir}"
            )

    # ═════════════════════════════════════════════════════════════════════════
    # Otros controles
    # ═════════════════════════════════════════════════════════════════════════

    def _toggle_panoramic_flip(self) -> None:
        self._panoramic_flipped = not self._panoramic_flipped
        stype = "panoramic_flipped" if self._panoramic_flipped else "panoramic"
        self._widgets["panoramica"].set_silhouette_type(stype)
        self._btn_flip.setText("Vista normal" if self._panoramic_flipped else "Invertir")

    def _toggle_silhouette(self, state: int) -> None:
        visible = state == Qt.Checked
        for widget in self._widgets.values():
            widget.set_silhouette_visible(visible)

    def _open_output_dir(self) -> None:
        os.makedirs(self._output_dir, exist_ok=True)
        import subprocess
        try:
            if os.name == "nt":
                subprocess.Popen(["explorer", os.path.normpath(self._output_dir)])
            else:
                # Intentar abrir el gestor de archivos del host (funciona cuando el
                # .desktop se lanza desde el escritorio con acceso al DISPLAY real)
                subprocess.Popen(["xdg-open", self._output_dir])
        except FileNotFoundError:
            pass
        # Siempre mostrar la ruta en la barra de estado
        self._status_bar.showMessage(f"Carpeta de videos: {self._output_dir}")

    # ═════════════════════════════════════════════════════════════════════════
    # Cierre
    # ═════════════════════════════════════════════════════════════════════════

    def closeEvent(self, event) -> None:  # noqa: N802
        if self._recording:
            self._stop_recording()
        self._disconnect_all()
        event.accept()

    # ═════════════════════════════════════════════════════════════════════════
    # Estilos
    # ═════════════════════════════════════════════════════════════════════════

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
/* ── Base ─────────────────────────────────────────────── */
QMainWindow, QWidget {
    background: #f0f4f8;
    font-family: 'Segoe UI', 'Inter', 'Arial', sans-serif;
    font-size: 13px;
    color: #1e293b;
}

/* ── Panel de conexión ───────────────────────────────── */
QGroupBox#connection_panel {
    background: #ffffff;
    border: 1px solid #dde3ed;
    border-radius: 12px;
}

/* ── Tarjeta de vista ────────────────────────────────── */
QWidget#view_card {
    background: #ffffff;
    border: 1px solid #dde3ed;
    border-radius: 12px;
}
QWidget#view_card_header {
    background: #ffffff;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}

/* ── Combo de cámaras ────────────────────────────────── */
QComboBox#camera_combo {
    background: #ffffff;
    border: 1.5px solid #cbd5e1;
    border-radius: 7px;
    padding: 5px 10px;
    color: #1e293b;
    selection-background-color: #eff6ff;
}
QComboBox#camera_combo:hover  { border-color: #3b82f6; }
QComboBox#camera_combo::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    selection-background-color: #dbeafe;
    outline: none;
}

/* ── Botones principales ─────────────────────────────── */
QPushButton#btn_connect {
    background: #ffffff;
    color: #2563eb;
    border: 2px solid #2563eb;
    border-radius: 10px;
    padding: 0 26px;
    font-size: 13px;
    font-weight: 600;
    min-width: 160px;
    letter-spacing: 0.2px;
}
QPushButton#btn_connect:hover   { background: #eff6ff; border-color: #1d4ed8; color: #1d4ed8; }
QPushButton#btn_connect:pressed { background: #dbeafe; }
QPushButton#btn_connect:disabled { color: #93c5fd; border-color: #bfdbfe; }

QPushButton#btn_record {
    background: #dc2626;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 0 26px;
    font-size: 13px;
    font-weight: 600;
    min-width: 130px;
    letter-spacing: 0.2px;
}
QPushButton#btn_record:hover   { background: #b91c1c; }
QPushButton#btn_record:disabled { background: #fca5a5; color: #fee2e2; }

QPushButton#btn_stop {
    background: #475569;
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 0 26px;
    font-size: 13px;
    font-weight: 600;
    min-width: 120px;
    letter-spacing: 0.2px;
}
QPushButton#btn_stop:hover   { background: #334155; }
QPushButton#btn_stop:disabled { background: #e2e8f0; color: #94a3b8; }

/* ── Botones secundarios ─────────────────────────────── */
QPushButton#btn_secondary {
    background: #ffffff;
    color: #334155;
    border: 1.5px solid #cbd5e1;
    border-radius: 7px;
    padding: 5px 16px;
    font-size: 12px;
    font-weight: 500;
}
QPushButton#btn_secondary:hover   { background: #f8fafc; border-color: #94a3b8; color: #1e293b; }
QPushButton#btn_secondary:pressed { background: #e9eff7; }

/* ── Checkbox ────────────────────────────────────────── */
QCheckBox { color: #475569; font-size: 13px; }
QCheckBox::indicator {
    width: 17px; height: 17px;
    border: 1.5px solid #cbd5e1;
    border-radius: 5px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #2563eb;
    border-color: #2563eb;
    image: url(none);
}

/* ── Botón flip panorámica ──────────────────────────── */
QPushButton#btn_flip {
    background: transparent;
    color: #4f46e5;
    border: 1px solid #c4b5fd;
    border-radius: 5px;
    padding: 0 10px;
    font-size: 11px;
    font-weight: 600;
}
QPushButton#btn_flip:hover   { background: #f5f3ff; border-color: #818cf8; }
QPushButton#btn_flip:pressed { background: #ede9fe; }

/* ── Timer de grabación ─────────────────────────────── */
QLabel#rec_timer_label {
    color: #dc2626;
    font-size: 16px;
    font-weight: 700;
    padding: 0 18px;
    border: 2px solid #dc2626;
    border-radius: 9px;
    background: #fff1f2;
    letter-spacing: 1.5px;
}

/* ── Barra de estado ─────────────────────────────────── */
QStatusBar {
    background: #e9eff7;
    color: #64748b;
    font-size: 12px;
    border-top: 1px solid #dde3ed;
}
"""
        )
