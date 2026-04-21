"""개인 공부 화면/성장/캐릭터 UI 로직 Mixin."""

import io
import math
import os
import struct
import subprocess
import time
import threading
import wave

import customtkinter as ctk
from PIL import Image

try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False

from config import MAIN
from services.camera_signals import DEFAULT_ANIM
from services.character_store import save_characters, touch_character
from services.study_time import load_daily_goal
import random as _random

_ENCOURAGE_MSGS = [
    "잘하고 있어!ꕤ",
    "화이팅!♡",
    "집중력 최고!★",
    "대단해!ꕤ",
    "이대로 계속 화이팅!♡",
    "멋지다!★",
    "조금만 더 힘내!♡",
    "할 수 있어! 😊",
]
_ENCOURAGE_INTERVAL = 10.0   # 초 (warning 없이 이 시간 유지 시 표시)
_ENCOURAGE_SHOW_SEC = 6.0     # 말풍선 표시 시간


def _make_tone(freq, duration_ms, volume=0.5, sample_rate=22050):
    """단일 주파수 톤 PCM 프레임 생성."""
    n = int(sample_rate * duration_ms / 1000)
    return b''.join(
        struct.pack('<h', int(volume * 32767 * math.sin(2 * math.pi * freq * i / sample_rate)))
        for i in range(n)
    )


def _make_silence(duration_ms, sample_rate=22050):
    return b'\x00\x00' * int(sample_rate * duration_ms / 1000)


def _generate_alarm_wav(sample_rate=22050):
    """경박한 알람 패턴 WAV 생성.

    패턴: (삐-- 삐삐삐) × 4 + 쉴  ≈ 2초
    LONG = 100ms 화음(1200+2400Hz), SHORT = 45ms 높은 음(1500Hz)
    """
    data = b''
    for rep in range(4):
        # LONG beep: 100ms 화음 (기본음 + 옥타브)
        data += _make_tone(1500, 100, 0.45, sample_rate)
        data += _make_silence(25, sample_rate)
        # 3× SHORT beep: 45ms 높은 톤
        for j in range(3):
            data += _make_tone(1500, 45, 0.40, sample_rate)
            data += _make_silence(25, sample_rate)
        # 그룹 간 간격
        data += _make_silence(35, sample_rate)
    # 마지막 여백
    data += _make_silence(300, sample_rate)

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(data)
    return buf.getvalue()


_ALARM_WAV = _generate_alarm_wav()


def _play_beep():
    """Windows/Linux 모두 지원하는 알람음 재생."""
    if _HAS_WINSOUND:
        winsound.PlaySound(_ALARM_WAV, winsound.SND_MEMORY)
        return
    for cmd in (['aplay', '-q', '-'], ['paplay', '--raw', '--format=s16le', '--rate=22050', '--channels=1']):
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.communicate(input=_ALARM_WAV, timeout=5)
            return
        except Exception:
            continue


class PersonalStudyMixin:

    # ── 세션 시작/종료 ───────────────────────────────────────

    def _start_personal_study_session(self):
        # 이전 세션 데이터가 있으면 이어서 진행 (앱 수명 동안 유지)
        if getattr(self, '_personal_session_preserved', False) and self.personal_study_state.elapsed_seconds > 0:
            self.personal_study_state.timer_running = True
            # 시작 시간을 elapsed만큼 과거로 보정
            self.personal_study_state.start_time = time.time() - self.personal_study_state.elapsed_seconds
            self._personal_paused = False
            self._personal_pause_accumulated = 0
            self._personal_pause_start = 0.0
            self._personal_signal_pause_accumulated = 0.0
            self._personal_signal_pause_start = 0.0
            self._personal_signal_paused = False
            # 호환성
            self._study_timer_running = True
            self._study_start_time = self.personal_study_state.start_time
            self._study_elapsed_seconds = self.personal_study_state.elapsed_seconds
            return

        self.personal_study_state.timer_running = True
        self.personal_study_state.start_time = time.time()
        self.personal_study_state.elapsed_seconds = 0
        self.personal_study_state.accumulated_points = 0
        self.personal_study_state.blocked_slots = set()
        self._personal_paused = False
        self._personal_pause_accumulated = 0  # 일시정지 중 누적 시간(수동)
        self._personal_pause_start = 0.0
        self._personal_signal_pause_accumulated = 0.0  # 시그널에 의한 정지 누적
        self._personal_signal_pause_start = 0.0
        self._personal_signal_paused = False
        self._personal_goal_completed = False
        self._personal_goal_flash_count = 0
        self._personal_session_preserved = True
        # 호환성
        self._study_timer_running = True
        self._study_start_time = time.time()
        self._study_elapsed_seconds = 0
        self._study_accumulated_points = 0
        self._study_blocked_slots = set()

    def _stop_personal_study_session(self, save=True):
        self.personal_study_state.timer_running = False
        self._study_timer_running = False
        if save:
            self._save_study_minutes("personal", self.personal_study_state.elapsed_seconds)
        # elapsed_seconds는 유지 (앱 수명 동안 재진입 시 이어서 진행)

    # ── 화면 빌드 ────────────────────────────────────────────

    def _build_screen_camera(self):
        frame = self.screen_camera
        # 상단바: 테두리/둥근 모서리/여백 없이 사각형, 배경색도 전체 배경과 동일하게
        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="개인 공부", anchor="w", font=self._make_font(18), text_color=self.theme["text"]).pack(side="left", padx=16)

        # 공부 시간 표시 (HH:MM:SS / HH:MM:SS 형태)
        goal_min = load_daily_goal(self.args.name) or 0
        g_h, g_rem = divmod(goal_min * 60, 3600)
        g_m, g_s = divmod(g_rem, 60)
        goal_str = f"{g_h:02d}:{g_m:02d}:{g_s:02d}"
        self._personal_goal_minutes = goal_min
        self._study_time_label = ctk.CTkLabel(top, text=f"공부시간: 00:00:00 / {goal_str}", font=self._make_font(14), text_color=self.theme["text_muted"])
        self._study_time_label.pack(side="left", padx=20)

        self._personal_pause_btn = ctk.CTkButton(
            top, text="⏸ 일시정지", width=110, height=36,
            font=self._make_font(14),
            command=self._toggle_personal_pause,
            **self._exit_button_style(),
        )
        self._personal_pause_btn.pack(side="right", padx=(0, 8), pady=0)

        ctk.CTkButton(top, text="나가기", width=110, height=36, command=self._on_camera_back,
              font=self._make_font(14), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        # ── 목표 시간 대비 진행 바 ──
        self._personal_progress_bar = ctk.CTkProgressBar(
            frame, width=0, height=10,
            fg_color=self.theme["gray_hover"],
            progress_color="#4A90D9",  # 파란색 (집중 상태)
            corner_radius=0,
        )
        self._personal_progress_bar.pack(fill="x", padx=0, pady=0)
        self._personal_progress_bar.set(0.0)

        # ── 목표 달성 축하 라벨 (숨김 상태) ──
        self._personal_congrats_label = ctk.CTkLabel(
            frame, text="",
            font=self._make_font(28, "bold"),
            text_color="#FFD700",
            fg_color="transparent",
        )

        # 카메라 피드 라벨
        self.img_label = ctk.CTkLabel(frame, text="")
        self.img_label.pack(fill="both", expand=True, padx=10, pady=10)

        # angry_goblin run_to_us 오버레이 상태 (졸음 감지 시 카메라 위에 합성)
        self._goblin_frame_idx = 0
        self._goblin_visible = False
        self._goblin_anim_running = False
        self._goblin_beep_counter = 0
        self._load_goblin_frames()

        # 캐릭터 애니메이션 + 성장도 바 영역
        char_area = ctk.CTkFrame(frame, fg_color="transparent")
        char_area.place(relx=0.05, rely=0.7, anchor="w")

        self._camera_char_label = ctk.CTkLabel(char_area, text="", fg_color="transparent")
        self._camera_char_label.pack()
        self._camera_char_name = ctk.CTkLabel(char_area, text="", font=self._make_font(14), text_color=self.theme["text"])
        self._camera_char_growth = ctk.CTkProgressBar(char_area, width=120, fg_color=self.theme["gray_hover"], progress_color=self.theme["pink_hover"])
        self._camera_char_growth.pack(pady=(2, 0))
        self._camera_char_growth_label = ctk.CTkLabel(char_area, text="0%", font=self._make_font(10), text_color=self.theme["text_muted"])

        # 응원 말풍선 (캐릭터 위 → 위로 떠오르는 연출)
        self._bubble_frame = ctk.CTkFrame(
            frame, fg_color=self.theme["gray_hover"],
            border_width=2, border_color="black",
            corner_radius=4,
        )
        self._bubble_label = ctk.CTkLabel(
            self._bubble_frame, text="", font=self._make_font(14),
            text_color=self.theme["text"],
            fg_color="transparent",
        )
        self._bubble_label.pack(padx=14, pady=6)
        self._bubble_visible = False
        self._last_warning_time = time.time()
        self._bubble_hide_time = 0.0
        self._bubble_y = 0.0      # 현재 y 비율 (rely)
        self._bubble_target_y = 0.0

        self._camera_char_frames = []
        self._camera_char_frame_idx = 0
        self._camera_char_anim_running = False

        # 시그널 기반 애니메이션 전환용
        self._camera_anim_sets = {}       # {"happy": [...], "tail": [...], "tear": [...]}
        self._camera_current_anim = DEFAULT_ANIM
        self._camera_signal_lock = threading.Lock()
        self._camera_current_signal = None  # 현재 감지된 시그널 이름
        
        # 상태 객체 초기화
        self.personal_study_state.anim_sets = {}
        self.personal_study_state.current_anim = DEFAULT_ANIM

        self._start_personal_study_session()
        self._load_camera_character_animation()
        self._update_study_timer()

        # 이전에 목표 달성했으면 축하 표시 복원
        if getattr(self, '_personal_goal_completed', False):
            self._personal_progress_bar.configure(progress_color="#FFD700")
            self._personal_congrats_label.configure(
                text="🎉 축하합니다! 목표 시간을 모두 완료하였습니다! 🎉",
                text_color="#FFD700",
            )
            self._personal_congrats_label.place(relx=0.5, rely=0.4, anchor="center")
            self._personal_congrats_label.lift()

        # 고블린 오버레이 애니메이션 시작 (200ms)
        self._goblin_anim_running = True
        self._goblin_anim_tick()
        self._encourage_bubble_tick()

    # ── 일시정지 토글 ───────────────────────────────────────

    def _toggle_personal_pause(self):
        if self._personal_goal_completed:
            return
        if self._personal_paused:
            # 재개
            pause_dur = time.time() - self._personal_pause_start
            self._personal_pause_accumulated += pause_dur
            self._personal_paused = False
            self._personal_pause_btn.configure(text="⏸ 일시정지")
        else:
            # 일시정지
            self._personal_paused = True
            self._personal_pause_start = time.time()
            self._personal_pause_btn.configure(text="▶ 재개")

    # ── 캐릭터 로드 / 애니메이션 ─────────────────────────────

    def _load_camera_character_animation(self):
        """선택된 캐릭터의 애니메이션 프리로드 + 성장도/이름 표시."""
        self._camera_anim_sets = {}
        self._camera_char_frames = []
        self._camera_char_frame_idx = 0
        self._camera_char_anim_running = False
        
        # 상태 객체도 초기화
        self.personal_study_state.anim_sets = {}
        self.personal_study_state.char_frames = []
        self.personal_study_state.char_idx = -1
        self.personal_study_state.char_id = None
        self.personal_study_state.char_name = ""

        char_ref = getattr(self, "_selected_char", None)
        chars, char_idx, char_name, char_id, char_growth, anim_sets = \
            self._load_study_character(char_ref, target_w=120, tear_fallback=False)

        if char_name and chars is not None:
            self._camera_char_id = char_id
            self.personal_study_state.char_id = char_id
            if touch_character(chars, char_id or char_ref):
                save_characters(chars)
        else:
            self._camera_char_id = None
            self.personal_study_state.char_id = None

        if not char_name:
            self._camera_char_label.configure(image=None)
            self._camera_char_name.configure(text="")
            self._camera_char_growth.set(0.0)
            self._camera_char_growth_label.configure(text="0%")
            self._camera_char_idx = -1
            self._camera_char_id = None
            self.personal_study_state.char_idx = -1
            self.personal_study_state.char_id = None
            return

        self._camera_char_idx = char_idx
        self._camera_anim_sets = anim_sets
        self.personal_study_state.char_idx = char_idx
        self.personal_study_state.anim_sets = anim_sets
        self.personal_study_state.char_name = char_name

        if not anim_sets.get("tail"):
            self._camera_char_label.configure(image=None)
            self._camera_char_name.configure(text=char_name)
            self._update_growth_widgets(self._camera_char_growth, self._camera_char_growth_label, char_growth)
            return

        self._camera_char_name.configure(text=char_name)
        self._update_growth_widgets(self._camera_char_growth, self._camera_char_growth_label, char_growth)

        # 기본 tail 애니메이션으로 시작
        self._camera_current_anim = DEFAULT_ANIM
        self._camera_char_frames = self._camera_anim_sets.get(DEFAULT_ANIM, [])
        self._camera_char_frame_idx = 0
        self.personal_study_state.current_anim = DEFAULT_ANIM
        self.personal_study_state.char_frames = self._camera_anim_sets.get(DEFAULT_ANIM, [])
        if self._camera_char_frames:
            self._camera_char_label.configure(image=self._camera_char_frames[0])
            self._camera_char_anim_running = True
            self._camera_char_anim_update()
        else:
            self._camera_char_label.configure(image=None)
            self._camera_char_anim_running = False

    def _load_goblin_frames(self):
        """angry_goblin/run_to_us PIL RGBA 프레임을 커스텀 시퀀스로 로드.

        시퀀스: dok1~dok8 순서대로 재생 → dok7,dok8을 3번 더 반복
        → dok8에서 1초 머무른 뒤 다시 dok1로 루프.
        """
        if getattr(self, '_goblin_frames', None):
            return  # 이미 로드됨
        self._goblin_frames = []
        goblin_dir = "frontend/assets/characters/angry_goblin/run_to_us"
        if not os.path.isdir(goblin_dir):
            return
        target_w = 300
        target_h = int(target_w * 650 / 430)
        raw_frames = []
        for i in range(1, 9):  # dok1 ~ dok8
            path = os.path.join(goblin_dir, f"dok{i}.png")
            if not os.path.isfile(path):
                continue
            try:
                pil_img = Image.open(path).convert("RGBA")
                bg = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                pil_img.thumbnail((target_w, target_h), Image.LANCZOS)
                ox = (target_w - pil_img.width) // 2
                oy = (target_h - pil_img.height) // 2
                bg.paste(pil_img, (ox, oy), pil_img)
                raw_frames.append(bg)
            except Exception:
                continue
        if len(raw_frames) < 8:
            self._goblin_frames = raw_frames
            return
        # 1,2,3,4,5,6,7,8,7,8,7,8,7,8  (dok7-dok8 세 번 더 반복)
        seq = list(range(8))
        for _ in range(3):
            seq.extend([6, 7])
        # dok8에서 1초 머무름 (5×200ms = 1000ms, 앞의 1프레임 포함 → 4개 추가)
        seq.extend([7] * 4)
        self._goblin_frames = [raw_frames[i] for i in seq]

    def _goblin_anim_tick(self):
        """200ms마다 졸음 감지 확인 + 고블린 프레임 전환 + 비프음."""
        if not getattr(self, '_goblin_anim_running', False):
            return

        # 목표 달성 후에는 졸음 감지 무시
        if getattr(self, '_personal_goal_completed', False):
            if self._goblin_visible:
                self._goblin_visible = False
            self.root.after(200, self._goblin_anim_tick)
            return

        # 일시정지 중에는 졸음 감지 무시
        if getattr(self, '_personal_paused', False):
            if self._goblin_visible:
                self._goblin_visible = False
            self.root.after(200, self._goblin_anim_tick)
            return

        with self._camera_signal_lock:
            current_signal = self._camera_current_signal

        is_drowsy = current_signal == "DROWSINESS"
        goblin_frames = getattr(self, '_goblin_frames', [])

        if is_drowsy and goblin_frames:
            if not self._goblin_visible:
                self._goblin_visible = True
                self._goblin_frame_idx = 0
                self._goblin_beep_counter = 0
            self._goblin_frame_idx = (self._goblin_frame_idx + 1) % len(goblin_frames)
            # 알람 패턴 재생 (≈2초, 10 × 200ms 간격)
            self._goblin_beep_counter += 1
            if self._goblin_beep_counter % 10 == 1:
                threading.Thread(target=_play_beep, daemon=True).start()
        else:
            if self._goblin_visible:
                self._goblin_visible = False

        self.root.after(200, self._goblin_anim_tick)

    def _encourage_bubble_tick(self):
        """200ms마다 응원 말풍선 표시/애니메이션 처리."""
        if not getattr(self, '_goblin_anim_running', False):
            return

        with self._camera_signal_lock:
            current_signal = self._camera_current_signal

        _now = time.time()

        # 경고 상태일 때 말풍선 숨기기 & 타이머 리셋
        if current_signal in ("DROWSINESS", "OFF_TASK", "LOW_FOCUS"):
            self._last_warning_time = _now
            if self._bubble_visible:
                self._bubble_frame.place_forget()
                self._bubble_visible = False

        # 일정 시간 경고 없이 집중하면 응원 말풍선 표시
        if not self._bubble_visible and (_now - self._last_warning_time) >= _ENCOURAGE_INTERVAL:
            msg = _random.choice(_ENCOURAGE_MSGS)
            self._bubble_label.configure(text=f"  {msg}  ")
            self._bubble_y = 0.62
            self._bubble_target_y = 0.08
            self._bubble_frame.place(relx=0.05, rely=self._bubble_y, anchor="sw")
            self._bubble_frame.lift()
            self._bubble_visible = True
            self._bubble_hide_time = _now + _ENCOURAGE_SHOW_SEC
            self._last_warning_time = _now

        # 위로 떠오르는 애니메이션 (200ms 틱마다)
        if self._bubble_visible:
            if self._bubble_y > self._bubble_target_y:
                self._bubble_y -= 0.015
                self._bubble_frame.place_configure(rely=max(self._bubble_y, self._bubble_target_y))
            if _now >= self._bubble_hide_time:
                self._bubble_frame.place_forget()
                self._bubble_visible = False

        self.root.after(200, self._encourage_bubble_tick)

    def _camera_char_anim_update(self):
        if not self._camera_char_anim_running:
            return
        self._camera_current_anim, self._camera_char_frames, self._camera_char_frame_idx = \
            self._tick_signal_anim(
                self._camera_anim_sets,
                self._camera_current_anim,
                self._camera_char_frames,
                self._camera_char_frame_idx,
                self._camera_char_label,
                500,
                self._camera_char_anim_update,
            )

    # ── 종료 ─────────────────────────────────────────────────

    def _on_camera_back(self):
        self._stop_personal_study_session()
        self.stop_camera()
        self._camera_char_anim_running = False
        self._goblin_anim_running = False
        self._goblin_visible = False
        # elapsed_seconds는 유지 (_personal_session_preserved 활용)
        if hasattr(self, '_personal_congrats_label'):
            self._personal_congrats_label.place_forget()
        self.show_screen(MAIN)

    # ── 성장 틱 / 타이머 ────────────────────────────────────

    def _tick_personal_study_growth(self):
        """개인 공부 성장 포인트 소비 + 반영."""
        if getattr(self, '_personal_paused', False):
            return
        if self._is_focus_blocking_signal() and not getattr(self, '_personal_goal_completed', False):
            self._mark_blocked_growth_slot("personal", self.personal_study_state.elapsed_seconds)

        add_points = self._consume_growth_points("personal", self.personal_study_state.elapsed_seconds)
        if add_points <= 0 or self.personal_study_state.char_idx < 0:
            return

        try:
            char_ref = self.personal_study_state.char_id
            selected_ref = char_ref if char_ref else self.personal_study_state.char_idx
            self._apply_growth_points(
                selected_ref,
                add_points,
                on_stage_changed=lambda _g: self._load_camera_character_animation(),
                on_progress_updated=lambda g: self._update_growth_widgets(
                    self._camera_char_growth, self._camera_char_growth_label, g),
            )
        except Exception:
            pass

    def _update_study_timer(self):
        """1초마다 타이머 갱신 + 성장 틱 + 목표 진행바 업데이트."""
        if not self.personal_study_state.timer_running:
            return

        # 시그널에 의한 일시정지 처리
        with self._camera_signal_lock:
            sig = self._camera_current_signal
        is_warning = sig in ("DROWSINESS", "OFF_TASK", "LOW_FOCUS") and not self._personal_goal_completed
        if is_warning and not self._personal_signal_paused:
            self._personal_signal_paused = True
            self._personal_signal_pause_start = time.time()
        elif not is_warning and self._personal_signal_paused:
            self._personal_signal_pause_accumulated += time.time() - self._personal_signal_pause_start
            self._personal_signal_paused = False

        # 일시정지 중(수동 또는 시그널)에는 elapsed를 증가시키지 않음
        if not self._personal_paused and not self._personal_signal_paused:
            total_pause = self._personal_pause_accumulated + self._personal_signal_pause_accumulated
            total_elapsed = time.time() - self.personal_study_state.start_time - total_pause
            self.personal_study_state.elapsed_seconds = max(0, int(total_elapsed))
        self._study_elapsed_seconds = self.personal_study_state.elapsed_seconds  # 호환성

        elapsed = self.personal_study_state.elapsed_seconds
        e_h, e_rem = divmod(elapsed, 3600)
        e_m, e_s = divmod(e_rem, 60)
        goal_min = self._personal_goal_minutes
        g_total = goal_min * 60
        g_h, g_rem = divmod(g_total, 3600)
        g_m, g_s = divmod(g_rem, 60)
        self._study_time_label.configure(text=f"공부시간: {e_h:02d}:{e_m:02d}:{e_s:02d} / {g_h:02d}:{g_m:02d}:{g_s:02d}")

        # 목표 진행바 업데이트
        if goal_min > 0:
            ratio = min(1.0, elapsed / (goal_min * 60))
            self._personal_progress_bar.set(ratio)
        else:
            self._personal_progress_bar.set(0.0)

        # 진행바 색상: 일시정지=회색, 경고시그널=빨강, 정상=파랑, 완료=노랑
        if self._personal_goal_completed:
            self._personal_progress_bar.configure(progress_color="#FFD700")
        elif self._personal_paused:
            self._personal_progress_bar.configure(progress_color="#A0A0A0")
        elif is_warning:
            self._personal_progress_bar.configure(progress_color="#D94A4A")
        else:
            self._personal_progress_bar.configure(progress_color="#4A90D9")

        # 목표 달성 체크
        if not self._personal_goal_completed and goal_min > 0 and elapsed >= goal_min * 60:
            self._personal_goal_completed = True
            self._show_personal_congrats()

        if not self._personal_paused and not self._personal_signal_paused:
            self._tick_personal_study_growth()
        self.root.after(1000, self._update_study_timer)

    # ── 축하 이벤트 ─────────────────────────────────────────

    def _show_personal_congrats(self):
        """목표 달성 축하 연출."""
        self._personal_congrats_label.configure(
            text="🎉 축하합니다! 목표 시간을 모두 완료하였습니다! 🎉"
        )
        self._personal_congrats_label.place(relx=0.5, rely=0.4, anchor="center")
        self._personal_congrats_label.lift()
        self._personal_goal_flash_count = 0
        self._personal_progress_bar.configure(progress_color="#FFD700")
        self._personal_congrats_flash()

    def _personal_congrats_flash(self):
        """축하 텍스트 깜빡임 효과 (노란색 계열)."""
        if not self.personal_study_state.timer_running:
            return
        self._personal_goal_flash_count += 1
        if self._personal_goal_flash_count > 20:
            # 깜빡임 종료 후 텍스트 유지
            self._personal_congrats_label.configure(text_color="#FFD700")
            return
        if self._personal_goal_flash_count % 2 == 0:
            self._personal_congrats_label.configure(text_color="#FFD700")
        else:
            self._personal_congrats_label.configure(text_color="#FFA500")
        self.root.after(400, self._personal_congrats_flash)
