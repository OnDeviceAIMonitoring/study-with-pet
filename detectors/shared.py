"""
SharedMediaPipe — 모든 Detector가 공유하는 MediaPipe Holistic 인스턴스

매 프레임당 1번만 추론하고 결과를 각 Detector에 전달하여
중복 추론(Face×2, Pose×3, Hands×2 → Holistic×1)을 제거합니다.
"""
import mediapipe as mp


class SharedMediaPipe:
    """
    MediaPipe Holistic을 한 번만 실행하고, 결과를 모든 Detector에 제공.

    Holistic은 내부적으로 Face Mesh + Pose + Hands를 모두 포함하므로
    개별 모델을 따로 돌릴 필요가 없습니다.

    refine_face_landmarks=True로 478 포인트(아이리스 포함)를 제공하여
    DrowsinessDetector의 EAR 계산에도 대응합니다.
    """

    def __init__(
        self,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        refine_face_landmarks=True,
        model_complexity=1,
    ):
        self._mp_holistic = mp.solutions.holistic
        self._mp_drawing = mp.solutions.drawing_utils
        self._mp_drawing_styles = mp.solutions.drawing_styles

        self.holistic = self._mp_holistic.Holistic(
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
            refine_face_landmarks=refine_face_landmarks,
            model_complexity=model_complexity,
        )

        # 최신 추론 결과
        self.results = None
        self.rgb = None

    # ── 매 프레임 1회 호출 ────────────────────────────────
    def process(self, rgb):
        """RGB 프레임을 받아 Holistic 추론 1회 실행, 결과를 저장·반환"""
        rgb.flags.writeable = False
        self.results = self.holistic.process(rgb)
        rgb.flags.writeable = True
        self.rgb = rgb
        return self.results

    # ── 편의 프로퍼티 ─────────────────────────────────────
    @property
    def face_landmarks(self):
        return self.results.face_landmarks if self.results else None

    @property
    def pose_landmarks(self):
        return self.results.pose_landmarks if self.results else None

    @property
    def left_hand_landmarks(self):
        return self.results.left_hand_landmarks if self.results else None

    @property
    def right_hand_landmarks(self):
        return self.results.right_hand_landmarks if self.results else None

    @property
    def mp_holistic(self):
        """mp.solutions.holistic 모듈 참조 (PoseLandmark enum 등에 필요)"""
        return self._mp_holistic

    @property
    def mp_drawing(self):
        return self._mp_drawing

    @property
    def mp_drawing_styles(self):
        return self._mp_drawing_styles

    def release(self):
        self.holistic.close()
