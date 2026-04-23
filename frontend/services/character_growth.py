"""Character growth helpers.

Single source of truth:
- growth is cumulative points
- stage is derived from growth (baby/adult/crown)
"""

STAGES = ("baby", "adult", "crown")
STAGE_UNIT = 3


def _to_growth(raw_growth):
    try:
        return max(0, int(raw_growth))
    except Exception:
        return 0


def get_stage_index_from_growth(raw_growth):
    growth = _to_growth(raw_growth)
    return min(growth // STAGE_UNIT, len(STAGES) - 1)


def get_stage_name_from_growth(raw_growth):
    return STAGES[get_stage_index_from_growth(raw_growth)]


def get_stage_progress(raw_growth):
    """Return (percent, ratio) for current stage progress.

    - baby/adult: progress inside each STAGE_UNIT-point stage
    - crown: fixed as complete (100%, 1.0)
    """
    growth = _to_growth(raw_growth)
    stage_idx = get_stage_index_from_growth(growth)

    if stage_idx >= len(STAGES) - 1:
        return 100, 1.0

    growth_in_stage = growth - (stage_idx * STAGE_UNIT)
    percent = min(100, int(growth_in_stage * 100 / STAGE_UNIT))
    ratio = growth_in_stage / STAGE_UNIT
    return percent, ratio
