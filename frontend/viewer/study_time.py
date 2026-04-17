import os
import json
from datetime import date

STUDY_TIME_FILE = "frontend/user/study_time.json"

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
