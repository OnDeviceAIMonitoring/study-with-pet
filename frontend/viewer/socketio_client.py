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


def _cleanup_stale_frames(app, stale_seconds: float = 3.0):
    """일정 시간 동안 갱신되지 않은 원격 프레임을 frame_map에서 제거합니다."""
    now = datetime.now()
    to_remove = []
    with app.lock:
        for nick, info in app.frame_map.items():
            try:
                updated = datetime.fromisoformat(info["updated_at"])
                if (now - updated).total_seconds() > stale_seconds:
                    to_remove.append(nick)
            except (ValueError, KeyError):
                to_remove.append(nick)
        for nick in to_remove:
            app.frame_map.pop(nick, None)
    if to_remove:
        print(f"[viewer:ctk] stale 프레임 제거: {to_remove}")


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

    @sio.on("member_left")
    async def on_member_left(data):
        """룸에서 나간 클라이언트의 프레임을 즉시 제거합니다."""
        nickname = data.get("nickname", "")
        if nickname:
            with app.lock:
                app.frame_map.pop(nickname, None)
            print(f"[viewer:ctk] removed frame for disconnected member: {nickname}")

    @sio.event
    async def disconnect():
        print("[viewer:ctk] disconnected")

    try:
        await sio.connect(app.args.server, socketio_path="socket.io")
        # 그룹 모드에서 로컬 카메라 프레임을 주기적으로 서버에 전송하는 백그라운드 태스크
        async def _frame_sender():
            import cv2

            while not app.stop_event.is_set():
                await asyncio.sleep(0.2)
                try:
                    # 오래된(stale) 원격 프레임 정리: 3초 이상 갱신 안 된 프레임 제거
                    _cleanup_stale_frames(app, stale_seconds=3)
                    # 카메라 실행 중 + 그룹 슬라이드(3)일 때만 전송
                    if not getattr(app, "camera_running", False):
                        continue
                    if getattr(app, "current_slide", None) != 3:
                        continue
                    # 소켓 연결 상태 확인
                    if not sio.connected:
                        continue
                    # non-blocking 잠금: 이벤트 루프 차단 방지
                    acquired = app.lock.acquire(blocking=False)
                    if not acquired:
                        continue
                    try:
                        frame = None if app.latest_frame is None else app.latest_frame.copy()
                    finally:
                        app.lock.release()
                    if frame is None:
                        continue
                    # JPEG 인코딩 후 base64 변환하여 서버에 전송
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
                    # 개별 전송 실패 시 태스크 전체가 죽지 않도록 예외 처리
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
