"""
CustomTkinter 기반 ViewerApp 정의

원본의 `ViewerApp` 클래스를 모듈화하되 Socket.IO 연결은 `socketio_client.start_background`
를 통해 분리합니다.
"""

from datetime import datetime
import threading
import time
from typing import Dict

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

import os
import sys
import json
import urllib.request
import urllib.error

from .layouts import compose_grid, compose_group
from .frame_utils import build_waiting_frame
from . import socketio_client

# frontend/ 디렉터리를 경로에 추가하여 user 패키지 임포트
_frontend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _frontend_dir not in sys.path:
    sys.path.insert(0, _frontend_dir)
from user import room_manager


class ViewerApp:
    def __init__(self, args):
        # 인스턴스 상태 초기화
        self.args = args
        self.frame_map: Dict[str, dict] = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self._socket_generation = 0  # 소켓 세션 세대 번호

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
        self.slide13 = ctk.CTkFrame(self.container)
        self.slide_group = ctk.CTkFrame(self.container)
        self.slide_group_list = ctk.CTkFrame(self.container)
        self.slide_group_join = ctk.CTkFrame(self.container)
        self.slide_group_create = ctk.CTkFrame(self.container)
        self.slide_char_select = ctk.CTkFrame(self.container)
        self.slide_camera = ctk.CTkFrame(self.container)

        self._refresh_period_ms = max(10, self.args.refresh_ms)

        # 슬라이드 빌드
        self._build_slide1()
        self._build_slide13()
        self._build_group_slide()
        self._build_group_list_slide()
        self._build_group_join_slide()
        self._build_group_create_slide()
        self._build_char_select_slide()
        self._build_camera_slide()

        self.show_slide(1)

        # 카메라 상태
        self.camera_running = False
        self.camera_thread = None
        self.latest_frame = None

    def start(self):
        # GUI 업데이트 루프 시작 (소켓은 단체방 입장 시에만 연결)
        self._schedule_update()
        try:
            self.root.mainloop()
        finally:
            self.stop_event.set()

    def show_slide(self, slide_no: int):
        for widget in self.container.winfo_children():
            widget.pack_forget()
        if slide_no == 1:
            self.slide1.pack(fill="both", expand=True)
            self.current_slide = 1
        elif slide_no == 2:
            self._refresh_group_list()
            self.slide_group_list.pack(fill="both", expand=True)
            self.current_slide = 2
        elif slide_no == 3:
            self.create_name_entry.delete(0, "end")
            self.create_code_entry.delete(0, "end")
            self.create_error_label.configure(text="")
            self.create_submit_btn.configure(state="normal", text="생성하기")
            self.slide_group_create.pack(fill="both", expand=True)
            self.current_slide = 3
        elif slide_no == 4:
            self.join_name_entry.delete(0, "end")
            self.join_code_entry.delete(0, "end")
            self.join_error_label.configure(text="")
            self.join_submit_btn.configure(state="normal", text="참가하기")
            self.slide_group_join.pack(fill="both", expand=True)
            self.current_slide = 4
        # slide 5: reserved
        elif slide_no == 6:
            self._refresh_char_select()
            self.slide_char_select.pack(fill="both", expand=True)
            self.current_slide = 6
        elif slide_no == 7:
            self.slide_group.pack(fill="both", expand=True)
            self.current_slide = 7
        elif slide_no == 10:
            self.slide_camera.pack(fill="both", expand=True)
            self.current_slide = 10
        elif slide_no == 13:
            self.slide13.pack(fill="both", expand=True)
            self.current_slide = 13

    def _build_slide1(self):
        frame = self.slide1
        frame.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(frame, text="Study With Pet", font=self._make_font(36))
        title.grid(row=0, column=0, pady=(40, 20))

        buttons = [
            ("개인 공부", self._on_personal_study),
            ("단체 공부", self._on_group_study),
            ("보유 캐릭터 (성장 현황)", self._on_show_characters),
            ("나가기", self.root.quit),
        ]

        for i, (label, cmd) in enumerate(buttons, start=1):
            btn = ctk.CTkButton(frame, text=label, width=600, height=48, command=cmd, font=self._make_font(16))
            btn.grid(row=i, column=0, pady=12, padx=20)

    def _build_slide13(self):
        frame = self.slide13
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="보유 캐릭터 (성장 현황)", anchor="w", font=self._make_font(20))
        title.pack(side="left")
        back_btn = ctk.CTkButton(top, text="<", width=40, command=lambda: self.show_slide(1), font=self._make_font(14))
        back_btn.pack(side="right")

        content = ctk.CTkFrame(frame)
        content.pack(fill="both", expand=True, padx=20, pady=10)
        content.grid_columnconfigure((0,1,2), weight=1)

        card_width = 260
        for col in range(3):
            card = ctk.CTkFrame(content, width=card_width, height=380, corner_radius=8)
            card.grid(row=0, column=col, padx=12, pady=8, sticky="nsew")
            placeholder = ctk.CTkFrame(card, height=220, corner_radius=16)
            placeholder.pack(pady=12, padx=12, fill="x")
            lbl = ctk.CTkLabel(placeholder, text="캐릭터", font=self._make_font(16))
            lbl.place(relx=0.5, rely=0.5, anchor="center")

            name_lbl = ctk.CTkLabel(card, text="캐릭터 이름", font=self._make_font(14))
            name_lbl.pack(pady=(8,2))
            growth_lbl = ctk.CTkLabel(card, text="성장도", font=self._make_font(12))
            growth_lbl.pack()
            prog = ctk.CTkProgressBar(card, width=200)
            prog.set(0.5)
            prog.pack(pady=10)

    def _on_show_characters(self):
        self.show_slide(13)

    def _on_personal_study(self):
        self.show_slide(10)
        self.start_camera()

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
        self.group_slide_title = ctk.CTkLabel(top, text="단체 공부", anchor="w", font=self._make_font(18))
        self.group_slide_title.pack(side="left")
        back_btn = ctk.CTkButton(top, text="← 방 목록", width=90, command=self._on_group_back, font=self._make_font(12))
        back_btn.pack(side="right")

        self.group_img_label = ctk.CTkLabel(frame, text="")
        self.group_img_label.pack(fill="both", expand=True, padx=10, pady=10)

    def _on_camera_back(self):
        self.stop_camera()
        self.show_slide(1)

    def _on_group_back(self):
        # 소켓 세션 종료
        self._socket_generation += 1
        self.stop_camera()
        with self.lock:
            self.frame_map.clear()
        self.show_slide(2)

    def _on_group_study(self):
        self.show_slide(2)

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
        if getattr(self, "current_slide", 1) == 10:
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
        elif getattr(self, "current_slide", 1) == 7:
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

    # ──────────────────────────────────────────────
    # 캐릭터 선택창 (slide 6)
    # ──────────────────────────────────────────────

    def _build_char_select_slide(self):
        frame = self.slide_char_select

        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="캐릭터 선택", anchor="w", font=self._make_font(20, "bold")).pack(side="left")
        ctk.CTkButton(top, text="←", width=40, command=lambda: self.show_slide(1),
                      font=self._make_font(14)).pack(side="right")

        self.char_select_scroll = ctk.CTkScrollableFrame(
            frame, label_text="보유 캐릭터", label_font=self._make_font(13)
        )
        self.char_select_scroll.pack(fill="both", expand=True, padx=20, pady=(8, 20))

    def _refresh_char_select(self):
        """캐릭터 선택 목록을 갱신합니다."""
        for widget in self.char_select_scroll.winfo_children():
            widget.destroy()

        _chars_path = os.path.join(_frontend_dir, "user", "characters.json")
        try:
            import json as _json
            with open(_chars_path, "r", encoding="utf-8") as f:
                characters = _json.load(f)
        except Exception:
            characters = []

        if not characters:
            ctk.CTkLabel(
                self.char_select_scroll,
                text="보유한 캐릭터가 없습니다.",
                font=self._make_font(13),
                text_color=("gray50", "gray60"),
            ).pack(pady=48)
            return

        for ch in characters:
            self._add_char_item(ch)

    def _add_char_item(self, ch: dict):
        name = ch.get("name", "?")
        kind = ch.get("type", "")
        growth = ch.get("growth", 0.0)
        is_selected = getattr(self, "_selected_char", None) == name

        item = ctk.CTkFrame(
            self.char_select_scroll, height=70, corner_radius=8,
            fg_color=("gray80", "gray25") if not is_selected else ("gray65", "gray35"),
            cursor="hand2",
        )
        item.pack(fill="x", pady=4, padx=2)
        item.pack_propagate(False)

        def select(n=name):
            self._selected_char = n
            self._refresh_char_select()

        item.bind("<Button-1>", lambda e, fn=select: fn())

        name_lbl = ctk.CTkLabel(item, text=f"{name}  ({kind})", font=self._make_font(14, "bold"),
                                 anchor="w", cursor="hand2")
        name_lbl.pack(side="left", padx=16)
        name_lbl.bind("<Button-1>", lambda e, fn=select: fn())

        prog_frame = ctk.CTkFrame(item, fg_color="transparent")
        prog_frame.pack(side="right", padx=16)
        ctk.CTkLabel(prog_frame, text="성장도", font=self._make_font(11),
                     text_color=("gray50", "gray60")).pack(anchor="e")
        bar = ctk.CTkProgressBar(prog_frame, width=140, height=10)
        bar.set(growth)
        bar.pack()

        if is_selected:
            ctk.CTkLabel(item, text="✓", font=self._make_font(18, "bold"),
                         text_color="#4ade80", cursor="hand2").pack(side="right", padx=4)

    # ──────────────────────────────────────────────
    # 단체방 목록 슬라이드 (slide 2)
    # ──────────────────────────────────────────────

    def _build_group_list_slide(self):
        frame = self.slide_group_list

        # 헤더
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="단체 공부", anchor="w", font=self._make_font(20, "bold")).pack(side="left")
        ctk.CTkButton(top, text="←", width=40, command=lambda: self.show_slide(1),
                      font=self._make_font(14)).pack(side="right")

        # 방 목록 (스크롤 가능)
        self.group_list_scroll = ctk.CTkScrollableFrame(
            frame, label_text="내 단체방 목록", label_font=self._make_font(13)
        )
        self.group_list_scroll.pack(fill="both", expand=True, padx=20, pady=(8, 4))

        # 하단 버튼
        bottom = ctk.CTkFrame(frame, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(4, 20))
        bottom.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            bottom, text="참가하기", height=46,
            command=lambda: self.show_slide(4),
            font=self._make_font(15),
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            text_color=("gray10", "gray90"),
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            bottom, text="생성하기", height=46,
            command=lambda: self.show_slide(3),
            font=self._make_font(15),
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _refresh_group_list(self):
        """단체방 목록 위젯을 갱신합니다."""
        for widget in self.group_list_scroll.winfo_children():
            widget.destroy()

        rooms = room_manager.load_rooms()
        if not rooms:
            ctk.CTkLabel(
                self.group_list_scroll,
                text="참가한 단체방이 없습니다.\n아래 버튼으로 방에 참가하거나 새로 생성하세요.",
                font=self._make_font(13),
                text_color=("gray50", "gray60"),
                justify="center",
            ).pack(pady=48)
            return

        for room in rooms:
            self._add_room_item(room["name"], room["room_code"])

    def _add_room_item(self, name: str, room_code: str):
        enter_fn = lambda rc=room_code, n=name: self._enter_group_room(rc, n)

        item = ctk.CTkFrame(
            self.group_list_scroll, height=60, corner_radius=8,
            fg_color=("gray85", "gray22"), cursor="hand2",
        )
        item.pack(fill="x", pady=4, padx=2)
        item.pack_propagate(False)
        item.bind("<Button-1>", lambda e, fn=enter_fn: fn())

        name_lbl = ctk.CTkLabel(
            item, text=name, font=self._make_font(14, "bold"), anchor="w", cursor="hand2"
        )
        name_lbl.pack(side="left", padx=16)
        name_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())

        code_lbl = ctk.CTkLabel(
            item, text=f"#{room_code}", font=self._make_font(12),
            text_color=("gray50", "gray60"), cursor="hand2",
        )
        code_lbl.pack(side="right", padx=16)
        code_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())

        arrow_lbl = ctk.CTkLabel(item, text="›", font=self._make_font(20), cursor="hand2")
        arrow_lbl.pack(side="right", padx=4)
        arrow_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())

    # ──────────────────────────────────────────────
    # 단체방 참가 슬라이드 (slide 5)
    # ──────────────────────────────────────────────

    def _build_group_join_slide(self):
        frame = self.slide_group_join

        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="단체방 참가하기", anchor="w", font=self._make_font(20, "bold")).pack(side="left")
        ctk.CTkButton(top, text="←", width=40, command=lambda: self.show_slide(2),
                      font=self._make_font(14)).pack(side="right")

        # 중앙 폼
        wrap = ctk.CTkFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(wrap, corner_radius=12)
        form.grid(row=1, column=0, padx=40, pady=20)

        ctk.CTkLabel(form, text="방 이름", font=self._make_font(13), anchor="w").pack(
            pady=(24, 4), padx=28, anchor="w")
        self.join_name_entry = ctk.CTkEntry(
            form, placeholder_text="단체방 이름 입력", height=42, width=380, font=self._make_font(13))
        self.join_name_entry.pack(padx=28)

        ctk.CTkLabel(form, text="참가 코드", font=self._make_font(13), anchor="w").pack(
            pady=(16, 4), padx=28, anchor="w")
        self.join_code_entry = ctk.CTkEntry(
            form, placeholder_text="참가 코드 입력", height=42, width=380, font=self._make_font(13))
        self.join_code_entry.pack(padx=28)

        self.join_error_label = ctk.CTkLabel(
            form, text="", text_color="#ef4444", font=self._make_font(12), width=380)
        self.join_error_label.pack(pady=(10, 0), padx=28)

        self.join_submit_btn = ctk.CTkButton(
            form, text="참가하기", height=46, width=380,
            command=self._on_join_submit, font=self._make_font(15, "bold"))
        self.join_submit_btn.pack(pady=(12, 28), padx=28)

    def _on_join_submit(self):
        name = self.join_name_entry.get().strip()
        code = self.join_code_entry.get().strip()
        if not name or not code:
            self.join_error_label.configure(text="방 이름과 참가 코드를 모두 입력해주세요.")
            return

        self.join_submit_btn.configure(state="disabled", text="확인 중...")
        self.join_error_label.configure(text="")

        def on_result(result, error):
            if error:
                self.join_submit_btn.configure(state="normal", text="참가하기")
                self.join_error_label.configure(text=f"서버 오류: {error}")
                return
            if not result.get("ok"):
                self.join_submit_btn.configure(state="normal", text="참가하기")
                err_map = {
                    "room_not_found": "방을 찾을 수 없습니다. 방 이름과 코드를 확인해주세요.",
                    "name_mismatch": "방 이름이 올바르지 않습니다.",
                    "name_and_code_required": "방 이름과 참가 코드를 입력해주세요.",
                }
                msg = err_map.get(result.get("error", ""), "참가에 실패했습니다.")
                self.join_error_label.configure(text=msg)
                return
            room_manager.add_room(name, code)
            self._enter_group_room(code, name)

        self._call_api("/rooms/join", {"name": name, "room_code": code}, on_result)

    # ──────────────────────────────────────────────
    # 단체방 생성 슬라이드 (slide 6)
    # ──────────────────────────────────────────────

    def _build_group_create_slide(self):
        frame = self.slide_group_create

        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="단체방 생성하기", anchor="w", font=self._make_font(20, "bold")).pack(side="left")
        ctk.CTkButton(top, text="←", width=40, command=lambda: self.show_slide(2),
                      font=self._make_font(14)).pack(side="right")

        # 중앙 폼
        wrap = ctk.CTkFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(wrap, corner_radius=12)
        form.grid(row=1, column=0, padx=40, pady=20)

        ctk.CTkLabel(form, text="방 이름", font=self._make_font(13), anchor="w").pack(
            pady=(24, 4), padx=28, anchor="w")
        self.create_name_entry = ctk.CTkEntry(
            form, placeholder_text="단체방 이름 입력", height=42, width=380, font=self._make_font(13))
        self.create_name_entry.pack(padx=28)

        ctk.CTkLabel(form, text="참가 코드", font=self._make_font(13), anchor="w").pack(
            pady=(16, 4), padx=28, anchor="w")
        self.create_code_entry = ctk.CTkEntry(
            form, placeholder_text="다른 사람이 입력할 코드 설정", height=42, width=380, font=self._make_font(13))
        self.create_code_entry.pack(padx=28)

        self.create_error_label = ctk.CTkLabel(
            form, text="", text_color="#ef4444", font=self._make_font(12), width=380)
        self.create_error_label.pack(pady=(10, 0), padx=28)

        self.create_submit_btn = ctk.CTkButton(
            form, text="생성하기", height=46, width=380,
            command=self._on_create_submit, font=self._make_font(15, "bold"))
        self.create_submit_btn.pack(pady=(12, 28), padx=28)

    def _on_create_submit(self):
        name = self.create_name_entry.get().strip()
        code = self.create_code_entry.get().strip()
        if not name or not code:
            self.create_error_label.configure(text="방 이름과 참가 코드를 모두 입력해주세요.")
            return

        self.create_submit_btn.configure(state="disabled", text="생성 중...")
        self.create_error_label.configure(text="")

        def on_result(result, error):
            if error:
                self.create_submit_btn.configure(state="normal", text="생성하기")
                self.create_error_label.configure(text=f"서버 오류: {error}")
                return
            if not result.get("ok"):
                self.create_submit_btn.configure(state="normal", text="생성하기")
                err_map = {
                    "room_code_exists": "이미 사용 중인 참가 코드입니다. 다른 코드를 입력해주세요.",
                    "name_and_code_required": "방 이름과 참가 코드를 입력해주세요.",
                }
                msg = err_map.get(result.get("error", ""), "생성에 실패했습니다.")
                self.create_error_label.configure(text=msg)
                return
            room_manager.add_room(name, code)
            self._enter_group_room(code, name)

        self._call_api("/rooms/create", {"name": name, "room_code": code}, on_result)

    # ──────────────────────────────────────────────
    # 공통 유틸리티
    # ──────────────────────────────────────────────

    def _enter_group_room(self, room_code: str, room_name: str):
        """단체방 공부 세션을 시작합니다."""
        # 이전 소켓 세션을 세대 번호로 무효화
        self._socket_generation += 1
        self.args.room = room_code
        with self.lock:
            self.frame_map.clear()

        # 슬라이드 제목 업데이트
        self.group_slide_title.configure(text=f"단체 공부  ·  {room_name}")

        # 소켓 연결 시작
        socketio_client.start_background(self, self._socket_generation)

        self.show_slide(7)
        self.start_camera()

    def _call_api(self, endpoint: str, payload: dict, callback):
        """REST API를 백그라운드 스레드에서 호출하고 결과를 GUI 스레드에 전달합니다."""
        def _worker():
            try:
                url = f"{self.args.server}{endpoint}"
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                self.root.after(0, lambda: callback(result, None))
            except urllib.error.HTTPError as e:
                err = f"HTTP {e.code}"
                self.root.after(0, lambda err=err: callback(None, err))
            except Exception as e:
                err = str(e)
                self.root.after(0, lambda err=err: callback(None, err))

        threading.Thread(target=_worker, daemon=True).start()
