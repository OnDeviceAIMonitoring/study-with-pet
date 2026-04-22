"""
SQLite 데이터베이스 초기화 및 단체방 CRUD 모듈

테이블:
- rooms: id(PK), name(UNIQUE), room_code, created_at, goal_minutes, study_seconds
    room_code는 유니크하지 않으며, id가 고유 식별자입니다.
    goal_minutes: 오늘의 목표 시간(분)
    study_seconds: 오늘까지 누적 공부 시간(초)
"""

import sqlite3
import os
from contextlib import contextmanager
from datetime import date

_DB_PATH = os.path.join(os.path.dirname(__file__), "pet.db")


def init_db() -> None:
    """DB 파일과 테이블을 초기화합니다. 서버 시작 시 한 번 호출합니다."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                room_code   TEXT    NOT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        # 기존 DB(이미 생성된 rooms 테이블)에도 이름 유니크 제약을 적용하기 위해 인덱스를 보장합니다.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_rooms_name_unique ON rooms(name)"
        )
        # 단체방 공부 시간 추적 테이블
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS room_study (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                room_code       TEXT    NOT NULL,
                study_date      TEXT    NOT NULL,
                goal_minutes    INTEGER NOT NULL DEFAULT 0,
                study_seconds   INTEGER NOT NULL DEFAULT 0,
                UNIQUE(room_code, study_date)
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
        # 동일 room_code로 오늘 날짜의 이전 공부 기록이 있으면 초기화
        study_date = date.today().isoformat()
        conn.execute(
            "UPDATE room_study SET study_seconds = 0 WHERE room_code = ? AND study_date = ?",
            (room_code, study_date),
        )
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


# ──────────────────────────────────────────────
# 단체방 공부 시간 추적
# ──────────────────────────────────────────────

def get_room_study(room_code: str, study_date: str = None) -> dict:
    """방의 오늘(또는 지정일) 공부 현황을 반환합니다."""
    if study_date is None:
        study_date = date.today().isoformat()
    with _connect() as conn:
        row = conn.execute(
            "SELECT goal_minutes, study_seconds FROM room_study WHERE room_code = ? AND study_date = ?",
            (room_code, study_date),
        ).fetchone()
    if row is None:
        return {"goal_minutes": 0, "study_seconds": 0}
    return dict(row)


def set_room_goal(room_code: str, goal_minutes: int, study_date: str = None) -> dict:
    """방의 오늘 목표 시간을 설정합니다.
    
    이미 목표가 설정된 경우(값 > 0) 덮어쓰지 않습니다.
    """
    if study_date is None:
        study_date = date.today().isoformat()
    with _connect() as conn:
        # 기존 목표가 이미 설정되어 있는지 확인
        row = conn.execute(
            "SELECT goal_minutes FROM room_study WHERE room_code = ? AND study_date = ?",
            (room_code, study_date),
        ).fetchone()
        if row and row["goal_minutes"] > 0:
            # 이미 목표가 설정되어 있으면 덮어쓰지 않음
            return {"room_code": room_code, "goal_minutes": row["goal_minutes"], "study_date": study_date}
        conn.execute(
            """
            INSERT INTO room_study (room_code, study_date, goal_minutes, study_seconds)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(room_code, study_date)
            DO UPDATE SET goal_minutes = excluded.goal_minutes
            """,
            (room_code, study_date, goal_minutes),
        )
    return {"room_code": room_code, "goal_minutes": goal_minutes, "study_date": study_date}


def update_room_study_seconds(room_code: str, seconds: int, study_date: str = None) -> dict:
    """방의 오늘 공부 시간(초)을 업데이트합니다."""
    if study_date is None:
        study_date = date.today().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO room_study (room_code, study_date, goal_minutes, study_seconds)
            VALUES (?, ?, 0, ?)
            ON CONFLICT(room_code, study_date)
            DO UPDATE SET study_seconds = excluded.study_seconds
            """,
            (room_code, study_date, seconds),
        )
    return get_room_study(room_code, study_date)
