"""개인 공부 화면/성장/캐릭터 UI 로직 Mixin."""

import time
import threading

import customtkinter as ctk

from config import MAIN
from services.camera_signals import DEFAULT_ANIM
from services.character_store import save_characters, touch_character


class PersonalStudyMixin:

    # ── 세션 시작/종료 ───────────────────────────────────────

    def _start_personal_study_session(self):
        self.personal_study_state.timer_running = True
        self.personal_study_state.start_time = time.time()
        self.personal_study_state.elapsed_seconds = 0
        self.personal_study_state.accumulated_points = 0
        self.personal_study_state.blocked_slots = set()
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

    # ── 화면 빌드 ────────────────────────────────────────────

    def _build_screen_camera(self):
        frame = self.screen_camera
        # 상단바: 테두리/둥근 모서리/여백 없이 사각형, 배경색도 전체 배경과 동일하게
        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="개인 공부 - 카메라", anchor="w", font=self._make_font(18), text_color=self.theme["text"]).pack(side="left")

        # 공부 시간 표시
        self._study_time_label = ctk.CTkLabel(top, text="공부시간: 00:00", font=self._make_font(14), text_color=self.theme["text_muted"])
        self._study_time_label.pack(side="left", padx=20)

        ctk.CTkButton(top, text="나가기", width=110, height=36, command=self._on_camera_back,
                  font=self._make_font(14), **self._exit_button_style()).pack(side="right", pady=0)

        # 카메라 피드 라벨
        self.img_label = ctk.CTkLabel(frame, text="")
        self.img_label.pack(fill="both", expand=True, padx=10, pady=10)

        # 캐릭터 애니메이션 + 성장도 바 영역
        char_area = ctk.CTkFrame(frame, fg_color="transparent")
        char_area.place(relx=0.05, rely=0.7, anchor="w")

        self._camera_char_label = ctk.CTkLabel(char_area, text="", fg_color="transparent")
        self._camera_char_label.pack()
        self._camera_char_name = ctk.CTkLabel(char_area, text="", font=self._make_font(14, "bold"), text_color=self.theme["text"])
        self._camera_char_growth = ctk.CTkProgressBar(char_area, width=120)
        self._camera_char_growth.pack(pady=(2, 0))
        self._camera_char_growth_label = ctk.CTkLabel(char_area, text="0%", font=self._make_font(10), text_color=self.theme["text_muted"])

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
        self.show_screen(MAIN)

    # ── 성장 틱 / 타이머 ────────────────────────────────────

    def _tick_personal_study_growth(self):
        """개인 공부 성장 포인트 소비 + 반영."""
        if self._is_focus_blocking_signal():
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
        """1초마다 타이머 갱신 + 성장 틱."""
        if not self.personal_study_state.timer_running:
            return

        self.personal_study_state.elapsed_seconds = int(time.time() - self.personal_study_state.start_time)
        self._study_elapsed_seconds = self.personal_study_state.elapsed_seconds  # 호환성
        minutes = self.personal_study_state.elapsed_seconds // 60
        seconds = self.personal_study_state.elapsed_seconds % 60
        self._study_time_label.configure(text=f"공부시간: {minutes:02d}:{seconds:02d}")

        self._tick_personal_study_growth()
        self.root.after(1000, self._update_study_timer)
