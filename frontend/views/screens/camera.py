"""
카메라 슬라이드 및 카메라 제어 Mixin
- screen_camera : 개인 공부 카메라 화면 (PERSONAL_CAMERA)
- signal_hub detectors 통합: 카메라 프레임에서 시그널 감지 → 캐릭터 반응
"""
import os
import sys
import time
import threading

import cv2

from services.camera_signals import (
    DEFAULT_STYLE,
    SIGNAL_PRIORITY,
    SIGNAL_STYLES,
)

# ─────────────────────────────────────────────────────────────
#  detectors import (프로젝트 루트에서)
# ─────────────────────────────────────────────────────────────
_DETECTORS_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_DETECTORS_ROOT = os.path.abspath(_DETECTORS_ROOT)
if _DETECTORS_ROOT not in sys.path:
    sys.path.insert(0, _DETECTORS_ROOT)

try:
    from detectors import DrowsinessDetector, FidgetDetector, HeartDetector, Signal
    _DETECTORS_AVAILABLE = True
except ImportError:
    _DETECTORS_AVAILABLE = False
    print("[screen_camera] WARNING: detectors not found, signal detection disabled")

class CameraScreenMixin:

    def start_camera(self, camera_index: int = 0):
        if self.camera_running:
            return
        self.camera_running = True

        # ── 파이프라인 병렬 공유 상태 ─────────────────────────
        shared = {
            "frame": None,         # 최신 BGR 프레임
            "rgb":   None,         # 최신 RGB 프레임
            "frame_lock": threading.Lock(),
            "signals": {},         # {detector_name: [Signal, ...]}  각 detector의 최신 결과
            "signals_lock": threading.Lock(),
            "hud_frames": {},      # {detector_name: drawn_frame}  각 detector가 HUD 그린 사본 (참고용)
        }

        # ── 카메라 캡처 스레드 ────────────────────────────────
        def capture_loop():
            cap = cv2.VideoCapture(camera_index)
            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH,
                        self.args.canvas_width - self.args.left_reserved_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.args.canvas_height)
            except Exception:
                pass
            while self.camera_running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.03)
                    continue
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                with shared["frame_lock"]:
                    shared["frame"] = frame
                    shared["rgb"]   = rgb
            try:
                cap.release()
            except Exception:
                pass

        # ── detector 워커 스레드 (각 detector 독립 실행) ──────
        def detector_worker(det):
            """하나의 detector를 독립 스레드에서 반복 실행"""
            name = det.name
            while self.camera_running:
                with shared["frame_lock"]:
                    frame = shared["frame"]
                    rgb   = shared["rgb"]
                if frame is None:
                    time.sleep(0.02)
                    continue
                try:
                    now = time.time()
                    sigs = det.process_frame(frame.copy(), now, rgb.copy())
                    with shared["signals_lock"]:
                        shared["signals"][name] = sigs
                except Exception:
                    import traceback
                    traceback.print_exc()
                # detector마다 자기 속도로 돌림 (sleep 최소화)
                time.sleep(0.005)
            try:
                det.release()
            except Exception:
                pass

        # ── 렌더 스레드 (HUD + visual effects + 프레임 전달) ──────
        def render_loop(detectors_list):
            import math
            import random
            import numpy as np

            prev_time = time.time()

            # warning
            _flash_phase = 0.0       # 사인파 위상 (0 ~ 2π)
            _FLASH_SPEED = 5.0       # 초당 라디안 (빠를수록 빠른 깜박임)
            _FLASH_MAX_A = 0.50      # 최대 불투명도

            # happy heart
            _hearts: list = []
            _HEART_COLORS = [
                (60,  20, 220),   # BGR: 빨강
                (180, 105, 255),  # BGR: 분홍
                (147, 20, 255),   # BGR: 핫핑크
                (100, 0,  200),   # BGR: 진빨강
                (200, 80, 255),   # BGR: 연분홍
            ]

            def _spawn_hearts(w: int, h: int, n: int = 2):
                for _ in range(n):
                    _hearts.append({
                        "x":     random.uniform(0.05, 0.95) * w,
                        "y":     random.uniform(-0.15, 0.0) * h,
                        "vy":    random.uniform(0.035, 0.075) * h,
                        "size":  random.randint(14, 34),
                        "alpha": random.uniform(0.55, 1.0),
                        "color": random.choice(_HEART_COLORS),
                    })

            def _draw_heart(dst, cx: int, cy: int, size: int, color: tuple, alpha: float):
                """하트 그리기"""
                t  = np.linspace(0, 2 * math.pi, 64)
                xs = 16 * np.sin(t) ** 3
                ys = -(13 * np.cos(t) - 5 * np.cos(2*t)
                       - 2 * np.cos(3*t) - np.cos(4*t))
                sc = size / 16.0
                pts = np.array(
                    [[int(cx + x * sc), int(cy + y * sc)] for x, y in zip(xs, ys)],
                    dtype=np.int32,
                )
                ov = dst.copy()
                cv2.fillPoly(ov, [pts], color)
                cv2.addWeighted(ov, alpha, dst, 1 - alpha, 0, dst)

            while self.camera_running:
                with shared["frame_lock"]:
                    frame = shared["frame"]
                if frame is None:
                    time.sleep(0.02)
                    continue

                frame = frame.copy()
                now   = time.time()
                dt    = now - prev_time
                fps   = 1.0 / max(dt, 1e-6)
                prev_time = now

                h_f, w_f = frame.shape[:2]

                # 모든 detector의 최신 signal 수집
                with shared["signals_lock"]:
                    all_signals = []
                    for sigs in shared["signals"].values():
                        all_signals.extend(sigs)

                # 우선순위 기준 최상위 시그널 결정
                top_signal = None
                if all_signals:
                    sig_names = set(s.name for s in all_signals)
                    for prio in SIGNAL_PRIORITY:
                        if prio in sig_names:
                            top_signal = prio
                            break
                    if not top_signal:
                        top_signal = all_signals[0].name

                # 각 detector HUD 그리기
                for det in detectors_list:
                    try:
                        det.draw_hud(frame)
                    except Exception:
                        pass

                # ──  warning effect ─────────
                is_warning = top_signal in ("DROWSINESS", "LOW_FOCUS")
                if is_warning:
                    _flash_phase = (_flash_phase + _FLASH_SPEED * dt) % (2 * math.pi)
                    alpha = _FLASH_MAX_A * (0.5 + 0.5 * math.sin(_flash_phase))

                    # 전체 화면 빨간 오버레이
                    red_ov = np.zeros_like(frame)
                    red_ov[:] = (0, 0, 200)          # BGR 빨강
                    cv2.addWeighted(red_ov, alpha * 0.5, frame, 1.0, 0, frame)

                    # 두꺼운 빨간 테두리 (비네트 효과)
                    bw = max(10, int(min(h_f, w_f) * 0.06))
                    border_ov = frame.copy()
                    cv2.rectangle(border_ov, (0, 0), (w_f - 1, h_f - 1),
                                  (0, 0, 255), bw * 3)
                    cv2.addWeighted(border_ov, alpha, frame, 1 - alpha, 0, frame)

                    # 경고 라벨 (중앙 상단)
                    label  = SIGNAL_STYLES.get(top_signal, DEFAULT_STYLE)["label"]
                    t_scale = 1.1
                    (tw, th), _ = cv2.getTextSize(
                        label, cv2.FONT_HERSHEY_SIMPLEX, t_scale, 3)
                    tx = (w_f - tw) // 2
                    ty = int(h_f * 0.15)
                    cv2.putText(frame, label, (tx + 2, ty + 2),
                                cv2.FONT_HERSHEY_SIMPLEX, t_scale, (0, 0, 0), 5)
                    pulse_r = int(180 + 75 * (0.5 + 0.5 * math.sin(_flash_phase)))
                    cv2.putText(frame, label, (tx, ty),
                                cv2.FONT_HERSHEY_SIMPLEX, t_scale,
                                (50, 50, pulse_r), 3)
                else:
                    _flash_phase = 0.0

                # ── happy heart effect ────────────────
                is_heart = (top_signal == "HEART")
                if is_heart and random.random() < 0.65:
                    _spawn_hearts(w_f, h_f, n=random.randint(1, 3))

                alive = []
                for hrt in _hearts:
                    hrt["y"] += hrt["vy"]
                    if hrt["y"] < h_f + hrt["size"] * 3:
                        alive.append(hrt)
                        _draw_heart(frame,
                                    int(hrt["x"]), int(hrt["y"]),
                                    hrt["size"], hrt["color"], hrt["alpha"])
                _hearts[:] = alive

                # FPS
                cv2.putText(frame, f"FPS:{fps:.1f}", (w_f - 110, 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

                # 시그널 → 캐릭터 애니메이션 전달
                with self._camera_signal_lock:
                    self._camera_current_signal = top_signal

                # 프레임 전달
                with self.lock:
                    self.latest_frame = frame
                time.sleep(0.01)

        # ── Thread  ───────────────────────────────────────
        # 1) camera capture
        self._capture_thread = threading.Thread(target=capture_loop, daemon=True)
        self._capture_thread.start()

        # 2) detector workers
        self._detector_threads = []
        detectors_list = []
        if _DETECTORS_AVAILABLE:
            try:
                detectors_list = [
                    DrowsinessDetector(),
                    FidgetDetector(),
                    HeartDetector(),
                ]
                print(f"[screen_camera] {len(detectors_list)} detectors initialized (parallel)")
            except Exception:
                import traceback
                traceback.print_exc()

        for det in detectors_list:
            t = threading.Thread(target=detector_worker, args=(det,), daemon=True)
            t.start()
            self._detector_threads.append(t)

        # 3) render thread
        self._render_thread = threading.Thread(
            target=render_loop, args=(detectors_list,), daemon=True)
        self._render_thread.start()

    def stop_camera(self):
        if not self.camera_running:
            return
        self.camera_running = False
        # 모든 스레드 종료 대기
        for t in getattr(self, '_detector_threads', []):
            t.join(timeout=1.0)
        self._detector_threads = []
        if hasattr(self, '_render_thread') and self._render_thread is not None:
            self._render_thread.join(timeout=1.0)
            self._render_thread = None
        if hasattr(self, '_capture_thread') and self._capture_thread is not None:
            self._capture_thread.join(timeout=1.0)
            self._capture_thread = None
        if self.camera_thread is not None:
            self.camera_thread.join(timeout=1.0)
            self.camera_thread = None
