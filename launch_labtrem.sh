#!/bin/bash
# launch_labtrem.sh — Arranca el contenedor LabTREM

LOG="/tmp/labtrem_launch.log"
exec > "$LOG" 2>&1

export DISPLAY="${DISPLAY:-:0}"
xhost +local:docker

# Directorio de videos — crear en el host antes de montar en Docker
VIDEO_DIR="/mnt/disco1/Camarapp/Videos"
mkdir -p "$VIDEO_DIR"

docker run --rm \
  --privileged \
  -e DISPLAY="$DISPLAY" \
  -e DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-}" \
  -e LIBCAMERA_LOG_LEVELS='*:FATAL' \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v /run/udev:/run/udev:ro \
  -v "$VIDEO_DIR":"$VIDEO_DIR" \
  labtrem

