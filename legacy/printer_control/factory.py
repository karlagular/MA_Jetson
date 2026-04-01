import json
import os

from legacy.printer_control.ports import PrinterPort

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "machine_config.json")

_ADAPTER_MAP = {
    "RatRig":    "legacy.printer_control.adapters.klipper.KlipperAdapter",
    "Bambulab":  "legacy.printer_control.adapters.bambulab.BambulabAdapter",
    "Prusa":     "legacy.printer_control.adapters.prusa.PrusaAdapter",
    "Ultimaker": "legacy.printer_control.adapters.ultimaker.UltimakerAdapter",
}


def create_printer_adapter(machine: str) -> PrinterPort:
    """Read machine_config.json and return the matching adapter instance."""
    with open(_CONFIG_PATH) as f:
        cfg = json.load(f)[machine]

    qualified = _ADAPTER_MAP.get(machine)
    if qualified is None:
        raise ValueError(f"Unknown machine: '{machine}'")

    module_path, class_name = qualified.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    adapter_cls = getattr(module, class_name)
    return adapter_cls(cfg)
