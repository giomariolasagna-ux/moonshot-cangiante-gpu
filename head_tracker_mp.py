import time
import cv2
import numpy as np
import mediapipe as mp
from dataclasses import dataclass
from typing import Tuple

@dataclass
class ViewerState:
    offset_x: float
    offset_y: float
    distance: float
    velocity: float
    stability: float
    time_centered: float

class HeadTrackerMP:
    def __init__(self, cam_index: int = 0):
        self.cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError(f\"Cannot open camera index {cam_index}\")

        # reduce CPU while keeping good tracking
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)

        self.mp_face = mp.solutions.face_detection.FaceDetection(model_selection=0, min_detection_confidence=0.6)

        self.prev = None
        self.prev_t = None
        self.centered_t0 = None
        self.time_centered = 0.0

        self.vel_ema = 0.0
        self.stab_ema = 1.0

    def read(self) -> Tuple[np.ndarray, ViewerState]:
        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError(\"Failed to read camera frame\")

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        res = self.mp_face.process(rgb)

        # Defaults: assume center
        cx, cy = w/2.0, h/2.0
        rel_area = 0.0

        if res.detections:
            det = res.detections[0]
            bb = det.location_data.relative_bounding_box
            # bounding box center (relative)
            bx = bb.xmin + bb.width/2.0
            by = bb.ymin + bb.height/2.0
            cx, cy = bx * w, by * h
            rel_area = float(np.clip(bb.width * bb.height, 0.0, 1.0))

        # normalized offsets [-1,1]
        offset_x = float((cx - w/2.0) / (w/2.0))
        offset_y = float((cy - h/2.0) / (h/2.0))

        # distance proxy 0..1 from bbox area (clamped)
        distance = float(np.clip(rel_area / 0.25, 0.0, 1.0))

        t = time.time()
        velocity = 0.0
        if self.prev is not None and self.prev_t is not None:
            dt = max(1e-3, t - self.prev_t)
            dx = (cx - self.prev[0]) / w
            dy = (cy - self.prev[1]) / h
            velocity = float(np.clip(np.sqrt(dx*dx + dy*dy) / dt * 0.10, 0.0, 1.0))

        self.prev = (cx, cy)
        self.prev_t = t

        # smoothing
        self.vel_ema = 0.85*self.vel_ema + 0.15*velocity
        stab = float(np.clip(1.0 - self.vel_ema, 0.0, 1.0))
        self.stab_ema = 0.85*self.stab_ema + 0.15*stab

        centered = (abs(offset_x) < 0.07) and (abs(offset_y) < 0.07) and (self.stab_ema > 0.75)
        if centered:
            if self.centered_t0 is None:
                self.centered_t0 = t
            self.time_centered = float(t - self.centered_t0)
        else:
            self.centered_t0 = None
            self.time_centered = 0.0

        vs = ViewerState(
            offset_x=offset_x,
            offset_y=offset_y,
            distance=distance,
            velocity=float(self.vel_ema),
            stability=float(self.stab_ema),
            time_centered=self.time_centered
        )
        return frame, vs

    def release(self):
        try:
            self.cap.release()
        except Exception:
            pass
