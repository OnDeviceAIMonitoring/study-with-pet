"""단체방 공부 세션/UI 로직 Mixin."""

import time

import customtkinter as ctk

from config import GROUP_LIST
from services.camera_signals import DEFAULT_ANIM


class GroupStudyMixin:

    # ── 화면 빌드 ────────────────────────────────────────────

    def _build_screen_group(self):
        frame = self.screen_group
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        self.group_screen_title = ctk.CTkLabel(top, text="단체 공부", anchor="w", font=self._make_font(18))
        self.group_screen_title.pack(side="left")
        ctk.CTkButton(top, text="나가기", width=110, height=36, command=self._on_group_back,
                      font=self._make_font(14)).pack(side="right")

        self.group_img_label = ctk.CTkLabel(frame, text="")
        self.group_img_label.pack(fill="both", expand=True, padx=10, pady=10)

        # 개인방과 동일한 캐릭터 UI
        char_area = ctk.CTkFrame(frame, fg_color="transparent")
        char_area.place(relx=0.05, rely=0.7, anchor="w")
        self._group_char_label = ctk.CTkLabel(char_area, text="", fg_color="transparent")
        self._group_char_label.pack()
        self._group_char_growth = ctk.CTkProgressBar(char_area, width=120)
        self._group_char_growth.pack(pady=(2, 0))

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
