import argparse
import asyncio
import base64
from datetime import datetime

import socketio

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Digital Pet room video viewer")
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


def require_opencv() -> None:
    if cv2 is None or np is None:
        raise RuntimeError("OpenCV is not installed. Install requirements again before running the viewer.")


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
    frame_map: dict[str, dict],
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
    # Left side is intentionally reserved for a character area in the next phase.
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

    # Keep one participant as a large main tile and render all others in smaller tiles.
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


async def main() -> None:
    args = parse_args()
    require_opencv()
    client = socketio.AsyncClient()
    frame_map: dict[str, dict] = {}
    stop_event = asyncio.Event()

    async def render_loop() -> None:
        while not stop_event.is_set():
            canvas = compose_grid(
                frame_map,
                args.canvas_width,
                args.canvas_height,
                args.left_reserved_width,
                args.main_width,
                args.main_height,
                args.sub_width,
                args.sub_height,
            )
            cv2.imshow(args.window_title, canvas)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                stop_event.set()
                break
            await asyncio.sleep(args.refresh_ms / 1000)

    @client.event
    async def connect():
        print("[viewer] connected")
        await client.emit(
            "join_room",
            {
                "room_code": args.room,
                "nickname": args.name,
            },
        )
        await client.emit(
            "status_update",
            {
                "room_code": args.room,
                "nickname": args.name,
                "state": "viewer",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            },
        )

    @client.on("member_list")
    async def on_member_list(data):
        print(f"[viewer] member_list: {data}")

    @client.on("member_left")
    async def on_member_left(data):
        nickname = data.get("nickname")
        if nickname:
            frame_map.pop(nickname, None)
        print(f"[viewer] member_left: {data}")

    @client.on("join_failed")
    async def on_join_failed(data):
        print(f"[viewer] join_failed: {data}")
        stop_event.set()

    @client.on("room_video")
    async def on_room_video(data):
        nickname = data.get("nickname", "unknown")
        jpeg_base64 = data.get("jpeg_base64", "")
        if not jpeg_base64:
            return

        try:
            frame = decode_frame(jpeg_base64)
        except Exception as exc:
            print(f"[viewer] failed to decode frame from {nickname}: {exc}")
            return

        frame_map[nickname] = {
            "frame": frame,
            "is_main": bool(data.get("is_main", False)),
            "updated_at": data.get("ts", datetime.now().isoformat(timespec="seconds")),
        }

    @client.event
    async def disconnect():
        print("[viewer] disconnected")

    render_task = None
    try:
        await client.connect(args.server, socketio_path="socket.io")
        render_task = asyncio.create_task(render_loop())

        if args.duration > 0:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=args.duration)
            except asyncio.TimeoutError:
                stop_event.set()
        else:
            await stop_event.wait()
    finally:
        stop_event.set()
        if render_task is not None:
            await render_task
        if client.connected:
            await client.disconnect()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    asyncio.run(main())