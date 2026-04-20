"""개인/그룹 공통 성장 정책 Mixin."""

from services.character_growth import get_stage_name_from_growth, get_stage_progress
from services.character_store import find_character_index, load_characters, save_characters
from services.study_time import save_study_time


class StudyGrowthMixin:

    def _resolve_character(self, char_ref):
        chars = load_characters(sort_by_last_accessed=False)
        char_idx = find_character_index(chars, char_ref)
        if char_idx < 0:
            return None, -1, None
        return chars, char_idx, chars[char_idx]

    def _update_growth_widgets(self, progress_widget, label_widget, growth):
        growth_percent, growth_ratio = get_stage_progress(growth)
        if progress_widget is not None:
            progress_widget.set(growth_ratio)
        if label_widget is not None:
            label_widget.configure(text=f"{growth_percent}%")
        return growth_percent, growth_ratio

    def _save_study_minutes(self, mode, elapsed_seconds):
        # 분 단위 저장(최소 1분)
        study_minutes = max(1, int(elapsed_seconds) // 60)
        user_name = getattr(self.args, "name", "user")
        save_study_time(user_name, mode, study_minutes)

    def _is_focus_blocking_signal(self):
        with self._camera_signal_lock:
            current_signal = self._camera_current_signal
        return current_signal in ("LOW_FOCUS", "DROWSINESS")

    def _mark_blocked_growth_slot(self, mode, elapsed_seconds):
        blocked_attr = "_study_blocked_slots" if mode == "personal" else "_group_study_blocked_slots"
        blocked_slots = getattr(self, blocked_attr, None)
        if blocked_slots is None:
            blocked_slots = set()
            setattr(self, blocked_attr, blocked_slots)

        # slot 1 => 0~29초, slot 2 => 30~59초, ...
        blocked_slots.add((elapsed_seconds // 30) + 1)

    def _consume_growth_points(self, mode, elapsed_seconds):
        if mode == "personal":
            acc_attr = "_study_accumulated_points"
            blocked_attr = "_study_blocked_slots"
        else:
            acc_attr = "_group_study_accumulated_points"
            blocked_attr = "_group_study_blocked_slots"

        current_slot = elapsed_seconds // 30
        processed_slot = getattr(self, acc_attr, 0)
        if current_slot <= processed_slot:
            return 0

        blocked_slots = getattr(self, blocked_attr, set())
        granted = 0
        for slot in range(processed_slot + 1, current_slot + 1):
            if slot not in blocked_slots:
                granted += 1

        setattr(self, acc_attr, current_slot)
        return granted

    def _apply_growth_points(self, char_ref, add_points, on_stage_changed=None, on_progress_updated=None):
        """공통 성장 반영 로직.

        - 캐릭터 조회(id/인덱스)
        - growth 저장
        - 단계 변경 여부 판단
        - 콜백으로 UI 반영 위임
        """
        if add_points <= 0:
            return False

        chars, char_idx, char = self._resolve_character(char_ref)
        if char is None:
            return False

        growth = int(char.get("growth", 0))
        old_stage = get_stage_name_from_growth(growth)
        growth += add_points
        new_stage = get_stage_name_from_growth(growth)

        char["growth"] = growth
        chars[char_idx] = char
        save_characters(chars)

        if new_stage != old_stage:
            if callable(on_stage_changed):
                on_stage_changed(growth)
        else:
            if callable(on_progress_updated):
                on_progress_updated(growth)

        return True
