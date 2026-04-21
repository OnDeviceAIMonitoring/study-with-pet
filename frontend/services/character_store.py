"""Character persistence helpers.

This module keeps character metadata consistent:
- id: unique identifier
- created_at: creation timestamp (UTC ISO-8601)
- last_accessed_at: latest access timestamp (UTC ISO-8601)
"""

import json
import uuid
from datetime import datetime, timezone


_CHARACTERS_FILE = "frontend/data/characters.json"


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(ts):
    if not isinstance(ts, str) or not ts:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        # Accept both ...Z and explicit offsets.
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _normalize_growth(raw):
    try:
        return max(0, int(raw))
    except Exception:
        return 0


def _normalize_character(raw, now_iso):
    char = dict(raw) if isinstance(raw, dict) else {}
    changed = False

    if not isinstance(char.get("name"), str) or not char.get("name"):
        char["name"] = "maltese"
        changed = True

    # breed가 없으면 name에서 복사 (하위 호환)
    if not isinstance(char.get("breed"), str) or not char.get("breed"):
        char["breed"] = char["name"]
        changed = True

    growth = _normalize_growth(char.get("growth", 0))
    if char.get("growth") != growth:
        char["growth"] = growth
        changed = True

    cid = char.get("id")
    if not isinstance(cid, str) or not cid:
        char["id"] = uuid.uuid4().hex
        changed = True

    created_at = char.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        char["created_at"] = now_iso
        changed = True

    last_accessed_at = char.get("last_accessed_at")
    if not isinstance(last_accessed_at, str) or not last_accessed_at:
        char["last_accessed_at"] = char["created_at"]
        changed = True

    return char, changed


def _write_characters(chars):
    with open(_CHARACTERS_FILE, "w", encoding="utf-8") as f:
        json.dump(chars, f, ensure_ascii=False, indent=2)


def load_characters(sort_by_last_accessed=False):
    try:
        with open(_CHARACTERS_FILE, "r", encoding="utf-8") as f:
            chars = json.load(f)
    except Exception:
        chars = []

    if not isinstance(chars, list):
        chars = []

    now_iso = _now_iso()
    normalized = []
    changed = False
    for raw in chars:
        char, is_changed = _normalize_character(raw, now_iso)
        normalized.append(char)
        changed = changed or is_changed

    if sort_by_last_accessed:
        normalized = sorted(
            normalized,
            key=lambda c: (_parse_iso(c.get("last_accessed_at")), _parse_iso(c.get("created_at"))),
            reverse=True,
        )

    if changed:
        _write_characters(normalized)

    return normalized


def save_characters(chars):
    now_iso = _now_iso()
    normalized = []
    for raw in chars if isinstance(chars, list) else []:
        char, _ = _normalize_character(raw, now_iso)
        normalized.append(char)
    _write_characters(normalized)


def find_character_index(chars, char_ref):
    if not isinstance(chars, list) or not chars:
        return -1

    if isinstance(char_ref, int):
        return char_ref if 0 <= char_ref < len(chars) else -1

    if isinstance(char_ref, str) and char_ref:
        for i, c in enumerate(chars):
            if c.get("id") == char_ref:
                return i
        # Legacy fallback: name-based lookup.
        for i, c in enumerate(chars):
            if c.get("name") == char_ref:
                return i

    return -1


def touch_character(chars, char_ref):
    idx = find_character_index(chars, char_ref)
    if idx < 0:
        return False
    chars[idx]["last_accessed_at"] = _now_iso()
    return True


def new_character(name, growth=0, breed=None):
    now_iso = _now_iso()
    return {
        "id": uuid.uuid4().hex,
        "name": name,
        "breed": breed or name,
        "growth": _normalize_growth(growth),
        "created_at": now_iso,
        "last_accessed_at": now_iso,
    }
