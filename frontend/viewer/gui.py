"""
CustomTkinter 기반 ViewerApp 정의

원본의 `ViewerApp` 클래스를 모듈화하되 Socket.IO 연결은 `socketio_client.start_background`
를 통해 분리합니다.
"""

from datetime import datetime
import threading
import time
from typing import Dict
import json

import tkinter.font as tkfont

try:
    import cv2
    import numpy as np
except ImportError:
    raise RuntimeError("OpenCV and NumPy are required. Install requirements before running the viewer.")

try:
    import customtkinter as ctk
    from PIL import Image, ImageTk
except Exception:
    raise RuntimeError("customtkinter and Pillow are required. Install them to run the GUI: pip install customtkinter pillow")

from .layouts import compose_grid, compose_group
from .frame_utils import build_waiting_frame
from . import socketio_client


class ViewerApp:
    def _show_info_dialog(self, title, message):
        """검정 배경의 클릭-투-클로즈 알림 다이얼로그"""
        import tkinter as tk

        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)  # 타이틀바/X 버튼 제거
        dlg.configure(bg="#000000")
        dlg.attributes("-topmost", True)
        dlg.transient(self.root)

        width, height = 320, 130
        self.root.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        x = root_x + (root_w - width) // 2
        y = root_y + (root_h - height) // 2
        dlg.geometry(f"{width}x{height}+{x}+{y}")

        box = tk.Frame(dlg, bg="#000000", highlightthickness=1, highlightbackground="#2a2a2a")
        box.pack(fill="both", expand=True)

        title_lbl = tk.Label(box, text=title, fg="#f2f2f2", bg="#000000", font=self._make_font(13, "bold"))
        title_lbl.pack(pady=(18, 6))

        msg_lbl = tk.Label(box, text=message, fg="#d6d6d6", bg="#000000", font=self._make_font(12), wraplength=280, justify="center")
        msg_lbl.pack(pady=(0, 14), padx=12)

        # 창 또는 메시지를 클릭하면 닫힘
        for widget in (dlg, box, title_lbl, msg_lbl):
            widget.bind("<Button-1>", lambda _e: dlg.destroy())

        dlg.grab_set()
    
    def get_selected_character(self):
        # slide6에서 선택된 캐릭터 인덱스 반환 (0, 1, 2 중 하나, 선택 없으면 None)
        return getattr(self, '_slide6_selected', None)
    def __init__(self, args):
        # 인스턴스 상태 초기화
        self.args = args
        self.frame_map: Dict[str, dict] = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title(self.args.window_title)
        self.root.geometry(f"{self.args.canvas_width}x{self.args.canvas_height}")

        # 한글을 지원하는 폰트 패밀리 탐색
        families = list(tkfont.families())
        preferred = [
            "Noto Sans CJK KR",
            "NotoSansCJKkr",
            "NanumGothic",
            "Nanum Gothic",
            "Malgun Gothic",
            "Apple SD Gothic Neo",
            "Arial Unicode MS",
            "DejaVu Sans",
        ]
        self.font_family = None
        for name in preferred:
            for fam in families:
                if name.lower() in fam.lower():
                    self.font_family = fam
                    break
            if self.font_family:
                break
        if not self.font_family:
            self.font_family = families[0] if families else "TkDefaultFont"

        def make_font(size: int, weight: str = "normal"):
            return (self.font_family, size, weight)

        self._make_font = make_font

        # UI 컨테이너 및 슬라이드
        self.container = ctk.CTkFrame(self.root)
        self.container.pack(fill="both", expand=True)

        self.slide1 = ctk.CTkFrame(self.container)
        self.slide6 = ctk.CTkFrame(self.container)
        self.slide13 = ctk.CTkFrame(self.container)
        self.slide14 = ctk.CTkFrame(self.container)  # 캐릭터 생성
        self.slide_group = ctk.CTkFrame(self.container)
        self.slide_camera = ctk.CTkFrame(self.container)
        self._slide6_page = 0
        self._slide13_page = 0
        self._slide14_page = 0

        self._refresh_period_ms = max(10, self.args.refresh_ms)

        # 슬라이드 빌드
        self._build_slide1()
        self._build_slide6()
        self._build_slide13()
        self._build_slide14()
        self._build_group_slide()
        self._build_camera_slide()

        # 초기 슬라이드 표시
        self.show_slide(1)
    def _build_slide6(self):
        import os
        from PIL import Image
        frame = self.slide6
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="캐릭터 선택 (성장시킬 캐릭터)", anchor="w", font=self._make_font(20))
        title.pack(side="left")
        back_top_btn = ctk.CTkButton(top, text="돌아가기", width=80, font=self._make_font(12), command=lambda: self.show_slide(1))
        back_top_btn.pack(side="right", padx=(0, 6))
        def on_create_character():
            self._slide14_page = 0
            self.show_slide(14)
        create_btn = ctk.CTkButton(top, text="캐릭터 생성", width=110, height=32, font=self._make_font(14), command=on_create_character)
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
        content.grid_columnconfigure((0,1,2), weight=1)

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
            self.show_slide(3)
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
                    for child in getattr(widget, 'winfo_children', lambda:[])():
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
                        target_w = 140
                        target_h = int(target_w * 650 / 430)
                        bg = Image.new("RGBA", (target_w, target_h), (0,0,0,0))
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
                        lbl = ctk.CTkLabel(placeholder, text=char.get("display", f"캐릭터 {col+1}"), font=self._make_font(16))
                        lbl.pack(expand=True)
                        lbl.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))
                else:
                    lbl = ctk.CTkLabel(placeholder, text=char.get("display", f"캐릭터 {col+1}"), font=self._make_font(16))
                    lbl.pack(expand=True)
                    lbl.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))

                name_lbl = ctk.CTkLabel(card, text=char.get("name", "캐릭터 이름"), font=self._make_font(14))
                name_lbl.pack(pady=(6,2))
                growth_lbl = ctk.CTkLabel(card, text=f"성장도: {char.get('growth', 0)}", font=self._make_font(12))
                growth_lbl.pack()
                prog = ctk.CTkProgressBar(card, width=140)
                prog.set(char.get('growth', 0.5))
                prog.pack(pady=8)

                self._slide6_cards.append(card)
        else:
            empty_lbl = ctk.CTkLabel(content, text="생성된 캐릭터가 없습니다.", font=self._make_font(16))
            empty_lbl.pack(pady=40)

        # 카메라 상태
        self.camera_running = False
        self.camera_thread = None
        self.latest_frame = None

    def _build_slide14(self):
        import os
        from PIL import Image
        frame = self.slide14
        for widget in frame.winfo_children():
            widget.destroy()
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="캐릭터 생성", anchor="w", font=self._make_font(20))
        title.pack(side="left")
        back_top_btn = ctk.CTkButton(top, text="돌아가기", width=80, font=self._make_font(12), command=lambda: self.show_slide(6))
        back_top_btn.pack(side="right")

        middle = ctk.CTkFrame(frame)
        middle.pack(fill="both", expand=True, padx=10, pady=10)

        # 캐릭터 후보 탐색
        char_root = "frontend/assets/characters"
        candidates = []
        for cname in os.listdir(char_root):
            baby_tail_dir = os.path.join(char_root, cname, "baby", "tail")
            if os.path.isdir(baby_tail_dir):
                pngs = sorted([f for f in os.listdir(baby_tail_dir) if f.endswith('.png')])
                if pngs:
                    candidates.append({
                        "name": cname,
                        "img_path": os.path.join(baby_tail_dir, pngs[0]),
                    })
        if not candidates:
            lbl = ctk.CTkLabel(content, text="생성 가능한 캐릭터 이미지가 없습니다.", font=self._make_font(16))
            lbl.pack(pady=40)
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

        back_btn = ctk.CTkButton(middle, text="<", width=50, font=self._make_font(14), command=on_prev_page)
        back_btn.pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle)
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0,1,2), weight=1)

        next_btn = ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14), command=on_next_page)
        next_btn.pack(side="left", padx=(8, 0))

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
            # 같은 캐릭터 타입이 이미 존재하는지 확인
            if any(c.get("name") == sel_cand["name"] for c in chars):
                self._show_info_dialog("중복 생성", f"{sel_cand['name']} 캐릭터는\n이미 생성되어 있습니다.")
                return
            # 새 캐릭터 생성
            new_char = {
                "name": sel_cand["name"],
                "type": "baby",
                "growth": 0.0
            }
            chars.append(new_char)
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
                for child in getattr(widget, 'winfo_children', lambda:[])():
                    bind_all(child, idx)
            bind_all(card, col)

            placeholder = ctk.CTkFrame(card, height=1, corner_radius=16)
            placeholder.pack(pady=10, padx=8, fill="both", expand=True)
            placeholder.bind("<Button-1>", lambda e, idx=col: on_card_click(idx))
            
            try:
                pil_img = Image.open(cand["img_path"]).convert("RGBA")
                target_w = 140
                target_h = int(target_w * 650 / 430)
                bg = Image.new("RGBA", (target_w, target_h), (0,0,0,0))
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

            name_lbl = ctk.CTkLabel(card, text=cand["name"], font=self._make_font(14))
            name_lbl.pack(pady=(6,2))

    def start(self):
        # Socket.IO 백그라운드 시작
        socketio_client.start_background(self)
        # GUI 업데이트 루프 시작
        self._schedule_update()
        try:
            self.root.mainloop()
        finally:
            self.stop_event.set()

    def show_slide(self, slide_no: int):
        for widget in self.container.winfo_children():
            widget.pack_forget()
        if slide_no == 1:
            # slide1이 다시 보여질 때마다 애니메이션 프레임 재생성
            for child in self.slide1.winfo_children():
                child.destroy()
            self._build_slide1()
            self.slide1.pack(fill="both", expand=True)
            self.current_slide = 1
        elif slide_no == 2:
            self.slide_camera.pack(fill="both", expand=True)
            self.current_slide = 2
        elif slide_no == 3:
            self.slide_group.pack(fill="both", expand=True)
            self.current_slide = 3
        elif slide_no == 6:
            self.slide6.pack(fill="both", expand=True)
            self.current_slide = 6
        elif slide_no == 13:
            self.slide13.pack(fill="both", expand=True)
            self.current_slide = 13
        elif slide_no == 14:
            self._build_slide14()
            self.slide14.pack(fill="both", expand=True)
            self.current_slide = 14


    def _build_slide1(self):
        import os
        import random
        from PIL import Image
        frame = self.slide1
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
        self._slide1_characters = []
        try:
            with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                char_list = json.load(f)
        except Exception:
            char_list = []

        # 영역당 1마리씩 랜덤으로 셔플 후 배치
        valid_areas = [a for a in possible_areas if a[2] >= char_w and a[3] >= char_h]
        candidates = []
        for char in char_list:
            name = char.get("name", "maltese")
            ctype = char.get("type", "baby")
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

        # 영역 수만큼만 랜덤 선택해서 1대1 배치
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
            self._slide1_characters.append({
                "frames": frames,
                "frame_idx": random.randint(0, len(frames) - 1),
                "frame_cnt": len(frames),
                "label": lbl,
            })

        # ── 타이틀·버튼을 캐릭터 위에 생성 ──
        title = ctk.CTkLabel(frame, text="Study With Pet", font=self._make_font(36))
        title.grid(row=0, column=0, pady=(40, 20))

        self._slide1_buttons = []
        for i, (label, cmd) in enumerate(buttons, start=1):
            btn = ctk.CTkButton(frame, text=label, width=600, height=48, command=cmd, font=self._make_font(16))
            btn.grid(row=i, column=0, pady=12, padx=20)
            self._slide1_buttons.append(btn)

        self._slide1_anim_running = True
        self._slide1_anim_update()

    def _slide1_anim_update(self):
        # 메인화면에 등장한 캐릭터들 프레임 갱신
        if not getattr(self, "_slide1_anim_running", False):
            return
        for c in getattr(self, "_slide1_characters", []):
            c["frame_idx"] = (c["frame_idx"] + 1) % c["frame_cnt"]
            if c["label"] is not None:
                c["label"].configure(image=c["frames"][c["frame_idx"]])
        # 100ms마다 갱신
        self.root.after(200, self._slide1_anim_update)

    def _build_slide13(self):
        frame = self.slide13
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="보유 캐릭터 (성장 현황)", anchor="w", font=self._make_font(20))
        title.pack(side="left")
        back_top_btn = ctk.CTkButton(top, text="돌아가기", width=80, font=self._make_font(12), command=lambda: self.show_slide(1))
        back_top_btn.pack(side="right")

        middle = ctk.CTkFrame(frame)
        middle.pack(fill="both", expand=True, padx=10, pady=10)

        # 로컬 DB에서 캐릭터 목록 로드
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
            # 더 렌더링할 캐릭터가 있을 때만 다음 페이지로 이동
            if self._slide13_page < total_pages - 1:
                self._slide13_page += 1
                self._rebuild_slide13()

        back_btn = ctk.CTkButton(middle, text="<", width=50, font=self._make_font(14), command=on_prev_page)
        back_btn.pack(side="left", padx=(0, 8))

        content = ctk.CTkFrame(middle)
        content.pack(side="left", fill="both", expand=True, padx=8)
        content.grid_columnconfigure((0,1,2), weight=1)

        next_btn = ctk.CTkButton(middle, text=">", width=50, font=self._make_font(14), command=on_next_page)
        next_btn.pack(side="left", padx=(8, 0))

        visible_characters = characters[self._slide13_page * page_size:(self._slide13_page + 1) * page_size]

        card_width = 110  # 카드 전체 폭 더 줄임
        import os
        from PIL import Image, ImageTk


        # 이미지 참조 유지용 리스트
        self._slide13_images = []
        for col, char in enumerate(visible_characters):
            card = ctk.CTkFrame(content, width=card_width, corner_radius=8)
            card.grid(row=0, column=col, padx=8, pady=8, sticky="nsew")
            # 카드가 content 영역을 세로로 가득 채우도록 확장
            card.pack_propagate(False)
            card.grid_propagate(False)
            content.grid_rowconfigure(0, weight=1)
            # placeholder도 카드 높이에 맞춰 꽉 차게
            placeholder = ctk.CTkFrame(card, height=1, corner_radius=16)
            placeholder.pack(pady=10, padx=8, fill="both", expand=True)

            # placeholder 내부 위젯 제거
            for w in placeholder.winfo_children():
                w.destroy()

            # 이미지 경로 조합
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
                    # 430x650 비율 유지 썸네일
                    target_w = 140
                    target_h = int(target_w * 650 / 430)
                    bg = Image.new("RGBA", (target_w, target_h), (0,0,0,0))
                    pil_img.thumbnail((target_w, target_h), Image.LANCZOS)
                    # 중앙 배치
                    x = (target_w - pil_img.width) // 2
                    y = (target_h - pil_img.height) // 2
                    bg.paste(pil_img, (x, y), pil_img)
                    ctk_img = ctk.CTkImage(light_image=bg, dark_image=bg, size=(target_w, target_h))
                    img_label = ctk.CTkLabel(placeholder, image=ctk_img, text="")
                    img_label.pack(expand=True)
                    self._slide13_images.append(ctk_img)
                except Exception as e:
                    lbl = ctk.CTkLabel(placeholder, text=char.get("display", "캐릭터"), font=self._make_font(16))
                    lbl.pack(expand=True)
            else:
                lbl = ctk.CTkLabel(placeholder, text=char.get("display", "캐릭터"), font=self._make_font(16))
                lbl.pack(expand=True)

            name_lbl = ctk.CTkLabel(card, text=char.get("name", "캐릭터 이름"), font=self._make_font(14))
            name_lbl.pack(pady=(6,2))
            growth_lbl = ctk.CTkLabel(card, text=f"성장도: {char.get('growth', 0)}", font=self._make_font(12))
            growth_lbl.pack()
            prog = ctk.CTkProgressBar(card, width=140)
            prog.set(char.get('growth', 0.5))
            prog.pack(pady=8)

    def _on_show_characters(self):
        self._slide13_page = 0
        self._rebuild_slide13()
        self.show_slide(13)

    def _rebuild_slide13(self):
        for widget in self.slide13.winfo_children():
            widget.destroy()
        self._build_slide13()

    def _on_personal_study(self):
        # 캐릭터가 없으면 카드 미표시
        self._rebuild_slide6()
        self.show_slide(6)

    def _build_camera_slide(self):
        frame = self.slide_camera
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="개인 공부 - 카메라", anchor="w", font=self._make_font(18))
        title.pack(side="left")
        back_btn = ctk.CTkButton(top, text="돌아가기", width=80, command=self._on_camera_back, font=self._make_font(12))
        back_btn.pack(side="right")

        self.img_label = ctk.CTkLabel(frame, text="")
        self.img_label.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_group_slide(self):
        frame = self.slide_group
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="단체 공부 - 방", anchor="w", font=self._make_font(18))
        title.pack(side="left")
        back_btn = ctk.CTkButton(top, text="돌아가기", width=80, command=self._on_group_back, font=self._make_font(12))
        back_btn.pack(side="right")

        self.group_img_label = ctk.CTkLabel(frame, text="")
        self.group_img_label.pack(fill="both", expand=True, padx=10, pady=10)

    def _on_camera_back(self):
        self.stop_camera()
        self.show_slide(1)

    def _on_group_back(self):
        self.stop_camera()
        self.show_slide(1)

    def _on_group_study(self):
        # 캐릭터가 없으면 카드 미표시
        self._rebuild_slide6()
        self.show_slide(6)

    def _rebuild_slide6(self):
        # slide6 프레임을 새로 빌드 (캐릭터 변경 반영)
        for widget in self.slide6.winfo_children():
            widget.destroy()
        self._build_slide6()
        self.show_slide(6)

    def _rebuild_slide14(self):
        for widget in self.slide14.winfo_children():
            widget.destroy()
        self._build_slide14()
        self.show_slide(14)

    def start_camera(self, camera_index: int = 0):
        if self.camera_running:
            return
        self.camera_running = True

        def cam_loop():
            cap = cv2.VideoCapture(camera_index)
            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.args.canvas_width - self.args.left_reserved_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.args.canvas_height)
            except Exception:
                pass
            while self.camera_running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue
                with self.lock:
                    self.latest_frame = frame.copy()
                time.sleep(0.01)
            try:
                cap.release()
            except Exception:
                pass

        self.camera_thread = threading.Thread(target=cam_loop, daemon=True)
        self.camera_thread.start()

    def stop_camera(self):
        if not self.camera_running:
            return
        self.camera_running = False
        if self.camera_thread is not None:
            self.camera_thread.join(timeout=1.0)
            self.camera_thread = None

    def _schedule_update(self):
        if hasattr(self, "img_label"):
            self._update_image()
        self.root.after(self._refresh_period_ms, self._schedule_update)

    def _update_image(self):
        if not hasattr(self, "img_label"):
            return
        if getattr(self, "current_slide", 1) == 2:
            with self.lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()
            if frame is None:
                canvas = build_waiting_frame(self.args.canvas_width, self.args.canvas_height)
                rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
                pil = Image.fromarray(rgb)
            else:
                try:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                except Exception:
                    rgb = frame[:, :, ::-1]
                pil = Image.fromarray(rgb)
            img_tk = ImageTk.PhotoImage(pil)
            self.img_label.image = img_tk
            self.img_label.configure(image=img_tk)
        elif getattr(self, "current_slide", 1) == 3:
            with self.lock:
                local_frame = None if self.latest_frame is None else self.latest_frame.copy()
                frame_map_copy = dict(self.frame_map)
            if local_frame is None:
                main_placeholder = build_waiting_frame(self.args.main_width, self.args.main_height)
                frame_map_copy[self.args.name] = {
                    "frame": main_placeholder,
                    "is_main": True,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
            else:
                frame_map_copy[self.args.name] = {
                    "frame": local_frame,
                    "is_main": True,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }

            canvas = compose_group(
                frame_map_copy,
                self.args.canvas_width,
                self.args.canvas_height,
                self.args.left_reserved_width,
                self.args.main_width,
                self.args.main_height,
                self.args.sub_width,
                self.args.sub_height,
            )
            try:
                rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            except Exception:
                rgb = canvas[:, :, ::-1]
            pil = Image.fromarray(rgb)
            img_tk = ImageTk.PhotoImage(pil)
            if hasattr(self, "group_img_label"):
                self.group_img_label.image = img_tk
                self.group_img_label.configure(image=img_tk)
        else:
            with self.lock:
                canvas = compose_grid(
                    self.frame_map,
                    self.args.canvas_width,
                    self.args.canvas_height,
                    self.args.left_reserved_width,
                    self.args.main_width,
                    self.args.main_height,
                    self.args.sub_width,
                    self.args.sub_height,
                )
            try:
                rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            except Exception:
                rgb = canvas[:, :, ::-1]
            pil = Image.fromarray(rgb)
            img_tk = ImageTk.PhotoImage(pil)
            if hasattr(self, "img_label"):
                self.img_label.image = img_tk
                self.img_label.configure(image=img_tk)
