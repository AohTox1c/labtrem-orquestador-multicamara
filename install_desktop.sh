#!/bin/bash
# install_desktop.sh — Instala el icono de escritorio en la Raspberry Pi
# Ejecutar UNA VEZ después de clonar/actualizar el repositorio:
#   bash install_desktop.sh

set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Construir la imagen Docker (si no existe)
echo "Construyendo imagen Docker..."
docker build -t labtrem "$REPO"

# 2. Copiar icono SVG
ICON_DIR="$HOME/.local/share/icons"
mkdir -p "$ICON_DIR"
cp "$REPO/assets/labtrem.svg" "$ICON_DIR/labtrem.svg"
echo "Icono copiado."

# 3. Dar permisos al script de lanzamiento
chmod +x "$REPO/launch_labtrem.sh"

# 4. Crear la entrada de escritorio
DESKTOP="$HOME/Desktop/LabTREM.desktop"
cat > "$DESKTOP" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=LabTREM Orquestador
Comment=Captura multicamara sincronizada
Exec=$REPO/launch_labtrem.sh
Icon=$ICON_DIR/labtrem.svg
Terminal=false
Categories=Science;
StartupWMClass=labtrem
EOF

chmod +x "$DESKTOP"

# 5. Marcar como confiable (LXDE/PCManFM/Wayfire)
if command -v gio &>/dev/null; then
  gio set "$DESKTOP" "metadata::trusted" true 2>/dev/null || true
fi
# Fallback para entornos sin gio (xfce/lxde older)
if command -v dbus-launch &>/dev/null; then
  dbus-launch gio set "$DESKTOP" "metadata::trusted" true 2>/dev/null || true
fi

echo ""
echo "Listo. El icono 'LabTREM Orquestador' aparece en el escritorio."
echo "Si no lo ves, cierra sesion y vuelve a entrar."
