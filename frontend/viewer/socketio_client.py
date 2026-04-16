"""
Socket.IO 배경 클라이언트 실행기

`ViewerApp` 인스턴스를 받아 백그라운드 스레드에서 소켓 연결을 관리합니다.
"""

import asyncio
import threading
from datetime import datetime

import socketio


def start_background(app, generation: int = 0):
    """알 인스턴스를 받아 별도 스레드에서 Socket.IO 이벤트 루프를 시작합니다.

    generation: 현재 소켓 세션 세대 번호. 앱의 _socket_generation이 일치하지 않으면
    해당 스레드는 스스로 종료됩니다.
    """
    t = threading.Thread(target=_start_socketio_loop, args=(app, generation), daemon=True)
    t.start()


def _start_socketio_loop(app, generation: int):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_socketio_main(app, generation))


async def _socketio_main(app, generation: int):
    sio = socketio.AsyncClient()
    app.sio = sio

    @sio.event
    async def connect():
        print(f"[viewer:ctk] connected (gen={generation})")
        await sio.emit("join_room", {"room_code": app.args.room, "nickname": app.args.name})
        await sio.emit(
            "status_update",
            {
                "room_code": app.args.room,
                "nickname": app.args.name,
                "state": "viewer",
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            },
        )

    @sio.on("room_video")
    async def on_room_video(data):
        # 세대 번호가 달라직면 프레임 무시
        if getattr(app, "_socket_generation", 0) != generation:
            return
        nickname = data.get("nickname", "unknown")
        jpeg_base64 = data.get("jpeg_base64", "")
        if not jpeg_base64:
            return
        try:
            # 지연 임포트: frame_utils는 OpenCV 의존성을 포함
            from .frame_utils import decode_frame

            frame = decode_frame(jpeg_base64)
        except Exception as exc:
            print(f"[viewer:ctk] failed to decode frame from {nickname}: {exc}")
            return
        with app.lock:
            app.frame_map[nickname] = {
                "frame": frame,
                "is_main": bool(data.get("is_main", False)),
                "updated_at": data.get("ts", datetime.now().isoformat(timespec="seconds")),
            }

    @sio.event
    async def disconnect():
        print(f"[viewer:ctk] disconnected (gen={generation})")

    try:
        await sio.connect(app.args.server, socketio_path="socket.io")
        while not app.stop_event.is_set() and getattr(app, "_socket_generation", 0) == generation:
            await asyncio.sleep(0.1)
    except Exception as exc:
        print("Socket.IO error:", exc)
    finally:
        if sio.connected:
            await sio.disconnect()
