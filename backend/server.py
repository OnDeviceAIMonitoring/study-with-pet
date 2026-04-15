from datetime import datetime
from typing import Dict

import socketio
from fastapi import FastAPI


app = FastAPI(title="Digital Pet Comm Test Server")
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
ROOM_LIMIT = 6

# sid -> {"room_code": str, "nickname": str}
SID_INFO: Dict[str, Dict[str, str]] = {}

# room_code -> {sid: nickname}
ROOM_MEMBERS: Dict[str, Dict[str, str]] = {}


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "time": datetime.now().isoformat(timespec="seconds"),
        "room_count": len(ROOM_MEMBERS),
    }


@sio.event
async def connect(sid, environ):
    print(f"[connect] sid={sid}")


@sio.event
async def disconnect(sid):
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
