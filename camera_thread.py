"""
camera_thread.py
QThread que captura frames de una cámara y los emite como señales Qt.
Grabación de video en H.264/MP4 real usando PyAV (binding oficial de FFmpeg).
"""
import platform
import queue
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
# C920: 720p@60fps es el máximo en MJPEG (1080p solo llega a 30fps).
USB_WIDTH  = 1280
USB_HEIGHT = 720
USB_FPS    = 60

# Índices >= PICAMERA2_OFFSET → cámara CSI via Picamera2
PICAMERA2_OFFSET = 1000

# Mutex global: impide que dos cámaras USB negocien MJPEG simultáneamente.
# cap.open() + FOURCC negotiation + warmup se ejecutan de a uno a la vez.
_USB_INIT_LOCK = threading.Lock()


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
        # Evento que se activa cuando _close_writer() termina (para UI no bloqueante)
        self._writer_closed = threading.Event()
        self._writer_closed.set()  # inicialmente "cerrado" (sin grabación activa)
        # Cola de frames para el hilo de encoding (desacopla captura de encoding)
        self._encode_queue: "queue.Queue | None" = None

    # ── Ciclo principal ───────────────────────────────────────────────────────

    def run(self) -> None:
        self._running = True
        if self.camera_index >= PICAMERA2_OFFSET:
            self._run_picamera2()
        else:
            self._run_v4l2()

    # ── Bucle V4L2 / OpenCV ───────────────────────────────────────────────────

    def _run_v4l2(self) -> None:
        device_path = f"/dev/video{self.camera_index}"

        # Adquirir el mutex global: sólo una cámara USB inicializa a la vez.
        # Impide que dos hilos negocien MJPEG simultáneamente en el bus USB,
        # lo que causaba distorsión/freeze en la cámara ya activa.
        with _USB_INIT_LOCK:
            cap = cv2.VideoCapture(device_path if platform.system() == "Linux" else self.camera_index, _BACKEND)
            if not cap.isOpened():
                self.error_occurred.emit(
                    f"No se pudo abrir la cámara {self.camera_index}"
                )
                self.connected.emit(False)
                self._running = False
                return

            # 1080p @ 15fps MJPEG.
            # Dos C920 a 1080p@30fps (~20 Mbps c/u) saturan el bus USB 2.0.
            # 15fps reduce a ~10 Mbps → caben dos cámaras sin contención,
            # manteniendo el doble de resolución espacial vs 720p@30fps.
            MJPG = cv2.VideoWriter_fourcc(*'MJPG')
            cap.set(cv2.CAP_PROP_FOURCC, MJPG)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH,  USB_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, USB_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, USB_FPS)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            accepted = int(cap.get(cv2.CAP_PROP_FOURCC))
            if accepted != MJPG:
                # El driver rechazó MJPEG — reabrir con negociación automática
                cap.release()
                cap = cv2.VideoCapture(device_path if platform.system() == "Linux" else self.camera_index, _BACKEND)
                if not cap.isOpened():
                    self.error_occurred.emit(f"No se pudo reabrir la cámara {self.camera_index}")
                    self.connected.emit(False)
                    self._running = False
                    return

            # FPS del driver tras negociar MJPEG — fiable en este punto
            fps = cap.get(cv2.CAP_PROP_FPS)
            self._actual_fps = fps if fps and fps > 0 else TARGET_FPS

            # Warm-up: esperar hasta obtener un frame válido
            last_frame = None
            for _ in range(20):
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    last_frame = frame
                    break
                self.msleep(100)

            if last_frame is None:
                self.error_occurred.emit(f"La cámara {self.camera_index} no responde")
                self.connected.emit(False)
                cap.release()
                self._running = False
                return

            self._frame_size = (last_frame.shape[1], last_frame.shape[0])
            self._actual_fps = USB_FPS  # usar el fps real negociado con el driver
        # ── Fin del bloque de init exclusivo ─────────────────────────────────

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

            # Poner el frame en la cola del encoder (no bloqueante).
            # El encoder corre en su propio hilo → cap.read() nunca espera al H.264.
            if self._encode_queue is not None:
                ts = time.perf_counter()
                try:
                    self._encode_queue.put_nowait((frame.copy(), ts))
                except queue.Full:
                    pass  # encoder va lento → descartar frame antes que bloquear

            self.frame_ready.emit(_frame_to_pixmap(frame))

        cap.release()
        self._close_writer()

    # ── Grabación ─────────────────────────────────────────────────────────────

    def start_recording(self, output_path: str, rec_t0: float | None = None) -> None:
        """Abre un contenedor MP4 y arranca el hilo encoder independiente.
        rec_t0: timestamp compartido (time.perf_counter) del momento de inicio
        de grabación. Pasar el mismo valor a todas las cámaras garantiza que
        los PTS de todos los videos estén alineados al mismo origen de tiempo.
        """
        w, h = self._frame_size
        fps_int = int(round(max(5.0, min(60.0, self._actual_fps))))
        t0 = rec_t0 if rec_t0 is not None else time.perf_counter()
        try:
            container = av.open(output_path, mode="w")
            stream = container.add_stream("h264", rate=fps_int)
            stream.width   = w
            stream.height  = h
            stream.pix_fmt = "yuv420p"
            # CRF 23 = buena calidad con menos CPU que CRF 18. ultrafast = mínima carga ARM.
            stream.options = {"crf": "23", "preset": "ultrafast"}

            eq: queue.Queue = queue.Queue(maxsize=10)
            self._encode_queue = eq

            with self._lock:
                self._container = container
                self._av_stream = stream
                self._fps_int   = fps_int
                self._rec_t0    = t0
                self._last_pts  = -1
                self._recording = True

            # Hilo encoder: lee frames de la cola y los escribe al MP4.
            # Al estar separado del hilo de captura, cap.read() nunca espera al H.264.
            self._writer_closed.clear()
            threading.Thread(
                target=self._encoder_loop,
                args=(eq, container, stream, fps_int, t0),
                daemon=True,
            ).start()

        except Exception as exc:
            self.error_occurred.emit(f"No se pudo crear el video: {exc}")

    def _encoder_loop(self, eq: "queue.Queue", container, stream, fps_int: int, rec_t0: float) -> None:
        """Hilo dedicado al encoding H.264. Lee (frame_bgr, timestamp) de la cola."""
        last_pts = -1
        try:
            while True:
                item = eq.get()
                if item is None:
                    break  # sentinel → fin de grabación
                frame_bgr, ts = item
                try:
                    # V4L2 entrega BGR; Picamera2 también (RGB888 = BGR en bytes)
                    av_frame = av.VideoFrame.from_ndarray(frame_bgr, format="bgr24")
                    av_frame = av_frame.reformat(format="yuv420p")
                    raw_pts = int((ts - rec_t0) * fps_int)
                    av_frame.pts = max(raw_pts, last_pts + 1)
                    last_pts = av_frame.pts
                    with self._lock:
                        if self._container is not None:
                            for packet in stream.encode(av_frame):
                                container.mux(packet)
                except Exception as enc_err:
                    self.error_occurred.emit(f"Error encoding: {enc_err}")
                    break  # abortar loop si el encoder falla — no seguir acumulando frames perdidos
        finally:
            # Flush y cerrar
            try:
                with self._lock:
                    if self._container is not None:
                        for packet in stream.encode():
                            container.mux(packet)
                        container.close()
                        self._container = None
                        self._av_stream = None
            except Exception:
                pass
            self._writer_closed.set()

    def stop_recording(self) -> None:
        """Señaliza el fin de grabación. El flush MP4 ocurre en el hilo encoder."""
        with self._lock:
            self._recording = False
        eq = self._encode_queue
        self._encode_queue = None
        if eq is not None:
            eq.put(None)  # sentinel → el encoder hace flush y cierra

    def _close_writer(self) -> None:
        """Llamado al final del bucle de captura si la grabación ya terminó."""
        eq = self._encode_queue
        self._encode_queue = None
        if eq is not None:
            eq.put(None)
        # Si no hay encoder activo, marcar como cerrado directamente
        elif not self._recording:
            self._writer_closed.set()

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

        # 1640×1232: modo 2×2 binning del IMX219 → usa el sensor COMPLETO → sin zoom.
        # 1920×1080 en el IMX219 es un recorte central del sensor (modo 6) → efecto zoom.
        # 1640×1232@30fps captura toda la escena: cabeza, manos y entorno completo.
        PICAM_W, PICAM_H, PICAM_FPS = 1640, 1232, 30
        config = picam.create_video_configuration(
            main={"format": "RGB888", "size": (PICAM_W, PICAM_H)},
            controls={"FrameRate": float(PICAM_FPS)},
        )
        picam.configure(config)
        try:
            picam.start()
        except Exception as exc:
            self.error_occurred.emit(f"Pi Camera {cam_idx} no arranca: {exc}")
            self.connected.emit(False)
            self._running = False
            return

        # 1640×1232 ya usa el sensor completo → no se necesita ScalerCrop

        # Warm-up
        last_frame = None
        for _ in range(10):
            try:
                arr = picam.capture_array("main")
                if arr is not None and arr.size > 0:
                    last_frame = arr
                    break
            except Exception:
                pass
            self.msleep(100)

        if last_frame is None:
            picam.stop()
            picam.close()
            self.error_occurred.emit(f"Pi Camera {cam_idx}: sin respuesta")
            self.connected.emit(False)
            self._running = False
            return

        self._frame_size = (last_frame.shape[1], last_frame.shape[0])
        self._actual_fps = float(PICAM_FPS)
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

            if self._encode_queue is not None:
                ts = time.perf_counter()
                try:
                    self._encode_queue.put_nowait((bgr.copy(), ts))
                except queue.Full:
                    pass

            self.frame_ready.emit(_frame_to_pixmap(bgr))

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
