"""
캐릭터 관련 슬라이드 Mixin
- screen_char_list : 보유 캐릭터 성장 현황 (CHAR_LIST)
- screen_char_create : 캐릭터 생성 (CREATE_CHAR)
- screen_char_select : 공부 시작 전 캐릭터 선택 (SELECT_CHAR)
"""
import os

from PIL import Image
import customtkinter as ctk

from config import MAIN, SELECT_CHAR, CREATE_CHAR
from services.character_growth import STAGE_UNIT, get_stage_name_from_growth
from services.character_store import (
    find_character_index,
    load_characters,
    new_character,
    save_characters,
    touch_character,
)


class CharScreenMixin:

    # ──────────────────────────────────────────────
    # 성장도 및 성장 단계 계산/반영 함수
    # ──────────────────────────────────────────────

    def update_character_growth(self, char_ref, add_points):
        """
        char_ref: characters.json에서의 id 또는 인덱스
        add_points: 추가할 성장 포인트(초 단위로 30초당 1포인트)
        성장도는 누적 포인트로 저장 (단계 기준: STAGE_UNIT 포인트)
        단계: baby → adult → crown
        """
        chars = load_characters(self.args.name, sort_by_last_accessed=False)
        char_idx = find_character_index(chars, char_ref)
        if char_idx < 0:
            return False
        char = chars[char_idx]
        growth = int(char.get("growth", 0))
        growth += add_points
        char["growth"] = growth  # 누적 포인트로 유지 (리셋하지 않음)
        chars[char_idx] = char
        touch_character(chars, char_ref)
        save_characters(self.args.name, chars)
        return True

    # ──────────────────────────────────────────────
    # screen_char_list : 보유 캐릭터 성장 현황 (CHAR_LIST)
    # ──────────────────────────────────────────────

    def _build_screen_char_list(self):
        frame = self.screen_char_list
        self._screen_char_list_anim_running = False
        for widget in frame.winfo_children():
            widget.destroy()
        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="보유 캐릭터 (성장 현황)", anchor="w", font=self._make_font(20), text_color=self.theme["text"]).pack(side="left", padx=16)
        ctk.CTkButton(top, text="뒤로가기", width=80, height=36, font=self._make_font(14),
              command=lambda: self.show_screen(MAIN), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        middle = ctk.CTkFrame(frame, fg_color="transparent")
        middle.pack(fill="both", expand=True, padx=10, pady=10)
        characters = load_characters(self.args.name, sort_by_last_accessed=True)

        page_size = 3
        total_pages = max(1, (len(characters) + page_size - 1) // page_size)
        self._screen_char_list_page = min(self._screen_char_list_page, total_pages - 1)

        def on_prev_page():
            if self._screen_char_list_page > 0:
                self._screen_char_list_page -= 1
                self._rebuild_screen_char_list()

        def on_next_page():
            if self._screen_char_list_page < total_pages - 1:
                self._screen_char_list_page += 1
                self._rebuild_screen_char_list()

        ctk.CTkButton(middle, text="<", width=50, font=self._make_font(14),
                      command=on_prev_page, **self._exit_button_style()).pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1, uniform="card")

        ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14),
                      command=on_next_page, **self._exit_button_style()).pack(side="left", padx=(8, 0))

        visible_characters = characters[self._screen_char_list_page * page_size:(self._screen_char_list_page + 1) * page_size]
        card_width = 160
        self._screen_char_list_images = []
        self._screen_char_list_anim_data = []  # list of {"label": lbl, "frames": [...], "idx": 0}
        self._screen_char_list_anim_running = True

        for col, char in enumerate(visible_characters):
            card = ctk.CTkFrame(
                content,
                width=card_width,
                corner_radius=8,
                fg_color=self.theme["ivory"],
                border_width=1,
                border_color=self.theme["sand"],
            )
            card.grid(row=0, column=col, padx=8, pady=8, sticky="nsew")
            card.pack_propagate(False)
            card.grid_propagate(False)
            content.grid_rowconfigure(0, weight=1)

            placeholder = ctk.CTkFrame(card, height=1, corner_radius=16, fg_color=self.theme["beige"])
            placeholder.pack(pady=10, padx=8, fill="both", expand=True)
            for w in placeholder.winfo_children():
                w.destroy()

            name = char.get("name", "maltese")
            breed = char.get("breed") or name
            ctype = get_stage_name_from_growth(char.get("growth", 0))
            # 성장도에 따라 계산된 단계 폴더 이미지를 사용
            tail_dir = f"frontend/assets/characters/{breed}/{ctype}/tail"
            frames = []
            if os.path.isdir(tail_dir):
                files = sorted([f for f in os.listdir(tail_dir) if f.endswith('.png')])
                target_w, target_h = 140, int(140 * 650 / 430)
                for fn in files:
                    try:
                        pil_img = Image.open(os.path.join(tail_dir, fn)).convert("RGBA")
                        bg = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                        pil_img.thumbnail((target_w, target_h), Image.LANCZOS)
                        x = (target_w - pil_img.width) // 2
                        y = (target_h - pil_img.height) // 2
                        bg.paste(pil_img, (x, y), pil_img)
                        ctk_img = ctk.CTkImage(light_image=bg, dark_image=bg, size=(target_w, target_h))
                        frames.append(ctk_img)
                    except Exception:
                        continue
                self._screen_char_list_images.extend(frames)

            if frames:
                lbl = ctk.CTkLabel(placeholder, image=frames[0], text="")
                lbl.pack(expand=True)
                self._screen_char_list_anim_data.append({"label": lbl, "frames": frames, "idx": 0})
            else:
                ctk.CTkLabel(placeholder, text=breed,
                             font=self._make_font(16)).pack(expand=True)

            ctk.CTkLabel(card, text=name, font=self._make_font(14), text_color=self.theme["text"]).pack(pady=(6, 2))
            growth_point = int(char.get('growth', 0))
            stage_idx = min(growth_point // STAGE_UNIT, 2)
            if stage_idx >= 2:
                growth_percent = 100
                prog_value = 1.0
            else:
                growth_in_stage = growth_point - (stage_idx * STAGE_UNIT)
                growth_percent = min(100, int(growth_in_stage * 100 / STAGE_UNIT))
                prog_value = growth_in_stage / STAGE_UNIT
            stage_text = {'baby': '1단계', 'adult': '2단계', 'crown': '3단계'}.get(ctype, ctype)
            ctk.CTkLabel(card, text=f"{stage_text}", font=self._make_font(12), text_color=self.theme["text_muted"]).pack()
            ctk.CTkLabel(card, text=f"성장도: {growth_percent}%", font=self._make_font(12), text_color=self.theme["text_muted"]).pack()
            prog = ctk.CTkProgressBar(card, width=140, fg_color=self.theme["gray_hover"], progress_color=self.theme["pink_hover"])
            prog.set(prog_value)
            prog.pack(pady=(4, 2))

            # 삭제 버튼
            char_id = char.get("id")
            def _delete_char(cid=char_id):
                chars_all = load_characters(self.args.name, sort_by_last_accessed=False)
                chars_all = [c for c in chars_all if c.get("id") != cid]
                save_characters(self.args.name, chars_all)
                self._rebuild_screen_char_list()
            ctk.CTkButton(
                card, text="삭제", width=60, height=24,
                font=self._make_font(11),
                fg_color="transparent",
                hover_color=self.theme["sand"],
                text_color=self.theme["error"],
                border_width=1,
                border_color=self.theme["sand"],
                command=_delete_char,
            ).pack(pady=(0, 6))

        if self._screen_char_list_anim_data:
            self._screen_char_list_anim_tick()

    def _on_show_characters(self):
        self._screen_char_list_page = 0
        from config import CHAR_LIST
        self.show_screen(CHAR_LIST)

    def _screen_char_list_anim_tick(self):
        if not getattr(self, '_screen_char_list_anim_running', False):
            return
        for entry in self._screen_char_list_anim_data:
            entry["idx"] = (entry["idx"] + 1) % len(entry["frames"])
            try:
                entry["label"].configure(image=entry["frames"][entry["idx"]])
            except Exception:
                pass
        self.root.after(350, self._screen_char_list_anim_tick)

    def _rebuild_screen_char_list(self):
        self._screen_char_list_anim_running = False
        for widget in self.screen_char_list.winfo_children():
            widget.destroy()
        self._build_screen_char_list()

    # ──────────────────────────────────────────────
    # screen_char_create : 캐릭터 생성 (CREATE_CHAR)
    # ──────────────────────────────────────────────

    def _build_screen_char_create(self):
        frame = self.screen_char_create
        for widget in frame.winfo_children():
            widget.destroy()

        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="캐릭터 생성", anchor="w", font=self._make_font(20), text_color=self.theme["text"]).pack(side="left", padx=16)
        ctk.CTkButton(top, text="뒤로가기", width=80,height=36, font=self._make_font(14),
              command=lambda: self.show_screen(SELECT_CHAR), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        # 이름 입력 영역
        name_bar = ctk.CTkFrame(frame, fg_color="transparent")
        name_bar.pack(fill="x", padx=20, pady=(12, 0))
        ctk.CTkLabel(name_bar, text="캐릭터 이름:", font=self._make_font(14), text_color=self.theme["text"]).pack(side="left", padx=(0, 8))
        self._create_char_name_entry = ctk.CTkEntry(
            name_bar,
            placeholder_text="이름을 입력해주세요",
            height=38,
            width=240,
            font=self._make_font(13),
            **self._entry_style(),
        )
        self._create_char_name_entry.pack(side="left")
        self._create_char_name_entry.bind("<Button-1>", lambda e: self._show_keyboard(self._create_char_name_entry))
        self._create_char_error_label = ctk.CTkLabel(name_bar, text="", font=self._make_font(12), **self._error_text_style())
        self._create_char_error_label.pack(side="left", padx=(12, 0))

        middle = ctk.CTkFrame(frame, fg_color="transparent")
        middle.pack(fill="both", expand=True, padx=10, pady=10)

        char_root = "frontend/assets/characters"
        candidates = []
        for cname in os.listdir(char_root):
            baby_tail_dir = os.path.join(char_root, cname, "baby", "tail")
            if os.path.isdir(baby_tail_dir):
                pngs = sorted([f for f in os.listdir(baby_tail_dir) if f.endswith('.png')])
                if pngs:
                    candidates.append({"name": cname, "img_path": os.path.join(baby_tail_dir, pngs[0])})

        if not candidates:
            ctk.CTkLabel(middle, text="생성 가능한 캐릭터 이미지가 없습니다.",
                         font=self._make_font(16), text_color=self.theme["text_muted"]).pack(pady=40)
            return

        page_size = 3
        total_pages = max(1, (len(candidates) + page_size - 1) // page_size)
        self._screen_char_create_page = min(self._screen_char_create_page, total_pages - 1)

        def on_prev_page():
            if self._screen_char_create_page > 0:
                self._screen_char_create_page -= 1
                self._rebuild_screen_char_create()

        def on_next_page():
            if self._screen_char_create_page < total_pages - 1:
                self._screen_char_create_page += 1
                self._rebuild_screen_char_create()

        ctk.CTkButton(middle, text="<", width=50, font=self._make_font(14),
                      command=on_prev_page, **self._exit_button_style()).pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1, uniform="card")

        ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14),
                      command=on_next_page, **self._exit_button_style()).pack(side="left", padx=(8, 0))

        visible_candidates = candidates[self._screen_char_create_page * page_size:(self._screen_char_create_page + 1) * page_size]
        self._screen_char_create_images = []
        card_width = 160

        def on_card_click(idx):
            char_name = self._create_char_name_entry.get().strip()
            if not char_name:
                self._create_char_error_label.configure(text="이름을 입력해주세요.")
                return
            self._create_char_error_label.configure(text="")
            chars = load_characters(self.args.name, sort_by_last_accessed=False)
            sel_cand = visible_candidates[idx]
            chars.append(new_character(char_name, 0, breed=sel_cand["name"]))
            save_characters(self.args.name, chars)
            self.show_screen(SELECT_CHAR)

        for col, cand in enumerate(visible_candidates):
            card = ctk.CTkFrame(
                content,
                width=card_width,
                corner_radius=8,
                fg_color=self.theme["ivory"],
                border_width=1,
                border_color=self.theme["sand"],
            )
            card.grid(row=0, column=col, padx=8, pady=8, sticky="nsew")
            card.pack_propagate(False)
            card.grid_propagate(False)
            content.grid_rowconfigure(0, weight=1)
            card.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))

            def bind_all(widget, idx=col):
                widget.bind("<Button-1>", lambda e: on_card_click(idx))
                for child in getattr(widget, 'winfo_children', lambda: [])():
                    bind_all(child, idx)
            bind_all(card, col)

            placeholder = ctk.CTkFrame(card, height=1, corner_radius=16, fg_color=self.theme["beige"])
            placeholder.pack(pady=10, padx=8, fill="both", expand=True)
            placeholder.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))

            try:
                pil_img = Image.open(cand["img_path"]).convert("RGBA")
                target_w, target_h = 140, int(140 * 650 / 430)
                bg = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                pil_img.thumbnail((target_w, target_h), Image.LANCZOS)
                x = (target_w - pil_img.width) // 2
                y = (target_h - pil_img.height) // 2
                bg.paste(pil_img, (x, y), pil_img)
                ctk_img = ctk.CTkImage(light_image=bg, dark_image=bg, size=(target_w, target_h))
                img_label = ctk.CTkLabel(placeholder, image=ctk_img, text="")
                img_label.pack(expand=True)
                self._screen_char_create_images.append(ctk_img)
                img_label.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))
            except Exception:
                lbl = ctk.CTkLabel(placeholder, text=cand["name"], font=self._make_font(16))
                lbl.pack(expand=True)
                lbl.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))

            ctk.CTkLabel(card, text=cand["name"], font=self._make_font(12), text_color=self.theme["text_muted"]).pack(pady=(6, 2))

    def _rebuild_screen_char_create(self):
        for widget in self.screen_char_create.winfo_children():
            widget.destroy()
        self._build_screen_char_create()

    # ──────────────────────────────────────────────
    # screen_char_select : 공부 시작 전 캐릭터 선택 (SELECT_CHAR)
    # ──────────────────────────────────────────────

    def _build_screen_char_select(self):
        frame = self.screen_char_select
        for widget in frame.winfo_children():
            widget.destroy()

        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="캐릭터 선택", anchor="w", font=self._make_font(20), text_color=self.theme["text"]).pack(side="left", padx=16)
        ctk.CTkButton(top, text="뒤로가기", width=80, height=36, command=self._on_char_select_back,
              font=self._make_font(14), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        def on_create_character():
            self._screen_char_create_page = 0
            self.show_screen(CREATE_CHAR)
        ctk.CTkButton(top, text="캐릭터 생성", height=36, font=self._make_font(14),
              command=on_create_character, **self._primary_button_style()).pack(side="right", padx=(0, 16), pady=0)

        middle = ctk.CTkFrame(frame, fg_color="transparent")
        middle.pack(fill="both", expand=True, padx=10, pady=10)

        characters = load_characters(self.args.name, sort_by_last_accessed=True)

        page_size = 3
        total_pages = max(1, (len(characters) + page_size - 1) // page_size)
        self._screen_char_select_page = min(self._screen_char_select_page, total_pages - 1)

        def on_prev_page():
            if self._screen_char_select_page > 0:
                self._screen_char_select_page -= 1
                self._refresh_char_select()

        def on_next_page():
            if self._screen_char_select_page < total_pages - 1:
                self._screen_char_select_page += 1
                self._refresh_char_select()

        ctk.CTkButton(middle, text="<", width=50, font=self._make_font(14),
                      command=on_prev_page, **self._exit_button_style()).pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle, fg_color="transparent")
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1, uniform="card")

        ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14),
                      command=on_next_page, **self._exit_button_style()).pack(side="left", padx=(8, 0))

        visible_characters = characters[self._screen_char_select_page * page_size:(self._screen_char_select_page + 1) * page_size]
        card_width = 160
        self._screen_char_select_images = []

        if visible_characters:
            for col, char in enumerate(visible_characters):
                card = ctk.CTkFrame(
                    content,
                    width=card_width,
                    corner_radius=8,
                    fg_color=self.theme["ivory"],
                    border_width=1,
                    border_color=self.theme["sand"],
                )
                card.grid(row=0, column=col, padx=8, pady=8, sticky="nsew")
                card.pack_propagate(False)
                card.grid_propagate(False)
                content.grid_rowconfigure(0, weight=1)

                selected_char_id = char.get("id")

                def on_card_click(selected_id=selected_char_id):
                    self._enter_selected_character(selected_id)

                card.bind("<Button-1>", lambda e, fn=on_card_click: fn())

                def bind_all(widget, fn=on_card_click):
                    widget.bind("<Button-1>", lambda e: fn())
                    for child in getattr(widget, 'winfo_children', lambda: [])():
                        bind_all(child, fn)
                bind_all(card, on_card_click)

                placeholder = ctk.CTkFrame(card, height=1, corner_radius=16, fg_color=self.theme["beige"])
                placeholder.pack(pady=10, padx=8, fill="both", expand=True)
                placeholder.bind("<Button-1>", lambda e, fn=on_card_click: fn())

                name = char.get("name", "maltese")
                breed = char.get("breed") or name
                ctype = get_stage_name_from_growth(char.get("growth", 0))
                tail_dir = f"frontend/assets/characters/{breed}/{ctype}/tail"
                img_path = None
                if os.path.isdir(tail_dir):
                    files = sorted([f for f in os.listdir(tail_dir) if f.endswith('.png')])
                    if files:
                        img_path = os.path.join(tail_dir, files[0])

                if img_path and os.path.exists(img_path):
                    try:
                        pil_img = Image.open(img_path).convert("RGBA")
                        target_w, target_h = 140, int(140 * 650 / 430)
                        bg = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                        pil_img.thumbnail((target_w, target_h), Image.LANCZOS)
                        x = (target_w - pil_img.width) // 2
                        y = (target_h - pil_img.height) // 2
                        bg.paste(pil_img, (x, y), pil_img)
                        ctk_img = ctk.CTkImage(light_image=bg, dark_image=bg, size=(target_w, target_h))
                        img_label = ctk.CTkLabel(placeholder, image=ctk_img, text="")
                        img_label.pack(expand=True)
                        self._screen_char_select_images.append(ctk_img)
                        img_label.bind("<Button-1>", lambda e, fn=on_card_click: fn())
                    except Exception:
                        lbl = ctk.CTkLabel(placeholder, text=breed, font=self._make_font(16))
                        lbl.pack(expand=True)
                        lbl.bind("<Button-1>", lambda e, fn=on_card_click: fn())
                else:
                    lbl = ctk.CTkLabel(placeholder, text=breed, font=self._make_font(16))
                    lbl.pack(expand=True)
                    lbl.bind("<Button-1>", lambda e, fn=on_card_click: fn())

                ctk.CTkLabel(card, text=name, font=self._make_font(14), text_color=self.theme["text"]).pack(pady=(6, 2))
                growth_point = int(char.get('growth', 0))
                stage_idx = min(growth_point // STAGE_UNIT, 2)
                if stage_idx >= 2:
                    growth_percent = 100
                    prog_value = 1.0
                else:
                    growth_in_stage = growth_point - (stage_idx * STAGE_UNIT)
                    growth_percent = min(100, int(growth_in_stage * 100 / STAGE_UNIT))
                    prog_value = growth_in_stage / STAGE_UNIT
                stage_text = {'baby': '1단계', 'adult': '2단계', 'crown': '3단계'}.get(ctype, ctype)
                ctk.CTkLabel(card, text=f"{stage_text}", font=self._make_font(12), text_color=self.theme["text_muted"]).pack()
                ctk.CTkLabel(card, text=f"성장도: {growth_percent}%", font=self._make_font(12), text_color=self.theme["text_muted"]).pack()
                prog = ctk.CTkProgressBar(card, width=140, fg_color=self.theme["gray_hover"], progress_color=self.theme["pink_hover"])
                prog.set(prog_value)
                prog.pack(pady=8)
        else:
            ctk.CTkLabel(content, text="보유한 캐릭터가 없습니다.", font=self._make_font(16), text_color=self.theme["text_muted"]).pack(pady=40)

    def _refresh_char_select(self):
        for widget in self.screen_char_select.winfo_children():
            widget.destroy()
        self._build_screen_char_select()
