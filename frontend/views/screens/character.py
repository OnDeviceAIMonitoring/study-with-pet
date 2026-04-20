"""
캐릭터 관련 슬라이드 Mixin
- screen_char_legacy  : (레거시) 캐릭터 선택 카드
- screen_char_list : 보유 캐릭터 성장 현황 (CHAR_LIST)
- screen_char_create : 캐릭터 생성 (CREATE_CHAR)
- screen_char_select : 공부 시작 전 캐릭터 선택 (SELECT_CHAR)
"""
import os

from PIL import Image
import customtkinter as ctk

from config import MAIN, GROUP_LIST, SELECT_CHAR, CREATE_CHAR, PERSONAL_CAMERA
from services.character_growth import get_stage_name_from_growth
from services.character_store import (
    find_character_index,
    load_characters,
    new_character,
    save_characters,
    touch_character,
)


class CharScreenMixin:

    def get_selected_character(self):
        return getattr(self, '_screen_char_legacy_selected', None)

    # ──────────────────────────────────────────────
    # 성장도 및 성장 단계 계산/반영 함수
    # ──────────────────────────────────────────────

    def update_character_growth(self, char_ref, add_points):
        """
        char_ref: characters.json에서의 id 또는 인덱스
        add_points: 추가할 성장 포인트(초 단위로 30초당 1포인트)
        성장도는 누적 포인트로 저장 (0~119: baby, 120~239: adult, 240+: crown)
        단계: baby → adult → crown
        """
        chars = load_characters(sort_by_last_accessed=False)
        char_idx = find_character_index(chars, char_ref)
        if char_idx < 0:
            return False
        char = chars[char_idx]
        growth = int(char.get("growth", 0))
        growth += add_points
        char["growth"] = growth  # 누적 포인트로 유지 (리셋하지 않음)
        chars[char_idx] = char
        touch_character(chars, char_ref)
        save_characters(chars)
        return True

    # ──────────────────────────────────────────────
    # screen_char_legacy (레거시 – 내부 참조용, 직접 표시 안 함)
    # ──────────────────────────────────────────────

    def _build_screen_char_legacy(self):
        frame = self.screen_char_legacy
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="캐릭터 선택 (성장시킬 캐릭터)", anchor="w", font=self._make_font(20))
        title.pack(side="left")
        back_top_btn = ctk.CTkButton(top, text="돌아가기", width=80, font=self._make_font(12),
                                     command=lambda: self.show_screen(MAIN))
        back_top_btn.pack(side="right", padx=(0, 6))

        def on_create_character():
            self._screen_char_create_page = 0
            self.show_screen(CREATE_CHAR)
        create_btn = ctk.CTkButton(top, text="캐릭터 생성", width=110, height=32,
                                   font=self._make_font(14), command=on_create_character)
        create_btn.pack(side="right", padx=(0, 6))

        middle = ctk.CTkFrame(frame)
        middle.pack(fill="both", expand=True, padx=10, pady=10)

        characters = load_characters(sort_by_last_accessed=True)

        page_size = 3
        total_pages = max(1, (len(characters) + page_size - 1) // page_size)
        self._screen_char_legacy_page = min(self._screen_char_legacy_page, total_pages - 1)

        def on_prev_page():
            if self._screen_char_legacy_page > 0:
                self._screen_char_legacy_page -= 1
                self._rebuild_screen_char_legacy()

        def on_next_page():
            if self._screen_char_legacy_page < total_pages - 1:
                self._screen_char_legacy_page += 1
                self._rebuild_screen_char_legacy()

        back_btn = ctk.CTkButton(middle, text="<", width=50, font=self._make_font(14), command=on_prev_page)
        back_btn.pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle)
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1, uniform="card")

        next_btn = ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14), command=on_next_page)
        next_btn.pack(side="left", padx=(8, 0))

        visible_characters = characters[self._screen_char_legacy_page * page_size:(self._screen_char_legacy_page + 1) * page_size]

        card_width = 160
        self._screen_char_legacy_selected = None
        self._screen_char_legacy_cards = []

        def on_card_click(idx):
            self._screen_char_legacy_selected = idx
            selected = visible_characters[idx]
            selected_id = selected.get("id")
            if selected_id:
                self._selected_char = selected_id
                chars = load_characters(sort_by_last_accessed=False)
                if touch_character(chars, selected_id):
                    save_characters(chars)
            for i, c in enumerate(self._screen_char_legacy_cards):
                if i == idx:
                    c.configure(border_width=4, border_color="#33aaff")
                else:
                    c.configure(border_width=0)
            self.start_camera()

        if visible_characters:
            self._screen_char_legacy_images = []
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
                ctype = get_stage_name_from_growth(char.get("growth", 0))
                # 성장도에 따라 계산된 단계 폴더 이미지를 사용
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
                        self._screen_char_legacy_images.append(ctk_img)
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
                growth_point = int(char.get('growth', 0))
                stage_idx = min(growth_point // 120, 2)
                if stage_idx >= 2:
                    growth_percent = 100
                    prog_value = 1.0
                else:
                    growth_in_stage = growth_point - (stage_idx * 120)
                    growth_percent = min(100, int(growth_in_stage * 100 / 120))
                    prog_value = growth_in_stage / 120
                ctk.CTkLabel(card, text=f"성장도: {growth_percent}%", font=self._make_font(12)).pack()
                prog = ctk.CTkProgressBar(card, width=140)
                prog.set(prog_value)
                prog.pack(pady=8)
                self._screen_char_legacy_cards.append(card)
        else:
            ctk.CTkLabel(content, text="생성된 캐릭터가 없습니다.", font=self._make_font(16)).pack(pady=40)

        self.camera_running = False
        self.camera_thread = None
        self.latest_frame = None

    def _rebuild_screen_char_legacy(self):
        for widget in self.screen_char_legacy.winfo_children():
            widget.destroy()
        self._build_screen_char_legacy()

    # ──────────────────────────────────────────────
    # screen_char_list : 보유 캐릭터 성장 현황 (CHAR_LIST)
    # ──────────────────────────────────────────────

    def _build_screen_char_list(self):
        frame = self.screen_char_list
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="보유 캐릭터 (성장 현황)", anchor="w", font=self._make_font(20)).pack(side="left")
        ctk.CTkButton(top, text="돌아가기", width=80, font=self._make_font(12),
                      command=lambda: self.show_screen(MAIN)).pack(side="right")

        middle = ctk.CTkFrame(frame)
        middle.pack(fill="both", expand=True, padx=10, pady=10)

        characters = load_characters(sort_by_last_accessed=True)

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
                      command=on_prev_page).pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle)
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1, uniform="card")

        ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14),
                      command=on_next_page).pack(side="left", padx=(8, 0))

        visible_characters = characters[self._screen_char_list_page * page_size:(self._screen_char_list_page + 1) * page_size]
        card_width = 160
        self._screen_char_list_images = []
        self._screen_char_list_anim_data = []  # list of {"label": lbl, "frames": [...], "idx": 0}
        self._screen_char_list_anim_running = True

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
            ctype = get_stage_name_from_growth(char.get("growth", 0))
            # 성장도에 따라 계산된 단계 폴더 이미지를 사용
            tail_dir = f"frontend/assets/characters/{name}/{ctype}/tail"
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
                ctk.CTkLabel(placeholder, text=char.get("display", "캐릭터"),
                             font=self._make_font(16)).pack(expand=True)

            ctk.CTkLabel(card, text=char.get("name", "캐릭터 이름"), font=self._make_font(14)).pack(pady=(6, 2))
            growth_point = int(char.get('growth', 0))
            stage_idx = min(growth_point // 120, 2)
            if stage_idx >= 2:
                growth_percent = 100
                prog_value = 1.0
            else:
                growth_in_stage = growth_point - (stage_idx * 120)
                growth_percent = min(100, int(growth_in_stage * 100 / 120))
                prog_value = growth_in_stage / 120
            ctk.CTkLabel(card, text=f"성장도: {growth_percent}%", font=self._make_font(12)).pack()
            prog = ctk.CTkProgressBar(card, width=140)
            prog.set(prog_value)
            prog.pack(pady=8)

        if self._screen_char_list_anim_data:
            self._screen_char_list_anim_tick()

    def _on_show_characters(self):
        self._screen_char_list_page = 0
        self._rebuild_screen_char_list()
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

        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="캐릭터 생성", anchor="w", font=self._make_font(20)).pack(side="left")
        ctk.CTkButton(top, text="돌아가기", width=80, font=self._make_font(12),
                      command=lambda: self.show_screen(SELECT_CHAR)).pack(side="right")

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
                      command=on_prev_page).pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle)
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1, uniform="card")

        ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14),
                      command=on_next_page).pack(side="left", padx=(8, 0))

        visible_candidates = candidates[self._screen_char_create_page * page_size:(self._screen_char_create_page + 1) * page_size]
        self._screen_char_create_images = []
        card_width = 160

        def on_card_click(idx):
            chars = load_characters(sort_by_last_accessed=False)
            sel_cand = visible_candidates[idx]
            # 신규 생성 캐릭터는 growth=0으로 시작하므로 동일 이름+growth=0이면 중복으로 간주
            sel_growth = int(sel_cand.get("growth", 0))
            if any(
                c.get("name") == sel_cand["name"] and
                int(c.get("growth", 0)) == sel_growth
                for c in chars
            ):
                self._show_info_dialog("중복 생성", f"{sel_cand['name']} 캐릭터는\n이미 생성되어 있습니다.")
                return
            chars.append(new_character(sel_cand["name"], sel_growth))
            save_characters(chars)
            self._rebuild_screen_char_legacy()

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
                self._screen_char_create_images.append(ctk_img)
                img_label.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))
            except Exception:
                lbl = ctk.CTkLabel(placeholder, text=cand["name"], font=self._make_font(16))
                lbl.pack(expand=True)
                lbl.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))

            ctk.CTkLabel(card, text=cand["name"], font=self._make_font(14)).pack(pady=(6, 2))

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

        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="캐릭터 선택", anchor="w", font=self._make_font(20, "bold")).pack(side="left")
        ctk.CTkButton(top, text="←", width=40, command=self._on_char_select_back,
                      font=self._make_font(14)).pack(side="right", padx=(0, 6))

        def on_create_character():
            self._screen_char_create_page = 0
            self.show_screen(CREATE_CHAR)
        ctk.CTkButton(top, text="캐릭터 생성", width=110, height=32, font=self._make_font(14),
                      command=on_create_character).pack(side="right", padx=(0, 6))

        middle = ctk.CTkFrame(frame)
        middle.pack(fill="both", expand=True, padx=10, pady=10)

        characters = load_characters(sort_by_last_accessed=True)

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
                      command=on_prev_page).pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle)
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0, 1, 2), weight=1, uniform="card")

        ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14),
                      command=on_next_page).pack(side="left", padx=(8, 0))

        visible_characters = characters[self._screen_char_select_page * page_size:(self._screen_char_select_page + 1) * page_size]
        card_width = 160
        self._screen_char_select_images = []

        if visible_characters:
            for col, char in enumerate(visible_characters):
                card = ctk.CTkFrame(content, width=card_width, corner_radius=8)
                card.grid(row=0, column=col, padx=8, pady=8, sticky="nsew")
                card.pack_propagate(False)
                card.grid_propagate(False)
                content.grid_rowconfigure(0, weight=1)

                selected_char_id = char.get("id")

                def on_card_click(selected_id=selected_char_id):
                    # 고유 id를 선택값으로 저장하여 정렬/중복 이름에도 안정적으로 동작
                    self._selected_char = selected_id
                    chars = load_characters(sort_by_last_accessed=False)
                    if touch_character(chars, selected_id):
                        save_characters(chars)
                    self.start_camera()
                    pending = getattr(self, "_pending_group_room", None)
                    if pending:
                        self._pending_group_room = None
                        self._enter_group_room(*pending)
                    else:
                        self.show_screen(PERSONAL_CAMERA)

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
                ctype = get_stage_name_from_growth(char.get("growth", 0))
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
                        self._screen_char_select_images.append(ctk_img)
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
                growth_point = int(char.get('growth', 0))
                stage_idx = min(growth_point // 120, 2)
                if stage_idx >= 2:
                    growth_percent = 100
                    prog_value = 1.0
                else:
                    growth_in_stage = growth_point - (stage_idx * 120)
                    growth_percent = min(100, int(growth_in_stage * 100 / 120))
                    prog_value = growth_in_stage / 120
                ctk.CTkLabel(card, text=f"성장도: {growth_percent}%", font=self._make_font(12)).pack()
                prog = ctk.CTkProgressBar(card, width=140)
                prog.set(prog_value)
                prog.pack(pady=8)
        else:
            ctk.CTkLabel(content, text="보유한 캐릭터가 없습니다.", font=self._make_font(16)).pack(pady=40)

    def _on_char_select_back(self):
        if self._pending_group_room is not None:
            self._pending_group_room = None
            self.show_screen(GROUP_LIST)
        else:
            self.show_screen(MAIN)

    def _refresh_char_select(self):
        for widget in self.screen_char_select.winfo_children():
            widget.destroy()
        self._build_screen_char_select()

    def _on_personal_study(self):
        self._screen_char_select_page = 0
        self._refresh_char_select()
        self.show_screen(SELECT_CHAR)
