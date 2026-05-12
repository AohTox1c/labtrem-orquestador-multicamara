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

FROM arm64v8/debian:bookworm-slim

# Evitar preguntas interactivas durante apt
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# ── Repositorio oficial de Raspberry Pi (necesario para picamera2/libcamera) ─
RUN apt-get update && apt-get install -y --no-install-recommends gnupg curl ca-certificates \
    && curl -fsSL https://archive.raspberrypi.com/debian/raspberrypi.gpg.key \
       | gpg --dearmor -o /usr/share/keyrings/raspberrypi-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.gpg] \
       https://archive.raspberrypi.com/debian/ bookworm main" \
       > /etc/apt/sources.list.d/raspi.list \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── Dependencias del sistema ──────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python del sistema (3.11, compatible con todos los paquetes apt)
    python3 \
    python3-pip \
    # FFmpeg (requerido por PyAV)
    ffmpeg \
    # PyQt5 y sus dependencias gráficas
    python3-pyqt5 \
    python3-pyqt5.sip \
    libqt5widgets5 \
    libqt5gui5 \
    libqt5core5a \
    libxcb-xinerama0 \
    libxcb-cursor0 \
    # OpenCV en ARM (más estable vía apt en la Pi)
    python3-opencv \
    # Picamera2 y libcamera (repositorio Raspberry Pi)
    python3-picamera2 \
    python3-libcamera \
    # Audio (sounddevice requiere PortAudio)
    libportaudio2 \
    portaudio19-dev \
    # Cámara V4L2
    v4l-utils \
    # Herramientas generales
    libgl1 \
    libglib2.0-0 \
    libdbus-1-3 \
    xvfb \
    xdg-utils \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Directorio de trabajo ─────────────────────────────────────────────────────
WORKDIR /app

# ── Dependencias Python (solo las que no están en apt) ───────────────────────
RUN pip3 install --no-cache-dir --break-system-packages \
    numpy \
    sounddevice \
    av \
    imageio-ffmpeg || true

# ── Código fuente ─────────────────────────────────────────────────────────────
COPY *.py .

# ── Variables de entorno ──────────────────────────────────────────────────────
ENV OPENCV_LOG_LEVEL=SILENT
ENV QT_AUTO_SCREEN_SCALE_FACTOR=1

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD ["python3", "main.py"]
