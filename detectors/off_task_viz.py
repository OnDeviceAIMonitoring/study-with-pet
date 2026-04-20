"""
딴 짓 (Off-Task) 감지기 시각화 모듈
draw_hud()에서 호출되며, config의 visualization 옵션으로 개별 켜기/끄기 가능
"""
import cv2
import numpy as np
import time


def draw_off_task_bar(frame, status, runtime):
    """좌측 하단에 딴 짓 감지 상태 바 표시 (fidget 바와 유사한 레이아웃)"""
    h, w = frame.shape[:2]
    y0 = h - 190  # fidget 바(h-120) 위쪽에 배치

    _put = lambda text, pos, color, scale=0.5, thick=1: cv2.putText(
        frame, text, pos, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)

    # ── 핸드폰 감지 바 ──────────────────────────────────
    phone_hit = status.get("phone_hit_count", 0)
    phone_thresh = status.get("phone_hit_threshold", 3)
    phone_alert = status.get("phone_alert", False)
    phone_ratio = min(phone_hit / max(phone_thresh, 1), 1.5)
    phone_bar_w = int(min(phone_ratio / 1.5, 1.0) * 200)
    phone_color = (0, 255, 0) if not phone_alert else (0, 0, 255)
    cv2.rectangle(frame, (10, y0), (10 + phone_bar_w, y0 + 12), phone_color, -1)
    cv2.rectangle(frame, (10, y0), (210, y0 + 12), (150, 150, 150), 1)
    # 임계선
    tx_phone = int((1.0 / 1.5) * 200) + 10
    cv2.line(frame, (tx_phone, y0 - 2), (tx_phone, y0 + 14), (0, 0, 255), 2)
    _put(f"Phone:{phone_hit}/{phone_thresh} "
         f"({status.get('phone_window_sec', 5.0):.0f}s)",
         (10, y0 + 26), (200, 200, 200), 0.42)

    # ── 고개 방향(Yaw) 감지 바 / 캘리브레이션 진행 바 ────
    y1 = y0 + 34
    calib_state = status.get("calibration_state", "off")
    if calib_state not in ("done", "off"):
        # 캘리브레이션 진행 중 — 프로그레스 바 표시
        calib_elapsed = status.get("calibration_elapsed", 0.0)
        calib_duration = max(status.get("calibration_duration", 5.0), 0.1)
        calib_ratio = min(calib_elapsed / calib_duration, 1.0)
        calib_bar_w = int(calib_ratio * 200)
        calib_color = (255, 180, 0)  # 주황/노랑
        cv2.rectangle(frame, (10, y1), (10 + calib_bar_w, y1 + 12),
                      calib_color, -1)
        cv2.rectangle(frame, (10, y1), (210, y1 + 12), (150, 150, 150), 1)
        _put(f"Calibrating... {calib_elapsed:.1f}/{calib_duration:.0f}s",
             (10, y1 + 26), (255, 220, 100), 0.42)
    else:
        # 캘리브레이션 완료 또는 비활성 — 기존 Yaw 바
        yaw_hit = status.get("yaw_hit_count", 0)
        yaw_thresh = status.get("yaw_hit_threshold", 3)
        yaw_alert = status.get("yaw_alert", False)
        yaw_ratio = min(yaw_hit / max(yaw_thresh, 1), 1.5)
        yaw_bar_w = int(min(yaw_ratio / 1.5, 1.0) * 200)
        yaw_color = (0, 255, 0) if not yaw_alert else (0, 0, 255)
        cv2.rectangle(frame, (10, y1), (10 + yaw_bar_w, y1 + 12),
                      yaw_color, -1)
        cv2.rectangle(frame, (10, y1), (210, y1 + 12), (150, 150, 150), 1)
        tx_yaw = int((1.0 / 1.5) * 200) + 10
        cv2.line(frame, (tx_yaw, y1 - 2), (tx_yaw, y1 + 14), (0, 0, 255), 2)
        _put(f"Yaw:{yaw_hit}/{yaw_thresh} "
             f"({status.get('yaw_window_sec', 5.0):.0f}s)",
             (10, y1 + 26), (200, 200, 200), 0.42)

    # # ── 최종 상태 --> Signal로 따로 보내주는 것으로 대체 ──────────────────────
    # y2 = y1 + 34
    # final = "CONCENTRATING" if status["is_concentrating"] else "DISTRACTED"
    # fc = (0, 255, 0) if status["is_concentrating"] else (0, 0, 255)
    # _put(f"[OffTask] {final}", (w-110, y2 + 42), fc, 0.5, 2)


def draw_off_task_ui(frame, status, cfg, viz_cfg):
    """오른쪽 패널에 Off-Task 상태 정보 표시"""
    h, w = frame.shape[:2]

    panel_alpha = float(viz_cfg.get("ui_panel_alpha", 0.42))
    panel_w = int(w * float(viz_cfg.get("ui_panel_width_ratio", 0.5)))
    panel_h = int(h * float(viz_cfg.get("ui_panel_height_ratio", 0.65)))

    x0 = w - panel_w - 10
    y0 = 10
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + panel_w, y0 + panel_h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, panel_alpha, frame, 1.0 - panel_alpha, 0, frame)

    ok = (0, 255, 0)
    alert = (0, 0, 255)
    tx = x0 + 10
    dy = 24
    ty = y0 + 20

    def _put(text, color, scale=0.5, thick=1):
        nonlocal ty
        cv2.putText(frame, text, (tx, ty),
                    cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick)
        ty += dy

    _put(f"Phone: {status['phone_alert']} ({status['phone_hit_count']}/{status['phone_hit_threshold']})",
         alert if status["phone_alert"] else ok, 0.5, 2)
    _put(f"Head: {'Out' if status['yaw_alert'] else 'OK'} ({status['yaw_hit_count']}/{status['yaw_hit_threshold']})",
         alert if status["yaw_alert"] else ok, 0.5, 2)
    _put(f"Hands: {'No' if status['status_no_hands'] else 'Yes'}",
         alert if status["status_no_hands"] else ok, 0.5, 2)
    _put(f"TrackerOut: {status['status_tracker_out']} ({status['tracker_out_sec']:.1f}s)",
         alert if status["status_tracker_out"] else ok, 0.5, 2)

    dy = 20
    _put(f"HandVis: {status['has_hand_visible']}  Start: {status['study_started']}",
         alert if status["status_no_hands"] else ok, 0.42)
    _put(f"Smile+Talk: {status['status_smile_talking']} "
         f"(S:{status['smile_ratio']:.1f}, T:{status['mouth_open_ratio']:.2f})",
         alert if status["status_smile_talking"] else ok, 0.42)
    _put(f"TalkDet: {status['smile_talk_detect_sec']:.1f}s/"
         f"{status['smile_talk_window_sec']:.1f}s Stdev:{status['talk_stdev']:.3f}",
         alert if status["status_smile_talking"] else ok, 0.42)
    _put(f"Tracker: {'OK' if status['tracker_matched'] else 'Pred'} "
         f"Lost:{status['tracker_lost_frames']}",
         alert if status["tracker_lost_frames"] > 0 else ok, 0.42)
    _put(f"TrackStd: {status['tracker_history_std']:.4f}",
         alert if status["tracker_history_std"] > 0.21 else ok, 0.42)
    _put(f"Calib: {status['calibration_state']}", ok, 0.42)

    # Yaw 정보
    def _yaw_deg(yaw):
        return f"{yaw * 90.0:.1f}" if yaw is not None else "-"

    _put(f"Yaw(c):{_yaw_deg(status.get('yaw_from_calib'))} "
         f"Yaw(mp):{_yaw_deg(status.get('mediapipe_yaw'))}",
         alert if status["status_yaw_out"] else (255, 255, 0), 0.42)

    # 최종 판단
    dy = 26
    final = "CONCENTRATING" if status["is_concentrating"] else "DISTRACTED"
    fc = ok if status["is_concentrating"] else alert
    _put(final, fc, 0.6, 2)


def draw_off_task_phone_boxes(frame, boxes, cfg=None):
    """감지된 객체 바운딩 박스 그리기"""
    label_id_to_name = None
    if cfg is not None:
        label_map_cfg = cfg.get("model", {}).get("phone_labels")
        if isinstance(label_map_cfg, dict):
            label_id_to_name = {}
            for k, v in label_map_cfg.items():
                try:
                    label_id_to_name[int(k)] = str(v)
                except (TypeError, ValueError):
                    continue

    for det in boxes:
        if len(det) == 6:
            x1, y1, x2, y2, score, class_id = det
        else:
            x1, y1, x2, y2, score = det
            class_id = None
        label = "Object"
        if label_id_to_name and class_id is not None:
            label = label_id_to_name.get(class_id, str(class_id))
        elif class_id is not None:
            label = str(class_id)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(frame, f"{label} {score:.2f}", (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)


def draw_off_task_landmarks(frame, mp_results, mp_holistic,
                            mp_drawing, mp_drawing_styles):
    """MediaPipe Holistic 랜드마크 그리기"""
    if mp_results.face_landmarks:
        mp_drawing.draw_landmarks(
            frame, mp_results.face_landmarks,
            mp_holistic.FACEMESH_TESSELATION,
            landmark_drawing_spec=None,
            connection_drawing_spec=(
                mp_drawing_styles.get_default_face_mesh_tesselation_style()))
        mp_drawing.draw_landmarks(
            frame, mp_results.face_landmarks,
            mp_holistic.FACEMESH_CONTOURS,
            landmark_drawing_spec=None,
            connection_drawing_spec=(
                mp_drawing_styles.get_default_face_mesh_contours_style()))
    if mp_results.left_hand_landmarks:
        mp_drawing.draw_landmarks(
            frame, mp_results.left_hand_landmarks,
            mp_holistic.HAND_CONNECTIONS,
            mp_drawing_styles.get_default_hand_landmarks_style(),
            mp_drawing_styles.get_default_hand_connections_style())
    if mp_results.right_hand_landmarks:
        mp_drawing.draw_landmarks(
            frame, mp_results.right_hand_landmarks,
            mp_holistic.HAND_CONNECTIONS,
            mp_drawing_styles.get_default_hand_landmarks_style(),
            mp_drawing_styles.get_default_hand_connections_style())
    if mp_results.pose_landmarks:
        mp_drawing.draw_landmarks(
            frame, mp_results.pose_landmarks,
            mp_holistic.POSE_CONNECTIONS,
            landmark_drawing_spec=(
                mp_drawing_styles.get_default_pose_landmarks_style()))


def _clip_point(pt):
    return min(max(pt[0], 0.0), 1.0), min(max(pt[1], 0.0), 1.0)


def draw_off_task_tracker_history(frame, runtime, tracker_result):
    """얼굴 트래커 히스토리 궤적 그리기"""
    h, w = frame.shape[:2]
    tracker = runtime["tracker"]
    n = len(tracker["history"])
    if n < 2:
        return

    overlay = frame.copy()
    for i in range(1, n):
        pt1, out1 = tracker["history"][i - 1]
        pt2, out2 = tracker["history"][i]
        if out1:
            pt1 = _clip_point(pt1)
        if out2:
            pt2 = _clip_point(pt2)
        x1, y1 = int(pt1[0] * w), int(pt1[1] * h)
        x2, y2 = int(pt2[0] * w), int(pt2[1] * h)
        color = (255, 0, 0) if not out2 else (0, 0, 255)
        cv2.line(overlay, (x1, y1), (x2, y2), color, 2)
        cv2.circle(overlay, (x2, y2), 4, color, -1)
    cv2.addWeighted(overlay, 0.5, frame, 0.5, 0, frame)

    pt, is_out = tracker["history"][-1]
    if is_out:
        pt = _clip_point(pt)
    x, y = int(pt[0] * w), int(pt[1] * h)
    color = (255, 0, 0) if not is_out else (0, 0, 255)
    if is_out:
        cv2.circle(frame, (x, y), 14, color, 2)
    else:
        cv2.circle(frame, (x, y), 14, color, -1)
        cv2.circle(frame, (x, y), 14, (255, 255, 255), 2)
