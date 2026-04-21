"""
메인 화면(screen_main) 빌드 Mixin
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

    def _build_screen_main(self):
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

        # ── 캐릭터 라벨 먼저 생성 (z-order상 버튼보다 아래로 위치) ──
        self.screen_main_characters = []
        char_list = load_characters(sort_by_last_accessed=True)

        candidates = []
        for char in char_list:
            name = char.get("name", "maltese")
            ctype = get_stage_name_from_growth(char.get("growth", 0))
            happy_dir = f"frontend/assets/characters/{name}/{ctype}/happy"
            if not os.path.isdir(happy_dir):
                continue
            pngs = sorted([f for f in os.listdir(happy_dir) if f.endswith('.png')])
            if not pngs:
                continue
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

        # ── 타이틀·버튼을 캐릭터 위에 생성 ──
        title_image_path = "frontend/assets/title.png"
        title = None
        if os.path.exists(title_image_path):
            try:
                pil_title = Image.open(title_image_path).convert("RGBA")
                max_w = min(460, max(180, canvas_w - 220))
                max_h = 120
                pil_title.thumbnail((max_w, max_h), Image.LANCZOS)
                self._screen_main_title_image = ctk.CTkImage(
                    light_image=pil_title,
                    dark_image=pil_title,
                    size=(pil_title.width, pil_title.height),
                )
                title = ctk.CTkLabel(frame, image=self._screen_main_title_image, text="")
            except Exception:
                title = None

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

        self.screen_main_anim_running = True
        self.screen_main_anim_update()

    def screen_main_anim_update(self):
        if not getattr(self, "screen_main_anim_running", False):
            return
        for c in getattr(self, "screen_main_characters", []):
            c["frame_idx"] = (c["frame_idx"] + 1) % c["frame_cnt"]
            if c["label"] is not None:
                c["label"].configure(image=c["frames"][c["frame_idx"]])
        self.root.after(200, self.screen_main_anim_update)
        is_fs = bool(self.root.attributes("-fullscreen"))
        if not is_fs:
            self.root.attributes("-fullscreen", True)
