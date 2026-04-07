import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from main_window import RealTimePlot


def main():
    """Punto de entrada de la aplicación."""
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("Sistema de Monitoreo Serial")
        app.setApplicationVersion("5.0.0")
        app.setStyle("Fusion")

        window = RealTimePlot()
        window.show()

        sys.exit(app.exec())

    except Exception as e:
        print(f"Error crítico en la aplicación: {e}")
        try:
            QMessageBox.critical(
                None,
                "Error Crítico",
                f"La aplicación encontró un error y debe cerrarse:\n\n{e}",
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
