import os
import json
from datetime import date, timedelta

STUDY_TIME_FILE = "frontend/data/study_time.json"


# ── 목표 시간 (daily_goal) ──────────────────────────────────

DAILY_GOAL_FILE = "frontend/data/daily_goal.json"


def load_daily_goal(user: str):
    """오늘 설정된 목표 시간(분)을 반환. 미설정이면 None."""
    today = date.today().isoformat()
    if not os.path.exists(DAILY_GOAL_FILE):
        return None
    try:
        with open(DAILY_GOAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(user, {}).get(today)
    except Exception:
        return None


def save_daily_goal(user: str, minutes: int):
    """오늘의 목표 시간(분)을 저장."""
    today = date.today().isoformat()
    data = {}
    if os.path.exists(DAILY_GOAL_FILE):
        try:
            with open(DAILY_GOAL_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    if user not in data:
        data[user] = {}
    data[user][today] = minutes
    with open(DAILY_GOAL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_consecutive_goal_days(user: str) -> int:
    """목표를 연속으로 설정한 일수를 반환 (오늘 포함)."""
    if not os.path.exists(DAILY_GOAL_FILE):
        return 0
    try:
        with open(DAILY_GOAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0
    user_data = data.get(user, {})
    if not user_data:
        return 0

    today = date.today()
    streak = 0
    d = today
    while d.isoformat() in user_data:
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
