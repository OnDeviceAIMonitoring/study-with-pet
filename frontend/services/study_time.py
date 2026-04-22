import os
import json
from datetime import date, timedelta

STUDY_TIME_FILE = "frontend/data/study_time.json"


# ── 목표 시간 (daily_goal) ──────────────────────────────────

DAILY_GOAL_FILE = "frontend/data/daily_goal.json"


def load_daily_goal(key: str):
    """오늘 설정된 목표 시간(분)을 반환. 미설정이면 None.

    key는 개인 공부의 경우 유저명, 단체 공부의 경우 방id(room_id).
    """
    today = date.today().isoformat()
    if not os.path.exists(DAILY_GOAL_FILE):
        return None
    try:
        with open(DAILY_GOAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(key, {}).get(today)
    except Exception:
        return None


def save_daily_goal(key: str, minutes: int):
    """오늘의 목표 시간(분)을 저장.

    key는 개인 공부의 경우 유저명, 단체 공부의 경우 방id(room_id).
    """
    today = date.today().isoformat()
    data = {}
    if os.path.exists(DAILY_GOAL_FILE):
        try:
            with open(DAILY_GOAL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    if key not in data:
        data[key] = {}
    data[key][today] = minutes
    with open(DAILY_GOAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_daily_goal(key: str):
    """특정 키의 모든 날짜에 대한 목표 시간을 삭제.

    방 삭제/재생성 시 호출하여 목표 설정 화면이 다시 등장하도록 합니다.
    """
    if not os.path.exists(DAILY_GOAL_FILE):
        return
    try:
        with open(DAILY_GOAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if key in data:
            del data[key]
            with open(DAILY_GOAL_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_consecutive_goal_days(key: str) -> int:
    """목표를 연속으로 설정한 일수를 반환 (오늘 포함).

    key는 개인 공부의 경우 유저명, 단체 공부의 경우 방id(room_id).
    """
    if not os.path.exists(DAILY_GOAL_FILE):
        return 0
    try:
        with open(DAILY_GOAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0
    key_data = data.get(key, {})
    if not key_data:
        return 0

    today = date.today()
    streak = 0
    d = today
    while d.isoformat() in key_data:
        streak += 1
        d -= timedelta(days=1)
    return streak


# ── 공부 시간 추적 ──────────────────────────────────────────

def load_study_time(user, mode):
    today = date.today().isoformat()
    if not os.path.exists(STUDY_TIME_FILE):
        return None
    try:
        with open(STUDY_TIME_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(user, {}).get(mode, {}).get(today)
    except Exception:
        return None

def save_study_time(user, mode, minutes):
    today = date.today().isoformat()
    data = {}
    if os.path.exists(STUDY_TIME_FILE):
        try:
            with open(STUDY_TIME_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    if user not in data:
        data[user] = {}
    if mode not in data[user]:
        data[user][mode] = {}
    data[user][mode][today] = minutes
    with open(STUDY_TIME_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
