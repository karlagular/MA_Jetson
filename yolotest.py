from pathlib import Path
import argparse

import cv2
import numpy as np
from ultralytics import YOLO


def _print_results(results: list) -> None:
    for result_index, result in enumerate(results, start=1):
        print(f"\n=== Result {result_index} ===")

        if result.boxes is None or len(result.boxes) == 0:
            print("No detections.")
            continue

        has_masks = hasattr(result, "masks") and result.masks is not None

        for det_index, box in enumerate(result.boxes, start=1):
            x1, y1, x2, y2 = map(float, box.xyxy[0].tolist())
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            cls_name = result.names[cls_id] if result.names else str(cls_id)

            print(f"Detection {det_index}:")
            print(f"  class: {cls_name} (id={cls_id})")
            print(f"  confidence: {conf:.4f}")
            print(f"  bbox_xyxy: ({x1:.2f}, {y1:.2f}, {x2:.2f}, {y2:.2f})")

            has_mask = has_masks and det_index - 1 < len(result.masks)
            print(f"  pixel_map: {'yes' if has_mask else 'no'}")


def save_result_image(result, source: Path) -> None:
    """Draw boxes and masks on the original image and save as [stem]-result.jpg."""
    img = result.orig_img.copy()  # BGR numpy array
    h, w = img.shape[:2]

    has_masks = hasattr(result, "masks") and result.masks is not None

    if result.boxes is not None:
        for det_index, box in enumerate(result.boxes):
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf = float(box.conf[0])
            cls_id = int(box.cls[0])
            cls_name = result.names[cls_id] if result.names else str(cls_id)

            # Overlay segmentation mask
            if has_masks and det_index < len(result.masks):
                mask = result.masks[det_index].data[0].cpu().numpy()
                binary_mask = cv2.resize(
                    (mask > 0.5).astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST
                )
                overlay = img.copy()
                overlay[binary_mask == 1] = (0, 255, 0)  # green fill
                cv2.addWeighted(overlay, 0.4, img, 0.6, 0, img)

            # Draw bounding box
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 0, 255), 2)
            label = f"{cls_name} {conf:.2f}"
            cv2.putText(img, label, (x1, max(y1 - 6, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

    out_path = source.parent / f"{source.stem}-result.jpg"
    cv2.imwrite(str(out_path), img)
    print(f"Saved result image: {out_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Quick YOLO inference test")
    parser.add_argument(
        "--model",
        default="best.pt",
        help="Path to model weights (default: best.pt)",
    )
    parser.add_argument(
        "--source",
        default="https://ultralytics.com/images/bus.jpg",
        help="Image/video source for inference",
    )
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.is_absolute():
        model_path = Path(__file__).resolve().parent / model_path

    if not model_path.exists():
        print(f"Model file not found: {model_path}")
        print("Run this script from repository root or pass --model with a valid path.")
        return 1

    source_path = Path(args.source)

    model = YOLO(str(model_path))
    results = model(args.source)

    print(f"Loaded model: {model_path}")
    print(f"Inference complete. Number of result items: {len(results)}")
    _print_results(results)

    if source_path.exists():
        for result in results:
            save_result_image(result, source_path)
    else:
        print("Note: source is not a local file path — result image not saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
