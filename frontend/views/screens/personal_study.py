"""개인 공부 화면/성장/캐릭터 UI 로직 Mixin."""

import time
import threading

import customtkinter as ctk

from config import MAIN
from services.character_animation import load_character_animation_sets
from services.character_growth import get_stage_name_from_growth
from services.camera_signals import DEFAULT_ANIM, SIGNAL_PRIORITY, SIGNAL_TO_ANIM
from services.character_store import save_characters, touch_character


class PersonalStudyMixin:

    def _build_screen_camera(self):
        frame = self.screen_camera
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
        self._camera_char_growth.pack(pady=(2, 0))
        self._camera_char_growth_label = ctk.CTkLabel(char_area, text="0%", font=self._make_font(10))

        self._camera_char_frames = []
        self._camera_char_frame_idx = 0
        self._camera_char_anim_running = False

        # 공부 시간 측정 변수
        self._study_start_time = time.time()
        self._study_elapsed_seconds = 0
        self._study_accumulated_points = 0
        self._study_blocked_slots = set()
        self._study_timer_running = True

        # 시그널 기반 애니메이션 전환용
        self._camera_anim_sets = {}       # {"happy": [...], "tail": [...], "tear": [...]}
        self._camera_current_anim = DEFAULT_ANIM
        self._camera_signal_lock = threading.Lock()
        self._camera_current_signal = None  # 현재 감지된 시그널 이름

        self._load_camera_character_animation()
        self._update_study_timer()

    def _load_camera_character_animation(self):
        """선택된 캐릭터의 happy/tail/tear 애니메이션을 모두 프리로드, 성장도/이름도 표시"""
        self._camera_anim_sets = {}
        self._camera_char_frames = []
        self._camera_char_frame_idx = 0
        char_ref = getattr(self, "_selected_char", None)
        char_name = None
        char_growth = 0
        char_idx = -1
        chars, char_idx, char = self._resolve_character(char_ref)
        if char is not None:
            char_growth = int(char.get("growth", 0))
            char_name = char.get("name")
            self._camera_char_id = char.get("id")
            if touch_character(chars, self._camera_char_id or char_ref):
                save_characters(chars)
        else:
            self._camera_char_id = None

        if not char_name or not isinstance(char_name, str):
            self._camera_char_label.configure(image=None)
            self._camera_char_name.configure(text="")
            self._camera_char_growth.set(0.0)
            self._camera_char_growth_label.configure(text="0%")
            self._camera_char_idx = -1
            self._camera_char_id = None
            return
        self._camera_char_idx = char_idx
        # 성장도에서 단계를 계산해 해당 폴더 이미지를 로드
        char_type = get_stage_name_from_growth(char_growth)
        self._camera_anim_sets = load_character_animation_sets(
            char_name,
            char_type,
            target_w=120,
            anim_names=("happy", "tail", "tear"),
            tear_fallback_to_sad=False,
        )
        if not self._camera_anim_sets.get("tail"):
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

        target_anim = DEFAULT_ANIM
        if sig:
            # 우선순위 높은 시그널 먼저
            for s in SIGNAL_PRIORITY:
                if s == sig:
                    target_anim = SIGNAL_TO_ANIM.get(s, DEFAULT_ANIM)
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

        self._save_study_minutes("personal", self._study_elapsed_seconds)
        # 성장도는 _update_study_timer에서 30초마다 실시간으로 저장되므로 여기서 중복 저장하지 않음

        self.stop_camera()
        self._camera_char_anim_running = False
        self.show_screen(MAIN)

    def _update_study_timer(self):
        """30초마다 성장도 1포인트 추가"""
        if not self._study_timer_running:
            return

        self._study_elapsed_seconds = int(time.time() - self._study_start_time)

        # 공부 시간 표시 업데이트 (분:초)
        minutes = self._study_elapsed_seconds // 60
        seconds = self._study_elapsed_seconds % 60
        self._study_time_label.configure(text=f"공부시간: {minutes:02d}:{seconds:02d}")

        if self._is_focus_blocking_signal():
            self._mark_blocked_growth_slot("personal", self._study_elapsed_seconds)

        add_points = self._consume_growth_points("personal", self._study_elapsed_seconds)
        if add_points > 0 and hasattr(self, "_camera_char_idx") and self._camera_char_idx >= 0:
            try:
                char_ref = getattr(self, "_camera_char_id", None)
                selected_ref = char_ref if char_ref else self._camera_char_idx

                def _on_stage_changed(_growth):
                    # 성장 단계 변경됨 - 이미지 리로드
                    self._load_camera_character_animation()

                def _on_progress_updated(growth):
                    # 성장도만 업데이트
                    self._update_growth_widgets(self._camera_char_growth, self._camera_char_growth_label, growth)

                applied = self._apply_growth_points(
                    selected_ref,
                    add_points,
                    on_stage_changed=_on_stage_changed,
                    on_progress_updated=_on_progress_updated,
                )
                if not applied:
                    self.root.after(1000, self._update_study_timer)
                    return
            except Exception:
                pass

        # 1초마다 다시 호출
        self.root.after(1000, self._update_study_timer)
