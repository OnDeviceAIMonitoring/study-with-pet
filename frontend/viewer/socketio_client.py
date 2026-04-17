"""
Socket.IO 배경 클라이언트 실행기

`ViewerApp` 인스턴스를 받아 백그라운드 스레드에서 소켓 연결을 관리합니다.
"""

import asyncio
import threading
from datetime import datetime

import socketio
import base64


def start_background(app):
    """앱 인스턴스를 받아 별도 스레드에서 Socket.IO 이벤트 루프를 시작합니다."""
    t = threading.Thread(target=_start_socketio_loop, args=(app,), daemon=True)
    t.start()


def _start_socketio_loop(app):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_socketio_main(app))


async def _socketio_main(app):
    sio = socketio.AsyncClient()
    app.sio = sio

    @sio.event
    async def connect():
        print("[viewer:ctk] connected")
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
            # 원격 프레임은 항상 is_main=False로 저장 (자기 카메라만 중앙에 표시하기 위함)
            app.frame_map[nickname] = {
                "frame": frame,
                "is_main": False,
                "updated_at": data.get("ts", datetime.now().isoformat(timespec="seconds")),
            }

    @sio.event
    async def disconnect():
        print("[viewer:ctk] disconnected")

    try:
        await sio.connect(app.args.server, socketio_path="socket.io")
        # Start background task to send local camera frames when in group mode
        async def _frame_sender():
            try:
                import cv2
            except Exception:
                cv2 = None
            while not app.stop_event.is_set():
                await asyncio.sleep(0.2)
                # only send when local camera is running and current slide is group
                if not getattr(app, "camera_running", False):
                    continue
                if getattr(app, "current_slide", None) != 3:
                    continue
                with app.lock:
                    frame = None if app.latest_frame is None else app.latest_frame.copy()
                if frame is None:
                    continue
                if cv2 is None:
                    continue
                try:
                    # JPEG encode with modest quality to limit payload size
                    ret, enc = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
                    if not ret:
                        continue
                    b64 = base64.b64encode(enc.tobytes()).decode('ascii')
                    await sio.emit(
                        'video_frame',
                        {
                            'jpeg_base64': b64,
                            'ts': datetime.now().isoformat(timespec='seconds'),
                            'is_main': True,
                        },
                    )
                except Exception as exc:
                    print(f"[viewer:ctk] frame send error: {exc}")

        frame_task = asyncio.create_task(_frame_sender())
        while not app.stop_event.is_set():
            await asyncio.sleep(0.1)
    except Exception as exc:
        print("Socket.IO error:", exc)
    finally:
        try:
            frame_task.cancel()
        except Exception:
            pass
        if sio.connected:
            await sio.disconnect()
