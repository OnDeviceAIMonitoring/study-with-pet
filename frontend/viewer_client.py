"""
뷰어 클라이언트 (CustomTkinter 버전)

이 모듈은 Socket.IO 서버에서 전송되는 JPEG 프레임을 수신하여
CustomTkinter GUI 창에 그리드 형태로 렌더링합니다.

- 요구: OpenCV, NumPy, Pillow, python-socketio, customtkinter
- 실행 예: python frontend/viewer_client.py --server http://127.0.0.1:8000 --room TEST_ROOM --name viewer_user
"""

import argparse
import asyncio
import base64
from datetime import datetime
import threading
from typing import Dict
import time

import socketio
import tkinter.font as tkfont

try:
    import cv2
    import numpy as np
except ImportError:
    raise RuntimeError("OpenCV and NumPy are required. Install requirements before running the viewer.")

try:
    import customtkinter as ctk
    from PIL import Image, ImageTk
except Exception as exc:
    raise RuntimeError("customtkinter and Pillow are required. Install them to run the GUI: pip install customtkinter pillow")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Digital Pet room video viewer (CustomTkinter)")
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--room", default="TEST_ROOM")
    parser.add_argument("--name", default="viewer_user")
    parser.add_argument("--duration", type=int, default=0)
    parser.add_argument("--window-title", default="Digital Pet Room Viewer")
    parser.add_argument("--canvas-width", type=int, default=1024)
    parser.add_argument("--canvas-height", type=int, default=600)
    parser.add_argument("--left-reserved-width", type=int, default=300)
    parser.add_argument("--main-width", type=int, default=430)
    parser.add_argument("--main-height", type=int, default=320)
    parser.add_argument("--sub-width", type=int, default=140)
    parser.add_argument("--sub-height", type=int, default=105)
    parser.add_argument("--refresh-ms", type=int, default=50)
    return parser.parse_args()


def decode_frame(jpeg_base64: str):
    raw = base64.b64decode(jpeg_base64)
    encoded = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Failed to decode JPEG frame.")
    return frame


def fit_frame(frame, width: int, height: int):
    src_h, src_w = frame.shape[:2]
    scale = min(width / src_w, height / src_h)
    dst_w = max(1, int(src_w * scale))
    dst_h = max(1, int(src_h * scale))
    resized = cv2.resize(frame, (dst_w, dst_h))

    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    y_offset = (height - dst_h) // 2
    x_offset = (width - dst_w) // 2
    canvas[y_offset:y_offset + dst_h, x_offset:x_offset + dst_w] = resized
    return canvas


def draw_label(frame, nickname: str, is_main: bool, updated_at: str):
    label = nickname
    if is_main:
        label += " [MAIN]"

    cv2.rectangle(frame, (0, 0), (frame.shape[1], 34), (25, 25, 25), -1)
    cv2.putText(frame, label, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, updated_at, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
    return frame


def build_waiting_frame(width: int, height: int):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(frame, "Waiting for frames...", (20, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    return frame


def compose_grid(
    frame_map: Dict[str, dict],
    canvas_width: int,
    canvas_height: int,
    left_reserved_width: int,
    main_width: int,
    main_height: int,
    sub_width: int,
    sub_height: int,
):
    if left_reserved_width >= canvas_width:
        raise RuntimeError("--left-reserved-width must be smaller than --canvas-width.")

    if main_width + (sub_width * 2) > (canvas_width - left_reserved_width):
        raise RuntimeError("Tile widths exceed the right-side video area width.")

    items = sorted(
        frame_map.items(),
        key=lambda item: (
            not item[1]["is_main"],
            item[0].lower(),
        ),
    )[:6]

    full_canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    full_canvas[:, :left_reserved_width] = (18, 18, 18)
    cv2.putText(
        full_canvas,
        "Character Area",
        (20, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (170, 170, 170),
        2,
    )

    right_width = canvas_width - left_reserved_width
    right_canvas = full_canvas[:, left_reserved_width:]

    if not items:
        waiting = build_waiting_frame(right_width, canvas_height)
        right_canvas[:, :] = waiting
        return full_canvas

    main_nickname, main_info = items[0]
    sub_items = items[1:]

    main_tile = fit_frame(main_info["frame"], main_width, main_height)
    main_tile = draw_label(main_tile, main_nickname, main_info["is_main"], main_info["updated_at"])

    sub_columns = 2
    sub_rows = max(1, (len(sub_items) + sub_columns - 1) // sub_columns)
    sub_panel_w = sub_columns * sub_width
    sub_panel_h = sub_rows * sub_height

    video_area_h = max(main_height, sub_panel_h)
    video_area_w = main_width + sub_panel_w
    video_area = np.zeros((video_area_h, video_area_w, 3), dtype=np.uint8)

    main_y = (video_area_h - main_height) // 2
    video_area[main_y:main_y + main_height, 0:main_width] = main_tile

    for index, (nickname, info) in enumerate(sub_items):
        row = index // sub_columns
        col = index % sub_columns
        tile = fit_frame(info["frame"], sub_width, sub_height)
        tile = draw_label(tile, nickname, info["is_main"], info["updated_at"]) 
        y_start = row * sub_height
        x_start = main_width + (col * sub_width)
        video_area[y_start:y_start + sub_height, x_start:x_start + sub_width] = tile

    right_y = (canvas_height - video_area_h) // 2
    right_x = (right_width - video_area_w) // 2
    right_canvas[
        right_y:right_y + video_area_h,
        right_x:right_x + video_area_w,
    ] = video_area

    return full_canvas


def compose_group(
    frame_map: Dict[str, dict],
    canvas_width: int,
    canvas_height: int,
    left_reserved_width: int,
    main_width: int,
    main_height: int,
    sub_width: int,
    sub_height: int,
):
    """단체 공부용 레이아웃: 중앙에 메인(내 카메라), 오른쪽에 참가자들을 세로로 나열

    - 왼쪽은 기존대로 캐릭터 영역을 유지
    - 중앙 영역에 메인 비디오를 가운데 정렬
    - 오른쪽에 다른 참가자들의 타일을 상하로 정렬
    """
    if left_reserved_width >= canvas_width:
        raise RuntimeError("--left-reserved-width must be smaller than --canvas-width.")

    right_total_width = canvas_width - left_reserved_width
    if right_total_width <= 0:
        raise RuntimeError("Canvas too small for right area.")

    # allocate a vertical column on the far right for participant tiles
    right_col_w = sub_width
    center_w = right_total_width - right_col_w
    if center_w <= 0:
        raise RuntimeError("Not enough width for center/main area.")

    # prepare canvas
    full_canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    full_canvas[:, :left_reserved_width] = (18, 18, 18)
    cv2.putText(
        full_canvas,
        "Character Area",
        (20, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (170, 170, 170),
        2,
    )

    right_canvas = full_canvas[:, left_reserved_width:]

    if not frame_map:
        waiting = build_waiting_frame(right_total_width, canvas_height)
        right_canvas[:, :] = waiting
        return full_canvas

    # pick main (first is_main True), otherwise the first item
    items = sorted(
        frame_map.items(),
        key=lambda item: (
            not item[1]["is_main"],
            item[0].lower(),
        ),
    )

    main_nickname, main_info = items[0]
    others = [it for it in items[1:]]

    # build main tile and place centered in center_w x canvas_height
    main_tile = fit_frame(main_info["frame"], main_width, main_height)
    main_tile = draw_label(main_tile, main_nickname, main_info["is_main"], main_info["updated_at"])

    center_area = np.zeros((canvas_height, center_w, 3), dtype=np.uint8)
    # place main centered
    m_h, m_w = main_tile.shape[:2]
    y_off = (canvas_height - m_h) // 2
    x_off = max(0, (center_w - m_w) // 2)
    center_area[y_off:y_off + m_h, x_off:x_off + m_w] = main_tile

    # build right column with others stacked vertically
    col_area = np.zeros((canvas_height, right_col_w, 3), dtype=np.uint8)
    max_display = max(1, canvas_height // sub_height)
    display_items = others[:max_display]
    total_h = len(display_items) * sub_height
    start_y = (canvas_height - total_h) // 2
    for idx, (nick, info) in enumerate(display_items):
        tile = fit_frame(info["frame"], sub_width, sub_height)
        tile = draw_label(tile, nick, info["is_main"], info["updated_at"])
        y0 = start_y + idx * sub_height
        col_area[y0:y0 + sub_height, 0:sub_width] = tile

    # place center_area and col_area into right_canvas
    right_canvas[:, :center_w] = center_area
    right_canvas[:, center_w:center_w + right_col_w] = col_area

    return full_canvas


# ---- CustomTkinter GUI + background Socket.IO client ----
class ViewerApp:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.frame_map: Dict[str, dict] = {}
        self.lock = threading.Lock()
        self.sio = socketio.AsyncClient()
        self.stop_event = threading.Event()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title(self.args.window_title)
        self.root.geometry(f"{self.args.canvas_width}x{self.args.canvas_height}")

        # detect a font family that supports Korean characters
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
            # fallback to the first available family
            self.font_family = families[0] if families else "TkDefaultFont"

        def make_font(size: int, weight: str = "normal"):
            return (self.font_family, size, weight)

        self._make_font = make_font

        # Container for slides
        self.container = ctk.CTkFrame(self.root)
        self.container.pack(fill="both", expand=True)

        # Slides (frames)
        self.slide1 = ctk.CTkFrame(self.container)
        self.slide13 = ctk.CTkFrame(self.container)
        self.slide_group = ctk.CTkFrame(self.container)
        self.slide_camera = ctk.CTkFrame(self.container)

        # Schedule GUI update (used for video grid if enabled later)
        self._refresh_period_ms = max(10, self.args.refresh_ms)

        # Build slide UIs
        self._build_slide1()
        self._build_slide13()
        self._build_group_slide()
        self._build_camera_slide()

        # Start with slide1 visible
        self.show_slide(1)

    def start(self):
        # Start socketio background thread
        t = threading.Thread(target=self._start_socketio_loop, daemon=True)
        t.start()
        # Start GUI update loop
        self._schedule_update()
        # Start Tk mainloop (must be in main thread)
        try:
            self.root.mainloop()
        finally:
            self.stop_event.set()

    def show_slide(self, slide_no: int):
        # simple slide switcher
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
        # Large centered title and vertical buttons
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
        # Top bar: title left, back arrow right
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="보유 캐릭터 (성장 현황)", anchor="w", font=self._make_font(20))
        title.pack(side="left")
        back_btn = ctk.CTkButton(top, text="<", width=40, command=lambda: self.show_slide(1), font=self._make_font(14))
        back_btn.pack(side="right")

        # Content: three character cards centered
        content = ctk.CTkFrame(frame)
        content.pack(fill="both", expand=True, padx=20, pady=10)
        content.grid_columnconfigure((0,1,2), weight=1)

        card_width = 260
        for col in range(3):
            card = ctk.CTkFrame(content, width=card_width, height=380, corner_radius=8)
            card.grid(row=0, column=col, padx=12, pady=8, sticky="nsew")
            # inner placeholder box
            placeholder = ctk.CTkFrame(card, height=220, corner_radius=16)
            placeholder.pack(pady=12, padx=12, fill="x")
            lbl = ctk.CTkLabel(placeholder, text="캐릭터", font=self._make_font(16))
            lbl.place(relx=0.5, rely=0.5, anchor="center")

            name_lbl = ctk.CTkLabel(card, text="캐릭터 이름", font=self._make_font(14))
            name_lbl.pack(pady=(8,2))
            growth_lbl = ctk.CTkLabel(card, text="성장도", font=self._make_font(12))
            growth_lbl.pack()
            # progress bar
            prog = ctk.CTkProgressBar(card, width=200)
            prog.set(0.5)
            prog.pack(pady=10)


    def _on_show_characters(self):
        self.show_slide(13)

    def _on_personal_study(self):
        # show camera slide and start camera capture
        self.show_slide(2)
        self.start_camera()

    def _build_camera_slide(self):
        frame = self.slide_camera
        # Top bar with back button
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="개인 공부 - 카메라", anchor="w", font=self._make_font(18))
        title.pack(side="left")
        back_btn = ctk.CTkButton(top, text="돌아가기", width=80, command=self._on_camera_back, font=self._make_font(12))
        back_btn.pack(side="right")

        # Image display area
        self.img_label = ctk.CTkLabel(frame, text="")
        self.img_label.pack(fill="both", expand=True, padx=10, pady=10)

        # Camera control state
        self.camera_running = False
        self.camera_thread = None
        self.latest_frame = None

    def _build_group_slide(self):
        # 단체 공부 슬라이드: 중앙에 내 카메라(메인), 오른쪽에 다른 클라이언트들 세로 나열
        frame = self.slide_group
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        title = ctk.CTkLabel(top, text="단체 공부 - 방", anchor="w", font=self._make_font(18))
        title.pack(side="left")
        back_btn = ctk.CTkButton(top, text="돌아가기", width=80, command=self._on_group_back, font=self._make_font(12))
        back_btn.pack(side="right")

        # Image display area for composed group view
        self.group_img_label = ctk.CTkLabel(frame, text="")
        self.group_img_label.pack(fill="both", expand=True, padx=10, pady=10)

        # group camera uses same camera thread as personal camera (latest_frame)

    def _on_camera_back(self):
        # stop camera and go back to main menu
        self.stop_camera()
        self.show_slide(1)

    def _on_group_back(self):
        # stop camera and return to main menu
        self.stop_camera()
        self.show_slide(1)

    def _on_group_study(self):
        # show group slide and start local camera (which will be used as main)
        self.show_slide(3)
        self.start_camera()

    def start_camera(self, camera_index: int = 0):
        if self.camera_running:
            return
        self.camera_running = True

        def cam_loop():
            cap = cv2.VideoCapture(camera_index)
            # try to set resolution
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
        # Only update image if an image widget exists (future video view)
        if hasattr(self, "img_label"):
            self._update_image()
        self.root.after(self._refresh_period_ms, self._schedule_update)

    def _update_image(self):
        # If no image label is present, skip (we're on menu slides)
        if not hasattr(self, "img_label"):
            return
        # If we're on camera slide, display latest camera frame; group slide composes center+right; otherwise display composed grid
        if getattr(self, "current_slide", 1) == 2:
            with self.lock:
                frame = None if self.latest_frame is None else self.latest_frame.copy()
            if frame is None:
                # show waiting text as an image
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
            # Keep a reference to avoid GC
            self.img_label.image = img_tk
            self.img_label.configure(image=img_tk)
        elif getattr(self, "current_slide", 1) == 3:
            # Group view: use local camera as main (injected) and remote frames from frame_map
            with self.lock:
                local_frame = None if self.latest_frame is None else self.latest_frame.copy()
                frame_map_copy = dict(self.frame_map)
            if local_frame is None:
                # placeholder main frame if camera not ready
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
            # Convert BGR to RGB
            try:
                rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            except Exception:
                rgb = canvas[:, :, ::-1]
            pil = Image.fromarray(rgb)
            img_tk = ImageTk.PhotoImage(pil)
            # Keep a reference to avoid GC
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
            # Convert BGR to RGB
            try:
                rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
            except Exception:
                rgb = canvas[:, :, ::-1]
            pil = Image.fromarray(rgb)
            img_tk = ImageTk.PhotoImage(pil)
            # Keep a reference to avoid GC
            # If an img_label exists (e.g., camera slide), update it; otherwise ignore
            if hasattr(self, "img_label"):
                self.img_label.image = img_tk
                self.img_label.configure(image=img_tk)

    def _start_socketio_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._socketio_main())

    async def _socketio_main(self):
        @self.sio.event
        async def connect():
            print("[viewer:ctk] connected")
            await self.sio.emit("join_room", {"room_code": self.args.room, "nickname": self.args.name})
            await self.sio.emit(
                "status_update",
                {
                    "room_code": self.args.room,
                    "nickname": self.args.name,
                    "state": "viewer",
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                },
            )

        @self.sio.on("room_video")
        async def on_room_video(data):
            nickname = data.get("nickname", "unknown")
            jpeg_base64 = data.get("jpeg_base64", "")
            if not jpeg_base64:
                return
            try:
                frame = decode_frame(jpeg_base64)
            except Exception as exc:
                print(f"[viewer:ctk] failed to decode frame from {nickname}: {exc}")
                return
            with self.lock:
                self.frame_map[nickname] = {
                    "frame": frame,
                    "is_main": bool(data.get("is_main", False)),
                    "updated_at": data.get("ts", datetime.now().isoformat(timespec="seconds")),
                }

        @self.sio.event
        async def disconnect():
            print("[viewer:ctk] disconnected")

        try:
            await self.sio.connect(self.args.server, socketio_path="socket.io")
            # wait until stop_event is set
            while not self.stop_event.is_set():
                await asyncio.sleep(0.1)
        except Exception as exc:
            print("Socket.IO error:", exc)
        finally:
            if self.sio.connected:
                await self.sio.disconnect()


if __name__ == "__main__":
    args = parse_args()
    app = ViewerApp(args)
    app.start()
