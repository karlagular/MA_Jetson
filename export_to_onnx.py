from ultralytics import YOLO
import os

def export_model(model_path, output_format="onnx", use_fp16=False):
    """
    Export YOLO model to specified format.
    
    Args:
        model_path (str): Path to the .pt model file
        output_format (str): Target format ('onnx', 'engine', etc.)
        use_fp16 (bool): Use FP16 precision (faster on Jetson, slightly less accurate)
    
    Returns:
        str: Path to exported model
    """
    if not os.path.exists(model_path):
        print(f"Error: Model file '{model_path}' not found!")
        return None
    
    model = YOLO(model_path)
    
    print(f"\n{'='*60}")
    print(f"Exporting {model_path} to {output_format.upper()}...")
    print(f"FP16: {use_fp16}")
    print(f"{'='*60}\n")
    
    try:
        exported_model = model.export(
            format=output_format,
            imgsz=640,          # Input image size
            half=use_fp16,      # FP16 precision for faster inference
            simplify=True,      # Simplify ONNX model (recommended)
            device='cpu'        # Use CPU for export (change to 0 for GPU on Jetson)
        )
        
        print(f"\n✓ Successfully exported to: {exported_model}\n")
        return exported_model
    
    except Exception as e:
        print(f"\n✗ Export failed: {e}\n")
        return None


if __name__ == "__main__":
    # List of models to export
    models = [
        "YOLO11n-seg-ret.pt"
    ]
    
    # Export format ('onnx' recommended for cross-platform)
    # Other options: 'engine' (TensorRT), 'torchscript', 'coreml', etc.
    export_format = "onnx"
    
    # Use FP16 for faster inference on Jetson (set to False for full precision)
    use_fp16 = True
    
    print("\n" + "="*60)
    print("YOLO Model Export Utility")
    print("="*60)
    
    exported_models = []
    for model in models:
        result = export_model(model, export_format, use_fp16)
        if result:
            exported_models.append(result)
    
    print("\n" + "="*60)
    print("Export Summary")
    print("="*60)
    print(f"Total models exported: {len(exported_models)}/{len(models)}")
    for model in exported_models:
        print(f"  ✓ {model}")
    print("="*60 + "\n")
