"""
main.py
Punto de entrada de Camarapp.

Uso:
    python main.py

Empaquetado (Windows .exe):
    pip install pyinstaller
    pyinstaller --onefile --windowed --name Camarapp main.py
"""
import os
import sys

# Silenciar TODOS los warnings de OpenCV antes de importar cv2
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_PRIORITY_MSMF"] = "0"
os.environ["OPENCV_VIDEOIO_PRIORITY_FFMPEG"] = "0"
os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from main_window import MainWindow


def main() -> None:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("LabTREM Orquestador")
    app.setApplicationDisplayName("LabTREM — Orquestador Multicámara")

    # Fuente base
    font = QFont()
    font.setFamily("Segoe UI" if sys.platform == "win32" else "Inter")
    font.setPointSize(10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
