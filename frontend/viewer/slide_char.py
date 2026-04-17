"""
캐릭터 관련 슬라이드 Mixin
- slide6  : (레거시) 캐릭터 선택 카드
- slide13 : 보유 캐릭터 성장 현황 (CHAR_LIST)
- slide14 : 캐릭터 생성 (CREATE_CHAR)
- slide_char_select : 공부 시작 전 캐릭터 선택 (SELECT_CHAR)
"""
import os
import json

from PIL import Image
import customtkinter as ctk

from .slides import MAIN, GROUP_LIST, SELECT_CHAR, CREATE_CHAR, PERSONAL_CAMERA


class CharSlideMixin:

    def get_selected_character(self):
        return getattr(self, '_slide6_selected', None)

    # ──────────────────────────────────────────────
    # slide6 (레거시 – 내부 참조용, 직접 표시 안 함)
    # ──────────────────────────────────────────────

    def _build_slide6(self):
        frame = self.slide6
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="캐릭터 선택 (성장시킬 캐릭터)", anchor="w", font=self._make_font(20))
        title.pack(side="left")
        back_top_btn = ctk.CTkButton(top, text="돌아가기", width=80, font=self._make_font(12),
                                     command=lambda: self.show_slide(MAIN))
        back_top_btn.pack(side="right", padx=(0, 6))

        def on_create_character():
            self._slide14_page = 0
            self.show_slide(CREATE_CHAR)
        create_btn = ctk.CTkButton(top, text="캐릭터 생성", width=110, height=32,
                                   font=self._make_font(14), command=on_create_character)
        create_btn.pack(side="right", padx=(0, 6))

        middle = ctk.CTkFrame(frame)
        middle.pack(fill="both", expand=True, padx=10, pady=10)

        try:
            with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                characters = json.load(f)
        except Exception:
            characters = []

        page_size = 3
        total_pages = max(1, (len(characters) + page_size - 1) // page_size)
        self._slide6_page = min(self._slide6_page, total_pages - 1)

        def on_prev_page():
            if self._slide6_page > 0:
                self._slide6_page -= 1
                self._rebuild_slide6()

        def on_next_page():
            if self._slide6_page < total_pages - 1:
                self._slide6_page += 1
                self._rebuild_slide6()

        back_btn = ctk.CTkButton(middle, text="<", width=50, font=self._make_font(14), command=on_prev_page)
        back_btn.pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle)
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1)

        next_btn = ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14), command=on_next_page)
        next_btn.pack(side="left", padx=(8, 0))

        visible_characters = characters[self._slide6_page * page_size:(self._slide6_page + 1) * page_size]

        card_width = 110
        self._slide6_selected = None
        self._slide6_cards = []

        def on_card_click(idx):
            self._slide6_selected = idx
            for i, c in enumerate(self._slide6_cards):
                if i == idx:
                    c.configure(border_width=4, border_color="#33aaff")
                else:
                    c.configure(border_width=0)
            self.start_camera()

        if visible_characters:
            self._slide6_images = []
            for col, char in enumerate(visible_characters):
                card = ctk.CTkFrame(content, width=card_width, corner_radius=8)
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

                placeholder = ctk.CTkFrame(card, height=1, corner_radius=16)
                placeholder.pack(pady=10, padx=8, fill="both", expand=True)
                placeholder.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))
                name = char.get("name", "maltese")
                ctype = char.get("type", "baby")
                tail_dir = f"frontend/assets/characters/{name}/{ctype}/tail"
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
                        self._slide6_images.append(ctk_img)
                        img_label.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))
                    except Exception:
                        lbl = ctk.CTkLabel(placeholder, text=char.get("display", f"캐릭터 {col+1}"),
                                           font=self._make_font(16))
                        lbl.pack(expand=True)
                        lbl.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))
                else:
                    lbl = ctk.CTkLabel(placeholder, text=char.get("display", f"캐릭터 {col+1}"),
                                       font=self._make_font(16))
                    lbl.pack(expand=True)
                    lbl.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))

                ctk.CTkLabel(card, text=char.get("name", "캐릭터 이름"), font=self._make_font(14)).pack(pady=(6, 2))
                ctk.CTkLabel(card, text=f"성장도: {char.get('growth', 0)}", font=self._make_font(12)).pack()
                prog = ctk.CTkProgressBar(card, width=140)
                prog.set(char.get('growth', 0.5))
                prog.pack(pady=8)
                self._slide6_cards.append(card)
        else:
            ctk.CTkLabel(content, text="생성된 캐릭터가 없습니다.", font=self._make_font(16)).pack(pady=40)

        self.camera_running = False
        self.camera_thread = None
        self.latest_frame = None

    def _rebuild_slide6(self):
        for widget in self.slide6.winfo_children():
            widget.destroy()
        self._build_slide6()

    # ──────────────────────────────────────────────
    # slide13 : 보유 캐릭터 성장 현황 (CHAR_LIST)
    # ──────────────────────────────────────────────

    def _build_slide13(self):
        frame = self.slide13
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="보유 캐릭터 (성장 현황)", anchor="w", font=self._make_font(20)).pack(side="left")
        ctk.CTkButton(top, text="돌아가기", width=80, font=self._make_font(12),
                      command=lambda: self.show_slide(MAIN)).pack(side="right")

        middle = ctk.CTkFrame(frame)
        middle.pack(fill="both", expand=True, padx=10, pady=10)

        try:
            with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                characters = json.load(f)
        except Exception:
            characters = []

        page_size = 3
        total_pages = max(1, (len(characters) + page_size - 1) // page_size)
        self._slide13_page = min(self._slide13_page, total_pages - 1)

        def on_prev_page():
            if self._slide13_page > 0:
                self._slide13_page -= 1
                self._rebuild_slide13()

        def on_next_page():
            if self._slide13_page < total_pages - 1:
                self._slide13_page += 1
                self._rebuild_slide13()

        ctk.CTkButton(middle, text="<", width=50, font=self._make_font(14),
                      command=on_prev_page).pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle)
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14),
                      command=on_next_page).pack(side="left", padx=(8, 0))

        visible_characters = characters[self._slide13_page * page_size:(self._slide13_page + 1) * page_size]
        card_width = 110
        self._slide13_images = []

        for col, char in enumerate(visible_characters):
            card = ctk.CTkFrame(content, width=card_width, corner_radius=8)
            card.grid(row=0, column=col, padx=8, pady=8, sticky="nsew")
            card.pack_propagate(False)
            card.grid_propagate(False)
            content.grid_rowconfigure(0, weight=1)

            placeholder = ctk.CTkFrame(card, height=1, corner_radius=16)
            placeholder.pack(pady=10, padx=8, fill="both", expand=True)
            for w in placeholder.winfo_children():
                w.destroy()

            name = char.get("name", "maltese")
            ctype = char.get("type", "baby")
            tail_dir = f"frontend/assets/characters/{name}/{ctype}/tail"
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
                    ctk.CTkLabel(placeholder, image=ctk_img, text="").pack(expand=True)
                    self._slide13_images.append(ctk_img)
                except Exception:
                    ctk.CTkLabel(placeholder, text=char.get("display", "캐릭터"),
                                 font=self._make_font(16)).pack(expand=True)
            else:
                ctk.CTkLabel(placeholder, text=char.get("display", "캐릭터"),
                             font=self._make_font(16)).pack(expand=True)

            ctk.CTkLabel(card, text=char.get("name", "캐릭터 이름"), font=self._make_font(14)).pack(pady=(6, 2))
            ctk.CTkLabel(card, text=f"성장도: {char.get('growth', 0)}", font=self._make_font(12)).pack()
            prog = ctk.CTkProgressBar(card, width=140)
            prog.set(char.get('growth', 0.5))
            prog.pack(pady=8)

    def _on_show_characters(self):
        self._slide13_page = 0
        self._rebuild_slide13()
        from .slides import CHAR_LIST
        self.show_slide(CHAR_LIST)

    def _rebuild_slide13(self):
        for widget in self.slide13.winfo_children():
            widget.destroy()
        self._build_slide13()

    # ──────────────────────────────────────────────
    # slide14 : 캐릭터 생성 (CREATE_CHAR)
    # ──────────────────────────────────────────────

    def _build_slide14(self):
        frame = self.slide14
        for widget in frame.winfo_children():
            widget.destroy()

        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="캐릭터 생성", anchor="w", font=self._make_font(20)).pack(side="left")
        ctk.CTkButton(top, text="돌아가기", width=80, font=self._make_font(12),
                      command=lambda: self.show_slide(SELECT_CHAR)).pack(side="right")

        middle = ctk.CTkFrame(frame)
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
                         font=self._make_font(16)).pack(pady=40)
            return

        page_size = 3
        total_pages = max(1, (len(candidates) + page_size - 1) // page_size)
        self._slide14_page = min(self._slide14_page, total_pages - 1)

        def on_prev_page():
            if self._slide14_page > 0:
                self._slide14_page -= 1
                self._rebuild_slide14()

        def on_next_page():
            if self._slide14_page < total_pages - 1:
                self._slide14_page += 1
                self._rebuild_slide14()

        ctk.CTkButton(middle, text="<", width=50, font=self._make_font(14),
                      command=on_prev_page).pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle)
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14),
                      command=on_next_page).pack(side="left", padx=(8, 0))

        visible_candidates = candidates[self._slide14_page * page_size:(self._slide14_page + 1) * page_size]
        self._slide14_images = []
        card_width = 110

        def on_card_click(idx):
            try:
                with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                    chars = json.load(f)
            except Exception:
                chars = []
            sel_cand = visible_candidates[idx]
            if any(c.get("name") == sel_cand["name"] for c in chars):
                self._show_info_dialog("중복 생성", f"{sel_cand['name']} 캐릭터는\n이미 생성되어 있습니다.")
                return
            chars.append({"name": sel_cand["name"], "type": "baby", "growth": 0.0})
            with open("frontend/user/characters.json", "w", encoding="utf-8") as f:
                json.dump(chars, f, ensure_ascii=False, indent=2)
            self._rebuild_slide6()

        for col, cand in enumerate(visible_candidates):
            card = ctk.CTkFrame(content, width=card_width, corner_radius=8)
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

            placeholder = ctk.CTkFrame(card, height=1, corner_radius=16)
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
                self._slide14_images.append(ctk_img)
                img_label.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))
            except Exception:
                lbl = ctk.CTkLabel(placeholder, text=cand["name"], font=self._make_font(16))
                lbl.pack(expand=True)
                lbl.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))

            ctk.CTkLabel(card, text=cand["name"], font=self._make_font(14)).pack(pady=(6, 2))

    def _rebuild_slide14(self):
        for widget in self.slide14.winfo_children():
            widget.destroy()
        self._build_slide14()

    # ──────────────────────────────────────────────
    # slide_char_select : 공부 시작 전 캐릭터 선택 (SELECT_CHAR)
    # ──────────────────────────────────────────────

    def _build_char_select_slide(self):
        frame = self.slide_char_select
        for widget in frame.winfo_children():
            widget.destroy()

        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="캐릭터 선택", anchor="w", font=self._make_font(20, "bold")).pack(side="left")
        ctk.CTkButton(top, text="←", width=40, command=self._on_char_select_back,
                      font=self._make_font(14)).pack(side="right", padx=(0, 6))

        def on_create_character():
            self._slide14_page = 0
            self.show_slide(CREATE_CHAR)
        ctk.CTkButton(top, text="캐릭터 생성", width=110, height=32, font=self._make_font(14),
                      command=on_create_character).pack(side="right", padx=(0, 6))

        middle = ctk.CTkFrame(frame)
        middle.pack(fill="both", expand=True, padx=10, pady=10)

        try:
            with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                characters = json.load(f)
        except Exception:
            characters = []

        page_size = 3
        total_pages = max(1, (len(characters) + page_size - 1) // page_size)
        self._char_select_page = min(self._char_select_page, total_pages - 1)

        def on_prev_page():
            if self._char_select_page > 0:
                self._char_select_page -= 1
                self._refresh_char_select()

        def on_next_page():
            if self._char_select_page < total_pages - 1:
                self._char_select_page += 1
                self._refresh_char_select()

        ctk.CTkButton(middle, text="<", width=50, font=self._make_font(14),
                      command=on_prev_page).pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle)
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14),
                      command=on_next_page).pack(side="left", padx=(8, 0))

        visible_characters = characters[self._char_select_page * page_size:(self._char_select_page + 1) * page_size]
        card_width = 110
        self._char_select_images = []

        if visible_characters:
            for col, char in enumerate(visible_characters):
                card = ctk.CTkFrame(content, width=card_width, corner_radius=8)
                card.grid(row=0, column=col, padx=8, pady=8, sticky="nsew")
                card.pack_propagate(False)
                card.grid_propagate(False)
                content.grid_rowconfigure(0, weight=1)

                def on_card_click(n=char.get("name")):
                    self._selected_char = n
                    self.start_camera()
                    pending = getattr(self, "_pending_group_room", None)
                    if pending:
                        self._pending_group_room = None
                        self._enter_group_room(*pending)
                    else:
                        self.show_slide(PERSONAL_CAMERA)

                card.bind("<Button-1>", lambda e, fn=on_card_click: fn())

                def bind_all(widget, fn=on_card_click):
                    widget.bind("<Button-1>", lambda e: fn())
                    for child in getattr(widget, 'winfo_children', lambda: [])():
                        bind_all(child, fn)
                bind_all(card, on_card_click)

                placeholder = ctk.CTkFrame(card, height=1, corner_radius=16)
                placeholder.pack(pady=10, padx=8, fill="both", expand=True)
                placeholder.bind("<Button-1>", lambda e, fn=on_card_click: fn())

                name = char.get("name", "maltese")
                ctype = char.get("type", "baby")
                tail_dir = f"frontend/assets/characters/{name}/{ctype}/tail"
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
                        self._char_select_images.append(ctk_img)
                        img_label.bind("<Button-1>", lambda e, fn=on_card_click: fn())
                    except Exception:
                        lbl = ctk.CTkLabel(placeholder, text=char.get("display", name), font=self._make_font(16))
                        lbl.pack(expand=True)
                        lbl.bind("<Button-1>", lambda e, fn=on_card_click: fn())
                else:
                    lbl = ctk.CTkLabel(placeholder, text=char.get("display", name), font=self._make_font(16))
                    lbl.pack(expand=True)
                    lbl.bind("<Button-1>", lambda e, fn=on_card_click: fn())

                ctk.CTkLabel(card, text=char.get("name", "캐릭터 이름"), font=self._make_font(14)).pack(pady=(6, 2))
                ctk.CTkLabel(card, text=f"성장도: {char.get('growth', 0)}", font=self._make_font(12)).pack()
                prog = ctk.CTkProgressBar(card, width=140)
                prog.set(char.get('growth', 0.5))
                prog.pack(pady=8)
        else:
            ctk.CTkLabel(content, text="보유한 캐릭터가 없습니다.", font=self._make_font(16)).pack(pady=40)

    def _on_char_select_back(self):
        if self._pending_group_room is not None:
            self._pending_group_room = None
            self.show_slide(GROUP_LIST)
        else:
            self.show_slide(MAIN)

    def _refresh_char_select(self):
        for widget in self.slide_char_select.winfo_children():
            widget.destroy()
        self._build_char_select_slide()

    def _on_personal_study(self):
        self.show_slide(SELECT_CHAR)
