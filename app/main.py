"""Entry point — replaces the old ``if __name__ == '__main__'`` block in RunwithUI.py."""

from __future__ import annotations

import sys
from datetime import datetime

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QDialog

from app.config import ExperimentConfig, save_experiment_config
from app.wiring import wire


def _show_config_dialog() -> ExperimentConfig | None:
    """Show the PyQt5 experiment-config dialog and return an ExperimentConfig."""
    from PyQt5.QtWidgets import (
        QComboBox, QCheckBox, QGridLayout, QHBoxLayout,
        QLabel, QPushButton, QVBoxLayout,
    )
    from PyQt5.QtCore import Qt

    class _Dialog(QDialog):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Experimentkonfiguration")
            self.setMinimumWidth(400)
            self.setStyleSheet(
                "QDialog    { background-color: #1C1C1C; }"
                "QWidget    { background-color: #1C1C1C; color: #FFFFFF; }"
                "QLabel     { font-size: 13px; color: #FFFFFF; }"
                "QComboBox  {"
                "    background-color: #2D2D2D; color: #FFFFFF;"
                "    border: 1px solid #3A3A3A; border-radius: 4px;"
                "    padding: 5px 8px; font-size: 13px; min-height: 24px;"
                "}"
                "QComboBox::drop-down { border: none; }"
                "QComboBox QAbstractItemView {"
                "    background-color: #2D2D2D; color: #FFFFFF;"
                "    selection-background-color: #505050; border: 1px solid #3A3A3A;"
                "}"
                "QCheckBox { font-size: 13px; color: #FFFFFF; spacing: 8px; }"
                "QCheckBox::indicator {"
                "    width: 16px; height: 16px;"
                "    border: 1px solid #3A3A3A; border-radius: 3px;"
                "    background-color: #2D2D2D;"
                "}"
                "QCheckBox::indicator:checked { background-color: #6A6A6A; }"
            )
            self._build()

        def _build(self):
            outer = QVBoxLayout()
            outer.setContentsMargins(24, 24, 24, 24)
            outer.setSpacing(18)

            title = QLabel("Experimentkonfiguration")
            title.setStyleSheet("font-size: 18px; font-weight: bold; color: #FFFFFF;")
            title.setAlignment(Qt.AlignCenter)
            outer.addWidget(title)

            self.videostream_combo = QComboBox()
            self.videostream_combo.addItems(["USB", "RTSP", "CSI"])

            self.kamera_combo = QComboBox()
            self.kamera_combo.addItems(["USB Basler BW Fix", "RTSP rpi cam 3 wide", "USB Webcam Logitech"])

            self.zachse_combo = QComboBox()
            self.zachse_combo.addItems(["Druckkopf", "Druckbett"])

            self.maschine_combo = QComboBox()
            self.maschine_combo.addItems(["Bambulab", "RatRig", "Prusa", "Ultimaker"])

            grid = QGridLayout()
            grid.setSpacing(10)
            grid.setColumnMinimumWidth(0, 110)
            grid.setColumnStretch(1, 1)

            for i, (label_text, widget) in enumerate([
                ("Videostream:", self.videostream_combo),
                ("Kamera:",      self.kamera_combo),
                ("Z-Achse:",     self.zachse_combo),
                ("Maschine:",    self.maschine_combo),
            ]):
                lbl = QLabel(label_text)
                lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                grid.addWidget(lbl, i, 0)
                grid.addWidget(widget, i, 1)
            outer.addLayout(grid)

            self.lighting_cb  = QCheckBox("Lighting")
            self.enclosure_cb = QCheckBox("Enclosure")
            self.vibration_cb = QCheckBox("Vibration")

            cb_row = QHBoxLayout()
            cb_row.setSpacing(20)
            cb_row.addWidget(self.lighting_cb)
            cb_row.addWidget(self.enclosure_cb)
            cb_row.addWidget(self.vibration_cb)
            outer.addLayout(cb_row)

            start_btn = QPushButton("Start")
            start_btn.setStyleSheet(
                "QPushButton {"
                "    font-size: 14px; padding: 8px 16px; border-radius: 6px;"
                "    background-color: #2D2D2D; color: #FFFFFF; border: 1px solid #3A3A3A;"
                "}"
                "QPushButton:hover   { background-color: #3A3A3A; }"
                "QPushButton:pressed { background-color: #505050; }"
            )
            start_btn.clicked.connect(self.accept)
            outer.addWidget(start_btn)
            self.setLayout(outer)

        def get_config(self) -> ExperimentConfig:
            return ExperimentConfig(
                videostream=self.videostream_combo.currentText(),
                kamera=self.kamera_combo.currentText(),
                z_achse=self.zachse_combo.currentText(),
                maschine=self.maschine_combo.currentText(),
                lighting=self.lighting_cb.isChecked(),
                enclosure=self.enclosure_cb.isChecked(),
                vibration=self.vibration_cb.isChecked(),
            )

    dlg = _Dialog()
    if dlg.exec_() != QDialog.Accepted:
        return None
    return dlg.get_config()


def main() -> None:
    qt_app = QApplication(sys.argv)

    cfg = _show_config_dialog()
    if cfg is None:
        sys.exit(0)

    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_experiment_config(cfg, f"experimental_results/{session_id}")

    pipeline, ui_window, camera = wire(cfg, session_id)

    if not camera.open():
        print("Error: Could not open video stream")
        sys.exit(1)

    ui_window.show()

    timer = QTimer()
    timer.timeout.connect(lambda: _tick(pipeline, timer))
    timer.start(30)

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
