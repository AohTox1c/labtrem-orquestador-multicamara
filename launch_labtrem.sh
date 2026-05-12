#!/bin/bash
# launch_labtrem.sh — Arranca el contenedor LabTREM

LOG="/tmp/labtrem_launch.log"
exec > "$LOG" 2>&1

# Asegurar DISPLAY
export DISPLAY="${DISPLAY:-:0}"

# Permitir que Docker dibuje en el display
xhost +local:docker

# Construir flags de dispositivos de video solo si existen
VIDEO_FLAGS=""
for dev in /dev/video0 /dev/video1 /dev/video2; do
    [ -e "$dev" ] && VIDEO_FLAGS="$VIDEO_FLAGS --device $dev"
done

docker run --rm \
  -e DISPLAY="$DISPLAY" \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  $VIDEO_FLAGS \
  labtrem
