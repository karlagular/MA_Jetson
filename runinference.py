import cv2
import numpy as np
from typing import Optional, Tuple
from ultralytics import YOLO
import torch
import tkinter as tk
from functools import partial

class VideoProcessor:
    def __init__(self, camera_id: int = 0, width: int = 640, height: int = 640):
        """Initialize the video processor with a camera ID."""
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.stream = None
    
    def open_stream(self) -> bool:
        """
        Open video stream.
        Returns:
            bool: True if stream opened successfully
        """
        pipeline = (
            "nvarguscamerasrc ! "
            "video/x-raw(memory:NVMM), width=1280, height=720, framerate=30/1, format=NV12 ! "
            "nvvidconv flip-method=0 ! "
            "video/x-raw, width=640, height=480, format=BGRx ! "
            "videoconvert ! "
            "video/x-raw, format=BGR ! appsink"
        )
        # self.stream = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        self.stream = cv2.VideoCapture(0) # WEBCAM WORKIN!
        
        self.stream.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.stream.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        return self.stream.isOpened()
    
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Read a frame from the stream.
        Returns:
            Tuple[bool, Optional[np.ndarray]]: Success flag and frame if successful
        """
        if self.stream is None:
            return False, None
        return self.stream.read()
    
    def close_stream(self):
        """Clean up resources."""
        if self.stream is not None:
            self.stream.release()
        cv2.destroyAllWindows()

    @staticmethod
    def process_frame(frame: np.ndarray) -> np.ndarray:
        """
        Process the frame. Override this method for custom processing.
        Args:
            frame (np.ndarray): Input frame
        Returns:
            np.ndarray: Processed frame
        """
        # Example processing: Edge detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        return cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)

    def run(self):
        """Main loop for capturing, processing, and displaying video."""
        if not self.open_stream():
            print("Error: Could not open video stream")
            return

        try:
            while True:
                # Read frame
                ret, frame = self.read_frame()
                if not ret:
                    break

                # Process frame
                processed_frame = self.process_frame(frame)

                # Display original and processed frames
                # cv2.imshow('Original', frame)
                cv2.imshow('Processed', processed_frame)

                # Break loop on 'q' press
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

        finally:
            self.close_stream()

# Example usage with custom processing
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
        print("Class names recognized by the model:")
        for class_id, class_name in self.model.names.items():
            print(f"{class_id}: {class_name}")
        
        # Configuration
        self.conf_threshold = 0.6
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
    # Initialize and run the YOLO processor
    # You can use different models like:
    # - 'yolov8n-seg.pt' (nano)
    # - 'yolov8s-seg.pt' (small)
    # - 'yolov8m-seg.pt' (medium)
    # - 'yolov8l-seg.pt' (large)
    # - 'yolov8x-seg.pt' (extra large)
    processor = YOLOProcessor('yolov8n-seg.pt')
    # create_gui(processor)
    processor.run()

