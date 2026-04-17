"""
카메라 슬라이드 및 카메라 제어 Mixin
- slide_camera : 개인 공부 카메라 화면 (PERSONAL_CAMERA)
- signal_hub detectors 통합: 카메라 프레임에서 시그널 감지 → 캐릭터 반응
"""
import os
import sys
import json
import time
import threading

import cv2
import customtkinter as ctk

from .slides import MAIN
from .study_time import save_study_time

# ─────────────────────────────────────────────────────────────
#  detectors import (examples 디렉토리에서)
# ─────────────────────────────────────────────────────────────
_DETECTORS_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
_DETECTORS_ROOT = os.path.abspath(_DETECTORS_ROOT)
if _DETECTORS_ROOT not in sys.path:
    sys.path.insert(0, _DETECTORS_ROOT)

try:
    from detectors import DrowsinessDetector, FidgetDetector, HeartDetector, Signal
    _DETECTORS_AVAILABLE = True
except ImportError:
    _DETECTORS_AVAILABLE = False
    print("[slide_camera] WARNING: detectors not found, signal detection disabled")

# ─────────────────────────────────────────────────────────────
#  시그널 → 캐릭터 애니메이션 매핑
# ─────────────────────────────────────────────────────────────
_SIGNAL_TO_ANIM = {
    "HEART":      "happy",   # 하트 제스처 → 기쁨
    "DROWSINESS": "tear",    # 졸음 → 걱정/눈물
    "LOW_FOCUS":  "tear",    # 산만 → 걱정/눈물
}
_DEFAULT_ANIM = "tail"       # 시그널 없음 → 꼬리 흔들기 (평상시)

# 시그널 우선순위 (앞에 있을수록 우선)
_SIGNAL_PRIORITY = ["DROWSINESS", "LOW_FOCUS", "HEART"]

# 시그널 종류별 색상 / 라벨 (카메라 영상 위 알림 바용)
_SIGNAL_STYLES = {
    "DROWSINESS": {"color": (0, 0, 200),   "label": "DROWSINESS"},
    "LOW_FOCUS":  {"color": (0, 100, 220), "label": "LOW_FOCUS"},
    "HEART":      {"color": (180, 0, 180), "label": "BIG HEART!"},
}
_DEFAULT_STYLE = {"color": (180, 180, 0), "label": "alarm"}


class CameraSlideMixin:


    def _build_camera_slide(self):
        frame = self.slide_camera
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="개인 공부 - 카메라", anchor="w", font=self._make_font(18)).pack(side="left")
        
        # 공부 시간 표시
        self._study_time_label = ctk.CTkLabel(top, text="공부시간: 00:00", font=self._make_font(14))
        self._study_time_label.pack(side="left", padx=20)
        
        ctk.CTkButton(top, text="돌아가기", width=80, command=self._on_camera_back,
                      font=self._make_font(12)).pack(side="right")

        # 카메라 피드 라벨
        self.img_label = ctk.CTkLabel(frame, text="")
        self.img_label.pack(fill="both", expand=True, padx=10, pady=10)

        # 캐릭터 애니메이션 + 성장도 바 영역
        char_area = ctk.CTkFrame(frame, fg_color="transparent")
        char_area.place(relx=0.05, rely=0.7, anchor="w")

        self._camera_char_label = ctk.CTkLabel(char_area, text="", fg_color="transparent")
        self._camera_char_label.pack()
        self._camera_char_name = ctk.CTkLabel(char_area, text="", font=self._make_font(14, "bold"))
        self._camera_char_growth = ctk.CTkProgressBar(char_area, width=120)
        self._camera_char_growth.pack(pady=(2,0))
        self._camera_char_growth_label = ctk.CTkLabel(char_area, text="0%", font=self._make_font(10))

        self._camera_char_frames = []
        self._camera_char_frame_idx = 0
        self._camera_char_anim_running = False
        
        # 공부 시간 측정 변수
        self._study_start_time = time.time()
        self._study_elapsed_seconds = 0
        self._study_accumulated_points = 0
        self._study_timer_running = True
        
        # 시그널 기반 애니메이션 전환용
        self._camera_anim_sets = {}       # {"happy": [...], "tail": [...], "tear": [...]}
        self._camera_current_anim = _DEFAULT_ANIM
        self._camera_signal_lock = threading.Lock()
        self._camera_current_signal = None  # 현재 감지된 시그널 이름

        self._load_camera_character_animation()
        self._update_study_timer()

    def _load_camera_character_animation(self):
        """선택된 캐릭터의 happy/tail/tear 애니메이션을 모두 프리로드, 성장도/이름도 표시"""
        self._camera_anim_sets = {}
        self._camera_char_frames = []
        self._camera_char_frame_idx = 0
        char_name = getattr(self, '_selected_char', None)
        char_growth = 0
        char_idx = -1
        # 인덱스일 경우 실제 이름/성장도로 변환
        if isinstance(char_name, int):
            try:
                with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                    characters = json.load(f)
                char_growth = int(characters[char_name].get("growth", 0))
                char_idx = char_name
                char_name = characters[char_name]["name"]
            except Exception:
                char_name = None
        else:
            try:
                with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                    characters = json.load(f)
                for i, c in enumerate(characters):
                    if c.get("name") == char_name:
                        char_growth = int(c.get("growth", 0))
                        char_idx = i
                        break
            except Exception:
                pass

        if not char_name or not isinstance(char_name, str):
            self._camera_char_label.configure(image=None)
            self._camera_char_name.configure(text="")
            self._camera_char_growth.set(0.0)
            self._camera_char_growth_label.configure(text="0%")
            self._camera_char_idx = -1
            return
        self._camera_char_idx = char_idx
        # type을 찾아서 해당 폴더에서 이미지 로드
        char_type = "baby"
        try:
            with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                characters = json.load(f)
                if 0 <= char_idx < len(characters):
                    char_type = characters[char_idx].get("type", "baby")
        except Exception:
            pass
        tail_dir = f"frontend/assets/characters/{char_name}/{char_type}/tail"
        if not os.path.isdir(tail_dir):
            self._camera_char_label.configure(image=None)
            self._camera_char_name.configure(text=char_name)
            growth_percent = min(100, int(char_growth * 100 / 120))
            self._camera_char_growth.set(char_growth / 120)
            self._camera_char_growth_label.configure(text=f"{growth_percent}%")
            return
        from PIL import Image
        for anim_name in ("happy", "tail", "tear"):
            anim_dir = f"frontend/assets/characters/{char_name}/{char_type}/{anim_name}"
            frames = []
            if os.path.isdir(anim_dir):
                files = sorted([f for f in os.listdir(anim_dir) if f.endswith('.png')])
                for fn in files:
                    try:
                        pil_img = Image.open(os.path.join(anim_dir, fn)).convert("RGBA")
                        target_w, target_h = 120, int(120 * 650 / 430)
                        bg = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                        pil_img.thumbnail((target_w, target_h), Image.LANCZOS)
                        x = (target_w - pil_img.width) // 2
                        y = (target_h - pil_img.height) // 2
                        bg.paste(pil_img, (x, y), pil_img)
                        ctk_img = ctk.CTkImage(light_image=bg, dark_image=bg, size=(target_w, target_h))
                        frames.append(ctk_img)
                    except Exception:
                        continue
            self._camera_anim_sets[anim_name] = frames

        self._camera_char_name.configure(text=char_name)
        # UI에 표시할 때만 % 120 사용
        display_growth = char_growth % 120
        growth_percent = min(100, int(display_growth * 100 / 120))
        self._camera_char_growth.set(display_growth / 120)
        self._camera_char_growth_label.configure(text=f"{growth_percent}%")

        # 기본 tail 애니메이션으로 시작
        self._camera_current_anim = _DEFAULT_ANIM
        self._camera_char_frames = self._camera_anim_sets.get(_DEFAULT_ANIM, [])
        self._camera_char_frame_idx = 0
        if self._camera_char_frames:
            self._camera_char_label.configure(image=self._camera_char_frames[0])
            self._camera_char_anim_running = True
            self._camera_char_anim_update()
        else:
            self._camera_char_label.configure(image=None)
            self._camera_char_anim_running = False

    def _camera_char_anim_update(self):
        if not self._camera_char_anim_running:
            return

        # 시그널에 따라 애니메이션 세트 전환
        with self._camera_signal_lock:
            sig = self._camera_current_signal

        target_anim = _DEFAULT_ANIM
        if sig:
            # 우선순위 높은 시그널 먼저
            for s in _SIGNAL_PRIORITY:
                if s == sig:
                    target_anim = _SIGNAL_TO_ANIM.get(s, _DEFAULT_ANIM)
                    break

        # 애니메이션 세트 변경 시 프레임 인덱스 리셋
        if target_anim != self._camera_current_anim:
            new_frames = self._camera_anim_sets.get(target_anim, [])
            if new_frames:
                self._camera_current_anim = target_anim
                self._camera_char_frames = new_frames
                self._camera_char_frame_idx = 0

        if not self._camera_char_frames:
            self.root.after(500, self._camera_char_anim_update)
            return

        self._camera_char_frame_idx = (self._camera_char_frame_idx + 1) % len(self._camera_char_frames)
        self._camera_char_label.configure(image=self._camera_char_frames[self._camera_char_frame_idx])
        self.root.after(500, self._camera_char_anim_update)

    def _on_camera_back(self):
        # 공부 시간 측정 종료
        self._study_timer_running = False
        
        # 공부 시간 저장 (분 단위)
        study_minutes = max(1, self._study_elapsed_seconds // 60)
        user_name = getattr(self.args, 'name', 'user')
        save_study_time(user_name, 'personal', study_minutes)
        
        # 성장도 저장
        if self._study_accumulated_points > 0 and hasattr(self, '_camera_char_idx'):
            char_idx = self._camera_char_idx
            if 0 <= char_idx:
                try:
                    with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                        chars = json.load(f)
                    char = chars[char_idx]
                    growth = int(char.get("growth", 0))
                    growth += self._study_accumulated_points
                    stages = ["baby", "adult", "crown"]
                    stage_idx = stages.index(char.get("type", "baby")) if char.get("type", "baby") in stages else 0
                    new_stage_idx = min(growth // 120, len(stages) - 1)
                    char["growth"] = growth  # 누적 포인트로 유지
                    if new_stage_idx != stage_idx:
                        char["type"] = stages[new_stage_idx]
                    chars[char_idx] = char
                    with open("frontend/user/characters.json", "w", encoding="utf-8") as f:
                        json.dump(chars, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
        
        self.stop_camera()
        self._camera_char_anim_running = False
        self.show_slide(MAIN)
    
    def _update_study_timer(self):
        """30초마다 성장도 1포인트 추가"""
        if not self._study_timer_running:
            return
        
        self._study_elapsed_seconds = int(time.time() - self._study_start_time)
        
        # 공부 시간 표시 업데이트 (분:초)
        minutes = self._study_elapsed_seconds // 60
        seconds = self._study_elapsed_seconds % 60
        self._study_time_label.configure(text=f"공부시간: {minutes:02d}:{seconds:02d}")
        
        # 30초마다 1포인트 추가
        new_points = self._study_elapsed_seconds // 30
        if new_points > self._study_accumulated_points:
            self._study_accumulated_points = new_points
            
            # 캐릭터 성장도 업데이트
            if hasattr(self, '_camera_char_idx') and self._camera_char_idx >= 0:
                try:
                    with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                        chars = json.load(f)
                    char = chars[self._camera_char_idx]
                    growth = int(char.get("growth", 0))
                    growth += 1
                    
                    # 성장 단계 변경 확인
                    stages = ["baby", "adult", "crown"]
                    stage_idx = stages.index(char.get("type", "baby")) if char.get("type", "baby") in stages else 0
                    new_stage_idx = min(growth // 120, len(stages) - 1)
                    old_growth_display = growth - 1
                    
                    if new_stage_idx != stage_idx:
                        # 성장 단계 변경됨 - 이미지 리로드
                        char["type"] = stages[new_stage_idx]
                        char["growth"] = growth  # 누적 포인트로 유지 (리셋하지 않음)
                        chars[self._camera_char_idx] = char
                        with open("frontend/user/characters.json", "w", encoding="utf-8") as f:
                            json.dump(chars, f, ensure_ascii=False, indent=2)
                        # 캐릭터 이미지 다시 로드
                        self._load_camera_character_animation()
                    else:
                        # 성장도만 업데이트
                        char["growth"] = growth
                        chars[self._camera_char_idx] = char
                        # UI에 표시할 때만 % 120 사용
                        display_growth = growth % 120
                        growth_percent = min(100, int(display_growth * 100 / 120))
                        self._camera_char_growth.set(display_growth / 120)
                        self._camera_char_growth_label.configure(text=f"{growth_percent}%")
                        with open("frontend/user/characters.json", "w", encoding="utf-8") as f:
                            json.dump(chars, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
        
        # 1초마다 다시 호출
        self.root.after(1000, self._update_study_timer)

    def start_camera(self, camera_index: int = 0):
        if self.camera_running:
            return
        self.camera_running = True

        # 애니메이션 루프 재시작 (슬라이드 재진입 시)
        if self._camera_anim_sets and not self._camera_char_anim_running:
            self._camera_char_frames = self._camera_anim_sets.get(_DEFAULT_ANIM, [])
            self._camera_current_anim = _DEFAULT_ANIM
            self._camera_char_frame_idx = 0
            if self._camera_char_frames:
                self._camera_char_anim_running = True
                self._camera_char_anim_update()

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
                    for prio in _SIGNAL_PRIORITY:
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
                    label  = _SIGNAL_STYLES.get(top_signal, _DEFAULT_STYLE)["label"]
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
                print(f"[slide_camera] {len(detectors_list)} detectors initialized (parallel)")
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
