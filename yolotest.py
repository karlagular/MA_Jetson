from ultralytics import YOLO

# Load a YOLO11n PyTorch model
model = YOLO("yolov8n-seg.pt")

# Run inference
results = model("https://ultralytics.com/images/bus.jpg")