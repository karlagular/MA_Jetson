"""Configuration schema and loaders."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ExperimentConfig:
    videostream: str = "USB"           # USB | RTSP | CSI
    kamera: str = "USB Webcam Logitech"  # camera selection
    z_achse: str = "Druckkopf"
    maschine: str = "Bambulab"
    lighting: bool = False
    enclosure: bool = False
    vibration: bool = False
    model_path: str = "models_available/yolo11n-seg.pt"
    alarm_m: int = 3
    alarm_n: int = 5
    rtsp_url: str = "rtsp://192.168.178.68:8554/cam"
    video_path: str = "test_video.mp4"


def load_experiment_config(path: str) -> ExperimentConfig:
    """Load from JSON file, falling back to defaults for missing keys."""
    with open(path, "r") as f:
        data = json.load(f)
    return ExperimentConfig(**{k: v for k, v in data.items() if k in ExperimentConfig.__dataclass_fields__})


def load_machine_config(path: str = "machine_config.json") -> dict:
    """Load the per-printer credential file."""
    with open(path, "r") as f:
        return json.load(f)


def save_experiment_config(cfg: ExperimentConfig, session_dir: str) -> str:
    """Persist experiment config as JSON in the session folder."""
    os.makedirs(session_dir, exist_ok=True)
    path = os.path.join(session_dir, "experiment_config.json")
    data = {k: getattr(cfg, k) for k in ExperimentConfig.__dataclass_fields__}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[Config] Saved to {path}")
    return path


def discover_models(models_dir: str = "models_available") -> list:
    """Return sorted list of .pt paths (relative to CWD) found in models_dir."""
    return sorted(str(p) for p in Path(models_dir).glob("*.pt"))
