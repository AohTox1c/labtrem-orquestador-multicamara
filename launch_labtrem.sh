#!/bin/bash
# launch_labtrem.sh — Arranca el contenedor LabTREM

LOG="/tmp/labtrem_launch.log"
exec > "$LOG" 2>&1

# Asegurar DISPLAY
export DISPLAY="${DISPLAY:-:0}"

# Permitir que Docker dibuje en el display
xhost +local:docker

# Directorio de videos — crear en el host antes de montar en Docker
VIDEO_DIR="/mnt/disco1/Camarapp/Videos"
mkdir -p "$VIDEO_DIR"

# GID numérico del grupo video del host (evita problemas de nombre dentro del contenedor)
VIDEO_GID=$(getent group video | cut -d: -f3 2>/dev/null || echo 44)

# Pasar todos los nodos de video, media y cámara CSI al contenedor
DEVICE_FLAGS=""
for dev in /dev/video* /dev/media*; do
    [ -c "$dev" ] && DEVICE_FLAGS="$DEVICE_FLAGS --device $dev"
done
# Dispositivos específicos de la Pi (libcamera / ISP)
for dev in /dev/dma_heap/linux,cma /dev/rpivid-hevcmem /dev/vcsm-cma; do
    [ -e "$dev" ] && DEVICE_FLAGS="$DEVICE_FLAGS --device $dev"
done

docker run --rm \
  -e DISPLAY="$DISPLAY" \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v "$VIDEO_DIR":"$VIDEO_DIR" \
  --group-add "$VIDEO_GID" \
  --device-cgroup-rule='c 81:* rmw' \
  $DEVICE_FLAGS \
  labtrem
