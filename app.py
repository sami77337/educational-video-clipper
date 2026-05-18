"""Application entry point for المقص البسيط."""

import sys

from PySide6.QtWidgets import QApplication

from src.main_window import MainWindow
from src.version import APP_NAME


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("المقص البسيط")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
