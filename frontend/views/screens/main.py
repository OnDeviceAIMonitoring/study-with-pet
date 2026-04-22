"""
메인 화면(screen_main) 빌드 Mixin
— 이미지/애니 프레임은 캐시하여 재사용, 위젯만 갱신
"""
import os
import random

from PIL import Image
import customtkinter as ctk

from config import MAIN, SELECT_CHAR, DAILY_GOAL
from services.character_growth import get_stage_name_from_growth
from services.character_store import load_characters
from services.study_time import load_daily_goal


class MainScreenMixin:

    # ── 캐시 초기화 (최초 1회) ──

    def _ensure_main_cache(self):
        """캐시 딕셔너리가 없으면 초기화"""
        if not hasattr(self, "_main_anim_cache"):
            self._main_anim_cache = {}   # (name, stage, w, h) → [CTkImage]
        if not hasattr(self, "_main_title_cache"):
            self._main_title_cache = None  # CTkImage
        if not hasattr(self, "_main_anim_gen"):
            self._main_anim_gen = 0  # 세대 카운터로 이전 타이머 무효화

    # ── 이벤트 핸들러 ──

    def _on_personal_study(self):
        # 개인 목표: 유저명 기준으로 오늘 미설정 시 목표 입력 화면 표시
        if load_daily_goal(self.args.name) is None:
            self._daily_goal_key = self.args.name  # 저장 키: 유저명
            self._daily_goal_next_action = self._on_personal_study_continue
            self.show_screen(DAILY_GOAL)
            return
        self._on_personal_study_continue()

    def _on_personal_study_continue(self):
        """목표 설정 완료 후 캐릭터 선택 화면으로 이동"""
        self.show_screen(SELECT_CHAR)

    # ── 캐시된 애니메이션 프레임 로드 ──

    def _load_main_char_frames(self, name, stage, char_w, char_h):
        """캐릭터 happy 프레임을 캐시에서 반환, 없으면 로드 후 캐싱"""
        self._ensure_main_cache()
        cache_key = (name, stage, char_w, char_h)
        if cache_key in self._main_anim_cache:
            return self._main_anim_cache[cache_key]

        happy_dir = f"frontend/assets/characters/{name}/{stage}/happy"
        if not os.path.isdir(happy_dir):
            return []
        pngs = sorted([f for f in os.listdir(happy_dir) if f.endswith('.png')])
        if not pngs:
            return []

        frames = []
        for fn in pngs:
            try:
                pil_img = Image.open(os.path.join(happy_dir, fn)).convert("RGBA")
                bg = Image.new("RGBA", (char_w, char_h), (0, 0, 0, 0))
                pil_img.thumbnail((char_w, char_h), Image.LANCZOS)
                ox = (char_w - pil_img.width) // 2
                oy = (char_h - pil_img.height) // 2
                bg.paste(pil_img, (ox, oy), pil_img)
                ctk_img = ctk.CTkImage(light_image=bg, dark_image=bg, size=(char_w, char_h))
                frames.append(ctk_img)
            except Exception:
                continue

        if frames:
            self._main_anim_cache[cache_key] = frames
        return frames

    def _load_main_title_image(self, canvas_w):
        """타이틀 이미지를 캐시에서 반환, 없으면 로드 후 캐싱"""
        self._ensure_main_cache()
        if self._main_title_cache is not None:
            return self._main_title_cache

        title_image_path = "frontend/assets/title.png"
        if not os.path.exists(title_image_path):
            return None
        try:
            pil_title = Image.open(title_image_path).convert("RGBA")
            max_w = min(460, max(180, canvas_w - 220))
            max_h = 120
            pil_title.thumbnail((max_w, max_h), Image.LANCZOS)
            img = ctk.CTkImage(
                light_image=pil_title,
                dark_image=pil_title,
                size=(pil_title.width, pil_title.height),
            )
            self._main_title_cache = img
            return img
        except Exception:
            return None

    # ── 화면 빌드 (위젯만 생성, 이미지는 캐시 사용) ──

    def _build_screen_main(self):
        self._ensure_main_cache()
        frame = self.screen_main
        frame.grid_columnconfigure(0, weight=1)

        buttons = [
            ("개인 공부", self._on_personal_study),
            ("단체 공부", self._on_group_study),
            ("보유 캐릭터 (성장 현황)", self._on_show_characters),
            ("나가기", self.root.quit),
        ]

        canvas_w = self.args.canvas_width
        canvas_h = self.args.canvas_height
        char_w = 120
        char_h = int(char_w * 650 / 430)

        btn_center_x = canvas_w // 2
        btn_left = btn_center_x - 310
        btn_right = btn_center_x + 310

        left_area_w = max(0, btn_left - 5)
        right_area_x = btn_right + 5
        right_area_w = max(0, canvas_w - right_area_x)

        fixed_slots = []
        center_y = max(0, (canvas_h - char_h) // 2)
        if left_area_w >= char_w:
            left_x = max(0, (left_area_w - char_w) // 2)
            fixed_slots.append((left_x, center_y))
        if right_area_w >= char_w:
            right_x = right_area_x + max(0, (right_area_w - char_w) // 2)
            fixed_slots.append((right_x, center_y))

        # ── 캐릭터 라벨 (캐시된 프레임 사용) ──
        self.screen_main_characters = []
        char_list = load_characters(self.args.name, sort_by_last_accessed=True)

        candidates = []
        for char in char_list:
            name = char.get("breed", "maltese")
            stage = get_stage_name_from_growth(char.get("growth", 0))
            frames = self._load_main_char_frames(name, stage, char_w, char_h)
            if frames:
                candidates.append({"frames": frames})

        for i, (char_data, slot) in enumerate(zip(candidates, fixed_slots)):
            px, py = slot
            frames = char_data["frames"]
            lbl = ctk.CTkLabel(frame, image=frames[0], text="", fg_color="transparent")
            lbl.place(x=px, y=py)
            self.screen_main_characters.append({
                "frames": frames,
                "frame_idx": random.randint(0, len(frames) - 1),
                "frame_cnt": len(frames),
                "label": lbl,
            })

        # 상/하단 spacer row를 둬서 중앙 정렬
        top_spacer_row = 0
        title_row = 1
        first_button_row = 2
        bottom_spacer_row = first_button_row + len(buttons)
        frame.grid_rowconfigure(top_spacer_row, weight=1)
        frame.grid_rowconfigure(bottom_spacer_row, weight=1)

        # ── 타이틀 (캐시된 이미지 사용) ──
        title_img = self._load_main_title_image(canvas_w)
        title = None
        if title_img is not None:
            self._screen_main_title_image = title_img
            title = ctk.CTkLabel(frame, image=title_img, text="")
        if title is None:
            title = ctk.CTkLabel(
                frame,
                text="Study With Pet",
                font=self._make_font(36),
                text_color=self.theme["text"],
            )
        title.grid(row=title_row, column=0, pady=(0, 20))

        self.screen_main_buttons = []
        for i, (label, cmd) in enumerate(buttons):
            btn_style = self._primary_button_style() if label != "나가기" else self._exit_button_style()
            btn = ctk.CTkButton(
                frame,
                text=label,
                width=600,
                height=48,
                command=cmd,
                font=self._make_font(16),
                **btn_style,
            )
            btn.grid(row=first_button_row + i, column=0, pady=12, padx=20)
            self.screen_main_buttons.append(btn)

        # 세대 카운터 증가 → 이전 타이머 콜백 자동 무효화
        self._main_anim_gen += 1
        self.screen_main_anim_running = True
        self._screen_main_anim_tick(self._main_anim_gen)

    # ── 애니메이션 (세대 카운터로 중복 방지) ──

    def _screen_main_anim_tick(self, gen):
        """세대(gen)가 현재와 일치할 때만 실행 — 이전 타이머는 자동 폐기"""
        if gen != getattr(self, "_main_anim_gen", -1):
            return
        if not getattr(self, "screen_main_anim_running", False):
            return
        for c in getattr(self, "screen_main_characters", []):
            c["frame_idx"] = (c["frame_idx"] + 1) % c["frame_cnt"]
            if c["label"] is not None:
                c["label"].configure(image=c["frames"][c["frame_idx"]])
        self.root.after(200, self._screen_main_anim_tick, gen)
        is_fs = bool(self.root.attributes("-fullscreen"))
        if not is_fs:
            self.root.attributes("-fullscreen", True)

    def _stop_main_anim(self):
        """MAIN 화면을 떠날 때 애니메이션 정지"""
        self.screen_main_anim_running = False
