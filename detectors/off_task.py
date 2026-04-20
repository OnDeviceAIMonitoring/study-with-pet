"""
OffTaskDetector — Off-Task-Detector 알고리즘을 BaseDetector 클래스로 래핑

MediaPipe Holistic + YOLO ONNX 기반 복합 딴 짓 (Off-Task) 감지:
  - 핸드폰/물체 사용 감지 (YOLO ONNX)
  - 머리 방향(Yaw) 이탈 감지
    - Calibration 필요: 초기 3초간 머리 방향 중앙값을 기준으로 설정
  - 손 가시성 / 책상 위 손 감지
  - 얼굴 트래커 화면 이탈 감지 (Kalman Filter 기반 Tracking)
  - 웃음·대화 감지
"""
import importlib
import json
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from .base import BaseDetector, Signal

# ─────────────────────────────────────────────────────────────
#  경로 상수
# ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "off_task.json"
_MODELS_DIR = _PROJECT_ROOT / "models"

# ─────────────────────────────────────────────────────────────
#  얼굴 기준 랜드마크 인덱스
# ─────────────────────────────────────────────────────────────
_FACE_NOSE_IDX = 1
_FACE_LEFT_EYE_OUTER_IDX = 33
_FACE_RIGHT_EYE_OUTER_IDX = 263
_MOUTH_LEFT_IDX = 61
_MOUTH_RIGHT_IDX = 291
_MOUTH_UPPER_IDX = 13
_MOUTH_LOWER_IDX = 14


# ─────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────
def _load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────────────────────
#  얼굴/손 분석 헬퍼
# ─────────────────────────────────────────────────────────────
def _get_face_head_yaw(face_landmarks):
    nose = face_landmarks.landmark[_FACE_NOSE_IDX]
    left_eye = face_landmarks.landmark[_FACE_LEFT_EYE_OUTER_IDX]
    right_eye = face_landmarks.landmark[_FACE_RIGHT_EYE_OUTER_IDX]
    eye_center_x = (left_eye.x + right_eye.x) / 2.0
    eye_width = abs(right_eye.x - left_eye.x)
    if eye_width < 1e-6:
        return 0.0
    return (nose.x - eye_center_x) / eye_width


def _check_hands_on_desk(pose_landmarks, mp_holistic, desk_y_threshold):
    if not pose_landmarks:
        return False
    left_wrist = pose_landmarks.landmark[mp_holistic.PoseLandmark.LEFT_WRIST]
    right_wrist = pose_landmarks.landmark[mp_holistic.PoseLandmark.RIGHT_WRIST]
    return (left_wrist.y > desk_y_threshold) or (right_wrist.y > desk_y_threshold)


def _has_any_visible_hand(mp_results, pose_landmarks, mp_holistic, min_visibility=0.35):
    if mp_results.left_hand_landmarks or mp_results.right_hand_landmarks:
        return True
    if not pose_landmarks:
        return False
    left_wrist = pose_landmarks.landmark[mp_holistic.PoseLandmark.LEFT_WRIST]
    right_wrist = pose_landmarks.landmark[mp_holistic.PoseLandmark.RIGHT_WRIST]
    return (left_wrist.visibility > min_visibility) or (right_wrist.visibility > min_visibility)


def _estimate_smile_talk_features(face_landmarks):
    if not face_landmarks:
        return 0.0, 0.0
    lm = face_landmarks.landmark
    mouth_w = abs(lm[_MOUTH_RIGHT_IDX].x - lm[_MOUTH_LEFT_IDX].x)
    mouth_h = abs(lm[_MOUTH_LOWER_IDX].y - lm[_MOUTH_UPPER_IDX].y)
    eye_w = abs(lm[_FACE_RIGHT_EYE_OUTER_IDX].x - lm[_FACE_LEFT_EYE_OUTER_IDX].x)
    mouth_h_safe = max(mouth_h, 1e-6)
    eye_w_safe = max(eye_w, 1e-6)
    smile_ratio = mouth_w / mouth_h_safe
    mouth_open_ratio = mouth_h / eye_w_safe
    return float(smile_ratio), float(mouth_open_ratio)


def _extract_face_measurement(face_landmarks, pose_landmarks=None, mp_holistic=None):
    if face_landmarks:
        xs = [lm.x for lm in face_landmarks.landmark]
        ys = [lm.y for lm in face_landmarks.landmark]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        area = max(1e-6, max_x - min_x) * max(1e-6, max_y - min_y)
        cx = 0.5 * (min_x + max_x)
        cy = 0.5 * (min_y + max_y)
        return {
            "center": np.array([cx, cy], dtype=np.float32),
            "bbox": (min_x, min_y, max_x, max_y),
            "area": float(area),
        }
    if pose_landmarks is not None and mp_holistic is not None:
        idxs = []
        for name in ["NOSE", "LEFT_EYE", "RIGHT_EYE", "LEFT_EAR", "RIGHT_EAR"]:
            idx = getattr(mp_holistic.PoseLandmark, name, None)
            if idx is not None:
                idxs.append(idx)
        points = []
        for idx in idxs:
            lm = pose_landmarks.landmark[idx]
            if lm.visibility >= 0.6:
                points.append((lm.x, lm.y))
        if len(points) < 2:
            return None
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        area = max(1e-6, max_x - min_x) * max(1e-6, max_y - min_y)
        cx = 0.5 * (min_x + max_x)
        cy = 0.5 * (min_y + max_y)
        return {
            "center": np.array([cx, cy], dtype=np.float32),
            "bbox": (min_x, min_y, max_x, max_y),
            "area": float(area),
        }
    return None


def _point_box_distance(px, py, box):
    x1, y1, x2, y2 = box[:4]
    dx = max(x1 - px, 0, px - x2)
    dy = max(y1 - py, 0, py - y2)
    return float(np.hypot(dx, dy))


def _is_object_held_by_hand(
    boxes, mp_results, pose_landmarks, mp_holistic,
    frame_shape, max_distance_ratio=0.05, lower_region_threshold=0.8,
):
    if not boxes:
        return False
    h, w = frame_shape[:2]
    hand_points = []
    for hand in [mp_results.left_hand_landmarks, mp_results.right_hand_landmarks]:
        if hand:
            for lm in hand.landmark:
                hand_points.append((lm.x * w, lm.y * h))
    if pose_landmarks:
        for idx in [mp_holistic.PoseLandmark.LEFT_WRIST, mp_holistic.PoseLandmark.RIGHT_WRIST]:
            wrist = pose_landmarks.landmark[idx]
            if wrist.visibility > 0.3:
                hand_points.append((wrist.x * w, wrist.y * h))
    if not hand_points:
        for box in boxes:
            y2_norm = float(box[3]) / max(float(h), 1.0)
            if y2_norm >= lower_region_threshold:
                return False
        return False
    max_distance = max(w, h) * max_distance_ratio
    for box in boxes:
        for px, py in hand_points:
            if _point_box_distance(px, py, box) <= max_distance:
                return True
    return False


# ─────────────────────────────────────────────────────────────
#  Kalman Filter 기반 트래커
# ─────────────────────────────────────────────────────────────
def _make_kalman_filter(dt):
    kf = cv2.KalmanFilter(4, 2)
    kf.measurementMatrix = np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
    kf.processNoiseCov = np.eye(4, dtype=np.float32) * 1e-3
    kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * 1e-2
    kf.errorCovPost = np.eye(4, dtype=np.float32)
    _update_kalman_dt(kf, dt)
    return kf


def _update_kalman_dt(kf, dt):
    kf.transitionMatrix = np.array(
        [[1.0, 0.0, dt, 0.0], [0.0, 1.0, 0.0, dt],
         [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]], dtype=np.float32)


def _limit_measurement_speed(prev_center, measured_center, dt, max_speed_per_second):
    if prev_center is None or dt <= 1e-6:
        return measured_center
    displacement = measured_center - prev_center
    dist_norm = float(np.linalg.norm(displacement))
    max_dist = max_speed_per_second * dt
    if dist_norm <= max_dist or dist_norm <= 1e-9:
        return measured_center
    return prev_center + (displacement / dist_norm) * max_dist


def _reset_tracker(runtime, measurement, dt):
    tracker = runtime["tracker"]
    kf = _make_kalman_filter(max(dt, 1.0 / max(runtime["fps"], 1.0)))
    cx, cy = measurement["center"]
    kf.statePost = np.array([[cx], [cy], [0.0], [0.0]], dtype=np.float32)
    tracker["kalman"] = kf
    tracker["initialized"] = True
    tracker["tracked_center"] = np.array([cx, cy], dtype=np.float32)
    tracker["tracked_area"] = measurement["area"]
    tracker["size_ema"] = measurement["area"]
    tracker["lost_frames"] = 0


def _update_face_tracker(runtime, measurement, dt, cfg):
    tcfg = cfg.get("tracking", {})
    tracker = runtime["tracker"]
    max_speed = tcfg.get("max_face_speed_screen_per_second", 2.5)
    max_match_dist = tcfg.get("max_match_distance_norm", 0.25)
    min_area_ratio = tcfg.get("min_area_ratio", 0.6)
    max_area_ratio = tcfg.get("max_area_ratio", 1.7)
    size_ema_alpha = tcfg.get("size_ema_alpha", 0.2)

    if not tracker["initialized"]:
        if measurement is None:
            return None
        _reset_tracker(runtime, measurement, dt)
        return {
            "center": tracker["tracked_center"],
            "area": tracker["tracked_area"],
            "matched": True,
            "valid_detection": True,
        }

    kf = tracker["kalman"]
    _update_kalman_dt(kf, max(dt, 1e-3))
    pred = kf.predict()
    pred_center = np.array([float(pred[0, 0]), float(pred[1, 0])], dtype=np.float32)
    matched = False
    valid_detection = measurement is not None

    if measurement is not None:
        meas_center = measurement["center"]
        meas_area = measurement["area"]
        size_ref = max(tracker["size_ema"], 1e-6)
        area_ratio = meas_area / size_ref
        dist_to_pred = float(np.linalg.norm(meas_center - pred_center))
        area_ok = (min_area_ratio <= area_ratio <= max_area_ratio)
        distance_ok = dist_to_pred <= max_match_dist
        matched = area_ok and distance_ok

        if matched:
            capped = _limit_measurement_speed(
                tracker["tracked_center"], meas_center, dt, max_speed)
            kf.correct(capped.reshape(2, 1).astype(np.float32))
            post = kf.statePost
            tracker["tracked_center"] = np.array(
                [float(post[0, 0]), float(post[1, 0])], dtype=np.float32)
            tracker["tracked_area"] = meas_area
            tracker["size_ema"] = (
                (1.0 - size_ema_alpha) * tracker["size_ema"]
                + size_ema_alpha * meas_area
            )
            tracker["lost_frames"] = 0
        else:
            _reset_tracker(runtime, measurement, dt)
            matched = True
    else:
        tracker["tracked_center"] = pred_center
        tracker["lost_frames"] += 1

    return {
        "center": tracker["tracked_center"],
        "area": tracker["tracked_area"],
        "matched": matched,
        "valid_detection": valid_detection,
    }


def _compute_tracker_out_of_screen(tracker_result):
    if tracker_result is None:
        return False
    center = tracker_result["center"]
    x, y = float(center[0]), float(center[1])
    return x < 0.0 or x > 1.0 or y < 0.0 or y > 1.0


def _maybe_update_calibration(runtime, status, tracker_result):
    calib = runtime["calibration"]
    if not calib["enabled"] or calib["done"]:
        return
    now_ts = time.perf_counter()
    if not calib["started"]:
        calib["started"] = True
        calib["start_ts"] = now_ts
    if tracker_result is not None:
        calib["center_x_samples"].append(float(tracker_result["center"][0]))
    if "yaw_samples" not in calib:
        calib["yaw_samples"] = []
    if status.get("mediapipe_yaw") is not None:
        calib["yaw_samples"].append(status["mediapipe_yaw"])
    elapsed = now_ts - calib["start_ts"]
    if elapsed < calib["duration_seconds"]:
        return
    if len(calib["center_x_samples"]) < calib["min_samples"]:
        return
    calib["done"] = True
    if calib["yaw_samples"]:
        runtime["yaw_calib"] = float(np.mean(calib["yaw_samples"]))


# ─────────────────────────────────────────────────────────────
#  ONNX 객체(핸드폰) 감지
# ─────────────────────────────────────────────────────────────
def _build_phone_label_metadata(model_cfg):
    label_map_cfg = model_cfg.get("phone_labels")
    if isinstance(label_map_cfg, dict) and label_map_cfg:
        id_to_name = {}
        for k, v in label_map_cfg.items():
            try:
                id_to_name[int(k)] = str(v)
            except (TypeError, ValueError):
                continue
            if id_to_name:
                pass
        if id_to_name:
            return set(id_to_name.keys()), id_to_name
    label_ids = list(model_cfg.get("phone_label_ids", [67]))
    label_names = list(model_cfg.get("phone_label_names", []))
    id_to_name = {}
    for class_id, class_name in zip(label_ids, label_names):
        try:
            id_to_name[int(class_id)] = str(class_name)
        except (TypeError, ValueError):
            continue
    label_id_set = {int(v) for v in label_ids if isinstance(v, (int, np.integer))}
    if not label_id_set:
        label_id_set = {67}
    return label_id_set, id_to_name


def _load_phone_detector(model_cfg):
    phone_label_ids, phone_label_map = _build_phone_label_metadata(model_cfg)
    model_path = _MODELS_DIR / model_cfg.get("phone_onnx_path", "yolo26n.onnx")
    try:
        ort = importlib.import_module("onnxruntime")
    except ImportError:
        print("[off_task] onnxruntime not installed. Phone detection disabled.")
        return None
    if not model_path.exists():
        print(f"[off_task] ONNX model not found at {model_path}. Phone detection disabled.")
        return None
    try:
        session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"])
    except Exception as exc:
        print(f"[off_task] Failed to initialize ONNX runtime: {exc}")
        return None
    input_info = session.get_inputs()[0]
    input_name = input_info.name
    shape = input_info.shape
    input_h = int(shape[2]) if len(shape) >= 4 and isinstance(shape[2], int) else 640
    input_w = int(shape[3]) if len(shape) >= 4 and isinstance(shape[3], int) else 640
    return {
        "session": session,
        "input_name": input_name,
        "output_names": [o.name for o in session.get_outputs()],
        "input_width": input_w,
        "input_height": input_h,
        "score_threshold": float(model_cfg.get("phone_score_threshold", 0.45)),
        "phone_label_ids": phone_label_ids,
        "phone_label_map": phone_label_map,
        "available": True,
    }


def _preprocess_onnx_frame(frame, detector):
    resized = cv2.resize(frame, (detector["input_width"], detector["input_height"]))
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    chw = np.transpose(rgb, (2, 0, 1)).astype(np.float32) / 255.0
    return np.expand_dims(chw, axis=0)


def _nms_detections(detections, iou_threshold=0.45):
    if not detections:
        return []
    boxes = []
    scores = []
    for x1, y1, x2, y2, score, _cid in detections:
        boxes.append([int(x1), int(y1), int(max(1, x2 - x1)), int(max(1, y2 - y1))])
        scores.append(float(score))
    keep = cv2.dnn.NMSBoxes(boxes, scores, score_threshold=0.0, nms_threshold=iou_threshold)
    if keep is None or len(keep) == 0:
        return []
    idxs = [int(i[0]) if isinstance(i, (list, tuple, np.ndarray)) else int(i) for i in keep]
    return [detections[i] for i in idxs]


def _parse_onnx_outputs(raw_outputs, frame_shape, detector):
    h, w = frame_shape[:2]
    score_threshold = detector["score_threshold"]
    phone_label_ids = detector["phone_label_ids"]
    if not raw_outputs:
        return False, []
    output = np.array(raw_outputs[0])
    if output.ndim == 3 and output.shape[0] == 1:
        output = output[0]
    candidates = []

    # Case A: [N, 6] — x1, y1, x2, y2, score, class_id
    if output.ndim == 2 and output.shape[1] >= 6:
        for det in output:
            x1, y1, x2, y2, score, class_id = det[:6]
            class_id = int(class_id)
            if score < score_threshold or class_id not in phone_label_ids:
                continue
            if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.5:
                x1, y1, x2, y2 = x1 * w, y1 * h, x2 * w, y2 * h
            x1, y1 = max(0, min(w - 1, int(x1))), max(0, min(h - 1, int(y1)))
            x2, y2 = max(0, min(w - 1, int(x2))), max(0, min(h - 1, int(y2)))
            if x2 <= x1 or y2 <= y1:
                continue
            candidates.append((x1, y1, x2, y2, float(score), class_id))

    # Case B: YOLO format [C, N] or [N, C]
    elif output.ndim == 2:
        preds = output
        if preds.shape[0] < preds.shape[1] and preds.shape[0] <= 128:
            preds = preds.T
        if preds.shape[1] >= 6:
            in_w = float(detector["input_width"])
            in_h = float(detector["input_height"])
            sx = w / max(in_w, 1.0)
            sy = h / max(in_h, 1.0)
            for row in preds:
                x, y, bw, bh = row[:4]
                class_scores = row[4:]
                if class_scores.size == 0:
                    continue
                class_id = int(np.argmax(class_scores))
                score = float(class_scores[class_id])
                if score < score_threshold or class_id not in phone_label_ids:
                    continue
                if max(abs(x), abs(y), abs(bw), abs(bh)) <= 1.5:
                    cx, cy, ww, hh = x * w, y * h, bw * w, bh * h
                else:
                    cx, cy, ww, hh = x * sx, y * sy, bw * sx, bh * sy
                x1 = max(0, min(w - 1, int(cx - ww / 2.0)))
                y1 = max(0, min(h - 1, int(cy - hh / 2.0)))
                x2 = max(0, min(w - 1, int(cx + ww / 2.0)))
                y2 = max(0, min(h - 1, int(cy + hh / 2.0)))
                if x2 <= x1 or y2 <= y1:
                    continue
                candidates.append((x1, y1, x2, y2, score, class_id))

    detections = _nms_detections(candidates)
    return len(detections) > 0, detections


def _detect_phone(frame, detector):
    session = detector["session"]
    input_name = detector["input_name"]
    output_names = detector["output_names"]
    input_tensor = _preprocess_onnx_frame(frame, detector)
    raw_outputs = session.run(output_names, {input_name: input_tensor})
    return _parse_onnx_outputs(raw_outputs, frame.shape, detector)


# ─────────────────────────────────────────────────────────────
#  OffTaskDetector
# ─────────────────────────────────────────────────────────────
class OffTaskDetector(BaseDetector):

    @property
    def name(self) -> str:
        return "off_task"

    def __init__(self, config_path=None):
        self.cfg = _load_config(config_path or _DEFAULT_CONFIG_PATH)

        # Phone detector (ONNX)
        features = self.cfg.get("features", {})
        self.phone_detector = None
        if features.get("enable_phone_detection", True):
            self.phone_detector = _load_phone_detector(self.cfg.get("model", {}))

        # Async YOLO executor
        self._executor = None
        self._yolo_future = None
        self._yolo_last_result = (False, [])
        if self.phone_detector is not None:
            self._executor = ThreadPoolExecutor(max_workers=1)

        # Runtime state
        self._fps = 30.0
        self._last_ts = None
        self.runtime = self._build_runtime_state()

        # HUD 상태 (draw_hud에서 사용)
        self._status = None
        self._tracker_result = None
        self._shared = None  # SharedMediaPipe 참조 (draw_hud에서 사용)

    def _build_runtime_state(self):
        cfg = self.cfg
        return {
            "tracker_out_counter": 0,
            "face_missing_counter": 0,
            "no_hand_counter": 0,
            "smile_talk_counter": 0,
            "yaw_out_counter": 0,
            "smile_talk_events": deque(),
            "talk_values": deque(),
            "study_started": False,
            "fps": self._fps,
            "frame_index": 0,
            "last_ts": time.perf_counter(),
            "active_thresholds": dict(cfg.get("thresholds", {})),
            "last_phone_detection": {
                "detected": False, "boxes": [], "available": False,
            },
            "calibration": {
                "enabled": cfg.get("calibration", {}).get("enabled", False),
                "duration_seconds": cfg.get("calibration", {}).get("duration_seconds", 3.0),
                "min_samples": cfg.get("calibration", {}).get("min_samples", 20),
                "started": False,
                "done": False,
                "start_ts": 0.0,
                "center_x_samples": [],
            },
            "tracker": {
                "kalman": None,
                "initialized": False,
                "lost_frames": 0,
                "tracked_center": None,
                "tracked_area": 0.0,
                "size_ema": 0.0,
                "history": [],
                "history_maxlen": 50,
            },
            "yaw_calib": None,
            "phone_events": deque(),
            "yaw_events": deque(),
        }

    # ── process_frame ───────────────────────────────────
    def process_frame(self, frame, now: float, shared=None) -> list[Signal]:
        signals: list[Signal] = []

        # dt 계산
        if self._last_ts is not None:
            dt = max(1e-3, now - self._last_ts)
        else:
            dt = 1.0 / 30.0
        self._last_ts = now
        self._fps = 1.0 / max(dt, 1e-6)
        self.runtime["fps"] = self._fps
        self.runtime["frame_index"] += 1

        h, w = frame.shape[:2]
        self._shared = shared

        face_landmarks = shared.face_landmarks if shared else None
        pose_landmarks = shared.pose_landmarks if shared else None
        thresholds = self.runtime["active_thresholds"]
        features = self.cfg.get("features", {})
        model_cfg = self.cfg.get("model", {})
        tracking_cfg = self.cfg.get("tracking", {})

        # ── 핸드폰 감지 (비동기 YOLO) ────────────────────
        phone_detected, phone_boxes = self._run_phone_detection(
            frame, features, model_cfg)

        # Hand contact 필터
        requires_hand_contact = bool(model_cfg.get("phone_requires_hand_contact", True))
        hand_contact_distance = float(tracking_cfg.get("object_hand_max_distance_ratio", 0.05))
        lower_region_thresh = float(tracking_cfg.get("object_bottom_ignore_threshold", 0.8))
        if phone_detected and requires_hand_contact:
            phone_detected = _is_object_held_by_hand(
                phone_boxes, shared.results, pose_landmarks,
                shared.mp_holistic, frame.shape,
                max_distance_ratio=hand_contact_distance,
                lower_region_threshold=lower_region_thresh)

        # ── Status dict ───────────────────────────────────
        status = {
            "phone_detected": phone_detected,
            "phone_boxes": phone_boxes,
            "phone_alert": False,
            "phone_hit_count": 0,
            "phone_hit_threshold": int(
                thresholds.get("phone_hit_threshold", 3)),
            "phone_window_sec": float(
                thresholds.get("phone_window_seconds", 5.0)),
            "status_no_hands": False,
            "status_face_missing": False,
            "status_tracker_out": False,
            "status_smile_talking": False,
            "status_yaw_out": False,
            "yaw_alert": False,
            "yaw_hit_count": 0,
            "yaw_hit_threshold": int(
                thresholds.get("yaw_hit_threshold", 3)),
            "yaw_window_sec": float(
                thresholds.get("yaw_window_seconds", 5.0)),
            "has_hand_visible": False,
            "study_started": self.runtime["study_started"],
            "tracker_out_sec": 0.0,
            "smile_ratio": 0.0,
            "mouth_open_ratio": 0.0,
            "talk_stdev": 0.0,
            "smile_talk_detect_sec": 0.0,
            "smile_talk_window_sec": float(
                thresholds.get("smile_talk_window_seconds", 2.0)),
            "tracker_history_std": 0.0,
            "tracker_matched": False,
            "tracker_lost_frames": self.runtime["tracker"]["lost_frames"],
            "calibration_state": "off",
            "is_concentrating": True,
            "mediapipe_yaw": None,
            "yaw_from_calib": None,
        }

        # ── 핸드폰 감지 슬라이딩 윈도우 ──────────────────
        phone_window_sec = status["phone_window_sec"]
        phone_hit_thresh = status["phone_hit_threshold"]
        now_ts = time.perf_counter()
        self.runtime["phone_events"].append(
            (now_ts, 1 if phone_detected else 0))
        cutoff_phone = now_ts - phone_window_sec
        while (self.runtime["phone_events"]
               and self.runtime["phone_events"][0][0] < cutoff_phone):
            self.runtime["phone_events"].popleft()
        phone_hit_count = int(
            sum(v for _, v in self.runtime["phone_events"]))
        status["phone_hit_count"] = phone_hit_count
        status["phone_alert"] = phone_hit_count >= phone_hit_thresh

        # ── 트래커 업데이트 ───────────────────────────────
        measurement = _extract_face_measurement(
            face_landmarks, pose_landmarks, shared.mp_holistic)
        tracker_result = _update_face_tracker(self.runtime, measurement, dt, self.cfg)
        if tracker_result is not None:
            status["tracker_matched"] = tracker_result["matched"]
            status["tracker_lost_frames"] = self.runtime["tracker"]["lost_frames"]

        # ── Smile/Talk 감지 ───────────────────────────────
        smile_talk_window_sec = status["smile_talk_window_sec"]
        smile_talk_req_frames = int(
            max(1, thresholds.get("smile_talk_frames", 5)))
        talk_stdev_thresh = float(
            thresholds.get("talking_stdev_threshold", 0.01))

        if face_landmarks:
            self.runtime["face_missing_counter"] = 0
            if features.get("enable_smile_talking_detection", True):
                smile_r, mouth_r = _estimate_smile_talk_features(face_landmarks)
                status["smile_ratio"] = smile_r
                status["mouth_open_ratio"] = mouth_r
                is_smile = smile_r <= thresholds.get("smile_ratio_threshold", 8.0)
                is_talking = mouth_r >= thresholds.get(
                    "talking_open_ratio_threshold", 0.06)
                self.runtime["smile_talk_events"].append(
                    (now_ts, 1 if (is_smile and is_talking) else 0))
                self.runtime["talk_values"].append((now_ts, float(mouth_r)))
        else:
            if features.get("enable_face_missing_detection", True):
                self.runtime["face_missing_counter"] += 1

        cutoff = now_ts - smile_talk_window_sec
        while (self.runtime["smile_talk_events"]
               and self.runtime["smile_talk_events"][0][0] < cutoff):
            self.runtime["smile_talk_events"].popleft()
        while (self.runtime["talk_values"]
               and self.runtime["talk_values"][0][0] < cutoff):
            self.runtime["talk_values"].popleft()

        hit_count = int(sum(v for _, v in self.runtime["smile_talk_events"]))
        talk_series = [v for _, v in self.runtime["talk_values"]]
        talk_stdev = (float(np.sqrt(np.var(talk_series)))
                      if len(talk_series) >= 2 else 0.0)
        status["talk_stdev"] = talk_stdev
        status["smile_talk_detect_sec"] = hit_count / max(self._fps, 1)
        status["status_smile_talking"] = (
            hit_count >= smile_talk_req_frames
            and talk_stdev >= talk_stdev_thresh
        )

        # ── 트래커 화면 이탈 ──────────────────────────────
        is_tracker_out = _compute_tracker_out_of_screen(tracker_result)
        if is_tracker_out:
            self.runtime["tracker_out_counter"] += 1
        else:
            self.runtime["tracker_out_counter"] = 0
        tracker_out_frames = int(max(
            1, thresholds.get("tracker_out_seconds", 0.6) * self._fps))
        status["status_tracker_out"] = (
            self.runtime["tracker_out_counter"] >= tracker_out_frames)
        status["tracker_out_sec"] = (
            self.runtime["tracker_out_counter"] / max(self._fps, 1))

        # ── 얼굴 미감지 ──────────────────────────────────
        if features.get("enable_face_missing_detection", True):
            fm_frames = int(max(
                1, thresholds.get("face_missing_seconds", 1.2) * self._fps))
            status["status_face_missing"] = (
                self.runtime["face_missing_counter"] >= fm_frames)

        # ── Yaw 감지 ─────────────────────────────────────
        mediapipe_yaw = None
        if face_landmarks:
            mediapipe_yaw = _get_face_head_yaw(face_landmarks)
        status["mediapipe_yaw"] = mediapipe_yaw

        calib_yaw = self.runtime.get("yaw_calib")
        if calib_yaw is not None and mediapipe_yaw is not None:
            status["yaw_from_calib"] = mediapipe_yaw - calib_yaw

        yaw_max_deg = float(thresholds.get("yaw_max_degrees", 30.0))
        yaw_window_sec = status["yaw_window_sec"]
        yaw_hit_thresh = status["yaw_hit_threshold"]
        yaw_deg = status["yaw_from_calib"]
        yaw_is_out = (yaw_deg is not None
                      and abs(yaw_deg * 90.0) > yaw_max_deg)
        self.runtime["yaw_events"].append(
            (now_ts, 1 if yaw_is_out else 0))
        cutoff_yaw = now_ts - yaw_window_sec
        while (self.runtime["yaw_events"]
               and self.runtime["yaw_events"][0][0] < cutoff_yaw):
            self.runtime["yaw_events"].popleft()
        yaw_hit_count = int(
            sum(v for _, v in self.runtime["yaw_events"]))
        status["yaw_hit_count"] = yaw_hit_count
        status["yaw_alert"] = yaw_hit_count >= yaw_hit_thresh
        status["status_yaw_out"] = status["yaw_alert"]

        # ── 손 가시성 ─────────────────────────────────────
        if features.get("enable_hands_on_desk_detection", True):
            min_hand_vis = float(
                thresholds.get("min_pose_visibility_for_hand", 0.35))
            has_hand = _has_any_visible_hand(
                shared.results, pose_landmarks, shared.mp_holistic,
                min_hand_vis)
            status["has_hand_visible"] = has_hand

            if not self.runtime["study_started"] and has_hand:
                self.runtime["study_started"] = True
            status["study_started"] = self.runtime["study_started"]

            no_hand_frames = int(max(
                1, thresholds.get("no_hand_seconds", 0.8) * self._fps))
            if self.runtime["study_started"]:
                if has_hand:
                    self.runtime["no_hand_counter"] = 0
                else:
                    self.runtime["no_hand_counter"] += 1
                status["status_no_hands"] = (
                    self.runtime["no_hand_counter"] >= no_hand_frames)
            else:
                status["status_no_hands"] = True

            if pose_landmarks:
                if not _check_hands_on_desk(
                        pose_landmarks, shared.mp_holistic,
                        thresholds.get("desk_y_threshold", 0.6)):
                    status["status_no_hands"] = True
        else:
            # 손 감지 비활성화 — 항상 study_started, no_hands=False
            if not self.runtime["study_started"]:
                self.runtime["study_started"] = True
            status["study_started"] = True
            status["has_hand_visible"] = True
            status["status_no_hands"] = False

        # ── 트래커 히스토리 분석 ──────────────────────────
        hist_pts = [
            np.asarray(c, dtype=np.float32)
            for c, _ in self.runtime["tracker"].get("history", [])
            if c is not None
        ]
        if len(hist_pts) >= 2:
            arr = np.vstack(hist_pts)
            status["tracker_history_std"] = float(np.sqrt(
                np.var(arr[-10:, 0]) + np.var(arr[-10:, 1])))

        # ── 캘리브레이션 업데이트 ─────────────────────────
        _maybe_update_calibration(self.runtime, status, tracker_result)
        calib = self.runtime["calibration"]
        if calib["enabled"]:
            if calib["done"]:
                status["calibration_state"] = "done"
                status["calibration_elapsed"] = calib["duration_seconds"]
                status["calibration_duration"] = calib["duration_seconds"]
            else:
                elapsed = (max(0.0, time.perf_counter() - calib["start_ts"])
                           if calib["started"] else 0.0)
                status["calibration_state"] = (
                    f"running {elapsed:.1f}/{calib['duration_seconds']:.1f}s")
                status["calibration_elapsed"] = elapsed
                status["calibration_duration"] = calib["duration_seconds"]

        # ── 트래커 히스토리 저장 (시각화용) ───────────────
        if (tracker_result is not None
                and tracker_result["center"] is not None):
            center = tracker_result["center"]
            is_out = _compute_tracker_out_of_screen(tracker_result)
            tracker = self.runtime["tracker"]
            tracker["history"].append((center.copy(), is_out))
            if len(tracker["history"]) > tracker["history_maxlen"]:
                tracker["history"] = tracker["history"][
                    -tracker["history_maxlen"]:]

        # ── 최종 판단 ────────────────────────────────────
        status["is_concentrating"] = not (
            (not status["study_started"])
            or status["status_no_hands"]
            or status["phone_alert"]
            or status["status_tracker_out"]
            or status["status_face_missing"]
            or status["status_smile_talking"]
            or status["status_yaw_out"]
        )

        self._status = status
        self._tracker_result = tracker_result

        # ── 시그널 생성 ──────────────────────────────────
        if not status["is_concentrating"]:
            reasons = []
            if not status["study_started"]:
                reasons.append("not_started")
            if status["phone_alert"]:
                reasons.append("phone")
            if status["status_yaw_out"]:
                reasons.append("yaw_out")
            if status["status_no_hands"]:
                reasons.append("no_hands")
            if status["status_tracker_out"]:
                reasons.append("tracker_out")
            if status["status_face_missing"]:
                reasons.append("face_missing")
            if status["status_smile_talking"]:
                reasons.append("smile_talking")
            signals.append(Signal(
                name="OFF_TASK", source=self.name, level=0.8,
                detail=", ".join(reasons), timestamp=now,
            ))

        return signals

    # ── 핸드폰 감지 내부 ─────────────────────────────────
    def _run_phone_detection(self, frame, features, model_cfg):
        phone_detected = False
        phone_boxes = []
        phone_interval = max(1, int(
            model_cfg.get("phone_detect_every_n_frames", 7)))
        phone_ready = (self.phone_detector is not None
                       and self.phone_detector.get("available", False))

        if not (features.get("enable_phone_detection", True) and phone_ready):
            self.runtime["last_phone_detection"] = {
                "detected": False, "boxes": [], "available": phone_ready}
            return False, []

        if self._executor is not None:
            if (self.runtime["frame_index"] - 1) % phone_interval == 0:
                if self._yolo_future is None or self._yolo_future.done():
                    if (self._yolo_future is not None
                            and self._yolo_future.done()):
                        try:
                            self._yolo_last_result = (
                                self._yolo_future.result())
                        except Exception:
                            self._yolo_last_result = (False, [])
                    self._yolo_future = self._executor.submit(
                        _detect_phone, frame.copy(), self.phone_detector)
            phone_detected, phone_boxes = self._yolo_last_result
        else:
            if (self.runtime["frame_index"] - 1) % phone_interval == 0:
                phone_detected, phone_boxes = _detect_phone(
                    frame, self.phone_detector)
            else:
                phone_detected = self.runtime[
                    "last_phone_detection"]["detected"]
                phone_boxes = self.runtime[
                    "last_phone_detection"]["boxes"]

        self.runtime["last_phone_detection"] = {
            "detected": phone_detected,
            "boxes": phone_boxes,
            "available": True,
        }
        return phone_detected, phone_boxes

    # ── HUD ──────────────────────────────────────────────
    def draw_hud(self, frame) -> None:
        if self._status is None:
            return
        viz_cfg = self.cfg.get("visualization", {})

        from .off_task_viz import (
            draw_off_task_ui, draw_off_task_phone_boxes,
            draw_off_task_landmarks, draw_off_task_tracker_history,
            draw_off_task_bar,
        )

        # 항상 표시: 좌측 하단 딴 짓 상태 바
        draw_off_task_bar(frame, self._status, self.runtime)

        if viz_cfg.get("draw_landmarks", True) and self._shared is not None:
            draw_off_task_landmarks(
                frame, self._shared.results, self._shared.mp_holistic,
                self._shared.mp_drawing, self._shared.mp_drawing_styles)

        if viz_cfg.get("draw_phone_boxes", True) and self._status.get("phone_boxes"):
            draw_off_task_phone_boxes(
                frame, self._status["phone_boxes"], self.cfg)

        if (viz_cfg.get("draw_tracker_history", True)
                and self._tracker_result is not None):
            draw_off_task_tracker_history(
                frame, self.runtime, self._tracker_result)

        if viz_cfg.get("draw_ui_panel", True):
            draw_off_task_ui(frame, self._status, self.cfg, viz_cfg)

    # ── 정리 ──────────────────────────────────────────────
    def release(self):
        if self._executor is not None:
            self._executor.shutdown(wait=False)
