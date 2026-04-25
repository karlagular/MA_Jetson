"""PyQt5 UI adapter — main window with video, model buttons, and alarm dialog."""

from __future__ import annotations

from typing import Callable, Optional

import cv2
import numpy as np
from PyQt5.QtCore import QMetaObject, QTimer, Qt, Q_ARG, pyqtSlot
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QVBoxLayout, QWidget,
)

from app.config import ExperimentConfig
from ports.ui import ConfigUiPort, UiPort

_BUTTON_STYLE = (
    "QPushButton {"
    "    font-size: 14px; padding: 8px 16px; border-radius: 6px;"
    "    background-color: #2D2D2D; color: #FFFFFF; border: 1px solid #3A3A3A;"
    "}"
    "QPushButton:hover   { background-color: #3A3A3A; }"
    "QPushButton:pressed { background-color: #505050; }"
)

_DIALOG_STYLE = (
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


class ExperimentConfigDialog(QDialog):
    """PyQt5 dialog for experiment configuration."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Experimentkonfiguration")
        self.setMinimumWidth(400)
        self.setStyleSheet(_DIALOG_STYLE)
        self._build()

    def _build(self) -> None:
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
        self.kamera_combo.addItems(["USB Basler BW Fix", "RTSP rpi cam 3 wide", "USB Webcam Logitech", "Replay Video"])

        self.zachse_combo = QComboBox()
        self.zachse_combo.addItems(["Druckkopf", "Druckbett"])

        self.maschine_combo = QComboBox()
        self.maschine_combo.addItems(["Bambulab", "RatRig", "Prusa", "Ultimaker", "Fake Printer"])

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
        start_btn.setStyleSheet(_BUTTON_STYLE)
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


class QtConfigUi(ConfigUiPort):
    """Adapter: shows the PyQt5 config dialog and returns an ExperimentConfig."""

    def request_session_config(self) -> Optional[ExperimentConfig]:
        dlg = ExperimentConfigDialog()
        if dlg.exec_() != QDialog.Accepted:
            return None
        return dlg.get_config()


class PersonAlarmDialog(QDialog):
    """Modal-looking alarm popup (stays on top, non-blocking)."""

    def __init__(
        self,
        parent: QWidget | None,
        on_continue: Callable[[], None],
        on_stop: Callable[[], None],
    ) -> None:
        super().__init__(parent)
        self._on_continue = on_continue
        self._on_stop = on_stop
        self.setWindowTitle("Person erkannt!")
        self.setModal(False)
        self.setMinimumWidth(380)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(
            "QDialog  { background-color: #1C1C1C; }"
            "QWidget  { background-color: #1C1C1C; color: #FFFFFF; }"
            "QLabel   { font-size: 14px; color: #FF5555; }"
            f"QPushButton {{ {_BUTTON_STYLE[len('QPushButton {'):]} }}"
        )
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        msg = QLabel("Person erkannt!\nBitte Druckvorgang überprüfen.")
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("font-size: 15px; font-weight: bold; color: #FF5555;")
        layout.addWidget(msg)

        self._status_label = QLabel("Printer pause in progress...")
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("font-size: 12px; color: #AAAAAA;")
        layout.addWidget(self._status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._continue_btn = QPushButton("Continue printing")
        self._continue_btn.setStyleSheet(_BUTTON_STYLE)
        self._continue_btn.setEnabled(False)
        self._continue_btn.clicked.connect(self._handle_continue)
        btn_row.addWidget(self._continue_btn)

        self._stop_btn = QPushButton("Stop Process")
        self._stop_btn.setStyleSheet(_BUTTON_STYLE)
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._handle_stop)
        btn_row.addWidget(self._stop_btn)

        layout.addLayout(btn_row)
        self.setLayout(layout)

    def enable_buttons(self) -> None:
        self._status_label.setText("Printer pause confirmed. Choose an action.")
        self._status_label.setStyleSheet("font-size: 12px; color: #55FF99;")
        self._continue_btn.setEnabled(True)
        self._stop_btn.setEnabled(True)

    def _handle_continue(self) -> None:
        self._on_continue()
        self.close()

    def _handle_stop(self) -> None:
        self._on_stop()
        self.close()


class QtVideoWindow(QMainWindow):
    """Main Qt window that implements the UiPort interface."""

    def __init__(self, on_model_change: Optional[Callable[[str], None]] = None) -> None:
        super().__init__()
        self._on_model_change = on_model_change
        self._alarm_dialog: Optional[PersonAlarmDialog] = None
        self._build_ui()

    # -- UiPort ---------------------------------------------------------

    def display_frame(self, frame: np.ndarray) -> None:
        window_w = self._video_label.width()
        window_h = self._video_label.height()
        stretched = cv2.resize(frame, (window_w, window_h))
        rgb = cv2.cvtColor(stretched, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self._video_label.setPixmap(QPixmap.fromImage(qimg))

    def show_alarm(self, on_continue: Callable[[], None], on_stop: Callable[[], None]) -> None:
        # Must be called from the main thread
        print("[UI] show_alarm() called — queuing dialog to main thread")
        QMetaObject.invokeMethod(
            self, "_show_alarm_main_thread",
            Qt.QueuedConnection,
            Q_ARG(object, on_continue),
            Q_ARG(object, on_stop),
        )

    @pyqtSlot(object, object)
    def _show_alarm_main_thread(self, on_continue, on_stop) -> None:
        print("[UI] _show_alarm_main_thread() — opening alarm dialog")
        if self._alarm_dialog is not None and self._alarm_dialog.isVisible():
            return
        self._alarm_dialog = PersonAlarmDialog(self, on_continue, on_stop)
        self._alarm_dialog.show()

    def dismiss_alarm(self) -> None:
        if self._alarm_dialog is not None:
            self._alarm_dialog.close()
            self._alarm_dialog = None

    def enable_alarm_buttons(self) -> None:
        print("[UI] enable_alarm_buttons() called — queuing to main thread")
        QMetaObject.invokeMethod(
            self,
            "_enable_alarm_buttons_main_thread",
            Qt.QueuedConnection,
        )

    @pyqtSlot()
    def _enable_alarm_buttons_main_thread(self) -> None:
        if self._alarm_dialog is not None and self._alarm_dialog.isVisible():
            self._alarm_dialog.enable_buttons()

    # -- UI construction ------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        headline = QLabel("Synthetic Inference")
        headline.setStyleSheet("font-size: 22px; font-weight: bold; color: #FFFFFF;")
        headline.setAlignment(Qt.AlignCenter)
        layout.addWidget(headline)

        self._video_label = QLabel()
        self._video_label.setStyleSheet(
            "border-radius: 8px; border: 1px solid #444; background-color: #1E1E1E;"
        )
        layout.addWidget(self._video_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(15)

        for label, model_path in [
            ("Model 1", "models_available/YOLO11n-seg-ret.pt"),
            ("Model 2", "models_available/yolo11n-seg.pt"),
            ("Model 3", "models_available/yolov8n-seg.pt"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(_BUTTON_STYLE)
            btn.clicked.connect(lambda checked, p=model_path: self._change_model(p))
            btn_row.addWidget(btn)

        fs_btn = QPushButton("Toggle Fullscreen")
        fs_btn.setStyleSheet(_BUTTON_STYLE)
        fs_btn.clicked.connect(self._toggle_fullscreen)
        btn_row.addWidget(fs_btn)

        layout.addLayout(btn_row)
        central.setLayout(layout)

        self.setWindowTitle("Video Processing App")
        self.setStyleSheet(
            "QMainWindow { background-color: #1C1C1C; } "
            "QWidget { background-color: #1C1C1C; color: #FFFFFF; } "
        )
        self.setMinimumSize(400, 300)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        w = self.centralWidget().width() - 20
        h = self.centralWidget().height() - 100
        self._video_label.setFixedSize(w, h)

    def _change_model(self, path: str) -> None:
        if self._on_model_change:
            self._on_model_change(path)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()


UiPort.register(QtVideoWindow)
