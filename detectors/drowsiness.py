"""
DrowsinessDetector — mediapipe_sleeping.py 알고리즘을 클래스로 래핑
경로 A: 얼굴 보임 → EAR 기반 졸음 판단
경로 B: 얼굴 안 보임 → Pose pitch 기반 고개 숙임 지속 판단
"""
import cv2
import mediapipe as mp
import numpy as np
import time

from .base import BaseDetector, Signal

# ─────────────────────────────────────────────────────────────
#  상수
# ─────────────────────────────────────────────────────────────
_EAR_THRESH_DOWN_INIT = 0.13
_EAR_THRESH_UP_INIT   = 0.15
_EAR_CONSEC_FRAMES    = 30
_DEEP_EAR_THRESH_INIT = _EAR_THRESH_UP_INIT

_CALIB_FRAMES      = 50
_CALIB_RATIO       = 0.40

_HEAD_DOWN_OFFSET     = 15.0
_DEEP_PITCH_OFFSET    = 22.0
_NO_FACE_SEC          = 2.0
_HEAD_DOWN_DROWSY_SEC = 3.0

# 눈 랜드마크 인덱스 (Face Mesh)
_EYE_LEFT  = [362, 385, 387, 263, 373, 380]
_EYE_RIGHT = [33,  160, 158, 133, 153, 144]


def _get_ear(landmarks, indices):
    p = [np.array([landmarks[i].x, landmarks[i].y]) for i in indices]
    v = np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])
    h = np.linalg.norm(p[0] - p[3])
    return v / (2.0 * h)


def _get_face_pitch(landmarks, h):
    nose_y = landmarks[1].y * h
    chin_y = landmarks[152].y * h
    fore_y = landmarks[10].y * h
    face_h = chin_y - fore_y
    if face_h < 1:
        return 0.0
    ratio = (nose_y - (fore_y + chin_y) / 2.0) / face_h
    return -ratio * 90.0


def _get_pose_pitch(landmarks, h):
    nose = landmarks[0]
    l_sh = landmarks[11]
    r_sh = landmarks[12]
    sh_y   = (l_sh.y + r_sh.y) / 2.0 * h
    nose_y = nose.y * h
    torso_h = max(sh_y - nose_y, 1)
    return -(1.0 - torso_h / (h * 0.25)) * 45.0


def _put(frame, text, pos, color=(255, 255, 255), scale=0.55, thickness=1):
    cv2.putText(frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness)


class DrowsinessDetector(BaseDetector):

    @property
    def name(self) -> str:
        return "drowsiness"

    def __init__(self):
        self.face_mesh = mp.solutions.face_mesh.FaceMesh(refine_landmarks=True)
        self.pose = mp.solutions.pose.Pose(
            model_complexity=0,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        # 캘리브레이션
        self.calib_ear_buf: list[float]   = []
        self.calib_pitch_buf: list[float] = []
        self.calib_done   = False
        self.normal_pitch = 0.0

        # EAR 임계값 (캘리브레이션 후 갱신)
        self.ear_thresh_up   = _EAR_THRESH_UP_INIT
        self.ear_thresh_down = _EAR_THRESH_DOWN_INIT
        self.deep_ear_thresh = _DEEP_EAR_THRESH_INIT

        # 상태
        self.counter       = 0
        self.alarm_on      = False
        self.last_face_time    = time.time()
        self.no_face_head_down = False
        self.head_down_start   = None
        self.head_down_drowsy  = False

        # HUD용 최신 값
        self._ear = 0.0
        self._pitch = 0.0
        self._pose_pitch = None
        self._ear_thresh = _EAR_THRESH_UP_INIT
        self._face_visible = False
        self._deep_mode = False

    # ── adaptive threshold ──────────────────────────────
    def _adaptive_ear_thresh(self, pitch):
        if pitch <= -15.0:
            return self.ear_thresh_down
        if pitch >= 10.0:
            return self.ear_thresh_up
        t = (pitch - (-15.0)) / (10.0 - (-15.0))
        t = t ** 2
        return self.ear_thresh_down + t * (self.ear_thresh_up - self.ear_thresh_down)

    # ── process_frame ───────────────────────────────────
    def process_frame(self, frame, now: float, rgb=None) -> list[Signal]:
        signals: list[Signal] = []
        h, w = frame.shape[:2]
        if rgb is None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        face_result = self.face_mesh.process(rgb)
        pose_result = self.pose.process(rgb)

        # Pose pitch
        self._pose_pitch = None
        if pose_result.pose_landmarks:
            self._pose_pitch = _get_pose_pitch(pose_result.pose_landmarks.landmark, h)

        # Face Mesh
        self._face_visible = face_result.multi_face_landmarks is not None
        self._ear = 0.0
        self._pitch = 0.0
        self._ear_thresh = self.ear_thresh_up
        self._deep_mode = False

        if self._face_visible:
            self.last_face_time = now
            self.no_face_head_down = False
            lm = face_result.multi_face_landmarks[0].landmark

            self._ear   = (_get_ear(lm, _EYE_LEFT) + _get_ear(lm, _EYE_RIGHT)) / 2.0
            self._pitch = _get_face_pitch(lm, h)
            self._ear_thresh = self._adaptive_ear_thresh(self._pitch)

            if not self.calib_done:
                # 캘리브레이션 수집
                self.calib_ear_buf.append(self._ear)
                self.calib_pitch_buf.append(self._pitch)
                if len(self.calib_ear_buf) >= _CALIB_FRAMES:
                    normal_ear = np.mean(self.calib_ear_buf)
                    self.normal_pitch = np.mean(self.calib_pitch_buf)
                    self.ear_thresh_up   = round(normal_ear * _CALIB_RATIO, 3)
                    self.ear_thresh_down = round(self.ear_thresh_up - 0.02, 3)
                    self.deep_ear_thresh = self.ear_thresh_up
                    self.calib_done = True
            else:
                # ── 경로 A ──
                if self._pitch < self.normal_pitch - _DEEP_PITCH_OFFSET:
                    self._ear_thresh = self.deep_ear_thresh
                    self._deep_mode = True

                if self._ear < self._ear_thresh:
                    self.counter += 1
                    if self.counter >= _EAR_CONSEC_FRAMES:
                        self.alarm_on = True
                else:
                    self.counter = 0
                    self.alarm_on = False
        else:
            if (now - self.last_face_time) > _NO_FACE_SEC:
                self.no_face_head_down = True

        # ── 경로 B ──
        head_down_now = False
        if not self._face_visible:
            if self._pose_pitch is not None:
                head_down_now = self._pose_pitch < self.normal_pitch - _HEAD_DOWN_OFFSET
            else:
                head_down_now = self.no_face_head_down

        if head_down_now:
            if self.head_down_start is None:
                self.head_down_start = now
            elif (now - self.head_down_start) >= _HEAD_DOWN_DROWSY_SEC:
                self.head_down_drowsy = True
        else:
            self.head_down_start = None
            self.head_down_drowsy = False

        # ── 시그널 생성 ──
        if self.alarm_on:
            signals.append(Signal(
                name="DROWSINESS", source=self.name, level=0.9,
                detail="EAR low sustained", timestamp=now,
            ))
        if self.head_down_drowsy:
            signals.append(Signal(
                name="DROWSINESS", source=self.name, level=0.8,
                detail="Head down sustained", timestamp=now,
            ))

        return signals

    # ── HUD ──────────────────────────────────────────────
    def draw_hud(self, frame) -> None:
        h, w = frame.shape[:2]

        if not self.calib_done:
            n = len(self.calib_ear_buf)
            _put(frame, f"[Sleep] Calibrating {n}/{_CALIB_FRAMES}",
                 (10, 30), (0, 200, 200), 0.55)
            return

        if self._face_visible:
            _put(frame, f"EAR:{self._ear:.2f} TH:{self._ear_thresh:.2f}",
                 (10, 30), (0, 0, 0))
            _put(frame, f"Pitch:{self._pitch:.1f}", (10, 50), (0, 255, 255))
            if self._deep_mode:
                _put(frame, "Deep-down mode", (200, 30), (100, 180, 255))
        else:
            _put(frame, "Face not visible", (10, 30), (100, 100, 255))

        down_sec = (time.time() - self.head_down_start) if self.head_down_start else 0.0
        _put(frame, f"Down:{down_sec:.1f}/{_HEAD_DOWN_DROWSY_SEC}s",
             (10, 70), (180, 180, 255))
        if self._pose_pitch is not None:
            _put(frame, f"PosePitch:{self._pose_pitch:.1f}", (200, 70), (180, 255, 180))

    # ── 정리 ──────────────────────────────────────────────
    def release(self):
        self.pose.close()
        self.face_mesh.close()
