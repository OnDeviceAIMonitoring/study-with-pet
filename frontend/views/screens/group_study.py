"""단체방 공부 세션 로직 Mixin."""

import time

import customtkinter as ctk

from services.character_animation import load_character_animation_sets
from services.camera_signals import DEFAULT_ANIM, SIGNAL_PRIORITY, SIGNAL_TO_ANIM
from services.character_growth import get_stage_name_from_growth


class GroupStudyMixin:

    def _start_group_study_session(self):
        self._group_study_running = True
        self._group_study_start_time = time.time()
        self._group_study_elapsed_seconds = 0
        self._group_study_accumulated_points = 0
        self._group_study_blocked_slots = set()

    def _stop_group_study_session(self, save=True):
        if not self._group_study_running and not save:
            return

        self._group_study_running = False

        if save:
            self._save_study_minutes("group", self._group_study_elapsed_seconds)

    def _tick_group_study_growth(self):
        if not self._group_study_running:
            return

        self._group_study_elapsed_seconds = int(time.time() - self._group_study_start_time)
        if getattr(self, "_group_char_idx", -1) < 0:
            return

        if self._is_focus_blocking_signal():
            self._mark_blocked_growth_slot("group", self._group_study_elapsed_seconds)

        add_points = self._consume_growth_points("group", self._group_study_elapsed_seconds)
        if add_points <= 0:
            return

        char_ref = getattr(self, "_group_char_id", self._group_char_idx)
        updated = self._apply_growth_points(char_ref, add_points)
        if updated:
            # 개인/그룹 동일 정책 적용 후 단체방 오버레이 반영
            self._reload_group_character_overlay()

    def _reload_group_character_overlay(self):
        """단체방 캐릭터 위젯(개인방과 동일한 UI)에 프레임/성장 정보를 반영합니다."""
        self._group_char_frames = []
        self._group_char_frame_idx = 0
        self._group_char_last_tick = time.monotonic()
        self._group_char_name = ""
        self._group_char_growth_percent = 0
        self._group_char_idx = -1
        self._group_char_id = None
        self._group_char_anim_running = False
        self._group_char_anim_sets = {}
        self._group_char_current_anim = "tail"

        if hasattr(self, "_group_char_label"):
            self._group_char_label.configure(image=None)
        if hasattr(self, "_group_char_growth"):
            self._group_char_growth.set(0.0)

        selected_value = getattr(self, "_selected_char", None)
        if selected_value is None:
            return

        _, selected_idx, selected = self._resolve_character(selected_value)
        if selected is None:
            return

        self._group_char_name = selected.get("name", "")
        self._group_char_idx = selected_idx
        self._group_char_id = selected.get("id")
        growth_points = int(selected.get("growth", 0))
        growth_widget = self._group_char_growth if hasattr(self, "_group_char_growth") else None
        self._group_char_growth_percent, _ = self._update_growth_widgets(growth_widget, None, growth_points)
        ctype = get_stage_name_from_growth(growth_points)

        self._group_char_anim_sets = load_character_animation_sets(
            self._group_char_name,
            ctype,
            target_w=120,
            anim_names=("happy", "tail", "tear"),
            tear_fallback_to_sad=True,
        )

        self._group_char_frames = self._group_char_anim_sets.get("tail", [])
        self._group_char_current_anim = "tail"

        if self._group_char_frames and hasattr(self, "_group_char_label"):
            self._group_char_label.configure(image=self._group_char_frames[0])
            self._group_char_anim_running = True
            self._group_char_anim_tick()

    def _group_char_anim_tick(self):
        if not self._group_char_anim_running:
            return

        sig = getattr(self, "_camera_current_signal", None)
        target_anim = DEFAULT_ANIM
        if sig:
            for s in SIGNAL_PRIORITY:
                if s == sig:
                    target_anim = SIGNAL_TO_ANIM.get(s, DEFAULT_ANIM)
                    break

        if target_anim != self._group_char_current_anim:
            new_frames = self._group_char_anim_sets.get(target_anim, [])
            if new_frames:
                self._group_char_current_anim = target_anim
                self._group_char_frames = new_frames
                self._group_char_frame_idx = 0

        if not self._group_char_frames:
            self.root.after(500, self._group_char_anim_tick)
            return

        self._group_char_frame_idx = (self._group_char_frame_idx + 1) % len(self._group_char_frames)
        try:
            if hasattr(self, "_group_char_label"):
                self._group_char_label.configure(image=self._group_char_frames[self._group_char_frame_idx])
        except Exception:
            pass
        self.root.after(350, self._group_char_anim_tick)
