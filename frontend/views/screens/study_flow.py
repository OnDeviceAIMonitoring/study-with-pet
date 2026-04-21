"""개인/그룹 공통 화면 흐름(Flow) Mixin."""

import json
import threading
import urllib.request

from config import DAILY_GOAL, GROUP_LIST, GROUP_ROOM, MAIN, PERSONAL_CAMERA, SELECT_CHAR
from services import socketio_client
from services.character_store import load_characters, save_characters, touch_character
from services.study_time import load_daily_goal


class StudyFlowMixin:

    # ── 그룹 플로우 ─────────────────────────────────────────

    def _start_group_room_flow(self, room_code: str, room_name: str):
        """캐릭터 선택 화면을 거쳐 단체방에 입장합니다."""
        self.nav_state.pending_group_room = (room_code, room_name)
        self._pending_group_room = (room_code, room_name)  # 호환성

        # 단체방 기준으로 오늘 목표 미설정 시 목표 입력 화면을 먼저 표시
        if load_daily_goal(room_code) is None:
            self._daily_goal_key = room_code  # 저장 키: 방코드
            self._daily_goal_next_action = self._continue_group_room_flow
            self.show_screen(DAILY_GOAL)
            return
        self._continue_group_room_flow()

    def _continue_group_room_flow(self):
        """목표 설정 완료 후 캐릭터 선택으로 진행 + 서버에 목표 저장"""
        # 단체방 목표 시간을 서버에도 저장
        pending = self.nav_state.pending_group_room
        if pending:
            room_code = pending[0]
            goal = load_daily_goal(room_code)
            if goal is not None:
                self._save_group_goal_to_server(room_code, goal)
        self._screen_char_select_page = 0
        self._refresh_char_select()
        self.show_screen(SELECT_CHAR)

    def _save_group_goal_to_server(self, room_code: str, goal_minutes: int):
        """서버에 단체방 목표 시간 저장 (비동기)."""
        def _worker():
            try:
                url = f"{self.args.server}/rooms/goal"
                data = json.dumps({"room_code": room_code, "goal_minutes": goal_minutes}).encode("utf-8")
                req = urllib.request.Request(
                    url, data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=5)
            except Exception as exc:
                print(f"[study_flow] goal save error: {exc}")
        threading.Thread(target=_worker, daemon=True).start()

    def _enter_group_room(self, room_code: str, room_name: str):
        """단체방 공부 세션을 시작합니다."""
        self._socket_generation += 1
        self.args.room = room_code
        with self.lock:
            self.frame_map.clear()

        self.show_screen(GROUP_ROOM)
        self.group_screen_title.configure(text=f"단체 공부  ·  {room_name}")
        self._group_room_code_label.configure(text=f"#코드 {room_code}")
        self._start_group_study_session()

        # 현재 방의 목표/진행 값으로 초기화 (이전 방 데이터 잔존 방지)
        goal_min = load_daily_goal(room_code) or 0
        self._group_goal_minutes = goal_min
        self._group_server_study_seconds = 0
        self._group_server_goal_minutes = goal_min
        self._group_server_all_studying = True
        # 라벨도 즉시 갱신
        g_total = goal_min * 60
        g_h, g_rem = divmod(g_total, 3600)
        g_m, g_s = divmod(g_rem, 60)
        if hasattr(self, '_group_study_time_label'):
            self._group_study_time_label.configure(
                text=f"공부시간: 00:00:00 / {g_h:02d}:{g_m:02d}:{g_s:02d}")

        socketio_client.start_background(self, self._socket_generation)
        self.start_camera()

    def _on_group_back(self):
        self._socket_generation += 1
        self._group_char_anim_running = False
        self._stop_group_study_session(save=True)
        self.stop_camera()
        with self.lock:
            self.frame_map.clear()
        self.show_screen(GROUP_LIST)

    # ── 개인/선택 플로우 ────────────────────────────────────

    def _enter_selected_character(self, selected_id):
        """캐릭터 선택 이후 개인/그룹 진입 분기 처리."""
        self.nav_state.selected_char = selected_id
        self._selected_char = selected_id  # 호환성
        chars = load_characters(sort_by_last_accessed=False)
        if touch_character(chars, selected_id):
            save_characters(chars)

        self.start_camera()

        pending = self.nav_state.pending_group_room
        if pending:
            self.nav_state.pending_group_room = None
            self._pending_group_room = None  # 호환성
            self._enter_group_room(*pending)
        else:
            self.show_screen(PERSONAL_CAMERA)

    def _on_char_select_back(self):
        if self.nav_state.pending_group_room is not None:
            self.nav_state.pending_group_room = None
            self._pending_group_room = None  # 호환성
            self.show_screen(GROUP_LIST)
        else:
            self.show_screen(MAIN)
