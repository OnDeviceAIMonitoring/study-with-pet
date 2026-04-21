"""
사용자가 속한 단체방 목록 관리 모듈

단체방 정보는 rooms.json에 저장됩니다.
각 항목: {"id": int, "name": str, "room_code": str}
"""

import json
import os
from typing import List, Dict

_ROOMS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "rooms.json")


def load_rooms() -> List[Dict]:
    """저장된 단체방 목록을 반환합니다."""
    if not os.path.exists(_ROOMS_FILE):
        return []
    try:
        with open(_ROOMS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_rooms(rooms: List[Dict]) -> None:
    """단체방 목록을 파일에 저장합니다."""
    with open(_ROOMS_FILE, "w", encoding="utf-8") as f:
        json.dump(rooms, f, ensure_ascii=False, indent=2)


def add_room(name: str, room_code: str, room_id: int) -> None:
    """단체방을 목록에 추가합니다. 동일 id가 있으면 해당 항목을 갱신합니다."""
    rooms = load_rooms()
    for r in rooms:
        if r.get("id") == room_id:
            r["name"] = name
            r["room_code"] = room_code
            save_rooms(rooms)
            return
    room = {"id": room_id, "name": name, "room_code": room_code}
    rooms.append(room)
    save_rooms(rooms)


def remove_room(room_id: int) -> None:
    """단체방을 목록에서 제거합니다."""
    rooms = [r for r in load_rooms() if r.get("id") != room_id]
    save_rooms(rooms)
