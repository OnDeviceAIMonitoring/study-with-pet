"""개인/그룹 공통 성장 정책 Mixin."""

from services.camera_signals import DEFAULT_ANIM, SIGNAL_PRIORITY, SIGNAL_TO_ANIM
from services.character_animation import load_character_animation_sets
from services.character_growth import get_stage_name_from_growth, get_stage_progress
from services.character_store import find_character_index, load_characters, save_characters
from services.study_time import save_study_time


class StudyGrowthMixin:

    def _resolve_character(self, char_ref):
        chars = load_characters(self.args.name, sort_by_last_accessed=False)
        char_idx = find_character_index(chars, char_ref)
        if char_idx < 0:
            return None, -1, None
        return chars, char_idx, chars[char_idx]

    def _load_study_character(self, char_ref, target_w=120, tear_fallback=False):
        """캐릭터 해석 + 애니메이션 세트 로드 공통 로직.

        Returns:
            (chars, char_idx, char_name, char_id, char_growth, anim_sets)
            캐릭터가 없으면 (None, -1, None, None, 0, {}).
        """
        chars, char_idx, char = self._resolve_character(char_ref)
        if char is None:
            return None, -1, None, None, 0, {}

        char_name = char.get("name")
        char_id = char.get("id")
        char_growth = int(char.get("growth", 0))
        breed = char.get("breed") or char_name

        if not breed or not isinstance(breed, str):
            return chars, -1, None, None, 0, {}

        ctype = get_stage_name_from_growth(char_growth)
        anim_sets = load_character_animation_sets(
            breed, ctype, target_w=target_w,
            anim_names=("happy", "tail", "tear"),
            tear_fallback_to_sad=tear_fallback,
        )
        return chars, char_idx, char_name, char_id, char_growth, anim_sets

    def _update_growth_widgets(self, progress_widget, label_widget, growth):
        growth_percent, growth_ratio = get_stage_progress(growth)
        stage_name = get_stage_name_from_growth(growth)
        stage_text = {'baby': '1단계', 'adult': '2단계', 'crown': '3단계'}.get(stage_name, stage_name)
        # 소수점 둘째자리까지 계산
        detailed_percent = growth_ratio * 100
        if progress_widget is not None:
            progress_widget.set(growth_ratio)
        if label_widget is not None:
            label_widget.configure(text=f"{stage_text} / 성장률: {detailed_percent:.2f}%")
        return growth_percent, growth_ratio

    def _save_study_minutes(self, mode, elapsed_seconds):
        # 분 단위 저장(최소 1분)
        study_minutes = max(1, int(elapsed_seconds) // 60)
        user_name = getattr(self.args, "name", "user")
        save_study_time(user_name, mode, study_minutes)

    # ── 시그널 → 애니메이션 ──────────────────────────────────

    def _resolve_target_anim(self):
        """현재 시그널에서 타겟 애니메이션 이름 결정."""
        sig = getattr(self, "_camera_current_signal", None)
        if sig:
            for s in SIGNAL_PRIORITY:
                if s == sig:
                    return SIGNAL_TO_ANIM.get(s, DEFAULT_ANIM)
        return DEFAULT_ANIM

    def _tick_signal_anim(self, anim_sets, current_anim, frames, frame_idx,
                          label, after_ms, tick_fn):
        """시그널 기반 애니메이션 프레임 전환 공통 로직.

        Returns:
            (current_anim, frames, frame_idx)
        """
        target_anim = self._resolve_target_anim()

        if target_anim != current_anim:
            new_frames = anim_sets.get(target_anim, [])
            if new_frames:
                current_anim = target_anim
                frames = new_frames
                frame_idx = 0

        if not frames:
            self.root.after(after_ms, tick_fn)
            return current_anim, frames, frame_idx

        frame_idx = (frame_idx + 1) % len(frames)
        try:
            label.configure(image=frames[frame_idx])
        except Exception:
            pass
        self.root.after(after_ms, tick_fn)
        return current_anim, frames, frame_idx

    # ── 집중 차단 / 성장 포인트 ──────────────────────────────

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
        save_characters(self.args.name, chars)

        if new_stage != old_stage:
            if callable(on_stage_changed):
                on_stage_changed(growth)
        else:
            if callable(on_progress_updated):
                on_progress_updated(growth)

        return True
