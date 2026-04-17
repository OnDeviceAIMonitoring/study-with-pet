"""
ViewerApp 메인 진입점

각 슬라이드 기능은 Mixin 클래스로 분리되어 있습니다.
  - slide_main.py  : MainSlideMixin   (메인 화면)
  - slide_char.py  : CharSlideMixin   (캐릭터 선택/목록/생성)
  - slide_group.py : GroupSlideMixin  (단체방)
  - slide_camera.py: CameraSlideMixin (카메라 피드)
"""

from datetime import datetime
import json
import threading
import urllib.request
import urllib.error
import tkinter.font as tkfont

try:
    import cv2
except ImportError:
    raise RuntimeError("OpenCV is required. Install requirements before running the viewer.")

try:
    import customtkinter as ctk
    from PIL import Image, ImageTk
except Exception:
    raise RuntimeError(
        "customtkinter and Pillow are required. Install them: pip install customtkinter pillow"
    )

import os
import sys

from .slides import (
    MAIN, GROUP_LIST, GROUP_CREATE, GROUP_JOIN,
    SELECT_CHAR, GROUP_ROOM, PERSONAL_CAMERA, CHAR_LIST, CREATE_CHAR,
)
from .slide_main import MainSlideMixin
from .slide_char import CharSlideMixin
from .slide_group import GroupSlideMixin
from .slide_camera import CameraSlideMixin
from .layouts import compose_grid, compose_group
from .frame_utils import build_waiting_frame

# frontend/ 디렉터리를 경로에 추가하여 user 패키지 임포트
_frontend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _frontend_dir not in sys.path:
    sys.path.insert(0, _frontend_dir)


class ViewerApp(MainSlideMixin, CharSlideMixin, GroupSlideMixin, CameraSlideMixin):

    # ──────────────────────────────────────────────
    # 초기화
    # ──────────────────────────────────────────────

    def __init__(self, args):
        self.args = args
        self.frame_map = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self._socket_generation = 0

        # 카메라 상태
        self.camera_running = False
        self.camera_thread = None
        self.latest_frame = None

        # 대기 중인 단체방 입장 정보
        self._pending_group_room = None
        self._selected_char = None

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title(self.args.window_title)
        self.root.geometry(f"{self.args.canvas_width}x{self.args.canvas_height}")

        # 한글 지원 폰트 탐색
        families = list(tkfont.families())
        preferred = [
            "Noto Sans CJK KR", "NotoSansCJKkr", "NanumGothic", "Nanum Gothic",
            "Malgun Gothic", "Apple SD Gothic Neo", "Arial Unicode MS", "DejaVu Sans",
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

        # 슬라이드 컨테이너
        self.container = ctk.CTkFrame(self.root)
        self.container.pack(fill="both", expand=True)

        self.slide1 = ctk.CTkFrame(self.container)
        self.slide6 = ctk.CTkFrame(self.container)
        self.slide13 = ctk.CTkFrame(self.container)
        self.slide14 = ctk.CTkFrame(self.container)
        self.slide_group = ctk.CTkFrame(self.container)
        self.slide2 = ctk.CTkFrame(self.container)
        self.slide_group_join = ctk.CTkFrame(self.container)
        self.slide_group_create = ctk.CTkFrame(self.container)
        self.slide_char_select = ctk.CTkFrame(self.container)
        self.slide_camera = ctk.CTkFrame(self.container)

        self._slide6_page = 0
        self._slide13_page = 0
        self._slide14_page = 0
        self._char_select_page = 0

        self._refresh_period_ms = max(10, self.args.refresh_ms)

        # 슬라이드 빌드
        self._build_slide1()
        self._build_slide6()
        self._build_slide13()
        self._build_slide14()
        self._build_group_slide()
        self._build_group_list_slide()
        self._build_group_join_slide()
        self._build_group_create_slide()
        self._build_char_select_slide()
        self._build_camera_slide()

        self.show_slide(MAIN)

    # ──────────────────────────────────────────────
    # 슬라이드 라우팅
    # ──────────────────────────────────────────────

    def show_slide(self, slide_no: int):
        for widget in self.container.winfo_children():
            widget.pack_forget()

        if slide_no == MAIN:
            for child in self.slide1.winfo_children():
                child.destroy()
            self._build_slide1()
            self.slide1.pack(fill="both", expand=True)

        elif slide_no == GROUP_LIST:
            self._refresh_group_list()
            self.slide2.pack(fill="both", expand=True)

        elif slide_no == GROUP_CREATE:
            self.create_name_entry.delete(0, "end")
            self.create_code_entry.delete(0, "end")
            self.create_error_label.configure(text="")
            self.create_submit_btn.configure(state="normal", text="생성하기")
            self.slide_group_create.pack(fill="both", expand=True)

        elif slide_no == GROUP_JOIN:
            self.join_name_entry.delete(0, "end")
            self.join_code_entry.delete(0, "end")
            self.join_error_label.configure(text="")
            self.join_submit_btn.configure(state="normal", text="참가하기")
            self.slide_group_join.pack(fill="both", expand=True)

        elif slide_no == SELECT_CHAR:
            self._refresh_char_select()
            self.slide_char_select.pack(fill="both", expand=True)

        elif slide_no == GROUP_ROOM:
            self.slide_group.pack(fill="both", expand=True)

        elif slide_no == PERSONAL_CAMERA:
            for child in self.slide_camera.winfo_children():
                child.destroy()
            self._build_camera_slide()
            self.slide_camera.pack(fill="both", expand=True)

        elif slide_no == CHAR_LIST:
            self.slide13.pack(fill="both", expand=True)

        elif slide_no == CREATE_CHAR:
            self._build_slide14()
            self.slide14.pack(fill="both", expand=True)

        self.current_slide = slide_no

    # ──────────────────────────────────────────────
    # 실행
    # ──────────────────────────────────────────────

    def start(self):
        self._schedule_update()
        try:
            self.root.mainloop()
        finally:
            self.stop_event.set()

    # ──────────────────────────────────────────────
    # 카메라 피드 갱신 루프
    # ──────────────────────────────────────────────

    def _schedule_update(self):
        if hasattr(self, "img_label"):
            self._update_image()
        self.root.after(self._refresh_period_ms, self._schedule_update)

    def _update_image(self):
        if not hasattr(self, "img_label"):
            return

        slide = getattr(self, "current_slide", MAIN)

        if slide == PERSONAL_CAMERA:
            with self.lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()
            if frame is None:
                canvas = build_waiting_frame(self.args.canvas_width, self.args.canvas_height)
                rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            else:
                try:
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                except Exception:
                    rgb = frame[:, :, ::-1]
            pil = Image.fromarray(rgb)
            img_tk = ImageTk.PhotoImage(pil)
            self.img_label.image = img_tk
            self.img_label.configure(image=img_tk)

        elif slide == GROUP_ROOM:
            with self.lock:
                local_frame = None if self.latest_frame is None else self.latest_frame.copy()
                frame_map_copy = dict(self.frame_map)

            if local_frame is None:
                placeholder = build_waiting_frame(self.args.main_width, self.args.main_height)
                frame_map_copy[self.args.name] = {
                    "frame": placeholder,
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

    # ──────────────────────────────────────────────
    # REST API 호출
    # ──────────────────────────────────────────────

    def _call_api(self, endpoint: str, payload: dict, callback):
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

    # ──────────────────────────────────────────────
    # 유틸리티 다이얼로그
    # ──────────────────────────────────────────────

    def _show_info_dialog(self, title, message):
        import tkinter as tk

        dlg = tk.Toplevel(self.root)
        dlg.overrideredirect(True)
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

        title_lbl = tk.Label(box, text=title, fg="#f2f2f2", bg="#000000",
                             font=self._make_font(13, "bold"))
        title_lbl.pack(pady=(18, 6))

        msg_lbl = tk.Label(box, text=message, fg="#d6d6d6", bg="#000000",
                           font=self._make_font(12), wraplength=280, justify="center")
        msg_lbl.pack(pady=(0, 14), padx=12)

        for widget in (dlg, box, title_lbl, msg_lbl):
            widget.bind("<Button-1>", lambda _e: dlg.destroy())

        dlg.grab_set()
