import sys
import cv2
import numpy as np
import os
import json
import time
import threading
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QDialog, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QComboBox, QCheckBox
)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer, Qt
from typing import Optional, Tuple
from ultralytics import YOLO
import torch
import printer_control

class VideoProcessor:
    def __init__(self, camera_id = 0, width: int = 640, height: int = 480):
        """Initialize the video processor with a camera ID (int) or GStreamer/RTSP pipeline (str)."""
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.stream = None

    def open_stream(self) -> bool:
        """Open video stream. Returns True if stream opened successfully."""
        
        if isinstance(self.camera_id, str):
            # RTSP or GStreamer pipeline string
            self.stream = cv2.VideoCapture(self.camera_id, cv2.CAP_GSTREAMER)
        else:
            # Integer device ID (USB webcam / CSI)
            self.stream = cv2.VideoCapture(self.camera_id)
            self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return self.stream.isOpened()

    def read_frame(self):
        """Read a frame from the stream. Returns a tuple (success, frame)."""
        if self.stream is None:
            return False, None
        return self.stream.read()

    def process_frame(self, frame):
        """Process the frame. Override this method for custom processing."""
        # Example: Convert frame to grayscale and apply Canny edge detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        return cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

    def close_stream(self):
        """Release video stream and close OpenCV windows."""
        if self.stream is not None:
            self.stream.release()
        cv2.destroyAllWindows()


class BaslerVideoProcessor:
    """Video processor that grabs frames from a Basler USB camera via pypylon."""

    def __init__(self, serial: str | None = None):
        self.serial = serial
        self._camera = None
        self._converter = None

    def open_stream(self) -> bool:
        try:
            from pypylon import pylon
        except ImportError:
            print("ERROR: pypylon is not installed. Run: pip install pypylon")
            return False

        factory = pylon.TlFactory.GetInstance()
        devices = factory.EnumerateDevices()
        if not devices:
            print("ERROR: No Basler camera detected.")
            return False

        selected = devices[0]
        if self.serial:
            for dev in devices:
                if dev.GetSerialNumber() == self.serial:
                    selected = dev
                    break

        self._camera = pylon.InstantCamera(factory.CreateDevice(selected))
        self._camera.Open()

        self._converter = pylon.ImageFormatConverter()
        self._converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        self._converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

        self._camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        info = self._camera.GetDeviceInfo()
        print(f"[Basler] Opened {info.GetModelName()} serial={info.GetSerialNumber()}")
        return True

    def read_frame(self):
        if self._camera is None or not self._camera.IsGrabbing():
            return False, None
        from pypylon import pylon
        grab = self._camera.RetrieveResult(3000, pylon.TimeoutHandling_Return)
        if grab is None or not grab.GrabSucceeded():
            if grab is not None:
                grab.Release()
            return False, None
        image = self._converter.Convert(grab)
        frame = image.GetArray()
        frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        grab.Release()
        return True, frame

    def close_stream(self):
        if self._camera is not None:
            if self._camera.IsGrabbing():
                self._camera.StopGrabbing()
            if self._camera.IsOpen():
                self._camera.Close()
            self._camera = None

class LatencyTracker:
    def __init__(self, window_size: int = 60, session_id: str = None):
        self._records = []  # list of (frame_idx, capture_ms, inference_ms, display_ms, total_ms)
        self._frame_index = 0
        self._lock = threading.Lock()
        self._window_size = window_size
        self._session_timestamp = session_id if session_id else datetime.now().strftime("%Y%m%d_%H%M%S")
        self._stop_event = threading.Event()
        self._print_thread = threading.Thread(target=self._print_loop, daemon=True)
        self._print_thread.start()

    def record(self, t_capture_ms, t_inference_ms, t_display_ms, t_total_ms):
        entry = (self._frame_index, t_capture_ms, t_inference_ms, t_display_ms, t_total_ms)
        with self._lock:
            self._records.append(entry)
        self._frame_index += 1

    def _print_loop(self):
        while not self._stop_event.wait(timeout=1.0):
            self._print_stats()

    def _print_stats(self):
        with self._lock:
            snapshot = self._records[-self._window_size:]
        if not snapshot:
            return
        n = len(snapshot)
        captures   = [r[1] for r in snapshot]
        inferences = [r[2] for r in snapshot]
        displays   = [r[3] for r in snapshot]
        totals     = [r[4] for r in snapshot]

        def stats(vals):
            arr = np.array(vals)
            return f"min={arr.min():.1f} mean={arr.mean():.1f} p99={np.percentile(arr, 99):.1f} max={arr.max():.1f} ms"

        ts = datetime.now().strftime("%H:%M:%S")
        print(
            f"[Latency {ts}] N={n} | "
            f"capture: {stats(captures)} | "
            f"inference: {stats(inferences)} | "
            f"display: {stats(displays)} | "
            f"total: {stats(totals)}"
        )

    def stop(self):
        self._stop_event.set()
        self._print_thread.join(timeout=2.0)

    def save_log(self, filename="latency_log.txt"):
        with self._lock:
            records_copy = list(self._records)
        log_dir = os.path.join("experimental_results", self._session_timestamp)
        os.makedirs(log_dir, exist_ok=True)
        filepath = os.path.join(log_dir, filename)
        with open(filepath, 'w') as f:
            f.write("frame,capture_ms,inference_ms,display_ms,total_ms\n")
            for r in records_copy:
                f.write(f"{r[0]},{r[1]:.3f},{r[2]:.3f},{r[3]:.3f},{r[4]:.3f}\n")
        print(f"[LatencyTracker] Saved {len(records_copy)} frames to {filepath}")


class ExperimentConfigDialog(QDialog):
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
        self._init_ui()

    def _init_ui(self):
        outer = QVBoxLayout()
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(18)

        # Title
        title = QLabel("Experimentkonfiguration")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #FFFFFF;")
        title.setAlignment(Qt.AlignCenter)
        outer.addWidget(title)

        # Dropdowns
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

        rows = [
            ("Videostream:", self.videostream_combo),
            ("Kamera:",      self.kamera_combo),
            ("Z-Achse:",     self.zachse_combo),
            ("Maschine:",    self.maschine_combo),
        ]
        for i, (label_text, widget) in enumerate(rows):
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            grid.addWidget(lbl, i, 0)
            grid.addWidget(widget, i, 1)
        outer.addLayout(grid)

        # Checkboxes
        self.lighting_cb  = QCheckBox("Lighting")
        self.enclosure_cb = QCheckBox("Enclosure")
        self.vibration_cb = QCheckBox("Vibration")

        cb_row = QHBoxLayout()
        cb_row.setSpacing(20)
        cb_row.addWidget(self.lighting_cb)
        cb_row.addWidget(self.enclosure_cb)
        cb_row.addWidget(self.vibration_cb)
        outer.addLayout(cb_row)

        # Start button
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

    def get_config(self) -> dict:
        return {
            "videostream": self.videostream_combo.currentText(),
            "kamera":      self.kamera_combo.currentText(),
            "z_achse":     self.zachse_combo.currentText(),
            "maschine":    self.maschine_combo.currentText(),
            "lighting":    self.lighting_cb.isChecked(),
            "enclosure":   self.enclosure_cb.isChecked(),
            "vibration":   self.vibration_cb.isChecked(),
        }


class PersonAlarmDialog(QDialog):
    def __init__(self, parent=None, machine: str = ""):
        super().__init__(parent)
        self._machine = machine
        self.setWindowTitle("Person erkannt!")
        self.setModal(False)
        self.setMinimumWidth(380)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(
            "QDialog  { background-color: #1C1C1C; }"
            "QWidget  { background-color: #1C1C1C; color: #FFFFFF; }"
            "QLabel   { font-size: 14px; color: #FF5555; }"
            "QPushButton {"
            "    font-size: 13px; padding: 8px 16px; border-radius: 6px;"
            "    background-color: #2D2D2D; color: #FFFFFF; border: 1px solid #3A3A3A;"
            "}"
            "QPushButton:hover   { background-color: #3A3A3A; }"
            "QPushButton:pressed { background-color: #505050; }"
        )
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        msg = QLabel("Person erkannt!\nBitte Druckvorgang überprüfen.")
        msg.setAlignment(Qt.AlignCenter)
        msg.setStyleSheet("font-size: 15px; font-weight: bold; color: #FF5555;")
        layout.addWidget(msg)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        continue_btn = QPushButton("Continue printing")
        continue_btn.clicked.connect(self.close)
        btn_row.addWidget(continue_btn)

        stop_btn = QPushButton("Stop Process")
        stop_btn.clicked.connect(self._on_stop_process)
        btn_row.addWidget(stop_btn)

        layout.addLayout(btn_row)
        self.setLayout(layout)

    def _on_stop_process(self):
        #aktuell pause statt stop 
        printer_control.pause_print(self._machine)
        self.close()


class VideoApp(QMainWindow):
    def __init__(self, video_processor, session_id: str = None, machine: str = ""):
        super().__init__()
        self.video_processor = video_processor
        self._machine = machine
        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)
        self.latency_tracker = LatencyTracker(window_size=60, session_id=session_id)
        self._person_consecutive = 0
        self._alarm_dialog = None

        # Start video processing
        if not self.video_processor.open_stream():
            print("Error: Could not open video stream")
            return
        self.timer.start(30)

    def init_ui(self):
        # Main widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Layout
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Headline label
        self.headline_label = QLabel("Synthetic Inference")
        self.headline_label.setStyleSheet(
            "font-size: 22px; font-weight: bold; text-align: center; color: #FFFFFF;"
        )
        self.headline_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.headline_label)

        # Video display label
        self.video_label = QLabel()
        self.video_label.setStyleSheet(
            "border-radius: 8px; border: 1px solid #444; background-color: #1E1E1E;"
        )
        self.layout.addWidget(self.video_label)

        # Button layout
        self.button_layout = QHBoxLayout()
        self.button_layout.setSpacing(15)

        # Button common style
        button_style = (
            "QPushButton {"
            "    font-size: 14px; padding: 8px 16px; border-radius: 6px;"
            "    background-color: #2D2D2D; color: #FFFFFF;"
            "    border: 1px solid #3A3A3A;"
            "}"
            "QPushButton:hover {"
            "    background-color: #3A3A3A;"
            "}"
            "QPushButton:pressed {"
            "    background-color: #505050;"
            "}"
        )

        # Buttons
        self.button1 = QPushButton("Model 1")
        self.button1.setStyleSheet(button_style)
        self.button1.clicked.connect(self.button1_action)
        self.button_layout.addWidget(self.button1)

        self.button2 = QPushButton("Model 2")
        self.button2.setStyleSheet(button_style)
        self.button2.clicked.connect(self.button2_action)
        self.button_layout.addWidget(self.button2)

        self.button3 = QPushButton("Model 3")
        self.button3.setStyleSheet(button_style)
        self.button3.clicked.connect(self.button3_action)
        self.button_layout.addWidget(self.button3)

        # Fourth button for toggling fullscreen
        self.fullscreen_button = QPushButton("Toggle Fullscreen")
        self.fullscreen_button.setStyleSheet(button_style)
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.button_layout.addWidget(self.fullscreen_button)

        self.layout.addLayout(self.button_layout)

        # Set layout
        self.central_widget.setLayout(self.layout)

        # Set window properties
        self.setWindowTitle("Video Processing App")
        self.setStyleSheet(
            "QMainWindow { background-color: #1C1C1C; } "
            "QWidget { background-color: #1C1C1C; color: #FFFFFF; } "
        )
        self.setMinimumSize(400, 300)  # Make window resizable

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Get the available size for the video frame
        available_width = self.central_widget.width() - 20
        available_height = self.central_widget.height() - 100
        
        # Set the size of the video label to match the available space
        self.video_label.setFixedSize(available_width, available_height)

    def update_frame(self):
        t0 = time.perf_counter()
        ret, frame = self.video_processor.read_frame()
        t1 = time.perf_counter()
        if ret:
            processed_frame = self.video_processor.process_frame(frame)
            t2 = time.perf_counter()
            self.display_frame(processed_frame)
            t3 = time.perf_counter()
            self.latency_tracker.record(
                t_capture_ms   = (t1 - t0) * 1000.0,
                t_inference_ms = (t2 - t1) * 1000.0,
                t_display_ms   = (t3 - t2) * 1000.0,
                t_total_ms     = (t3 - t0) * 1000.0,
            )
            if self.video_processor.person_detected:
                self._person_consecutive += 1
                if self._person_consecutive == 5:
                    self._save_alarm_frame(processed_frame)
                    self._show_alarm()
            else:
                self._person_consecutive = 0
        else:
            self.timer.stop()
            print("Error: Failed to read frame")

    def display_frame(self, frame):
        # Get the aspect ratio of the video
        frame_height, frame_width = frame.shape[:2]
        window_width = self.video_label.width()
        window_height = self.video_label.height()
        
        # Resize the frame to fill the entire label (stretching)
        stretched_frame = cv2.resize(frame, (window_width, window_height))

        # Convert the stretched frame to RGB
        rgb_image = cv2.cvtColor(stretched_frame, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb_image.shape
        bytes_per_line = channel * width
        q_image = QImage(rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)

        # Create a QPixmap from the image
        pixmap = QPixmap.fromImage(q_image)

        # Set the pixmap to the video label
        self.video_label.setPixmap(pixmap)
        self.video_label.setAlignment(Qt.AlignCenter)
    
    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def button1_action(self):
        print("Action 1 triggered")
        self.video_processor.change_model("YOLO11n-seg-ret.pt")

    def button2_action(self):
        print("Action 2 triggered")
        self.video_processor.change_model("yolo11n-seg.pt")

    def button3_action(self):
        print("Action 3 triggered")
        self.video_processor.change_model("yolov8n-seg.pt")

    def _save_alarm_frame(self, frame):
        log_dir = os.path.join("experimental_results", self.latency_tracker._session_timestamp)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(log_dir, f"person_alarm_{ts}.jpg")
        cv2.imwrite(filepath, frame)
        print(f"[Alarm] Frame saved to {filepath}")

    def _show_alarm(self):
        if self._alarm_dialog is not None and self._alarm_dialog.isVisible():
            return
        self._alarm_dialog = PersonAlarmDialog(parent=self, machine=self._machine)
        self._alarm_dialog.show()

    def closeEvent(self, event):
        # Stop the video capture and close windows when the app is closed
        self.latency_tracker.stop()
        self.latency_tracker.save_log("latency_log.txt")
        self.video_processor.close_stream()
        event.accept()

class BaslerYOLOProcessor(BaslerVideoProcessor):
    """YOLO processor that grabs frames from a Basler USB camera."""

    def __init__(self, model_path: str, serial: str | None = None):
        super().__init__(serial)
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f'Using device: {device}')
        self.device = device
        self.model = YOLO(model_path)
        self.conf_threshold = 0.5
        self.colors = np.random.randint(0, 255, size=(100, 3)).tolist()
        self.person_detected = False

    def change_model(self, new_model_path: str):
        print(f"Switching model to: {new_model_path}")
        self.model = YOLO(new_model_path)
        self.model.to(self.device)
        print(f"Model changed to: {new_model_path}")

    process_frame = None  # assigned below after YOLOProcessor is defined


class YOLOProcessor(VideoProcessor):
    def __init__(self, model_path: str, camera_id: int = 0):
        """
        Initialize YOLO processor with model path.
        Args:
            model_path: Path to YOLO model (e.g., 'yolov8n-seg.pt')
            camera_id: Camera device ID
        """
        super().__init__(camera_id)
        # Check for CUDA device and set it
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f'Using device: {device}')
        self.device = device
        
        self.model = YOLO(model_path)
        
        # Configuration
        self.conf_threshold = 0.5
        self.colors = np.random.randint(0, 255, size=(100, 3)).tolist()
        self.person_detected = False
    
    def change_model(self, new_model_path: str):
        """Change the YOLO model without restarting the video stream."""
        print(f"Switching model to: {new_model_path}")
        self.model = YOLO(new_model_path)
        self.model.to(self.device)
        print(f"Model changed to: {new_model_path}")

    @staticmethod
    def draw_mask(img: np.ndarray, mask: np.ndarray, color: Tuple[int, int, int], alpha: float = 0.5) -> np.ndarray:
        """ Draw segmentation mask on image. """
        overlay = img.copy()
        
        # Resize mask to match image dimensions
        if mask.shape[:2] != img.shape[:2]:
            mask = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)

        mask = mask.astype(bool)
        overlay[mask] = color
        return cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)
    
    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Process frame with YOLO model for detection and segmentation.
        Args:
            frame: Input frame
        Returns:
            np.ndarray: Processed frame with detections and segmentations
        """
        # Run YOLO prediction
        results = self.model.predict(
            source=frame,
            conf=self.conf_threshold,
            device='cuda' if torch.cuda.is_available() else 'cpu',
            verbose=False
        )[0]
        
        processed_frame = frame.copy()

        # Update person_detected for this frame
        self.person_detected = (
            results.boxes is not None
            and any(results.names[int(b.cls[0])] == "person" for b in results.boxes)
        )

        if hasattr(results, 'masks') and results.masks is not None:
            # Process each detection
            for i, (box, mask) in enumerate(zip(results.boxes, results.masks)):
                # Get box coordinates
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = float(box.conf[0])
                cls = int(box.cls[0])
                
                # Get class name
                class_name = results.names[cls]
                
                # Get color for this class
                color = self.colors[cls % len(self.colors)]
                
                # Draw segmentation mask
                mask_array = mask.data[0].cpu().numpy()
                processed_frame = self.draw_mask(
                    processed_frame,
                    mask_array,
                    color,
                    alpha=0.3
                )
                
                # Draw bounding box
                cv2.rectangle(
                    processed_frame,
                    (x1, y1),
                    (x2, y2),
                    color,
                    2
                )
                
                # Add label with confidence
                label = f"{class_name} {conf:.2f}"
                text_size = cv2.getTextSize(
                    label,
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    2
                )[0]
                
                # Draw label background
                cv2.rectangle(
                    processed_frame,
                    (x1, y1 - text_size[1] - 8),
                    (x1 + text_size[0], y1),
                    color,
                    -1
                )
                
                # Draw label text
                cv2.putText(
                    processed_frame,
                    label,
                    (x1, y1 - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (255, 255, 255),
                    2
                )
        
        return processed_frame

# Share process_frame / draw_mask between both YOLO processors
BaslerYOLOProcessor.process_frame = YOLOProcessor.process_frame
BaslerYOLOProcessor.draw_mask = staticmethod(YOLOProcessor.draw_mask)

if __name__ == "__main__":
    # --- Source selection --- (comment or uncomment the processor lines as needed)
    # USB webcam:  camera_id = 0
    # CSI camera:  camera_id = "nvarguscamerasrc ! ..."
    # RTSP stream: camera_id = rtsp_pipeline (below)

    RTSP_URL = "rtsp://192.168.178.68:8554/cam"
    rtsp_pipeline = (
        f"rtspsrc location={RTSP_URL} latency=200 ! "
        "rtph264depay ! h264parse ! nvv4l2decoder ! "
        "nvvidconv ! video/x-raw,format=BGRx ! "
        "videoconvert ! video/x-raw,format=BGR ! appsink drop=1"
    )

    app = QApplication(sys.argv)

    # Show experiment configuration dialog before starting inference
    config_dialog = ExperimentConfigDialog()
    if config_dialog.exec_() != QDialog.Accepted:
        sys.exit(0)

    config = config_dialog.get_config()
    session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Save experiment config to the session folder
    log_dir = os.path.join("experimental_results", session_ts)
    os.makedirs(log_dir, exist_ok=True)
    config_path = os.path.join(log_dir, "experiment_config.json")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"[Config] Saved to {config_path}")

    # Verify the selected printer is connected and reachable
    machine = config["maschine"]
    if printer_control.check_printer_status(machine):
        print(f"[Config] Printer '{machine}' is connected and available")
    else:
        print(f"[Config] WARNING: Printer '{machine}' is not connected or not reachable")

    kamera = config["kamera"]
    if kamera == "USB Basler BW Fix":
        processor = BaslerYOLOProcessor('yolo11n-seg.pt')
    elif kamera == "RTSP rpi cam 3 wide":
        processor = YOLOProcessor('yolo11n-seg.pt', camera_id=rtsp_pipeline)
    else:  # "USB Webcam Logitech" or fallback
        processor = YOLOProcessor('yolo11n-seg.pt', camera_id=0)

    video_app = VideoApp(processor, session_id=session_ts, machine=config["maschine"])
    video_app.show()
    sys.exit(app.exec_())
