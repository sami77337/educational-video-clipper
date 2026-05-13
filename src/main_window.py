"""Minimal main window for the desktop application."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QWidget, QVBoxLayout


class MainWindow(QMainWindow):
    """Initial application shell."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Educational Video Clipper")
        self.resize(720, 420)
        self.setCentralWidget(self._build_placeholder())

    def _build_placeholder(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        label = QLabel("Educational Video Clipper")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        return container
