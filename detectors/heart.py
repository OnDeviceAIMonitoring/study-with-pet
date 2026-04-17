"""
HeartDetector — heart_recog.py 알고리즘을 클래스로 래핑
양손 검지+엄지 모양을 분석해 큰 하트 제스처를 감지하고 HEART 시그널을 반환
"""
import cv2
import math
import mediapipe as mp
import numpy as np

from .base import BaseDetector, Signal

# ─────────────────────────────────────────────────────────────
#  상수
# ─────────────────────────────────────────────────────────────
_BUFFER_SIZE     = 7    # 히스토리 버퍼 (Jitter 방지)
_MAJORITY_RATIO  = 0.6  # 버퍼 내 과반수 기준

_DIST_THRESH     = 0.08  # 검지/엄지 끝 거리 (정규화)
_ANGLE_THRESH    = 150   # 검지 굽힘 각도 상한 (작을수록 더 구부러짐)


def _put(frame, text, pos, color=(255, 255, 255), scale=0.55, thickness=1):
    cv2.putText(frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)


class HeartDetector(BaseDetector):

    @property
    def name(self) -> str:
        return "heart"

    def __init__(self):
        self.hands = mp.solutions.hands.Hands(
            max_num_hands=2,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._mp_draw = mp.solutions.drawing_utils

        # 히스토리 (Jitter 방지)
        self._history: list[bool] = []

        # HUD용
        self._detected   = False
        self._hand_count = 0

        # # 너무 느리면 추가하기 - 프레임 스킵 (Hands 추론은 매 N프레임에 1회)
        # self._skip_n      = 3   # 3프레임에 1번 추론
        # self._frame_count = 0
        # self._last_signals: list[Signal] = []

    # ── 각도 계산 ──────────────────────────────────────
    @staticmethod
    def _get_angle(p1, p2, p3) -> float:
        v1 = np.array([p1.x - p2.x, p1.y - p2.y])
        v2 = np.array([p3.x - p2.x, p3.y - p2.y])
        u1 = v1 / (np.linalg.norm(v1) + 1e-6)
        u2 = v2 / (np.linalg.norm(v2) + 1e-6)
        return float(np.degrees(np.arccos(np.clip(np.dot(u1, u2), -1.0, 1.0))))

    # ── 하트 판별 ──────────────────────────────────────
    def _is_big_heart(self, multi_hand_landmarks) -> bool:
        if len(multi_hand_landmarks) < 2:
            return self._update_history(False)

        h1 = multi_hand_landmarks[0].landmark
        h2 = multi_hand_landmarks[1].landmark

        dist_index = math.dist([h1[8].x, h1[8].y], [h2[8].x, h2[8].y])
        dist_thumb = math.dist([h1[4].x, h1[4].y], [h2[4].x, h2[4].y])

        angle_h1 = self._get_angle(h1[8], h1[6], h1[5])
        angle_h2 = self._get_angle(h2[8], h2[6], h2[5])

        thumb_cross = h1[4].y > h1[3].y and h2[4].y > h2[3].y

        is_dist_ok = dist_index < _DIST_THRESH and dist_thumb < _DIST_THRESH
        is_curved  = angle_h1 < _ANGLE_THRESH and angle_h2 < _ANGLE_THRESH

        return self._update_history(is_dist_ok and is_curved and thumb_cross)

    def _update_history(self, detected: bool) -> bool:
        self._history.append(detected)
        if len(self._history) > _BUFFER_SIZE:
            self._history.pop(0)
        return sum(self._history) / len(self._history) > _MAJORITY_RATIO

    # ── process_frame ───────────────────────────────────
    def process_frame(self, frame, now: float, rgb=None) -> list[Signal]:
        # 너무 느리면 추가하기
        # self._frame_count += 1
        # # 스킵 프레임: 추론 생략하고 마지막 결과 재사용
        # if self._frame_count % self._skip_n != 0:
        #     return self._last_signals

        signals: list[Signal] = []
        if rgb is None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.hands.process(rgb)

        self._hand_count = len(result.multi_hand_landmarks) if result.multi_hand_landmarks else 0
        self._detected   = False

        if result.multi_hand_landmarks:
            if self._is_big_heart(result.multi_hand_landmarks):
                self._detected = True
                signals.append(Signal(
                    name="HEART",
                    source=self.name,
                    level=1.0,
                    detail="Big heart gesture detected",
                    timestamp=now,
                ))

        self._last_signals = signals
        return signals

    # ── HUD ──────────────────────────────────────────────
    def draw_hud(self, frame) -> None:
        h, w = frame.shape[:2]
        hands_text = f"Hands: {self._hand_count}"
        _put(frame, f"[Heart] {hands_text}", (w - 200, 30), (200, 200, 200))
        # if self._detected:
        #     cv2.putText(frame, "BIG HEART!", (w // 2 - 120, h // 2),
        #                 cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 80, 255), 3)

    # ── 정리 ──────────────────────────────────────────────
    def release(self):
        self.hands.close()
