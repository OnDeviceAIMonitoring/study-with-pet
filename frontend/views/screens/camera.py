"""
카메라 슬라이드 및 카메라 제어 Mixin
- screen_camera : 개인 공부 카메라 화면 (PERSONAL_CAMERA)
- signal_hub detectors 통합: 카메라 프레임에서 시그널 감지 -> 캐릭터 반응
"""

import os
import sys
import time
import threading

import cv2

from services.camera_signals import DEFAULT_STYLE, SIGNAL_PRIORITY, SIGNAL_STYLES

# -------------------------------------------------------------
# detectors import (프로젝트 루트에서)
# -------------------------------------------------------------
_DETECTORS_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_DETECTORS_ROOT = os.path.abspath(_DETECTORS_ROOT)
if _DETECTORS_ROOT not in sys.path:
    sys.path.insert(0, _DETECTORS_ROOT)

try:
    from detectors import DrowsinessDetector, FidgetDetector, OffTaskDetector, HeartDetector, Signal, SharedMediaPipe
    _DETECTORS_AVAILABLE = True
except ImportError:
    _DETECTORS_AVAILABLE = False
    print("[screen_camera] WARNING: detectors not found, signal detection disabled")


class CameraScreenMixin:

    def start_camera(self, camera_index: int = 0):
        if self.camera_state.running:
            return
        self.camera_state.running = True
        # 기존 호환성 유지
        self.camera_running = True

        # 공유 상태
        shared = {
            "frame": None,
            "frame_lock": threading.Lock(),
        }

        # SharedMediaPipe (Holistic 1회 추론 공유)
        shared_mp = SharedMediaPipe() if _DETECTORS_AVAILABLE else None
        self._shared_mp = shared_mp

        # 카메라 캡처 스레드
        def capture_loop():
            cap = cv2.VideoCapture(camera_index)
            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.args.canvas_width - self.args.left_reserved_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.args.canvas_height)
            except Exception:
                pass
            while self.camera_state.running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.03)
                    continue
                with shared["frame_lock"]:
                    shared["frame"] = frame
            try:
                cap.release()
            except Exception:
                pass

        # 처리 스레드 (순차: shared_mp -> detectors -> render)
        def process_loop(detectors_list):
            import math
            import random
            import numpy as np

            prev_time = time.time()

            # 캘리브레이션 페이즈
            _CALIB_MIN_SEC = 8.0
            _INTRO_SEC = 3.0
            _COUNTDOWN_SEC = 5.0
            _calib_start = time.time()
            _calibrating = True

            def _all_detectors_calibrated(dets) -> bool:
                for det in dets:
                    if hasattr(det, "calib_done") and not det.calib_done:
                        return False
                    if hasattr(det, "runtime"):
                        calib = det.runtime.get("calibration", {})
                        if calib.get("enabled", True) and not calib.get("done", False):
                            return False
                return True

            def _draw_calib_overlay(frm, elapsed: float):
                h, w = frm.shape[:2]
                dark = frm.copy()
                dark[:] = (20, 20, 20)
                cv2.addWeighted(dark, 0.45, frm, 0.55, 0, frm)

                if elapsed < _INTRO_SEC:
                    msgs = ["Look at the camera for 5 seconds."]
                    sizes = [0.75]
                    cols = [(220, 220, 220)]
                    ths = [2]
                elif elapsed < _CALIB_MIN_SEC:
                    remaining = _CALIB_MIN_SEC - elapsed
                    count = int(remaining) + 1
                    msgs = ["Calibrating...", f"{count}"]
                    sizes = [0.7, 2.5]
                    cols = [(180, 180, 180), (80, 200, 80)]
                    ths = [2, 4]
                else:
                    msgs = ["Almost ready..."]
                    sizes = [0.8]
                    cols = [(80, 200, 80)]
                    ths = [2]

                total_h = 0
                dims = []
                for txt, sc, th in zip(msgs, sizes, ths):
                    (tw, th2), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, sc, th)
                    dims.append((tw, th2))
                    total_h += th2 + 20
                y = (h - total_h) // 2
                for txt, sc, col, th, (tw, th2) in zip(msgs, sizes, cols, ths, dims):
                    cv2.putText(frm, txt, ((w - tw) // 2, y + th2), cv2.FONT_HERSHEY_SIMPLEX, sc, col, th)
                    y += th2 + 20

                bar_w = int(w * 0.6)
                bx = (w - bar_w) // 2
                by = h - 50
                if elapsed < _INTRO_SEC:
                    progress = 0.0
                else:
                    progress = min(1.0, (elapsed - _INTRO_SEC) / _COUNTDOWN_SEC)
                filled = int(bar_w * progress)
                cv2.rectangle(frm, (bx, by), (bx + bar_w, by + 12), (60, 60, 60), -1)
                cv2.rectangle(frm, (bx, by), (bx + filled, by + 12), (80, 200, 80), -1)

            _flash_phase = 0.0
            _FLASH_SPEED = 5.0
            _FLASH_MAX_A = 0.50

            _hearts = []
            _HEART_COLORS = [
                (60, 20, 220),
                (180, 105, 255),
                (147, 20, 255),
                (100, 0, 200),
                (200, 80, 255),
            ]

            def _spawn_hearts(w: int, h: int, n: int = 2):
                for _ in range(n):
                    _hearts.append({
                        "x": random.uniform(0.05, 0.95) * w,
                        "y": random.uniform(-0.15, 0.0) * h,
                        "vy": random.uniform(0.035, 0.075) * h,
                        "size": random.randint(14, 34),
                        "alpha": random.uniform(0.55, 1.0),
                        "color": random.choice(_HEART_COLORS),
                    })

            def _draw_heart(dst, cx: int, cy: int, size: int, color: tuple, alpha: float):
                t = np.linspace(0, 2 * math.pi, 64)
                xs = 16 * np.sin(t) ** 3
                ys = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
                sc = size / 16.0
                pts = np.array([[int(cx + x * sc), int(cy + y * sc)] for x, y in zip(xs, ys)], dtype=np.int32)
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
                now = time.time()
                dt = now - prev_time
                fps = 1.0 / max(dt, 1e-6)
                prev_time = now

                h_f, w_f = frame.shape[:2]

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if shared_mp is not None:
                    shared_mp.process(rgb)

                if _calibrating:
                    elapsed = now - _calib_start
                    for det in detectors_list:
                        try:
                            det.process_frame(frame, now, shared_mp)
                        except Exception:
                            pass
                    _draw_calib_overlay(frame, elapsed)
                    if elapsed >= _CALIB_MIN_SEC and _all_detectors_calibrated(detectors_list):
                        _calibrating = False
                    with self.lock:
                        self.camera_state.latest_frame = frame
                        self.latest_frame = frame  # 호환성
                    continue

                all_signals = []
                for det in detectors_list:
                    try:
                        sigs = det.process_frame(frame, now, shared_mp)
                        all_signals.extend(sigs)
                    except Exception:
                        import traceback
                        traceback.print_exc()

                top_signal = None
                if all_signals:
                    sig_names = set(sig.name for sig in all_signals)

                    # HEART 제스처에서는 손 움직임으로 인한 LOW_FOCUS 오탐을 제외
                    if "HEART" in sig_names:
                        all_signals = [sig for sig in all_signals if sig.name != "LOW_FOCUS"]
                        sig_names.discard("LOW_FOCUS")

                    for prio in SIGNAL_PRIORITY:
                        if prio in sig_names:
                            top_signal = prio
                            break
                    if not top_signal:
                        top_signal = all_signals[0].name

                for det in detectors_list:
                    try:
                        det.draw_hud(frame)
                    except Exception:
                        pass

                is_warning = top_signal in ("DROWSINESS", "LOW_FOCUS", "OFF_TASK")
                if is_warning:
                    _flash_phase = (_flash_phase + _FLASH_SPEED * dt) % (2 * math.pi)
                    alpha = _FLASH_MAX_A * (0.5 + 0.5 * math.sin(_flash_phase))

                    red_ov = np.zeros_like(frame)
                    red_ov[:] = (0, 0, 200)
                    cv2.addWeighted(red_ov, alpha * 0.5, frame, 1.0, 0, frame)

                    bw = max(10, int(min(h_f, w_f) * 0.06))
                    border_ov = frame.copy()
                    cv2.rectangle(border_ov, (0, 0), (w_f - 1, h_f - 1), (0, 0, 255), bw * 3)
                    cv2.addWeighted(border_ov, alpha, frame, 1 - alpha, 0, frame)

                    label = SIGNAL_STYLES.get(top_signal, DEFAULT_STYLE)["label"]
                    t_scale = 1.1
                    (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, t_scale, 3)
                    tx = (w_f - tw) // 2
                    ty = int(h_f * 0.15)
                    cv2.putText(frame, label, (tx + 2, ty + 2), cv2.FONT_HERSHEY_SIMPLEX, t_scale, (0, 0, 0), 5)
                    pulse_r = int(180 + 75 * (0.5 + 0.5 * math.sin(_flash_phase)))
                    cv2.putText(frame, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, t_scale, (50, 50, pulse_r), 3)
                else:
                    _flash_phase = 0.0

                if top_signal == "HEART" and random.random() < 0.65:
                    _spawn_hearts(w_f, h_f, n=random.randint(1, 3))

                alive = []
                for hrt in _hearts:
                    hrt["y"] += hrt["vy"]
                    if hrt["y"] < h_f + hrt["size"] * 3:
                        alive.append(hrt)
                        _draw_heart(
                            frame,
                            int(hrt["x"]),
                            int(hrt["y"]),
                            hrt["size"],
                            hrt["color"],
                            hrt["alpha"],
                        )
                _hearts[:] = alive

                cv2.putText(frame, f"FPS:{fps:.1f}", (w_f - 110, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1)

                with self.camera_state.signal_lock:
                    self.camera_state.current_signal = top_signal
                    self._camera_current_signal = top_signal  # 호환성

                with self.lock:
                    self.camera_state.latest_frame = frame
                    self.latest_frame = frame  # 호환성
                time.sleep(0.01)

        self._capture_thread = threading.Thread(target=capture_loop, daemon=True)
        self._capture_thread.start()

        detectors_list = []
        if _DETECTORS_AVAILABLE:
            try:
                detectors_list = [
                    DrowsinessDetector(),
                    FidgetDetector(),
                    HeartDetector(),
                    OffTaskDetector(),
                ]
                print(f"[screen_camera] {len(detectors_list)} detectors initialized (sequential)")
            except Exception:
                import traceback
                traceback.print_exc()

        self._detector_threads = []
        self._render_thread = threading.Thread(target=process_loop, args=(detectors_list,), daemon=True)
        self._render_thread.start()

    def stop_camera(self):
        if not self.camera_state.running:
            return
        self.camera_state.running = False
        self.camera_running = False  # 호환성

        for t in getattr(self, "_detector_threads", []):
            t.join(timeout=1.0)
        self._detector_threads = []

        if hasattr(self, "_render_thread") and self._render_thread is not None:
            self._render_thread.join(timeout=1.0)
            self._render_thread = None

        if hasattr(self, "_capture_thread") and self._capture_thread is not None:
            self._capture_thread.join(timeout=1.0)
            self._capture_thread = None

        if hasattr(self, "_shared_mp") and self._shared_mp is not None:
            try:
                self._shared_mp.release()
            except Exception:
                pass
            self._shared_mp = None

        if self.camera_thread is not None:
            self.camera_thread.join(timeout=1.0)
            self.camera_thread = None
