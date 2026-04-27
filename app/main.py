"""Entry point — replaces the old ``if __name__ == '__main__'`` block in RunwithUI.py."""

from __future__ import annotations

import sys
from datetime import datetime

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from app.config import save_experiment_config, discover_models
from app.wiring import wire


def main() -> None:
    qt_app = QApplication(sys.argv)

    from adapters.ui.qt_app import QtConfigUi
    config_ui = QtConfigUi()
    cfg = config_ui.request_session_config(discover_models())
    if cfg is None:
        sys.exit(0)

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_experiment_config(cfg, f"experimental_results/{session_id}")

    pipeline, ui_window, camera = wire(cfg, session_id)

    if not camera.open():
        print("Error: Could not open video stream")
        sys.exit(1)

    ui_window.show()

    # Set up inference timer
    timer = QTimer()
    timer.timeout.connect(lambda: _tick(pipeline, timer))
    timer.start(30)

    # Register shutdown callback for alarm system
    def shutdown_app():
        """Complete application shutdown sequence."""
        print("[Main] Shutdown requested — stopping timer and pipeline")
        timer.stop()
        pipeline.shutdown()
        QApplication.instance().quit()

    ui_window.set_shutdown_callback(shutdown_app)

    # Register cleanup on manual window close
    def on_close(event):
        pipeline.shutdown()
        event.accept()

    ui_window.closeEvent = on_close
    sys.exit(qt_app.exec_())


def _tick(pipeline, timer):
    if not pipeline.tick():
        timer.stop()
        print("Error: Failed to read frame")


if __name__ == "__main__":
    main()
