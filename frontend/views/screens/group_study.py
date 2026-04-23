"""단체방 공부 세션/UI 로직 Mixin."""

import os
import time
import threading

import customtkinter as ctk

from config import GROUP_LIST
import random as _random
from .personal_study import (
    _ENCOURAGE_MSGS, _ENCOURAGE_INTERVAL, _ENCOURAGE_SHOW_SEC,
    _WARNING_MSGS, _WARNING_SHOW_SEC,
)
from services.camera_signals import DEFAULT_ANIM
from services import socketio_client


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

        self._group_room_code_label = ctk.CTkLabel(top, text="", font=self._make_font(14), text_color=self.theme["text_muted"])
        self._group_room_code_label.pack(side="left", padx=(0, 12))

        # 공부시간 라벨 (HH:MM:SS / HH:MM:SS 형태)
        goal_min = getattr(self, '_group_server_goal_minutes', 0)
        g_total = goal_min * 60
        g_h, g_rem = divmod(g_total, 3600)
        g_m, g_s = divmod(g_rem, 60)
        goal_str = f"{g_h:02d}:{g_m:02d}:{g_s:02d}"
        self._group_goal_minutes = goal_min
        self._group_study_time_label = ctk.CTkLabel(top, text=f"공부시간: 00:00:00 / {goal_str}", font=self._make_font(14), text_color=self.theme["text_muted"])
        self._group_study_time_label.pack(side="left", padx=20)

        ctk.CTkButton(top, text="나가기", width=110, height=36, command=self._on_group_back,
              font=self._make_font(14), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        # ── 목표 시간 대비 진행 바 ──
        self._group_progress_bar = ctk.CTkProgressBar(
            frame, width=0, height=10,
            fg_color=self.theme["gray_hover"],
            progress_color="#4A90D9",
            corner_radius=0,
        )
        self._group_progress_bar.pack(fill="x", padx=0, pady=0)
        self._group_progress_bar.set(0.0)

        # ── 목표 달성 축하 라벨 (숨김 상태) ──
        self._group_congrats_label = ctk.CTkLabel(
            frame, text="",
            font=self._make_font(28, "bold"),
            text_color="#FFD700",
            fg_color="transparent",
        )

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
        self._group_char_name_label = ctk.CTkLabel(char_area, text="", font=self._make_font(13), text_color=self.theme["text"])
        self._group_char_name_label.pack(pady=(2, 0))
        self._group_char_growth = ctk.CTkProgressBar(
            char_area,
            width=120,
            fg_color=self.theme["gray_hover"],
            progress_color=self.theme["pink_hover"],
        )
        self._group_char_growth.pack(pady=(2, 0))
        self._group_char_growth_label = ctk.CTkLabel(char_area, text="", font=self._make_font(10), text_color=self.theme["text_muted"])
        self._group_char_growth_label.pack(pady=(1, 0))

        # 디버그 패널 토글 버튼
        if not hasattr(self, '_debug_panel_visible'):
            self._debug_panel_visible = True
        self._grp_debug_toggle_btn = ctk.CTkButton(
            char_area, text="Debug: ON" if self._debug_panel_visible else "Debug: OFF",
            width=110, height=32,
            font=self._make_font(12),
            fg_color="#ffffff",
            hover_color="#e0e0e0",
            text_color="#333333",
            border_width=1,
            border_color="#000000",
            corner_radius=4,
            command=self._toggle_debug_panel_group,
        )
        self._grp_debug_toggle_btn.pack(pady=(6, 0))

        # 응원/경고 말풍선
        self._grp_bubble_frame = ctk.CTkFrame(
            frame, fg_color=self.theme["gray_hover"],
            border_width=2, border_color="black",
            corner_radius=4,
        )
        self._grp_bubble_label = ctk.CTkLabel(
            self._grp_bubble_frame, text="", font=self._make_font(14),
            text_color=self.theme["text"],
            fg_color="transparent",
        )
        self._grp_bubble_label.pack(padx=14, pady=6)
        self._grp_bubble_visible = False
        self._grp_bubble_kind = None
        self._grp_last_warning_time = time.time()
        self._grp_bubble_hide_time = 0.0
        self._grp_bubble_y = 0.0
        self._grp_bubble_target_y = 0.0

        # 타이머 시작
        self._start_group_study_session()
        self._update_group_study_timer()

    def _update_group_study_timer(self):
        """1초마다 타이머 갱신 + 목표 진행바 업데이트 (서버 동기화)"""
        if not getattr(self, 'group_study_state', None) or not getattr(self.group_study_state, 'running', False):
            return

        # 서버에서 받은 공부 시간 사용 (서버에서 전체 참가자가 studying일 때만 증가)
        server_seconds = getattr(self, '_group_server_study_seconds', 0)
        server_goal = getattr(self, '_group_server_goal_minutes', getattr(self, '_group_goal_minutes', 0))
        all_studying = getattr(self, '_group_server_all_studying', True)

        # 서버 값 반영
        self.group_study_state.elapsed_seconds = server_seconds
        self._group_study_elapsed_seconds = server_seconds

        elapsed = server_seconds
        e_h, e_rem = divmod(elapsed, 3600)
        e_m, e_s = divmod(e_rem, 60)
        goal_min = server_goal if server_goal > 0 else getattr(self, '_group_goal_minutes', 0)
        g_total = goal_min * 60
        g_h, g_rem = divmod(g_total, 3600)
        g_m, g_s = divmod(g_rem, 60)
        if hasattr(self, '_group_study_time_label'):
            self._group_study_time_label.configure(text=f"공부시간: {e_h:02d}:{e_m:02d}:{e_s:02d} / {g_h:02d}:{g_m:02d}:{g_s:02d}")

        # 목표 진행바 업데이트
        if hasattr(self, '_group_progress_bar') and goal_min > 0:
            ratio = min(1.0, elapsed / (goal_min * 60))
            self._group_progress_bar.set(ratio)

        # 진행바 색상
        if getattr(self, '_group_goal_completed', False):
            if hasattr(self, '_group_progress_bar'):
                self._group_progress_bar.configure(progress_color="#FFD700")
        elif not all_studying:
            if hasattr(self, '_group_progress_bar'):
                self._group_progress_bar.configure(progress_color="#A0A0A0")
        else:
            with self._camera_signal_lock:
                sig = self._camera_current_signal
            if sig in ("DROWSINESS", "OFF_TASK", "LOW_FOCUS"):
                if hasattr(self, '_group_progress_bar'):
                    self._group_progress_bar.configure(progress_color="#D94A4A")
            else:
                if hasattr(self, '_group_progress_bar'):
                    self._group_progress_bar.configure(progress_color="#4A90D9")

        # 목표 달성 체크
        if not getattr(self, '_group_goal_completed', False) and goal_min > 0 and elapsed >= goal_min * 60:
            self._group_goal_completed = True
            self._show_group_congrats()

        self.root.after(1000, self._update_group_study_timer)

    # ── 세션 시작/종료 ───────────────────────────────────────

    def _start_group_study_session(self):
        self.group_study_state.running = True
        self.group_study_state.start_time = time.time()
        self.group_study_state.elapsed_seconds = 0
        self.group_study_state.accumulated_points = 0
        self.group_study_state.blocked_slots = set()
        self._group_goal_completed = False
        self._group_goal_flash_count = 0
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
        self._group_goal_completed = False

        # 고블린 오버레이 정지
        self._group_goblin_anim_running = False
        self._group_goblin_visible = False

        if hasattr(self, '_group_congrats_label'):
            self._group_congrats_label.place_forget()

        if save:
            self._save_study_minutes("group", self.group_study_state.elapsed_seconds)

    # ── 축하 이벤트 ─────────────────────────────────────────

    def _show_group_congrats(self):
        self._group_congrats_label.configure(
            text="축하합니다! 목표 시간을 모두 완료하였습니다!"
        )
        self._group_congrats_label.place(relx=0.5, rely=0.4, anchor="center")
        self._group_congrats_label.lift()
        self._group_goal_flash_count = 0
        if hasattr(self, '_group_progress_bar'):
            self._group_progress_bar.configure(progress_color="#FFD700")
        self._group_congrats_flash()

    def _group_congrats_flash(self):
        if not self.group_study_state.running:
            return
        self._group_goal_flash_count += 1
        if self._group_goal_flash_count > 20:
            self._group_congrats_label.configure(text_color="#FFD700")
            return
        if self._group_goal_flash_count % 2 == 0:
            self._group_congrats_label.configure(text_color="#FFD700")
        else:
            self._group_congrats_label.configure(text_color="#FFA500")
        self.root.after(400, self._group_congrats_flash)

    def _tick_group_study_growth(self):
        if not self.group_study_state.running:
            return

        # OFF_TASK 등의 시그널이 있을 때 서버에 상태 전송
        with self._camera_signal_lock:
            sig = self._camera_current_signal
        if not getattr(self, '_group_goal_completed', False):
            if sig in ("DROWSINESS", "OFF_TASK", "LOW_FOCUS"):
                socketio_client.send_study_status(self, "off_task")
            else:
                socketio_client.send_study_status(self, "studying")

        self.group_study_state.elapsed_seconds = max(0, int(
            time.time() - self.group_study_state.start_time
        ))
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
                getattr(self, "_group_char_growth", None), getattr(self, "_group_char_growth_label", None), g),
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
        if hasattr(self, "_group_char_name_label"):
            self._group_char_name_label.configure(text="")
        if hasattr(self, "_group_char_growth_label"):
            self._group_char_growth_label.configure(text="")

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
        growth_label = getattr(self, "_group_char_growth_label", None)
        self._group_char_growth_percent, _ = self._update_growth_widgets(growth_widget, growth_label, char_growth)
        self.group_study_state.char_growth_percent = self._group_char_growth_percent

        # 이름 라벨 표시
        if hasattr(self, "_group_char_name_label"):
            self._group_char_name_label.configure(text=char_name)

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
        self._grp_encourage_bubble_tick()

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

        # 목표 달성 후에는 졸음 감지 무시
        if getattr(self, '_group_goal_completed', False):
            if self._group_goblin_visible:
                self._group_goblin_visible = False
            self.root.after(200, self._group_goblin_anim_tick)
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

    # ── 디버그 패널 토글 (단체) ─────────────────────────────

    def _toggle_debug_panel_group(self):
        self._debug_panel_visible = not self._debug_panel_visible
        label = "Debug: ON" if self._debug_panel_visible else "Debug: OFF"
        self._grp_debug_toggle_btn.configure(text=label)
        # 개인 공부 버튼도 동기화
        if hasattr(self, '_debug_toggle_btn'):
            self._debug_toggle_btn.configure(text=label)
        # off_task 폰 박스 표시도 연동
        det = getattr(self, '_off_task_detector', None)
        if det is not None:
            det.cfg.setdefault("visualization", {})["draw_phone_boxes"] = self._debug_panel_visible

    def _grp_encourage_bubble_tick(self):
        """단체방 말풍선 표시/애니메이션 (200ms 틱)."""
        if not getattr(self, '_group_goblin_anim_running', False):
            return

        # 목표 달성 또는 캘리브레이션 중 말풍선 숨김
        if getattr(self, '_group_goal_completed', False) \
                or getattr(self.camera_state, 'calibrating', False):
            if self._grp_bubble_visible:
                self._grp_bubble_frame.place_forget()
                self._grp_bubble_visible = False
            self.root.after(200, self._grp_encourage_bubble_tick)
            return

        with self._camera_signal_lock:
            current_signal = self._camera_current_signal

        _now = time.time()
        is_warning = current_signal in ("DROWSINESS", "OFF_TASK", "LOW_FOCUS")

        if is_warning:
            self._grp_last_warning_time = _now
            if self._grp_bubble_visible and self._grp_bubble_kind == "encourage":
                self._grp_bubble_frame.place_forget()
                self._grp_bubble_visible = False
            if not self._grp_bubble_visible:
                msgs = _WARNING_MSGS.get(current_signal, [])
                if msgs:
                    self._grp_show_bubble(_random.choice(msgs), 0, kind="warning")
        else:
            if self._grp_bubble_visible and self._grp_bubble_kind == "warning":
                self._grp_bubble_frame.place_forget()
                self._grp_bubble_visible = False
            if not self._grp_bubble_visible and (_now - self._grp_last_warning_time) >= _ENCOURAGE_INTERVAL:
                self._grp_show_bubble(_random.choice(_ENCOURAGE_MSGS), _ENCOURAGE_SHOW_SEC, kind="encourage")
                self._grp_last_warning_time = _now

        if self._grp_bubble_visible and self._grp_bubble_kind == "encourage":
            if self._grp_bubble_y > self._grp_bubble_target_y:
                self._grp_bubble_y -= 0.015
                self._grp_bubble_frame.place_configure(rely=max(self._grp_bubble_y, self._grp_bubble_target_y))
            if _now >= self._grp_bubble_hide_time:
                self._grp_bubble_frame.place_forget()
                self._grp_bubble_visible = False

        self.root.after(200, self._grp_encourage_bubble_tick)

    def _grp_show_bubble(self, msg: str, duration: float, kind: str = "encourage"):
        """단체방 말풍선을 표시한다."""
        if kind == "warning":
            bg_color   = "#cc2222"
            text_color = "#ffffff"
            border     = "#880000"
            self._grp_bubble_y = 0.52
            self._grp_bubble_target_y = 0.52
        else:
            bg_color   = self.theme["white"]
            text_color = self.theme["text"]
            border     = "black"
            self._grp_bubble_y = 0.52
            self._grp_bubble_target_y = 0.08

        self._grp_bubble_frame.configure(fg_color=bg_color, border_color=border)
        self._grp_bubble_label.configure(text=f"  {msg}  ", text_color=text_color)
        self._grp_bubble_frame.place(relx=0.05, rely=self._grp_bubble_y, anchor="sw")
        self._grp_bubble_frame.lift()
        self._grp_bubble_visible = True
        self._grp_bubble_kind = kind
        self._grp_bubble_hide_time = time.time() + duration if duration > 0 else float('inf')
