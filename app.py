"""Application entry point for المقص البسيط."""

import sys

from PySide6.QtWidgets import QApplication

from src.main_window import MainWindow
from src.version import APP_NAME


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from src.release_self_test import run_release_self_test
        return run_release_self_test(sys.argv[2])

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("المقص البسيط")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
