"""Smoke detection with the project's YOLOv8 model (best.pt)."""

import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

SMOKE_LABEL = "smoke"

# Box colours in BGR. "nonsmoke" is the model's class for smoke look-alikes (fog, cloud, haze).
BOX_COLORS = {"smoke": (40, 40, 230), "nonsmoke": (150, 150, 150)}


@dataclass
class Detection:
    label: str
    confidence: float
    box: list[int]  # x1, y1, x2, y2 in pixels of the original image


@dataclass
class DetectionResult:
    detections: list[Detection]
    annotated: np.ndarray  # BGR image with boxes drawn
    inference_ms: float

    @property
    def smoke(self) -> list[Detection]:
        return [d for d in self.detections if d.label == SMOKE_LABEL]

    @property
    def smoke_detected(self) -> bool:
        return bool(self.smoke)

    @property
    def max_smoke_confidence(self) -> float:
        return max((d.confidence for d in self.smoke), default=0.0)


class SmokeDetector:
    def __init__(self, model_path: Path, ultralytics_dir: Path):
        # Import the professor's ultralytics fork (it adds the WIoU v4 loss) instead of a pip-installed
        # ultralytics, so best.pt is loaded with the same code it was trained with.
        sys.path.insert(0, str(ultralytics_dir))
        import ultralytics
        from ultralytics import YOLO

        self.ultralytics_path = Path(ultralytics.__file__).parent
        self.model = YOLO(str(model_path))
        self.labels = self.model.names  # {0: "smoke", 1: "nonsmoke"}
        self._lock = threading.Lock()  # one predict at a time; YOLO models aren't thread-safe

    def detect(self, frame: np.ndarray, conf: float) -> DetectionResult:
        """Detect smoke in one BGR frame: an uploaded photo for now, a video frame later."""
        start = time.perf_counter()
        with self._lock:
            result = self.model.predict(frame, conf=conf, verbose=False)[0]
        inference_ms = (time.perf_counter() - start) * 1000

        detections = [
            Detection(
                label=self.labels[int(cls)],
                confidence=round(float(score), 3),
                box=[int(v) for v in xyxy],
            )
            for xyxy, cls, score in zip(result.boxes.xyxy.tolist(), result.boxes.cls, result.boxes.conf)
        ]
        detections.sort(key=lambda d: (d.label != SMOKE_LABEL, -d.confidence))
        return DetectionResult(detections, draw_detections(frame, detections), round(inference_ms, 1))


def draw_detections(frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
    image = frame.copy()
    scale = max(image.shape[:2]) / 1000  # keep lines and text readable on any image size
    thickness = max(2, round(3 * scale))
    font_scale = max(0.5, 0.8 * scale)

    # Draw nonsmoke first so smoke boxes stay on top.
    for d in sorted(detections, key=lambda d: d.label == SMOKE_LABEL):
        color = BOX_COLORS.get(d.label, (0, 200, 255))
        x1, y1, x2, y2 = d.box
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)

        text = f"{d.label} {d.confidence:.0%}"
        (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        ty = y1 if y1 - th - baseline > 0 else y1 + th + baseline  # move label inside the box at the top edge
        cv2.rectangle(image, (x1, ty - th - baseline), (x1 + tw + 8, ty), color, -1)
        cv2.putText(image, text, (x1 + 4, ty - baseline // 2), cv2.FONT_HERSHEY_SIMPLEX,
                    font_scale, (255, 255, 255), thickness, cv2.LINE_AA)
    return image
