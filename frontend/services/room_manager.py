"""
사용자가 속한 단체방 목록 관리 모듈

계정(username)별로 별도 JSON 파일에 저장한다.
  frontend/data/rooms_{username}.json
각 항목: {"id": int, "name": str, "room_code": str}
"""

import json
import os
import re
from typing import List, Dict

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def _sanitize(username: str) -> str:
    """파일명에 안전한 문자열로 변환"""
    return re.sub(r'[^\w\-.]', '_', username or "default")


def _rooms_path(username: str) -> str:
    """계정별 rooms JSON 경로 반환"""
    return os.path.join(_DATA_DIR, f"rooms_{_sanitize(username)}.json")


def load_rooms(username: str) -> List[Dict]:
    """계정별 저장된 단체방 목록을 반환"""
    path = _rooms_path(username)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_rooms(username: str, rooms: List[Dict]) -> None:
    """계정별 단체방 목록을 파일에 저장"""
    path = _rooms_path(username)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rooms, f, ensure_ascii=False, indent=2)


def add_room(username: str, name: str, room_code: str, room_id: int) -> None:
    """단체방을 계정 목록에 추가. 동일 id면 갱신"""
    rooms = load_rooms(username)
    for r in rooms:
        if r.get("id") == room_id:
            r["name"] = name
            r["room_code"] = room_code
            save_rooms(username, rooms)
            return
    rooms.append({"id": room_id, "name": name, "room_code": room_code})
    save_rooms(username, rooms)


def remove_room(username: str, room_id: int) -> None:
    """단체방을 계정 목록에서 제거"""
    rooms = [r for r in load_rooms(username) if r.get("id") != room_id]
    save_rooms(username, rooms)
