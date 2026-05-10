# ──────────────────────────────────────────────────────────────────────────────
# LabTREM — Orquestador Multicámara
# Dockerfile para Raspberry Pi 5 (arm64 / aarch64)
#
# Build:
#   docker build -t labtrem .
#
# Run (con pantalla conectada a la Pi):
#   docker run --rm \
#     --device /dev/video0 \
#     --device /dev/video2 \
#     --device /dev/video4 \
#     -e DISPLAY=$DISPLAY \
#     -v /tmp/.X11-unix:/tmp/.X11-unix \
#     -v ~/Videos/LabTREM:/root/Videos/LabTREM \
#     labtrem
# ──────────────────────────────────────────────────────────────────────────────

FROM arm64v8/python:3.12-slim

# Evitar preguntas interactivas durante apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# ── Dependencias del sistema ──────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # FFmpeg (requerido por PyAV)
    ffmpeg \
    # PyQt5 y sus dependencias gráficas
    python3-pyqt5 \
    libqt5widgets5 \
    libqt5gui5 \
    libqt5core5a \
    libxcb-xinerama0 \
    libxcb-cursor0 \
    # OpenCV en ARM (más estable vía apt en la Pi)
    python3-opencv \
    # Audio (sounddevice requiere PortAudio)
    libportaudio2 \
    portaudio19-dev \
    # Cámara V4L2
    v4l-utils \
    # Herramientas generales
    libgl1 \
    libglib2.0-0 \
    libdbus-1-3 \
    # Display virtual (útil para desarrollo headless)
    xvfb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Directorio de trabajo ─────────────────────────────────────────────────────
WORKDIR /app

# ── Dependencias Python ───────────────────────────────────────────────────────
COPY requirements.txt .

# En ARM64 usamos el opencv del sistema (ya instalado arriba),
# así que excluimos opencv-python del pip para no duplicar
RUN pip install --no-cache-dir \
    PyQt5>=5.15.0 \
    numpy>=1.19.0 \
    sounddevice>=0.4.0 \
    av>=11.0.0 \
    && pip install --no-cache-dir imageio-ffmpeg>=0.4.9 || true

# ── Código fuente ─────────────────────────────────────────────────────────────
COPY *.py .

# ── Variables de entorno para silenciar logs de OpenCV/Qt ────────────────────
ENV OPENCV_LOG_LEVEL=SILENT
ENV OPENCV_VIDEOIO_PRIORITY_MSMF=0
ENV QT_AUTO_SCREEN_SCALE_FACTOR=1
# En Raspberry Pi usar backend V4L2 (se detecta automáticamente en el código)

# ── Carpeta de salida de videos ───────────────────────────────────────────────
RUN mkdir -p /root/Videos/LabTREM

# ── Entrypoint ────────────────────────────────────────────────────────────────
# Con pantalla real: python main.py
# Sin pantalla (headless): xvfb-run python main.py
CMD ["python", "main.py"]
