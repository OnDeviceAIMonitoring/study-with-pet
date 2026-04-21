"""
ViewerApp 메인 진입점

각 슬라이드 기능은 Mixin 클래스로 분리되어 있습니다.
  - screens/main.py  : MainScreenMixin   (메인 화면)
  - screens/character.py  : CharScreenMixin   (캐릭터 선택/목록/생성)
  - screens/group.py : GroupScreenMixin  (단체방)
  - screens/camera.py: CameraScreenMixin (카메라 피드)
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

from config import (
    MAIN, GROUP_LIST, GROUP_CREATE, GROUP_JOIN, DAILY_GOAL,
    SELECT_CHAR, GROUP_ROOM, PERSONAL_CAMERA, CHAR_LIST, CREATE_CHAR,
)
from .screens import (
    MainScreenMixin,
    CharScreenMixin,
    GroupScreenMixin,
    StudyFlowMixin,
    GroupStudyMixin,
    PersonalStudyMixin,
    StudyGrowthMixin,
    CameraScreenMixin,
    DailyGoalTimeSettingScreenMixin,
)
from .states import CameraState, PersonalStudyState, GroupStudyState, NavigationState
from .screen_manager import ScreenManager
from .onscreen_keyboard import OnScreenKeyboard
from .layouts import compose_grid, compose_group, compose_others_column
from .frame_utils import build_waiting_frame, draw_rect_border, CAMERA_BORDER_BGR


class ViewerApp(MainScreenMixin, CharScreenMixin, GroupScreenMixin, StudyFlowMixin, GroupStudyMixin, PersonalStudyMixin, StudyGrowthMixin, CameraScreenMixin, DailyGoalTimeSettingScreenMixin):

    THEME_COZY_STUDY = {
        "ivory": "#F6F2EA",
        "white": "#FFFDF8",
        "beige": "#F0E8DC",
        "sand": "#E3D9C8",
        "pink": "#F9DFDF",
        "pink_hover": "#E6B6B6",
        "gray": "#E8E6E3",
        "gray_hover": "#DAD6D1",
        "text": "#2F2A24",
        "text_muted": "#75685C",
        "error": "#C75B4B",
        "on_primary": "#2F2A24",
    }

    # ──────────────────────────────────────────────
    # 초기화
    # ──────────────────────────────────────────────

    def __init__(self, args):
        self.args = args
        self.frame_map = {}
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self._socket_generation = 0

        # ──── 상태 객체 초기화 ────────────────────────────────────────────────
        self.camera_state = CameraState()
        self.personal_study_state = PersonalStudyState()
        self.group_study_state = GroupStudyState()
        self.nav_state = NavigationState()

        # ──── 기존 호환성 유지 (점진적 마이그레이션용) ────────────────────────
        # 카메라 상태
        self.camera_running = False
        self.camera_thread = None
        self.latest_frame = None
        self._camera_anim_sets = {}
        self._camera_char_frames = []
        self._camera_char_frame_idx = 0
        self._camera_char_anim_running = False
        self._camera_signal_lock = threading.Lock()
        self._camera_current_signal = None

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
        self._group_char_id = None
        self._group_char_anim_running = False
        self._group_char_anim_sets = {}   # {"happy": [...], "tail": [...], "tear": [...]}
        self._group_char_current_anim = "tail"

        # 단체방 공부 시간/성장 상태
        self._group_study_running = False
        self._group_study_start_time = 0.0
        self._group_study_elapsed_seconds = 0
        self._group_study_accumulated_points = 0

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("green")

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

        self.screen_main = ctk.CTkFrame(self.container)
        self.screen_char_legacy = ctk.CTkFrame(self.container)
        self.screen_char_list = ctk.CTkFrame(self.container)
        self.screen_char_create = ctk.CTkFrame(self.container)
        self.screen_group = ctk.CTkFrame(self.container)
        self.screen_group_list = ctk.CTkFrame(self.container)
        self.screen_group_join = ctk.CTkFrame(self.container)
        self.screen_group_create = ctk.CTkFrame(self.container)
        self.screen_char_select = ctk.CTkFrame(self.container)
        self.screen_daily_goal = ctk.CTkFrame(self.container)
        self.screen_camera = ctk.CTkFrame(self.container)

        self.theme = dict(self.THEME_COZY_STUDY)
        self._apply_theme_to_root()

        # 화상 키보드 (단체방 생성/참가 화면용)
        self.onscreen_keyboard = OnScreenKeyboard(
            self.container,
            theme=self.theme,
            make_font=self._make_font,
            fg_color=self.theme["beige"],
            corner_radius=12,
            border_width=1,
            border_color=self.theme["sand"],
        )

        self._screen_char_legacy_page = 0
        self._screen_char_list_page = 0
        self._screen_char_create_page = 0
        self._screen_char_select_page = 0

        self._refresh_period_ms = max(10, self.args.refresh_ms)

        # Lazy loading: 화면별 1회 빌드 여부
        self._built_screens = set()

        # ──── ScreenManager 초기화 및 화면 등록 ────
        self.screen_manager = ScreenManager()

        def _ensure_screen_built(screen_id: int):
            if screen_id in self._built_screens:
                return

            if screen_id == MAIN:
                self._build_screen_main()
            elif screen_id == GROUP_LIST:
                self._build_screen_group_list()
            elif screen_id == GROUP_CREATE:
                self._build_screen_group_create()
            elif screen_id == GROUP_JOIN:
                self._build_screen_group_join()
            elif screen_id == DAILY_GOAL:
                self._build_screen_daily_goal()
            elif screen_id == SELECT_CHAR:
                self._build_screen_char_select()
            elif screen_id == GROUP_ROOM:
                self._build_screen_group()
            elif screen_id == PERSONAL_CAMERA:
                self._build_screen_camera()
            elif screen_id == CHAR_LIST:
                self._build_screen_char_list()
            elif screen_id == CREATE_CHAR:
                self._build_screen_char_create()
            else:
                return

            self._built_screens.add(screen_id)
        
        # 각 화면별 on_show/on_hide 콜백 정의
        def _on_show_main():
            for child in self.screen_main.winfo_children():
                child.destroy()
            self._build_screen_main()
        
        def _on_show_group_list():
            _ensure_screen_built(GROUP_LIST)
            self._refresh_group_list()
        
        def _on_show_group_create():
            _ensure_screen_built(GROUP_CREATE)
            self.create_name_entry.delete(0, "end")
            self.create_code_entry.delete(0, "end")
            self.create_error_label.configure(text="")
            self.create_submit_btn.configure(state="normal", text="생성하기")
        
        def _on_show_group_join():
            _ensure_screen_built(GROUP_JOIN)
            self.join_name_entry.delete(0, "end")
            self.join_code_entry.delete(0, "end")
            self.join_error_label.configure(text="")
            self.join_submit_btn.configure(state="normal", text="참가하기")
        
        def _on_show_daily_goal():
            # 매번 새로 빌드 (시간 초기화 + 캐릭터 갱신)
            for child in self.screen_daily_goal.winfo_children():
                child.destroy()
            self._build_screen_daily_goal()

        def _on_show_select_char():
            _ensure_screen_built(SELECT_CHAR)
            self._screen_char_select_page = 0
            self._refresh_char_select()
        
        def _on_show_group_room():
            _ensure_screen_built(GROUP_ROOM)
            self._reload_group_character_overlay()
        
        def _on_show_personal_camera():
            for child in self.screen_camera.winfo_children():
                child.destroy()
            self._build_screen_camera()
        
        def _on_show_char_list():
            self._rebuild_screen_char_list()

        def _on_show_create_char():
            self._build_screen_char_create()
        
        # 화면 등록
        self.screen_manager.register(MAIN, self.screen_main, on_show=_on_show_main)
        self.screen_manager.register(GROUP_LIST, self.screen_group_list, on_show=_on_show_group_list)
        self.screen_manager.register(GROUP_CREATE, self.screen_group_create, on_show=_on_show_group_create)
        self.screen_manager.register(GROUP_JOIN, self.screen_group_join, on_show=_on_show_group_join)
        self.screen_manager.register(DAILY_GOAL, self.screen_daily_goal, on_show=_on_show_daily_goal, on_hide=self._on_daily_goal_hide)
        self.screen_manager.register(SELECT_CHAR, self.screen_char_select, on_show=_on_show_select_char)
        self.screen_manager.register(GROUP_ROOM, self.screen_group, on_show=_on_show_group_room)
        self.screen_manager.register(PERSONAL_CAMERA, self.screen_camera, on_show=_on_show_personal_camera)
        self.screen_manager.register(CHAR_LIST, self.screen_char_list, on_show=_on_show_char_list)
        self.screen_manager.register(CREATE_CHAR, self.screen_char_create, on_show=_on_show_create_char)

        self.show_screen(MAIN)

    def _apply_theme_to_root(self):
        bg = self.theme["ivory"]
        self.root.configure(fg_color=bg)
        self.container.configure(fg_color=bg)
        screens = [
            self.screen_main,
            self.screen_char_legacy,
            self.screen_char_list,
            self.screen_char_create,
            self.screen_group,
            self.screen_group_list,
            self.screen_group_join,
            self.screen_group_create,
            self.screen_char_select,
            self.screen_daily_goal,
            self.screen_camera,
        ]
        for screen in screens:
            screen.configure(fg_color=bg)

    def _topbar_style(self):
        return {
            "fg_color": self.theme["beige"],
            "corner_radius": 12,
            "border_width": 1,
            "border_color": self.theme["sand"],
        }

    def _surface_style(self):
        return {
            "fg_color": self.theme["white"],
            "corner_radius": 12,
            "border_width": 1,
            "border_color": self.theme["sand"],
        }

    def _primary_button_style(self):
        return {
            "fg_color": self.theme["pink"],
            "hover_color": self.theme["pink_hover"],
            "text_color": self.theme["on_primary"],
        }

    def _secondary_button_style(self):
        return {
            "fg_color": self.theme["pink"],
            "hover_color": self.theme["pink_hover"],
            "text_color": self.theme["on_primary"],
        }

    def _accent_button_style(self):
        return {
            "fg_color": self.theme["beige"],
            "hover_color": self.theme["sand"],
            "text_color": self.theme["text"],
        }

    def _exit_button_style(self):
        return {
            "fg_color": "#E8E6E3",
            "hover_color": "#DAD6D1",
            "text_color": self.theme["text"],
            "border_width": 1,
            "border_color": self.theme["sand"],
        }

    def _error_text_style(self):
        return {
            "text_color": self.theme["error"],
        }

    def _muted_text_style(self):
        return {
            "text_color": self.theme["text_muted"],
        }

    def _entry_style(self):
        return {
            "fg_color": self.theme["white"],
            "border_color": self.theme["sand"],
            "text_color": self.theme["text"],
            "placeholder_text_color": self.theme["text_muted"],
        }

    # ──────────────────────────────────────────────
    # 슬라이드 라우팅
    # ──────────────────────────────────────────────

    def show_screen(self, screen_id: int):
        # 화면 전환 시 화상 키보드 자동 숨김
        if hasattr(self, "onscreen_keyboard") and self.onscreen_keyboard.is_visible:
            self.onscreen_keyboard.hide()

        def _hide_all():
            for widget in self.container.winfo_children():
                widget.pack_forget()
        
        self.screen_manager.show(self.container, screen_id, _hide_all)
        self.current_screen = screen_id

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
        self._update_image()
        self.root.after(self._refresh_period_ms, self._schedule_update)

    def _update_image(self):
        screen = getattr(self, "current_screen", MAIN)

        if screen == PERSONAL_CAMERA:
            if not hasattr(self, "img_label"):
                return
            with self.lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()
            if frame is None:
                canvas = build_waiting_frame(self.args.canvas_width, self.args.canvas_height)
            else:
                canvas = frame


            # 기존대로 사각형 프레임에 일반 사각형 테두리 적용
            draw_rect_border(canvas, color=CAMERA_BORDER_BGR, thickness=4)

            try:
                rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            except Exception:
                rgb = canvas[:, :, ::-1]
            pil = Image.fromarray(rgb)
            # 졸음 감지 시 angry_goblin 오버레이 합성 (알파 투명)
            goblin_frames = getattr(self, '_goblin_frames', [])
            if getattr(self, '_goblin_visible', False) and goblin_frames:
                idx = self._goblin_frame_idx % len(goblin_frames)
                g = goblin_frames[idx]
                gx = (pil.width - g.width) // 2
                gy = (pil.height - g.height) // 2
                pil_rgba = pil.convert("RGBA")
                overlay = Image.new("RGBA", pil_rgba.size, (0, 0, 0, 0))
                overlay.paste(g, (gx, gy))
                pil = Image.alpha_composite(pil_rgba, overlay).convert("RGB")
            img_tk = ImageTk.PhotoImage(pil)
            self.img_label.image = img_tk
            self.img_label.configure(image=img_tk)

        elif screen == GROUP_ROOM:
            if not hasattr(self, "group_img_label"):
                return
            self._tick_group_study_growth()

            with self.lock:
                local_frame = None if self.latest_frame is None else self.latest_frame.copy()
                frame_map_copy = dict(self.frame_map)

            # 메인 카메라 — 개인방과 동일하게 직접 표시
            if local_frame is None:
                main_canvas = build_waiting_frame(self.args.canvas_width, self.args.canvas_height)
            else:
                main_canvas = local_frame

            draw_rect_border(main_canvas, color=CAMERA_BORDER_BGR, thickness=4)

            try:
                rgb = cv2.cvtColor(main_canvas, cv2.COLOR_BGR2RGB)
            except Exception:
                rgb = main_canvas[:, :, ::-1]
            pil = Image.fromarray(rgb)
            # 졸음 감지 시 angry_goblin 오버레이 합성 (단체방)
            goblin_frames = getattr(self, '_goblin_frames', [])
            if getattr(self, '_group_goblin_visible', False) and goblin_frames:
                idx = self._group_goblin_frame_idx % len(goblin_frames)
                g = goblin_frames[idx]
                gx = (pil.width - g.width) // 2
                gy = (pil.height - g.height) // 2
                pil_rgba = pil.convert("RGBA")
                overlay = Image.new("RGBA", pil_rgba.size, (0, 0, 0, 0))
                overlay.paste(g, (gx, gy))
                pil = Image.alpha_composite(pil_rgba, overlay).convert("RGB")
            img_tk = ImageTk.PhotoImage(pil)
            self.group_img_label.image = img_tk
            self.group_img_label.configure(image=img_tk)

            # 다른 참가자 사이드 컬럼
            if hasattr(self, "_group_others_label"):
                hex_ivory = self.theme["ivory"].lstrip("#")
                r, g, b = int(hex_ivory[0:2], 16), int(hex_ivory[2:4], 16), int(hex_ivory[4:6], 16)
                ivory_bgr = (b, g, r)
                others = sorted(
                    [(k, v) for k, v in frame_map_copy.items()],
                    key=lambda item: item[0].lower(),
                )
                others_canvas = compose_others_column(
                    others,
                    self.args.sub_width,
                    self.args.canvas_height,
                    self.args.sub_width,
                    self.args.sub_height,
                    bg_color=ivory_bgr,
                )
                try:
                    others_rgb = cv2.cvtColor(others_canvas, cv2.COLOR_BGR2RGB)
                except Exception:
                    others_rgb = others_canvas[:, :, ::-1]
                others_pil = Image.fromarray(others_rgb)
                others_tk = ImageTk.PhotoImage(others_pil)
                self._group_others_label.image = others_tk
                self._group_others_label.configure(image=others_tk)

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
        dlg.configure(bg=self.theme["beige"])
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

        box = tk.Frame(
            dlg,
            bg=self.theme["white"],
            highlightthickness=1,
            highlightbackground=self.theme["sand"],
        )
        box.pack(fill="both", expand=True)

        title_lbl = tk.Label(box, text=title, fg=self.theme["text"], bg=self.theme["white"],
                             font=self._make_font(13, "bold"))
        title_lbl.pack(pady=(18, 6))

        msg_lbl = tk.Label(box, text=message, fg=self.theme["text_muted"], bg=self.theme["white"],
                           font=self._make_font(12), wraplength=280, justify="center")
        msg_lbl.pack(pady=(0, 14), padx=12)

        for widget in (dlg, box, title_lbl, msg_lbl):
            widget.bind("<Button-1>", lambda _e: dlg.destroy())

        dlg.grab_set()
