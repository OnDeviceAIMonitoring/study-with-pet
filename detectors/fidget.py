"""
FidgetDetector — fidget_detector.py 알고리즘을 클래스로 래핑
상반신 키포인트 이동량 → burst 반복 → LOW_FOCUS 시그널
"""
import cv2
import mediapipe as mp
import numpy as np
import time
from collections import deque

from .base import BaseDetector, Signal

# ─────────────────────────────────────────────────────────────
#  상수
# ─────────────────────────────────────────────────────────────
_CALIB_SEC         = 5.0
_FIDGET_RATIO      = 4.0
_BURST_THRESH      = 5.0
_BURST_MIN_SEC     = 0.8
_BURST_GAP_SEC     = 1.5
_LONG_WINDOW_SEC   = 30.0
_BURST_COUNT_THRESH = 4
_SMOOTH_SEC        = 0.8

_TRACK_IDS = [0, 11, 12, 13, 14]
_CONNECTIONS = [(0, 11), (0, 12), (11, 12), (11, 13), (12, 14)]


def _put(frame, text, pos, color=(255, 255, 255), scale=0.55, thickness=1):
    cv2.putText(frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)


class FidgetDetector(BaseDetector):

    @property
    def name(self) -> str:
        return "fidget"

    def __init__(self):
        self.pose = mp.solutions.pose.Pose(
            model_complexity=0,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self.prev_pts = None

        # 캘리브레이션
        self.calib_start   = None
        self.calib_buf: list[float] = []
        self.calib_done    = False
        self.normal_energy = 1.0

        # burst 상태
        self.energy_window: deque  = deque()
        self.burst_active   = False
        self.burst_start    = None
        self.burst_cooldown = 0.0
        self.burst_times: deque    = deque()
        self.fidget_alert   = False

        # HUD용
        self._ratio      = 0.0
        self._is_moving  = False
        self._burst_count = 0

    # ── process_frame ───────────────────────────────────
    def process_frame(self, frame, now: float, rgb=None) -> list[Signal]:
        signals: list[Signal] = []
        h, w = frame.shape[:2]
        if rgb is None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.pose.process(rgb)

        energy = 0.0
        curr_pts = None

        if result.pose_landmarks:
            lm = result.pose_landmarks.landmark
            curr_pts = np.array(
                [[lm[i].x * w, lm[i].y * h] for i in _TRACK_IDS],
                dtype=np.float32,
            )
            if self.prev_pts is not None:
                energy = float(np.mean(np.linalg.norm(curr_pts - self.prev_pts, axis=1)))
        self.prev_pts = curr_pts

        # 캘리브레이션
        if not self.calib_done:
            if self.calib_start is None:
                self.calib_start = now
            if energy > 0:
                self.calib_buf.append(energy)
            if (now - self.calib_start) >= _CALIB_SEC and len(self.calib_buf) > 10:
                self.normal_energy = 3
                self.calib_done = True
            return signals

        # 스무딩
        self.energy_window.append((now, energy))
        while self.energy_window and (now - self.energy_window[0][0]) > _SMOOTH_SEC:
            self.energy_window.popleft()
        smooth = np.mean([e for _, e in self.energy_window]) if self.energy_window else 0.0
        self._ratio = smooth / self.normal_energy
        self._is_moving = self._ratio > _BURST_THRESH

        # burst 감지
        if self._is_moving:
            if not self.burst_active and now > self.burst_cooldown:
                self.burst_active = True
                self.burst_start = now
        else:
            if self.burst_active:
                if self.burst_start and (now - self.burst_start) >= _BURST_MIN_SEC:
                    self.burst_times.append(now)
                    self.burst_cooldown = now + _BURST_GAP_SEC
                self.burst_active = False

        while self.burst_times and (now - self.burst_times[0]) > _LONG_WINDOW_SEC:
            self.burst_times.popleft()

        self._burst_count = len(self.burst_times)
        self.fidget_alert = self._burst_count >= _BURST_COUNT_THRESH

        if self.fidget_alert:
            signals.append(Signal(
                name="LOW_FOCUS", source=self.name, level=0.7,
                detail=f"bursts={self._burst_count}/{_BURST_COUNT_THRESH} in {_LONG_WINDOW_SEC:.0f}s",
                timestamp=now,
            ))

        return signals

    # ── HUD ──────────────────────────────────────────────
    def draw_hud(self, frame) -> None:
        h, w = frame.shape[:2]
        # HUD y 오프셋 (하단 배치)
        y0 = h - 120

        if not self.calib_done:
            elapsed = (time.time() - self.calib_start) if self.calib_start else 0.0
            _put(frame, f"[Fidget] Calibrating {elapsed:.1f}/{_CALIB_SEC}s",
                 (10, y0), (0, 200, 200), 0.55)
            return

        # 에너지 바 (bar 전체 범위 = BURST_THRESH × 1.5 → 임계선이 2/3 지점)
        _BAR_SCALE = _BURST_THRESH * 2.0
        bar_w = int(min(self._ratio / _BAR_SCALE, 1.0) * 200)
        bar_color = (0, 255, 0) if not self._is_moving else (0, 150, 255)
        cv2.rectangle(frame, (10, y0), (10 + bar_w, y0 + 14), bar_color, -1)
        cv2.rectangle(frame, (10, y0), (210, y0 + 14), (150, 150, 150), 1)
        tx = int((_BURST_THRESH / _BAR_SCALE) * 200) + 10
        cv2.line(frame, (tx, y0 - 2), (tx, y0 + 16), (0, 0, 255), 2)

        _put(frame, f"Energy x{self._ratio:.1f}  Bursts:{self._burst_count}/{_BURST_COUNT_THRESH}",
             (10, y0 + 30), (200, 200, 200))

        # burst 타임라인
        tl_y = y0 + 40
        now = time.time()
        cv2.rectangle(frame, (10, tl_y), (210, tl_y + 6), (60, 60, 60), -1)
        for bt in self.burst_times:
            bx = int(10 + (1.0 - (now - bt) / _LONG_WINDOW_SEC) * 200)
            cv2.line(frame, (bx, tl_y), (bx, tl_y + 6), (0, 100, 255), 2)

    # ── 정리 ──────────────────────────────────────────────
    def release(self):
        self.pose.close()
