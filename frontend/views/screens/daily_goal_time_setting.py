"""
오늘의 목표 시간 입력 화면 Mixin

메인 화면에서 '개인 공부' 또는 '단체 공부'를 오늘 처음 누르면
이 화면이 표시된다. 시간/분을 ▲▼ 버튼으로 조절하고 확인하면
다음 화면(캐릭터 선택 등)으로 이동한다.
"""

import customtkinter as ctk

from config import DAILY_GOAL, MAIN
from services.character_growth import get_stage_name_from_growth
from services.character_animation import load_character_animation_sets
from services.character_store import load_characters
from services.study_time import (
    load_daily_goal,
    save_daily_goal,
    get_consecutive_goal_days,
)


class DailyGoalTimeSettingScreenMixin:
    """'오늘의 목표 시간 입력' 화면을 구성합니다"""

    # ── 빌드 ──────────────────────────────────────────────

    def _build_screen_daily_goal(self):
        """목표 시간 입력 화면 위젯 생성"""
        frame = self.screen_daily_goal
        frame.configure(fg_color="transparent")

        # 상태 초기화
        self._daily_goal_hours = 0
        self._daily_goal_minutes = 0
        self._daily_goal_char_anim_running = False

        # ── 상단 타이틀 + 뒤로가기 ───────────────────────
        top_bar = ctk.CTkFrame(frame, fg_color="transparent")
        top_bar.pack(fill="x", padx=20, pady=(15, 5))

        title = ctk.CTkLabel(
            top_bar, text="오늘의 목표 시간 입력",
            font=self._make_font(20, "bold"),
        )
        title.pack(side="left")

        back_btn = ctk.CTkButton(
            top_bar, text="<", width=40, height=34,
            font=self._make_font(16),
            command=self._on_daily_goal_back,
        )
        back_btn.pack(side="right")

        # ── 본문 영역 (왼쪽 패널 + 오른쪽 캐릭터) ────────
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)

        # 왼쪽 설정 패널
        left_panel = ctk.CTkFrame(body, corner_radius=12)
        left_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))

        # 안내 문구
        guide_label = ctk.CTkLabel(
            left_panel,
            text="오늘의 공부 목표 시간을 설정해 주세요.",
            font=self._make_font(16),
        )
        guide_label.pack(pady=(30, 5))

        # 연속 달성 일수 (저장 키에 따라 조회)
        goal_key = getattr(self, "_daily_goal_key", self.args.name)
        streak = get_consecutive_goal_days(goal_key)
        streak_text = f"연속 달성 {streak}일째!" if streak > 0 else ""
        self._daily_goal_streak_label = ctk.CTkLabel(
            left_panel, text=streak_text,
            font=self._make_font(14),
            text_color="gray",
        )
        self._daily_goal_streak_label.pack(pady=(0, 20))

        # ── 시간/분 조절 위젯 ────────────────────────────
        spinner_frame = ctk.CTkFrame(left_panel, fg_color="transparent")
        spinner_frame.pack(pady=10)

        # 시간 스피너
        hour_col = ctk.CTkFrame(spinner_frame, fg_color="transparent")
        hour_col.pack(side="left", padx=30)

        hour_up = ctk.CTkButton(
            hour_col, text="▲", width=60, height=40,
            font=self._make_font(22),
            command=lambda: self._on_daily_goal_adjust("hour", 1),
        )
        hour_up.pack()

        self._daily_goal_hour_label = ctk.CTkLabel(
            hour_col, text="0", font=self._make_font(36, "bold"),
        )
        self._daily_goal_hour_label.pack(pady=10)

        hour_down = ctk.CTkButton(
            hour_col, text="▼", width=60, height=40,
            font=self._make_font(22),
            command=lambda: self._on_daily_goal_adjust("hour", -1),
        )
        hour_down.pack()

        # "시간" 라벨
        hour_unit = ctk.CTkLabel(
            hour_col, text="시간", font=self._make_font(14),
        )
        hour_unit.pack(pady=(5, 0))

        # 분 스피너
        min_col = ctk.CTkFrame(spinner_frame, fg_color="transparent")
        min_col.pack(side="left", padx=30)

        min_up = ctk.CTkButton(
            min_col, text="▲", width=60, height=40,
            font=self._make_font(22),
            command=lambda: self._on_daily_goal_adjust("min", 10),
        )
        min_up.pack()

        self._daily_goal_min_label = ctk.CTkLabel(
            min_col, text="0", font=self._make_font(36, "bold"),
        )
        self._daily_goal_min_label.pack(pady=10)

        min_down = ctk.CTkButton(
            min_col, text="▼", width=60, height=40,
            font=self._make_font(22),
            command=lambda: self._on_daily_goal_adjust("min", -10),
        )
        min_down.pack()

        # "분" 라벨
        min_unit = ctk.CTkLabel(
            min_col, text="분", font=self._make_font(14),
        )
        min_unit.pack(pady=(5, 0))

        # 확인 버튼
        confirm_btn = ctk.CTkButton(
            left_panel, text="공부 시작!", width=200, height=44,
            font=self._make_font(16, "bold"),
            command=self._on_daily_goal_confirm,
        )
        confirm_btn.pack(pady=(25, 30))

        # ── 오른쪽 캐릭터 애니메이션 영역 ────────────────
        right_panel = ctk.CTkFrame(body, corner_radius=12, width=220)
        right_panel.pack(side="right", fill="y", padx=(10, 0))
        right_panel.pack_propagate(False)

        self._daily_goal_char_label = ctk.CTkLabel(
            right_panel, text="캐릭터 애니메이션",
            font=self._make_font(14), text_color="gray",
        )
        self._daily_goal_char_label.pack(expand=True)

        # 캐릭터 애니메이션 로드 시도
        self._daily_goal_char_frames = []
        self._daily_goal_char_frame_idx = 0
        self._load_daily_goal_character(right_panel)

    # ── 캐릭터 애니메이션 ─────────────────────────────────

    def _load_daily_goal_character(self, parent):
        """선택된(또는 최근) 캐릭터의 happy 애니메이션을 로드"""
        chars = load_characters(sort_by_last_accessed=True)
        if not chars:
            return

        char = chars[0]
        name = char.get("name", "maltese")
        growth = char.get("growth", 0)
        stage = get_stage_name_from_growth(growth)

        anim_sets = load_character_animation_sets(
            name, stage, target_w=160, anim_names=("happy",),
        )
        frames = anim_sets.get("happy", [])
        if not frames:
            return

        self._daily_goal_char_frames = frames
        self._daily_goal_char_frame_idx = 0
        self._daily_goal_char_label.configure(
            text="", image=frames[0],
        )

        # 애니메이션 루프 시작
        self._daily_goal_char_anim_running = True
        self._daily_goal_char_anim_tick()

    def _daily_goal_char_anim_tick(self):
        """캐릭터 프레임 순환"""
        if not self._daily_goal_char_anim_running:
            return
        frames = self._daily_goal_char_frames
        if not frames:
            return
        self._daily_goal_char_frame_idx = (
            (self._daily_goal_char_frame_idx + 1) % len(frames)
        )
        self._daily_goal_char_label.configure(
            image=frames[self._daily_goal_char_frame_idx],
        )
        self.root.after(200, self._daily_goal_char_anim_tick)

    # ── 이벤트 핸들러 ─────────────────────────────────────

    def _on_daily_goal_adjust(self, unit: str, delta: int):
        """시간 또는 분 값 증감"""
        if unit == "hour":
            self._daily_goal_hours = max(0, min(23, self._daily_goal_hours + delta))
            self._daily_goal_hour_label.configure(text=str(self._daily_goal_hours))
        else:
            self._daily_goal_minutes = max(0, min(50, self._daily_goal_minutes + delta))
            self._daily_goal_min_label.configure(text=str(self._daily_goal_minutes))

    def _on_daily_goal_confirm(self):
        """목표 시간 확정 후 원래 흐름으로 복귀"""
        total_minutes = self._daily_goal_hours * 60 + self._daily_goal_minutes
        if total_minutes <= 0:
            total_minutes = 0  # 0분도 허용 (스킵과 동일)

        # 목표 시간 저장 (개인=유저명, 단체=방코드)
        goal_key = getattr(self, "_daily_goal_key", self.args.name)
        save_daily_goal(goal_key, total_minutes)

        # 애니메이션 정지
        self._daily_goal_char_anim_running = False

        # 대기 중인 원래 흐름으로 복귀
        pending = getattr(self, "_daily_goal_next_action", None)
        if pending:
            self._daily_goal_next_action = None
            pending()

    def _on_daily_goal_back(self):
        """뒤로가기 — 진입 경로에 따라 메인 또는 단체방 목록으로 복귀"""
        self._daily_goal_char_anim_running = False
        self._daily_goal_next_action = None
        # 단체방 흐름 중이면 GROUP_LIST, 아니면 MAIN으로 복귀
        if self.nav_state.pending_group_room is not None:
            self.nav_state.pending_group_room = None
            self._pending_group_room = None  # 호환성
            from config import GROUP_LIST
            self.show_screen(GROUP_LIST)
        else:
            self.show_screen(MAIN)

    def _on_daily_goal_hide(self):
        """화면 숨김 시 애니메이션 정지"""
        self._daily_goal_char_anim_running = False
