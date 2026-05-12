"""
camera_detector.py
Detecta cámaras disponibles en Windows y Linux/Raspberry Pi.
"""
import os
import platform
import subprocess

import cv2


def detect_cameras(max_index: int = 10) -> list[tuple[int, str]]:
    """
    Retorna una lista de (índice, nombre) de cámaras disponibles.
    Funciona en Windows (DirectShow/MSMF) y Linux (V4L2).
    """
    system = platform.system()
    cameras: list[tuple[int, str]] = []

    if system == "Linux":
        cameras = _detect_linux()
    elif system == "Windows":
        cameras = _detect_windows(max_index)
    else:
        cameras = _detect_generic(max_index)

    return cameras


# ── Windows ──────────────────────────────────────────────────────────────────

def _detect_windows(max_index: int) -> list[tuple[int, str]]:
    """Prueba índices de cámara con backend automático en Windows."""
    cameras: list[tuple[int, str]] = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, cv2.CAP_ANY)
        if not cap.isOpened():
            cap.release()
            continue
        # Leer varios frames para descartar cámaras fantasma (IR, virtuales, etc.)
        valid = False
        for _ in range(4):
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                h, w = frame.shape[:2]
                if w > 0 and h > 0:
                    valid = True
                    break
        cap.release()
        if valid:
            name = _get_windows_camera_name(idx) or f"Cámara {idx}"
            cameras.append((idx, name))
    return cameras


def _get_windows_camera_name(index: int) -> str | None:
    """Intenta obtener el nombre de la cámara en Windows via PowerShell."""
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-PnpDevice -Class Camera | Select-Object -ExpandProperty FriendlyName",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        names = [ln.strip() for ln in result.stdout.strip().splitlines() if ln.strip()]
        if index < len(names):
            return names[index]
    except Exception:
        pass
    return None


# ── Linux / Raspberry Pi ─────────────────────────────────────────────────────

def _detect_linux() -> list[tuple[int, str]]:
    """Detecta cámaras en Linux usando /dev/video* y V4L2."""
    cameras: list[tuple[int, str]] = []
    try:
        devices = sorted(
            [f for f in os.listdir("/dev") if f.startswith("video")],
            key=lambda d: int(d.replace("video", "")),
        )
    except OSError:
        return _detect_generic(10)

    for device in devices:
        idx = int(device.replace("video", ""))
        device_path = f"/dev/{device}"

        # Algunos dispositivos V4L2 no son cámaras de imagen (son metadata, etc.)
        # Intentar abrir con V4L2 y leer varios frames antes de descartar
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            continue

        valid = False
        for _ in range(6):
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                valid = True
                break
        cap.release()

        if valid:
            name = _get_v4l2_name(device_path) or f"Cámara {idx}"
            cameras.append((idx, name))

    return cameras if cameras else _detect_generic(10)


def _get_v4l2_name(device_path: str) -> str | None:
    """Consulta el nombre de la cámara vía v4l2-ctl."""
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--device", device_path, "--info"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        for line in result.stdout.splitlines():
            lower = line.lower()
            if "card type" in lower or "card :" in lower:
                return line.split(":", 1)[-1].strip()
    except Exception:
        pass
    return None


# ── Genérico ─────────────────────────────────────────────────────────────────

def _detect_generic(max_index: int) -> list[tuple[int, str]]:
    cameras: list[tuple[int, str]] = []
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                cameras.append((idx, f"Cámara {idx}"))
        cap.release()
    return cameras
