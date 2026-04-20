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
        # 오늘 목표 시간 미설정이면 목표 입력 화면으로 이동
        if load_daily_goal(self.args.name) is None:
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
        btn_top_y = 70
        btn_bottom_y = btn_top_y + len(buttons) * 72 + 30

        possible_areas = [
            (0, btn_top_y, btn_left - 5, btn_bottom_y - btn_top_y),
            (btn_right + 5, btn_top_y, canvas_w - btn_right - 5, btn_bottom_y - btn_top_y),
        ]

        # ── 캐릭터 라벨 먼저 생성 (z-order상 버튼보다 아래로 위치) ──
        self.screen_main_characters = []
        char_list = load_characters(sort_by_last_accessed=True)

        valid_areas = [a for a in possible_areas if a[2] >= char_w and a[3] >= char_h]
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

        random.shuffle(candidates)
        shuffled_areas = list(valid_areas)
        random.shuffle(shuffled_areas)
        for i, (char_data, area) in enumerate(zip(candidates, shuffled_areas)):
            x0, y0, w, h = area
            px = x0 + random.randint(0, max(0, w - char_w))
            py = y0 + random.randint(0, max(0, h - char_h))
            frames = char_data["frames"]
            lbl = ctk.CTkLabel(frame, image=frames[0], text="", fg_color="transparent")
            lbl.place(x=px, y=py)
            self.screen_main_characters.append({
                "frames": frames,
                "frame_idx": random.randint(0, len(frames) - 1),
                "frame_cnt": len(frames),
                "label": lbl,
            })

        # ── 타이틀·버튼을 캐릭터 위에 생성 ──
        title = ctk.CTkLabel(frame, text="Study With Pet", font=self._make_font(36))
        title.grid(row=0, column=0, pady=(40, 20))

        self.screen_main_buttons = []
        for i, (label, cmd) in enumerate(buttons, start=1):
            btn = ctk.CTkButton(frame, text=label, width=600, height=48, command=cmd, font=self._make_font(16))
            btn.grid(row=i, column=0, pady=12, padx=20)
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
