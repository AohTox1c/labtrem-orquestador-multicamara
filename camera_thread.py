"""
camera_thread.py
QThread que captura frames de una cámara y los emite como señales Qt.
Grabación de video en H.264/MP4 real usando PyAV (binding oficial de FFmpeg).
"""
import platform
import time
import threading

import av
import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap

# Backend preferido por plataforma
_BACKEND = cv2.CAP_ANY if platform.system() == "Windows" else cv2.CAP_V4L2

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TARGET_FPS = 30

# Índices >= PICAMERA2_OFFSET → cámara CSI via Picamera2
PICAMERA2_OFFSET = 1000


class CameraThread(QThread):
    """Hilo de captura de una sola cámara."""

    frame_ready = pyqtSignal(QPixmap)
    connected = pyqtSignal(bool)          # True = OK, False = error
    error_occurred = pyqtSignal(str)

    def __init__(self, camera_index: int, parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self._running      = False
        self._recording    = False
        self._container    = None   # av.Container
        self._av_stream    = None   # av.VideoStream
        self._lock         = threading.Lock()
        self._actual_fps   = float(TARGET_FPS)
        self._frame_size: tuple[int, int] = (TARGET_WIDTH, TARGET_HEIGHT)
        self._rec_t0       = 0.0    # tiempo de inicio de grabación (perf_counter)
        self._fps_int      = TARGET_FPS  # fps entero usado en el stream
        self._last_pts     = -1     # garantiza pts monotonicamente creciente

    # ── Ciclo principal ───────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        if self.camera_index >= PICAMERA2_OFFSET:
            self._run_picamera2()
        else:
            self._run_v4l2()

    # ── Bucle V4L2 / OpenCV ───────────────────────────────────────────────────

    def _run_v4l2(self) -> None:
        cap = cv2.VideoCapture(self.camera_index, _BACKEND)
        if not cap.isOpened():
            self.error_occurred.emit(
                f"No se pudo abrir la cámara {self.camera_index}"
            )
            self.connected.emit(False)
            self._running = False
            return

        # Solicitar la mayor resolución que soporte la cámara
        # (el driver la limita a su máximo real)
        try:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  4096)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 4096)
            cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)
        except Exception:
            pass  # Usar la resolución nativa de la cámara

        # FPS inicial del driver (se reemplazará con la medición real más abajo)
        fps = cap.get(cv2.CAP_PROP_FPS)
        self._actual_fps = fps if fps and fps > 0 else TARGET_FPS

        # Warm-up: esperar hasta obtener un frame válido
        last_frame = None
        for _ in range(10):
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                last_frame = frame
                break
            self.msleep(150)

        if last_frame is None:
            self.error_occurred.emit(f"La cámara {self.camera_index} no responde")
            self.connected.emit(False)
            cap.release()
            self._running = False
            return

        # Dimensiones reales del frame capturado
        self._frame_size = (last_frame.shape[1], last_frame.shape[0])

        # Medir FPS real cronometrando 30 frames (cap.get(FPS) suele mentir)
        t0 = time.perf_counter()
        ok = 0
        for _ in range(30):
            r, _ = cap.read()
            if r:
                ok += 1
        elapsed = time.perf_counter() - t0
        if ok > 2 and elapsed > 0:
            self._actual_fps = ok / elapsed
        fps_clamped = max(10.0, min(60.0, self._actual_fps))

        interval_ms = max(10, int(1000 / fps_clamped))
        self.connected.emit(True)

        consecutive_errors = 0
        while self._running:
            ret, frame = cap.read()
            if not ret or frame is None:
                consecutive_errors += 1
                if consecutive_errors >= 15:
                    self.error_occurred.emit(f"Cámara {self.camera_index}: señal perdida")
                    break
                self.msleep(50)
                continue
            consecutive_errors = 0

            # Grabación con PyAV — pts basado en tiempo real del reloj
            with self._lock:
                if self._recording and self._av_stream is not None:
                    try:
                        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        av_frame = av.VideoFrame.from_ndarray(rgb, format="rgb24")
                        av_frame = av_frame.reformat(format="yuv420p")
                        # pts = tiempo real transcurrido * fps_del_stream
                        # Esto garantiza duración exacta independientemente de la
                        # tasa real de entrega de frames de la cámara
                        raw_pts = int((time.perf_counter() - self._rec_t0) * self._fps_int)
                        av_frame.pts = max(raw_pts, self._last_pts + 1)
                        self._last_pts = av_frame.pts
                        for packet in self._av_stream.encode(av_frame):
                            self._container.mux(packet)
                    except Exception:
                        pass

            self.frame_ready.emit(_frame_to_pixmap(frame))
            self.msleep(interval_ms)

        cap.release()
        self._close_writer()

    # ── Grabación ─────────────────────────────────────────────────────────────

    def start_recording(self, output_path: str) -> None:
        """Abre un contenedor MP4 con H.264 vía PyAV."""
        w, h = self._frame_size
        fps = max(5.0, min(60.0, self._actual_fps))
        fps_int = int(round(fps))
        try:
            container = av.open(output_path, mode="w")
            stream    = container.add_stream("h264", rate=fps_int)
            stream.width   = w
            stream.height  = h
            stream.pix_fmt = "yuv420p"
            # CRF 18 = alta calidad para análisis clínico
            stream.options = {"crf": "18", "preset": "fast"}
            with self._lock:
                self._container = container
                self._av_stream = stream
                self._fps_int   = fps_int
                self._rec_t0    = time.perf_counter()
                self._last_pts  = -1
                self._recording = True
        except Exception as exc:
            self.error_occurred.emit(f"No se pudo crear el video: {exc}")

    def stop_recording(self) -> None:
        """Finaliza la grabación y cierra el archivo."""
        with self._lock:
            self._recording = False
        self._close_writer()

    def _close_writer(self) -> None:
        with self._lock:
            if self._container is not None:
                try:
                    if self._av_stream is not None:
                        for packet in self._av_stream.encode():
                            self._container.mux(packet)
                    self._container.close()
                except Exception:
                    pass
                self._container = None
                self._av_stream = None

    # ── Bucle Picamera2 (cámara CSI Raspberry Pi) ─────────────────────────────

    def _run_picamera2(self) -> None:
        try:
            from picamera2 import Picamera2  # type: ignore
        except ImportError:
            self.error_occurred.emit("Picamera2 no disponible en el contenedor")
            self.connected.emit(False)
            self._running = False
            return

        cam_idx = self.camera_index - PICAMERA2_OFFSET
        try:
            picam = Picamera2(cam_idx)
        except Exception as exc:
            self.error_occurred.emit(f"No se pudo abrir Pi Camera {cam_idx}: {exc}")
            self.connected.emit(False)
            self._running = False
            return

        # 1920x1080 es el máximo que cabe en la memoria DMA del contenedor Docker.
        # El sensor IMX219 a resolución completa (3280x2464) necesita ~90 MB DMA
        # contigua, que Docker no puede garantizar → OSError ENOMEM.
        config = picam.create_video_configuration(
            main={"format": "RGB888", "size": (TARGET_WIDTH, TARGET_HEIGHT)},
            controls={"FrameRate": float(TARGET_FPS)},
        )
        picam.configure(config)
        try:
            picam.start()
        except Exception as exc:
            self.error_occurred.emit(f"Pi Camera {cam_idx} no arranca: {exc}")
            self.connected.emit(False)
            self._running = False
            return

        # Warm-up
        last_frame = None
        for _ in range(8):
            try:
                arr = picam.capture_array("main")
                if arr is not None and arr.size > 0:
                    last_frame = arr
                    break
            except Exception:
                pass
            self.msleep(200)

        if last_frame is None:
            picam.stop()
            picam.close()
            self.error_occurred.emit(f"Pi Camera {cam_idx}: sin respuesta")
            self.connected.emit(False)
            self._running = False
            return

        self._frame_size = (last_frame.shape[1], last_frame.shape[0])

        # Medir FPS real
        t0 = time.perf_counter()
        ok = 0
        for _ in range(30):
            try:
                arr = picam.capture_array("main")
                if arr is not None:
                    ok += 1
            except Exception:
                pass
        elapsed = time.perf_counter() - t0
        if ok > 2 and elapsed > 0:
            self._actual_fps = ok / elapsed
        fps_clamped = max(10.0, min(60.0, self._actual_fps))
        interval_ms = max(10, int(1000 / fps_clamped))
        self.connected.emit(True)

        consecutive_errors = 0
        while self._running:
            try:
                rgb = picam.capture_array("main")  # ya viene en RGB888
            except Exception:
                consecutive_errors += 1
                if consecutive_errors >= 15:
                    self.error_occurred.emit(f"Pi Camera {cam_idx}: señal perdida")
                    break
                self.msleep(50)
                continue

            if rgb is None or rgb.size == 0:
                consecutive_errors += 1
                if consecutive_errors >= 15:
                    self.error_occurred.emit(f"Pi Camera {cam_idx}: señal perdida")
                    break
                self.msleep(50)
                continue
            consecutive_errors = 0

            # Picamera2 con formato "RGB888" entrega bytes en orden BGR
            # (comportamiento real de libcamera — el nombre es confuso).
            # bgr se pasa directamente a _frame_to_pixmap (espera BGR como OpenCV)
            # y a PyAV como "bgr24" para grabación con colores correctos.
            bgr = rgb  # los bytes ya están en BGR

            # Grabación con PyAV (mismo pipeline que V4L2)
            with self._lock:
                if self._recording and self._av_stream is not None:
                    try:
                        av_frame = av.VideoFrame.from_ndarray(bgr, format="bgr24")
                        av_frame = av_frame.reformat(format="yuv420p")
                        raw_pts = int((time.perf_counter() - self._rec_t0) * self._fps_int)
                        av_frame.pts = max(raw_pts, self._last_pts + 1)
                        self._last_pts = av_frame.pts
                        for packet in self._av_stream.encode(av_frame):
                            self._container.mux(packet)
                    except Exception:
                        pass

            self.frame_ready.emit(_frame_to_pixmap(bgr))
            self.msleep(interval_ms)

        picam.stop()
        picam.close()
        self._close_writer()

    # ── Control ───────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Detiene el hilo limpiamente."""
        self._recording = False
        self._running   = False
        self.wait(4000)


# ── Utilidades ────────────────────────────────────────────────────────────────

def _frame_to_pixmap(frame: np.ndarray) -> QPixmap:
    """Convierte un frame BGR de OpenCV a QPixmap."""
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qt_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
    return QPixmap.fromImage(qt_img)
