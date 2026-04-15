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


MAIN_PROFILE = {
    "width": 640,
    "height": 480,
    "fps": 15,
}

SUB_PROFILE = {
    "width": 320,
    "height": 240,
    "fps": 10,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Digital Pet Socket.IO client test")
    parser.add_argument("--server", default="http://127.0.0.1:8000")
    parser.add_argument("--room", default="TEST_ROOM")
    parser.add_argument("--name", default="app_user")
    parser.add_argument("--state", default="focused")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--fps", type=int, default=0)
    parser.add_argument("--send-video", action="store_true")
    parser.add_argument("--use-camera", action="store_true")
    parser.add_argument("--camera-device", type=int, default=0)
    parser.add_argument("--frame-width", type=int, default=0)
    parser.add_argument("--frame-height", type=int, default=0)
    parser.add_argument("--jpeg-quality", type=int, default=70)
    parser.add_argument("--is-main", action="store_true")
    parser.add_argument("--audio-on", action="store_true")
    return parser.parse_args()


def resolve_video_policy(args: argparse.Namespace) -> tuple[int, int, int]:
    profile = MAIN_PROFILE if args.is_main else SUB_PROFILE
    width = args.frame_width if args.frame_width > 0 else profile["width"]
    height = args.frame_height if args.frame_height > 0 else profile["height"]
    fps = args.fps if args.fps > 0 else profile["fps"]

    if width <= 0 or height <= 0:
        raise RuntimeError("--frame-width and --frame-height must be greater than 0.")
    if fps <= 0:
        raise RuntimeError("--fps must be greater than 0.")

    return width, height, fps


def build_fake_jpeg_base64(name: str, frame_idx: int, width: int, height: int) -> str:
    if cv2 is None or np is None:
        raise RuntimeError("OpenCV and numpy are required to build fake JPEG frames.")

    frame = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(frame, f"{name}", (12, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 255, 200), 2)
    cv2.putText(frame, f"frame={frame_idx}", (12, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(
        frame,
        datetime.now().strftime("%H:%M:%S"),
        (12, 165),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (180, 220, 255),
        2,
    )

    encode_ok, encoded = cv2.imencode(
        ".jpg",
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), 70],
    )
    if not encode_ok:
        raise RuntimeError("Failed to encode fake frame as JPEG.")

    return base64.b64encode(encoded.tobytes()).decode()


def open_camera(args: argparse.Namespace, width: int, height: int):
    if cv2 is None:
        raise RuntimeError("OpenCV is not installed. Install requirements again to use --use-camera.")

    capture = cv2.VideoCapture(args.camera_device)
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    if not capture.isOpened():
        raise RuntimeError(
            f"Could not open camera device {args.camera_device}. Check the Raspberry Pi camera connection."
        )

    return capture


def build_camera_frame_base64(capture, jpeg_quality: int) -> str:
    ok, frame = capture.read()
    if not ok or frame is None:
        raise RuntimeError("Failed to read a frame from the camera.")

    encode_ok, encoded = cv2.imencode(
        ".jpg",
        frame,
        [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality],
    )
    if not encode_ok:
        raise RuntimeError("Failed to encode a camera frame as JPEG.")

    return base64.b64encode(encoded.tobytes()).decode()


async def main() -> None:
    args = parse_args()
    client = socketio.AsyncClient()
    running = True
    capture = None
    video_width = 0
    video_height = 0
    video_fps = 0

    if args.send_video:
        video_width, video_height, video_fps = resolve_video_policy(args)
        print(
            "[client] video profile "
            f"is_main={args.is_main} "
            f"size={video_width}x{video_height} "
            f"fps={video_fps}"
        )

    if args.use_camera:
        if not args.send_video:
            raise RuntimeError("--use-camera requires --send-video.")
        if args.jpeg_quality < 1 or args.jpeg_quality > 100:
            raise RuntimeError("--jpeg-quality must be between 1 and 100.")
        capture = open_camera(args, video_width, video_height)

    async def send_video_loop() -> None:
        interval = 1 / video_fps
        frame_idx = 0
        while running:
            frame_idx += 1
            if capture is not None:
                jpeg_base64 = build_camera_frame_base64(capture, args.jpeg_quality)
            else:
                jpeg_base64 = build_fake_jpeg_base64(
                    args.name,
                    frame_idx,
                    video_width,
                    video_height,
                )

            await client.emit(
                "video_frame",
                {
                    "room_code": args.room,
                    "nickname": args.name,
                    "jpeg_base64": jpeg_base64,
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "is_main": args.is_main,
                },
            )
            await asyncio.sleep(interval)

    @client.event
    async def connect():
        print("[client] connected")
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
                "state": args.state,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            },
        )

        await client.emit(
            "audio_toggle",
            {
                "room_code": args.room,
                "nickname": args.name,
                "audio_on": args.audio_on,
            },
        )

    @client.on("member_joined")
    async def on_member_joined(data):
        print(f"[client] member_joined: {data}")

    @client.on("member_status")
    async def on_member_status(data):
        print(f"[client] member_status: {data}")

    @client.on("member_left")
    async def on_member_left(data):
        print(f"[client] member_left: {data}")

    @client.on("member_list")
    async def on_member_list(data):
        print(f"[client] member_list: {data}")

    @client.on("join_failed")
    async def on_join_failed(data):
        print(f"[client] join_failed: {data}")

    @client.on("room_video")
    async def on_room_video(data):
        print(
            "[client] room_video: "
            f"nickname={data.get('nickname')} "
            f"is_main={data.get('is_main')} "
            f"payload_len={len(data.get('jpeg_base64', ''))}"
        )

    @client.on("audio_changed")
    async def on_audio_changed(data):
        print(f"[client] audio_changed: {data}")

    @client.on("video_rejected")
    async def on_video_rejected(data):
        print(f"[client] video_rejected: {data}")

    @client.event
    async def disconnect():
        print("[client] disconnected")

    try:
        await client.connect(args.server, socketio_path="socket.io")
        sender_task = None
        if args.send_video:
            sender_task = asyncio.create_task(send_video_loop())

        await asyncio.sleep(args.duration)
        running = False
        if sender_task:
            await sender_task

        await client.disconnect()
    finally:
        if capture is not None:
            capture.release()


if __name__ == "__main__":
    asyncio.run(main())
