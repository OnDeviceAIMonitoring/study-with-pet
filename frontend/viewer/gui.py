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
import time
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
from .study_time import save_study_time

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

        # 단체방 왼쪽 캐릭터 오버레이 상태
        self._group_char_frames = []
        self._group_char_frame_idx = 0
        self._group_char_last_tick = 0.0
        self._group_char_name = ""
        self._group_char_growth_percent = 0
        self._group_char_idx = -1
        self._group_char_anim_running = False

        # 단체방 공부 시간/성장 상태
        self._group_study_running = False
        self._group_study_start_time = 0.0
        self._group_study_elapsed_seconds = 0
        self._group_study_accumulated_points = 0

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
            self._reload_group_character_overlay()
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
            self._tick_group_study_growth()

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

    def _start_group_study_session(self):
        self._group_study_running = True
        self._group_study_start_time = time.time()
        self._group_study_elapsed_seconds = 0
        self._group_study_accumulated_points = 0

    def _stop_group_study_session(self, save: bool = True):
        if not self._group_study_running and not save:
            return

        self._group_study_running = False

        if save:
            # 분 단위 저장(최소 1분)
            study_minutes = max(1, self._group_study_elapsed_seconds // 60)
            user_name = getattr(self.args, "name", "user")
            save_study_time(user_name, "group", study_minutes)

    def _tick_group_study_growth(self):
        if not self._group_study_running:
            return

        self._group_study_elapsed_seconds = int(time.time() - self._group_study_start_time)
        new_points = self._group_study_elapsed_seconds // 30
        if new_points <= self._group_study_accumulated_points:
            return

        add_points = new_points - self._group_study_accumulated_points
        self._group_study_accumulated_points = new_points

        if getattr(self, "_group_char_idx", -1) < 0:
            return

        # 개인방과 동일하게 30초당 1포인트 누적
        updated = self.update_character_growth(self._group_char_idx, add_points)
        if updated:
            # 단계가 바뀌면 type 폴더가 바뀌므로 오버레이를 다시 로드
            self._reload_group_character_overlay()

    def _reload_group_character_overlay(self):
        """단체방 캐릭터 위젯(개인방과 동일한 UI)에 프레임/성장 정보를 반영합니다."""
        self._group_char_frames = []
        self._group_char_frame_idx = 0
        self._group_char_last_tick = time.monotonic()
        self._group_char_name = ""
        self._group_char_growth_percent = 0
        self._group_char_anim_running = False

        if hasattr(self, "_group_char_label"):
            self._group_char_label.configure(image=None)
        if hasattr(self, "_group_char_growth"):
            self._group_char_growth.set(0.0)

        selected_value = getattr(self, "_selected_char", None)
        if selected_value is None:
            return

        try:
            with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                characters = json.load(f)
        except Exception:
            return

        selected = None
        selected_idx = -1
        if isinstance(selected_value, int):
            if 0 <= selected_value < len(characters):
                selected_idx = selected_value
                selected = characters[selected_idx]
        elif isinstance(selected_value, str):
            for i, c in enumerate(characters):
                if c.get("name") == selected_value:
                    selected_idx = i
                    selected = c
                    break
        if selected is None:
            return

        self._group_char_name = selected.get("name", "")
        self._group_char_idx = selected_idx
        growth_points = int(selected.get("growth", 0))
        display_growth = growth_points % 120
        self._group_char_growth_percent = min(100, int(display_growth * 100 / 120))
        if hasattr(self, "_group_char_growth"):
            self._group_char_growth.set(display_growth / 120)
        ctype = selected.get("type", "baby")

        tail_dir = f"frontend/assets/characters/{self._group_char_name}/{ctype}/tail"
        if not os.path.isdir(tail_dir):
            return

        files = sorted([f for f in os.listdir(tail_dir) if f.endswith(".png")])
        if not files:
            return

        # 개인방 캐릭터 크기와 동일하게 고정
        target_w = 120
        target_h = int(120 * 650 / 430)

        for fn in files:
            img_path = os.path.join(tail_dir, fn)
            try:
                pil_img = Image.open(img_path).convert("RGBA")
                bg = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                pil_img.thumbnail((target_w, target_h), Image.LANCZOS)
                ox = (target_w - pil_img.width) // 2
                oy = (target_h - pil_img.height) // 2
                bg.paste(pil_img, (ox, oy), pil_img)
                ctk_img = ctk.CTkImage(light_image=bg, dark_image=bg, size=(target_w, target_h))
                self._group_char_frames.append(ctk_img)
            except Exception:
                continue

        if self._group_char_frames and hasattr(self, "_group_char_label"):
            self._group_char_label.configure(image=self._group_char_frames[0])
            self._group_char_anim_running = True
            self._group_char_anim_tick()

    def _group_char_anim_tick(self):
        if not self._group_char_anim_running or not self._group_char_frames:
            return
        self._group_char_frame_idx = (self._group_char_frame_idx + 1) % len(self._group_char_frames)
        try:
            if hasattr(self, "_group_char_label"):
                self._group_char_label.configure(image=self._group_char_frames[self._group_char_frame_idx])
        except Exception:
            pass
        self.root.after(350, self._group_char_anim_tick)

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
