"""PipelineRunner — the hot-path loop with 6 timing stages."""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np
from app.alarm_runtime import AlarmRuntime

from domain.models import FramePacket
from pipeline.latency import LatencyTracker
from pipeline.steps import draw_overlay
from ports.camera import CameraPort
from ports.clock import ClockPort
from ports.inference import InferencePort
from ports.system_metrics_logger import SystemMetricsLoggerPort
from ports.ui import UiPort


class PipelineRunner:
    """Stateless-ish runner: call ``tick()`` once per frame."""

    def __init__(
        self,
        camera: CameraPort,
        inference: InferencePort,
        ui: UiPort,
        alarm_runtime: AlarmRuntime,
        latency_tracker: LatencyTracker,
        clock: ClockPort,
        system_metrics_logger: SystemMetricsLoggerPort | None = None,
        colors: List[Tuple[int, int, int]] | None = None,
    ) -> None:
        self._camera = camera
        self._inference = inference
        self._ui = ui
        self._alarm_runtime = alarm_runtime
        self._tracker = latency_tracker
        self._clock = clock
        self._system_metrics_logger = system_metrics_logger
        self._system_metrics_started = False
        self._colors = colors or np.random.randint(0, 255, size=(100, 3)).tolist()
        self._frame_index = 0

    def tick(self) -> bool:
        """Process one frame.  Returns False when the camera stream ends."""
        t0 = self._clock.perf_counter()

        ok, frame = self._camera.read_frame()
        t1 = self._clock.perf_counter()
        if not ok or frame is None:
            return False

        if self._system_metrics_logger is not None and not self._system_metrics_started:
            self._system_metrics_logger.start()
            self._system_metrics_started = True

        result = self._inference.predict(frame)
        t2 = self._clock.perf_counter()

        overlay = draw_overlay(frame, result, self._colors)
        mask_frame = self._render_mask_frame(result, frame.shape)
        t3 = self._clock.perf_counter()

        # Save overlay plus raw/mask alarm artifacts through the runtime effect path.
        packet = FramePacket(
            frame=overlay,
            index=self._frame_index,
            timestamp_ns=int(t0 * 1e9),
            raw_frame=frame.copy(),
            mask_frame=mask_frame,
        )
        self._alarm_runtime.handle_detection(result, packet)
        self._alarm_runtime.process_pending_events()
        t4 = self._clock.perf_counter()

        self._ui.display_frame(overlay)
        t5 = self._clock.perf_counter()

        self._tracker.record(
            capture_ms=(t1 - t0) * 1000.0,
            inference_ms=(t2 - t1) * 1000.0,
            postprocess_ms=(t3 - t2) * 1000.0,
            policy_ms=(t4 - t3) * 1000.0,
            display_ms=(t5 - t4) * 1000.0,
            total_ms=(t5 - t0) * 1000.0,
        )
        self._frame_index += 1
        return True

    def shutdown(self) -> None:
        if self._system_metrics_logger is not None:
            self._system_metrics_logger.stop()
        self._alarm_runtime.shutdown(frame_count=self._frame_index)
        self._tracker.stop()
        self._tracker.save_log()
        self._camera.close()

    @property
    def frame_count(self) -> int:
        return self._frame_index

    @staticmethod
    def _render_mask_frame(result, frame_shape: tuple[int, ...]) -> np.ndarray | None:
        if not result.masks:
            return None

        h, w = frame_shape[:2]
        merged = np.zeros((h, w), dtype=np.uint8)
        for mask in result.masks:
            if mask.shape[:2] != (h, w):
                mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
            merged[mask.astype(bool)] = 255
        return np.stack([merged, merged, merged], axis=-1)
