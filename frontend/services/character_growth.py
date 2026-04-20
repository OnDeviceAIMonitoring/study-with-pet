"""Character growth helpers.

Single source of truth:
- growth is cumulative points
- stage is derived from growth (baby/adult/crown)
"""

STAGES = ("baby", "adult", "crown")
_STAGE_UNIT = 120


def _to_growth(raw_growth):
    try:
        return max(0, int(raw_growth))
    except Exception:
        return 0


def get_stage_index_from_growth(raw_growth):
    growth = _to_growth(raw_growth)
    return min(growth // _STAGE_UNIT, len(STAGES) - 1)


def get_stage_name_from_growth(raw_growth):
    return STAGES[get_stage_index_from_growth(raw_growth)]


def get_stage_progress(raw_growth):
    """Return (percent, ratio) for current stage progress.

    - baby/adult: progress inside each 120-point stage
    - crown: fixed as complete (100%, 1.0)
    """
    growth = _to_growth(raw_growth)
    stage_idx = get_stage_index_from_growth(growth)

    if stage_idx >= len(STAGES) - 1:
        return 100, 1.0

    growth_in_stage = growth - (stage_idx * _STAGE_UNIT)
    percent = min(100, int(growth_in_stage * 100 / _STAGE_UNIT))
    ratio = growth_in_stage / _STAGE_UNIT
    return percent, ratio
