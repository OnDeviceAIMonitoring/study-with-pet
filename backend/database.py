"""
SQLite 데이터베이스 초기화 및 단체방 CRUD 모듈

테이블:
- rooms: id(PK), name, room_code, created_at
  room_code는 유니크하지 않으며, id가 고유 식별자입니다.
"""

import sqlite3
import os
from contextlib import contextmanager

_DB_PATH = os.path.join(os.path.dirname(__file__), "pet.db")


def init_db() -> None:
    """DB 파일과 테이블을 초기화합니다. 서버 시작 시 한 번 호출합니다."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL,
                room_code   TEXT    NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """
        )


@contextmanager
def _connect():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ──────────────────────────────────────────────
# 단체방 CRUD
# ──────────────────────────────────────────────

def create_room(name: str, room_code: str) -> dict:
    """방을 생성하고 생성된 행을 반환합니다."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO rooms (name, room_code) VALUES (?, ?)",
            (name, room_code),
        )
        row_id = cur.lastrowid
    return {"id": row_id, "name": name, "room_code": room_code}


def exists_room_name(name: str) -> bool:
    """동일한 이름의 방이 이미 존재하는지 반환합니다."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM rooms WHERE name = ? LIMIT 1",
            (name,),
        ).fetchone()
    return row is not None


def find_room(name: str, room_code: str) -> dict | None:
    """name과 room_code가 일치하는 방을 반환합니다. 없으면 None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, room_code FROM rooms WHERE name = ? AND room_code = ?",
            (name, room_code),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_room_by_id(room_id: int) -> dict | None:
    """id로 방을 조회합니다."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, name, room_code FROM rooms WHERE id = ?",
            (room_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def list_rooms() -> list[dict]:
    """모든 방 목록을 반환합니다."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, name, room_code, created_at FROM rooms ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]
