"""단체방 공부 세션/UI 로직 Mixin."""

import os
import time
import threading

import customtkinter as ctk

from config import GROUP_LIST
from services.camera_signals import DEFAULT_ANIM


class GroupStudyMixin:

    # ── 화면 빌드 ────────────────────────────────────────────

    def _build_screen_group(self):
        frame = self.screen_group
        frame.configure(fg_color=self.theme["ivory"])

        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        self.group_screen_title = ctk.CTkLabel(top, text="단체 공부", anchor="w", font=self._make_font(18), text_color=self.theme["text"])
        self.group_screen_title.pack(side="left", padx=16)

        # 공부시간 라벨 추가
        self._group_study_time_label = ctk.CTkLabel(top, text="공부시간: 00:00", font=self._make_font(14), text_color=self.theme["text_muted"])
        self._group_study_time_label.pack(side="left", padx=20)

        ctk.CTkButton(top, text="나가기", width=110, height=36, command=self._on_group_back,
              font=self._make_font(14), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        body = ctk.CTkFrame(frame, fg_color=self.theme["ivory"])
        body.pack(fill="both", expand=True)

        # 메인 카메라 (개인방과 동일하게 frame에 직접 표시)
        self.group_img_label = ctk.CTkLabel(body, text="")
        self.group_img_label.pack(fill="both", expand=True, padx=10, pady=10)

        # angry_goblin 오버레이 상태 (졸음 감지 시 카메라 위에 합성)
        self._group_goblin_frame_idx = 0
        self._group_goblin_visible = False
        self._group_goblin_anim_running = False
        self._group_goblin_beep_counter = 0
        self._load_goblin_frames()


        # 오른쪽: 다른 참가자 컬럼 (오버레이)
        self._group_others_label = ctk.CTkLabel(
            body, text="",
            fg_color=self.theme["ivory"],
            width=self.args.sub_width,
        )
        self._group_others_label.place(relx=1.0, rely=0.5, anchor="e", relheight=1.0)

        # 개인방과 동일한 캐릭터 UI
        char_area = ctk.CTkFrame(frame, fg_color="transparent")
        char_area.place(relx=0.05, rely=0.7, anchor="w")
        self._group_char_label = ctk.CTkLabel(char_area, text="", fg_color="transparent")
        self._group_char_label.pack()
        self._group_char_growth = ctk.CTkProgressBar(
            char_area,
            width=120,
            fg_color=self.theme["gray_hover"],
            progress_color=self.theme["pink_hover"],
        )
        self._group_char_growth.pack(pady=(2, 0))

        # 타이머 시작
        self._start_group_study_session()
        self._update_group_study_timer()

    def _update_group_study_timer(self):
        """1초마다 타이머 갱신"""
        if not getattr(self, 'group_study_state', None) or not getattr(self.group_study_state, 'running', False):
            return
        self.group_study_state.elapsed_seconds = int(time.time() - self.group_study_state.start_time)
        minutes = self.group_study_state.elapsed_seconds // 60
        seconds = self.group_study_state.elapsed_seconds % 60
        if hasattr(self, '_group_study_time_label'):
            self._group_study_time_label.configure(text=f"공부시간: {minutes:02d}:{seconds:02d}")
        self.root.after(1000, self._update_group_study_timer)

    # ── 세션 시작/종료 ───────────────────────────────────────

    def _start_group_study_session(self):
        self.group_study_state.running = True
        self.group_study_state.start_time = time.time()
        self.group_study_state.elapsed_seconds = 0
        self.group_study_state.accumulated_points = 0
        self.group_study_state.blocked_slots = set()
        # 호환성
        self._group_study_running = True
        self._group_study_start_time = time.time()
        self._group_study_elapsed_seconds = 0
        self._group_study_accumulated_points = 0
        self._group_study_blocked_slots = set()

    def _stop_group_study_session(self, save=True):
        if not self.group_study_state.running and not save:
            return

        self.group_study_state.running = False
        self._group_study_running = False

        # 고블린 오버레이 정지
        self._group_goblin_anim_running = False
        self._group_goblin_visible = False

        if save:
            self._save_study_minutes("group", self.group_study_state.elapsed_seconds)

    def _tick_group_study_growth(self):
        if not self.group_study_state.running:
            return

        self.group_study_state.elapsed_seconds = int(time.time() - self.group_study_state.start_time)
        self._group_study_elapsed_seconds = self.group_study_state.elapsed_seconds  # 호환성
        if self.group_study_state.char_idx < 0:
            return

        if self._is_focus_blocking_signal():
            self._mark_blocked_growth_slot("group", self.group_study_state.elapsed_seconds)

        add_points = self._consume_growth_points("group", self.group_study_state.elapsed_seconds)
        if add_points <= 0:
            return

        char_ref = self.group_study_state.char_id or self.group_study_state.char_idx
        self._apply_growth_points(
            char_ref,
            add_points,
            on_stage_changed=lambda _g: self._reload_group_character_overlay(),
            on_progress_updated=lambda g: self._update_growth_widgets(
                getattr(self, "_group_char_growth", None), None, g),
        )

    def _reload_group_character_overlay(self):
        """단체방 캐릭터 위젯에 프레임/성장 정보를 반영합니다."""
        self._group_char_frames = []
        self._group_char_frame_idx = 0
        self._group_char_last_tick = time.monotonic()
        self._group_char_name = ""
        self._group_char_growth_percent = 0
        self._group_char_idx = -1
        self._group_char_id = None
        self._group_char_anim_running = False
        self._group_char_anim_sets = {}
        self._group_char_current_anim = DEFAULT_ANIM
        
        # 상태 객체도 초기화
        self.group_study_state.char_frames = []
        self.group_study_state.char_frame_idx = 0
        self.group_study_state.char_last_tick = 0.0
        self.group_study_state.char_name = ""
        self.group_study_state.char_growth_percent = 0.0
        self.group_study_state.char_idx = -1
        self.group_study_state.char_id = None
        self.group_study_state.char_anim_running = False
        self.group_study_state.char_anim_sets = {}
        self.group_study_state.char_current_anim = DEFAULT_ANIM

        if hasattr(self, "_group_char_label"):
            self._group_char_label.configure(image=None)
        if hasattr(self, "_group_char_growth"):
            self._group_char_growth.set(0.0)

        selected_value = getattr(self, "_selected_char", None)
        if selected_value is None:
            return

        chars, char_idx, char_name, char_id, char_growth, anim_sets = \
            self._load_study_character(selected_value, target_w=120, tear_fallback=True)

        if not char_name:
            return

        self._group_char_name = char_name
        self._group_char_idx = char_idx
        self._group_char_id = char_id
        self._group_char_anim_sets = anim_sets
        
        self.group_study_state.char_name = char_name
        self.group_study_state.char_idx = char_idx
        self.group_study_state.char_id = char_id
        self.group_study_state.char_anim_sets = anim_sets

        growth_widget = getattr(self, "_group_char_growth", None)
        self._group_char_growth_percent, _ = self._update_growth_widgets(growth_widget, None, char_growth)
        self.group_study_state.char_growth_percent = self._group_char_growth_percent

        self._group_char_frames = anim_sets.get(DEFAULT_ANIM, [])
        self._group_char_current_anim = DEFAULT_ANIM
        self.group_study_state.char_frames = anim_sets.get(DEFAULT_ANIM, [])
        self.group_study_state.char_current_anim = DEFAULT_ANIM

        if self._group_char_frames and hasattr(self, "_group_char_label"):
            self._group_char_label.configure(image=self._group_char_frames[0])
            self._group_char_anim_running = True
            self.group_study_state.char_anim_running = True
            self._group_char_anim_tick()

        # 고블린 오버레이 애니메이션 시작 (200ms)
        self._load_goblin_frames()
        self._group_goblin_anim_running = True
        self._group_goblin_frame_idx = 0
        self._group_goblin_visible = False
        self._group_goblin_anim_tick()

    def _group_char_anim_tick(self):
        if not self.group_study_state.char_anim_running:
            return
        label = getattr(self, "_group_char_label", None)
        if label is None:
            return
        self.group_study_state.char_current_anim, self.group_study_state.char_frames, self.group_study_state.char_frame_idx = \
            self._tick_signal_anim(
                self.group_study_state.char_anim_sets,
                self.group_study_state.char_current_anim,
                self.group_study_state.char_frames,
                self.group_study_state.char_frame_idx,
                label,
                350,
                self._group_char_anim_tick,
            )
        # 호환성
        self._group_char_current_anim = self.group_study_state.char_current_anim
        self._group_char_frames = self.group_study_state.char_frames
        self._group_char_frame_idx = self.group_study_state.char_frame_idx
        self._group_char_anim_running = self.group_study_state.char_anim_running

    def _group_goblin_anim_tick(self):
        """200ms마다 졸음 감지 확인 + 고블린 프레임 전환 + 비프음 (단체방)."""
        if not getattr(self, '_group_goblin_anim_running', False):
            return

        with self._camera_signal_lock:
            current_signal = self._camera_current_signal

        is_drowsy = current_signal == "DROWSINESS"
        goblin_frames = getattr(self, '_goblin_frames', [])

        if is_drowsy and goblin_frames:
            if not self._group_goblin_visible:
                self._group_goblin_visible = True
                self._group_goblin_frame_idx = 0
                self._group_goblin_beep_counter = 0
            self._group_goblin_frame_idx = (self._group_goblin_frame_idx + 1) % len(goblin_frames)
            # 알람 패턴 재생 (≈2초, 10 × 200ms 간격)
            self._group_goblin_beep_counter += 1
            if self._group_goblin_beep_counter % 10 == 1:
                from .personal_study import _play_beep
                threading.Thread(target=_play_beep, daemon=True).start()
        else:
            if self._group_goblin_visible:
                self._group_goblin_visible = False

        self.root.after(200, self._group_goblin_anim_tick)
