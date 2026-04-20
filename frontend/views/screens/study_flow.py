"""개인/그룹 공통 화면 흐름(Flow) Mixin."""

from config import GROUP_LIST, GROUP_ROOM, MAIN, PERSONAL_CAMERA, SELECT_CHAR
from services import socketio_client
from services.character_store import load_characters, save_characters, touch_character


class StudyFlowMixin:

    # ── 그룹 플로우 ─────────────────────────────────────────

    def _start_group_room_flow(self, room_code: str, room_name: str):
        """캐릭터 선택 화면을 거쳐 단체방에 입장합니다."""
        self.nav_state.pending_group_room = (room_code, room_name)
        self._pending_group_room = (room_code, room_name)  # 호환성
        self._screen_char_select_page = 0
        self._refresh_char_select()
        self.show_screen(SELECT_CHAR)

    def _enter_group_room(self, room_code: str, room_name: str):
        """단체방 공부 세션을 시작합니다."""
        self._socket_generation += 1
        self.args.room = room_code
        with self.lock:
            self.frame_map.clear()

        self.group_screen_title.configure(text=f"단체 공부  ·  {room_name}")
        self._start_group_study_session()
        socketio_client.start_background(self, self._socket_generation)

        self.show_screen(GROUP_ROOM)
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
