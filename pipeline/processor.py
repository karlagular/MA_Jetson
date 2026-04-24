"""PipelineRunner — the hot-path loop with 6 timing stages."""

from __future__ import annotations

from typing import List, Tuple

import numpy as np
from app.alarm_runtime import AlarmRuntime

from domain.models import FramePacket
from pipeline.latency import LatencyTracker
from pipeline.steps import draw_overlay
from ports.camera import CameraPort
from ports.clock import ClockPort
from ports.inference import InferencePort
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
        colors: List[Tuple[int, int, int]] | None = None,
    ) -> None:
        self._camera = camera
        self._inference = inference
        self._ui = ui
        self._alarm_runtime = alarm_runtime
        self._tracker = latency_tracker
        self._clock = clock
        self._colors = colors or np.random.randint(0, 255, size=(100, 3)).tolist()
        self._frame_index = 0

    def tick(self) -> bool:
        """Process one frame.  Returns False when the camera stream ends."""
        t0 = self._clock.perf_counter()

        ok, frame = self._camera.read_frame()
        t1 = self._clock.perf_counter()
        if not ok or frame is None:
            return False

        result = self._inference.predict(frame)
        t2 = self._clock.perf_counter()

        overlay = draw_overlay(frame, result, self._colors)
        t3 = self._clock.perf_counter()

        packet = FramePacket(frame=frame, index=self._frame_index, timestamp_ns=int(t0 * 1e9))
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

    def change_model(self, path: str) -> None:
        self._inference.change_model(path)

    def shutdown(self) -> None:
        self._alarm_runtime.shutdown()
        self._tracker.stop()
        self._tracker.save_log()
        self._camera.close()
