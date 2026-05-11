#!/bin/bash
# launch_labtrem.sh — Arranca el contenedor LabTREM con acceso a display y cámaras

# Permitir que Docker dibuje en el display X del usuario actual
xhost +local:docker 2>/dev/null

docker run --rm \
  -e DISPLAY="$DISPLAY" \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  --device /dev/video0 \
  --device /dev/video1 \
  --device /dev/video2 \
  labtrem
