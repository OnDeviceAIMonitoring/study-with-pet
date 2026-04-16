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

from .layouts import compose_grid, compose_group
from .frame_utils import build_waiting_frame
from . import socketio_client


class ViewerApp:
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
        self.slide13 = ctk.CTkFrame(self.container)
        self.slide_group = ctk.CTkFrame(self.container)
        self.slide_camera = ctk.CTkFrame(self.container)

        self._refresh_period_ms = max(10, self.args.refresh_ms)

        # 슬라이드 빌드
        self._build_slide1()
        self._build_slide13()
        self._build_group_slide()
        self._build_camera_slide()

        self.show_slide(1)

        # 카메라 상태
        self.camera_running = False
        self.camera_thread = None
        self.latest_frame = None

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
            self.slide1.pack(fill="both", expand=True)
            self.current_slide = 1
        elif slide_no == 2:
            self.slide_camera.pack(fill="both", expand=True)
            self.current_slide = 2
        elif slide_no == 3:
            self.slide_group.pack(fill="both", expand=True)
            self.current_slide = 3
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
        self.show_slide(2)
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
        self.show_slide(3)
        self.start_camera()

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
