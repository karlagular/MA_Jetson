import sys
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QHBoxLayout
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer, Qt
from typing import Optional, Tuple
from ultralytics import YOLO
import torch

class VideoProcessor:
    def __init__(self, camera_id: int = 0, width: int = 640, height: int = 480):
        """Initialize the video processor with a camera ID."""
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.stream = None

    def open_stream(self) -> bool:
        """Open video stream. Returns True if stream opened successfully."""
        
        pipeline = (
            "nvarguscamerasrc ! "
            "video/x-raw(memory:NVMM), width=1280, height=720, framerate=30/1, format=NV12 ! "
            "nvvidconv flip-method=0 ! "
            "video/x-raw, width=640, height=480, format=BGRx ! "
            "videoconvert ! "
            "video/x-raw, format=BGR ! appsink"
            )
        
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

class VideoApp(QMainWindow):
    def __init__(self, video_processor):
        super().__init__()
        self.video_processor = video_processor
        self.init_ui()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

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
        self.video_label.setFixedSize(780, 440)
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
        self.button1 = QPushButton("Action 1")
        self.button1.setStyleSheet(button_style)
        self.button1.clicked.connect(self.button1_action)
        self.button_layout.addWidget(self.button1)

        self.button2 = QPushButton("Action 2")
        self.button2.setStyleSheet(button_style)
        self.button2.clicked.connect(self.button2_action)
        self.button_layout.addWidget(self.button2)

        self.button3 = QPushButton("Action 3")
        self.button3.setStyleSheet(button_style)
        self.button3.clicked.connect(self.button3_action)
        self.button_layout.addWidget(self.button3)

        self.layout.addLayout(self.button_layout)

        # Set layout
        self.central_widget.setLayout(self.layout)

        # Set window properties
        # self.setWindowTitle("Video Processing App")
        self.setFixedSize(800, 480)
        self.setStyleSheet(
            "QMainWindow { background-color: #1C1C1C; } "
            "QWidget { background-color: #1C1C1C; color: #FFFFFF; } "
        )
        #self.showFullScreen()

    def update_frame(self):
        ret, frame = self.video_processor.read_frame()
        if ret:
            processed_frame = self.video_processor.process_frame(frame)
            self.display_frame(processed_frame)
        else:
            self.timer.stop()
            print("Error: Failed to read frame")

    def display_frame(self, frame):
        # Convert the frame to a format suitable for Qt
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width, channel = rgb_image.shape
        bytes_per_line = channel * width
        q_image = QImage(rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)

        # Display the image on the label
        self.video_label.setPixmap(QPixmap.fromImage(q_image))

    def button1_action(self):
        print("Action 1 triggered")
        # Placeholder function

    def button2_action(self):
        print("Action 2 triggered")
        # Placeholder function

    def button3_action(self):
        print("Action 3 triggered")
        # Placeholder function

    def closeEvent(self, event):
        # Stop the video capture and close windows when the app is closed
        self.video_processor.close_stream()
        event.accept()

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
        
        self.model = YOLO(model_path)
        
        # Configuration
        self.conf_threshold = 0.5
        self.colors = np.random.randint(0, 255, size=(100, 3)).tolist()
    
    @staticmethod
    def draw_mask(img: np.ndarray, mask: np.ndarray, color: Tuple[int, int, int], alpha: float = 0.5) -> np.ndarray:
        """
        Draw segmentation mask on image.
        Args:
            img: Original image
            mask: Binary mask
            color: RGB color for the mask
            alpha: Transparency value (0-1)
        Returns:
            np.ndarray: Image with mask overlay
        """
        overlay = img.copy()
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    processor = YOLOProcessor('yolo11n-seg.pt')
    video_app = VideoApp(processor)
    video_app.show()
    sys.exit(app.exec_())
