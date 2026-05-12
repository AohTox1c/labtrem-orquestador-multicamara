#!/bin/bash
# launch_labtrem.sh — Arranca el contenedor LabTREM

LOG="/tmp/labtrem_launch.log"
exec > "$LOG" 2>&1

export DISPLAY="${DISPLAY:-:0}"
xhost +local:docker

# Directorio de videos — crear en el host antes de montar en Docker
VIDEO_DIR="/mnt/disco1/Camarapp/Videos"
mkdir -p "$VIDEO_DIR"

# ── Watcher de reproducción ────────────────────────────────────────────────
# El contenedor Docker no puede lanzar apps gráficas del host directamente.
# Solución: el contenedor escribe la ruta en .play_request; este watcher
# corre en el HOST y lanza VLC con acceso completo al entorno gráfico.
PLAY_REQ="$VIDEO_DIR/.play_request"
rm -f "$PLAY_REQ"

(
  while true; do
    if [ -f "$PLAY_REQ" ]; then
      FILE=$(cat "$PLAY_REQ")
      rm -f "$PLAY_REQ"
      if [ -f "$FILE" ]; then
        DISPLAY="$DISPLAY" vlc --started-from-file "$FILE" &>/dev/null &
      fi
    fi
    sleep 0.3
  done
) &
WATCHER_PID=$!

docker run --rm \
  --privileged \
  -e DISPLAY="$DISPLAY" \
  -e DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
  -e LIBCAMERA_LOG_LEVELS='*:FATAL' \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v /run/udev:/run/udev:ro \
  -v /dev/dma_heap:/dev/dma_heap \
  -v "$VIDEO_DIR":"$VIDEO_DIR" \
  labtrem

# Limpiar watcher al salir
kill "$WATCHER_PID" 2>/dev/null
rm -f "$PLAY_REQ"

