"""
서버: Socket.IO 기반의 간단한 디지털 펫 통신 테스트 서버

이 모듈은 FastAPI와 python-socketio를 사용하여 실시간 룸(join/leave),
비디오 프레임 전송, 오디오 상태 토글 등의 동작을 처리합니다.

주요 전역 구조:
- `SID_INFO`: sid(클라이언트 식별자) -> room/nickname 매핑
- `ROOM_MEMBERS`: room_code -> {sid: nickname} 맵

이 파일의 주석과 함수 설명은 한국어로 작성되어 있어 코드 이해를 돕습니다.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict

import socketio
from fastapi import FastAPI
from pydantic import BaseModel

from backend import database


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


# FastAPI 앱과 Socket.IO 서버 인스턴스
app = FastAPI(title="Digital Pet Comm Test Server", lifespan=lifespan)
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
ROOM_LIMIT = 6

# sid -> {"room_code": str, "nickname": str}
SID_INFO: Dict[str, Dict[str, str]] = {}

# room_code -> {sid: nickname}
ROOM_MEMBERS: Dict[str, Dict[str, str]] = {}


class _RoomPayload(BaseModel):
    name: str
    room_code: str


@app.post("/rooms/create")
async def create_room(payload: _RoomPayload) -> dict:
    """단체방 생성 엔드포인트

    요청 body: {name, room_code}
    반환값: ok, id, name, room_code 또는 오류 코드
    """
    name = payload.name.strip()
    room_code = payload.room_code.strip()
    if not name or not room_code:
        return {"ok": False, "error": "name_and_code_required"}
    room = database.create_room(name, room_code)
    return {"ok": True, **room}


@app.post("/rooms/join")
async def join_room_http(payload: _RoomPayload) -> dict:
    """단체방 참가 검증 엔드포인트

    요청 body: {name, room_code}
    방 이름과 참가 코드가 모두 일치해야 참가 허용.
    """
    name = payload.name.strip()
    room_code = payload.room_code.strip()
    if not name or not room_code:
        return {"ok": False, "error": "name_and_code_required"}
    room = database.find_room(name, room_code)
    if room is None:
        return {"ok": False, "error": "room_not_found"}
    return {"ok": True, **room}


@app.get("/rooms")
async def list_rooms() -> dict:
    """등록된 단체방 목록 조회"""
    return {"ok": True, "rooms": database.list_rooms()}


@app.get("/health")
async def health() -> dict:
    """헬스체크 엔드포인트

    반환값: 서버 상태를 담은 dict (ok, 현재시간, 방 개수)
    """
    return {
        "ok": True,
        "time": datetime.now().isoformat(timespec="seconds"),
        "room_count": len(ROOM_MEMBERS),
    }


@sio.event
async def connect(sid, environ):
    """클라이언트 연결 핸들러

    매개변수:
    - sid: Socket.IO가 부여한 클라이언트 세션 ID
    - environ: ASGI 환경 정보 (사용 안함)
    """
    print(f"[connect] sid={sid}")


@sio.event
async def disconnect(sid):
    """클라이언트 연결 해제 처리

    SID_INFO와 ROOM_MEMBERS에서 해당 sid를 제거하고 동일 룸 참가자에게
    `member_left` 이벤트를 브로드캐스트합니다.
    """
    info = SID_INFO.pop(sid, None)
    if info:
        room_code = info["room_code"]
        nickname = info["nickname"]
        members = ROOM_MEMBERS.get(room_code, {})
        members.pop(sid, None)
        if not members:
            ROOM_MEMBERS.pop(room_code, None)

        await sio.emit(
            "member_left",
            {
                "nickname": nickname,
                "room_code": room_code,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
            },
            room=room_code,
        )
    print(f"[disconnect] sid={sid}")


@sio.event
async def join_room(sid, data):
    """클라이언트의 룸 참가 요청 처리

    동작 요약:
    - 룸 수용 가능 여부 확인(ROOM_LIMIT)
    - 기존 룸에서 이동한 경우 이전 룸에서 제거
    - SID_INFO와 ROOM_MEMBERS를 갱신하고 다른 참가자에게
      `member_joined`와 `member_list` 이벤트를 전송

    매개변수:
    - sid: 클라이언트 세션 ID
    - data: 클라이언트가 보낸 payload (room_code, nickname 등)
    """
    room_code = data.get("room_code", "TEST_ROOM")
    nickname = data.get("nickname", "unknown")

    members = ROOM_MEMBERS.setdefault(room_code, {})
    if len(members) >= ROOM_LIMIT and sid not in members:
        await sio.emit(
            "join_failed",
            {
                "reason": "room_full",
                "room_code": room_code,
                "limit": ROOM_LIMIT,
            },
            to=sid,
        )
        print(
            f"[join_room] rejected sid={sid} nickname={nickname} "
            f"room={room_code} reason=room_full"
        )
        return

    old_info = SID_INFO.get(sid)
    if old_info and old_info["room_code"] != room_code:
        old_room = old_info["room_code"]
        old_members = ROOM_MEMBERS.get(old_room, {})
        old_members.pop(sid, None)
        if not old_members:
            ROOM_MEMBERS.pop(old_room, None)

    await sio.enter_room(sid, room_code)
    SID_INFO[sid] = {
        "room_code": room_code,
        "nickname": nickname,
    }
    members[sid] = nickname

    await sio.emit(
        "member_joined",
        {
            "nickname": nickname,
            "room_code": room_code,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        },
        room=room_code,
    )

    await sio.emit(
        "member_list",
        {
            "room_code": room_code,
            "members": list(members.values()),
            "count": len(members),
            "limit": ROOM_LIMIT,
        },
        room=room_code,
    )

    print(
        f"[join_room] sid={sid} nickname={nickname} "
        f"room={room_code} count={len(members)}/{ROOM_LIMIT}"
    )


@sio.event
async def status_update(sid, data):
    """클라이언트 상태 업데이트 수신

    클라이언트가 전송한 상태(state 등)를 받아서 같은 룸의 참가자들에게
    `member_status` 이벤트로 브로드캐스트합니다.
    """
    info = SID_INFO.get(sid, {})
    room_code = info.get("room_code", data.get("room_code", "TEST_ROOM"))
    payload = {
        "nickname": info.get("nickname", data.get("nickname", "unknown")),
        "state": data.get("state", "focused"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }

    await sio.emit("member_status", payload, room=room_code)
    print(f"[status_update] sid={sid} room={room_code} payload={payload}")


@sio.event
async def video_frame(sid, data):
    """비디오 프레임 수신 처리

    - 클라이언트가 룸에 참가하지 않은 경우 거부 응답 전송
    - 페이로드 크기(문자열 길이)가 너무 큰 경우 거부
    - 유효하면 `room_video` 이벤트로 같은 룸의 다른 참가자들에게 전송
    """
    info = SID_INFO.get(sid)
    if not info:
        await sio.emit(
            "video_rejected",
            {"reason": "not_joined"},
            to=sid,
        )
        return

    jpeg_base64 = data.get("jpeg_base64", "")
    if not jpeg_base64:
        return

    # Limit payload size to avoid runaway memory usage in PoC phase.
    if len(jpeg_base64) > 500_000:
        await sio.emit(
            "video_rejected",
            {"reason": "frame_too_large", "max_size": 500_000},
            to=sid,
        )
        return

    payload = {
        "nickname": info["nickname"],
        "jpeg_base64": jpeg_base64,
        "ts": data.get("ts", datetime.now().isoformat(timespec="seconds")),
        "is_main": bool(data.get("is_main", False)),
    }

    await sio.emit("room_video", payload, room=info["room_code"], skip_sid=sid)


@sio.event
async def audio_toggle(sid, data):
    """오디오 토글 요청 처리

    클라이언트가 오디오를 켜거나 끌 때 같은 룸의 참가자들에게
    `audio_changed` 이벤트를 전송합니다.
    """
    info = SID_INFO.get(sid)
    if not info:
        return

    payload = {
        "nickname": info["nickname"],
        "audio_on": bool(data.get("audio_on", True)),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    await sio.emit("audio_changed", payload, room=info["room_code"])
    print(
        f"[audio_toggle] sid={sid} room={info['room_code']} "
        f"payload={payload}"
    )


socket_app = socketio.ASGIApp(sio, other_asgi_app=app)
