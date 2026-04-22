"""단체방 관련 화면 UI Mixin."""

import customtkinter as ctk

from config import MAIN, GROUP_LIST, GROUP_CREATE, GROUP_JOIN
from services import room_manager


class GroupScreenMixin:

    def _on_group_study(self):
        # 단체방 목록 화면으로 이동 (목표 시간 체크는 방 선택 후 수행)
        self.show_screen(GROUP_LIST)

    # ──────────────────────────────────────────────
    # screen_group_list : 단체방 목록 (GROUP_LIST)
    # ──────────────────────────────────────────────

    def _build_screen_group_list(self):
        frame = self.screen_group_list

        # 상단바: 테두리/둥근 모서리/여백 없이 사각형, 배경색도 전체 배경과 동일하게
        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        ctk.CTkLabel(
            top,
            text="단체 공부",
            anchor="w",
            font=self._make_font(20),
            text_color=self.theme["text"],
        ).pack(side="left", padx=16)
        ctk.CTkButton(top, text="뒤로가기", width=80, height=36, command=lambda: self.show_screen(MAIN),
              font=self._make_font(14), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        self.group_list_scroll = ctk.CTkScrollableFrame(
            frame,
            label_text="내 단체방 목록",
            label_font=self._make_font(13),
            fg_color=self.theme["gray"],
            border_width=1,
            border_color=self.theme["gray_hover"],
        )
        self.group_list_scroll.pack(fill="both", expand=True, padx=20, pady=(8, 4))

        self.group_list_error_label = ctk.CTkLabel(
            frame,
            text="",
            font=self._make_font(12),
            **self._error_text_style(),
        )
        self.group_list_error_label.pack(fill="x", padx=20, pady=(0, 4))

        bottom = ctk.CTkFrame(frame, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(4, 20))
        bottom.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            bottom, text="참가하기", height=46,
            command=lambda: self.show_screen(GROUP_JOIN),
            font=self._make_font(15),
            **self._secondary_button_style(),
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            bottom, text="생성하기", height=46,
            command=lambda: self.show_screen(GROUP_CREATE),
            font=self._make_font(15),
            **self._primary_button_style(),
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _refresh_group_list(self):
        self.group_list_error_label.configure(text="")
        for widget in self.group_list_scroll.winfo_children():
            widget.destroy()

        rooms = room_manager.load_rooms()
        if not rooms:
            ctk.CTkLabel(
                self.group_list_scroll,
                text="참가한 단체방이 없습니다.\n아래 버튼으로 방에 참가하거나 새로 생성하세요.",
                font=self._make_font(13),
                **self._muted_text_style(),
                justify="center",
            ).pack(pady=48)
            return

        # 서버에서 공부 현황 조회 (비동기)
        self._room_study_cache = {}
        for room in rooms:
            self._add_room_item(room["id"], room["name"], room["room_code"])
        # 서버에서 각 방의 공부 시간 정보를 비동기로 가져와 표시
        self._fetch_room_study_info(rooms)

    def _fetch_room_study_info(self, rooms):
        """서버에서 각 방의 공부 현황을 비동기로 조회하여 라벨 업데이트."""
        import urllib.request
        import json
        import threading

        def _worker():
            for room in rooms:
                try:
                    url = f"{self.args.server}/rooms/{room['id']}/study"
                    req = urllib.request.Request(url, method="GET")
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        result = json.loads(resp.read().decode("utf-8"))
                    if result.get("ok", False):
                        self._room_study_cache[room["room_code"]] = {
                            "study_seconds": result.get("study_seconds", 0),
                            "goal_minutes": result.get("goal_minutes", 0),
                        }
                except Exception:
                    pass
            # UI 업데이트는 메인 스레드에서
            self.root.after(0, self._update_room_study_labels)

        threading.Thread(target=_worker, daemon=True).start()

    def _update_room_study_labels(self):
        """캐시된 공부 현황으로 방 목록 아이템의 시간 라벨을 업데이트."""
        for rc, data in self._room_study_cache.items():
            lbl = getattr(self, f"_room_study_lbl_{rc}", None)
            if lbl is not None:
                ss = data.get("study_seconds", 0)
                gm = data.get("goal_minutes", 0)
                s_h, s_rem = divmod(ss, 3600)
                s_m, s_s = divmod(s_rem, 60)
                g_total = gm * 60
                g_h, g_rem = divmod(g_total, 3600)
                g_m, g_s = divmod(g_rem, 60)
                lbl.configure(text=f"{s_h:02d}:{s_m:02d}:{s_s:02d} / {g_h:02d}:{g_m:02d}:{g_s:02d}")

    def _add_room_item(self, room_id: int, name: str, room_code: str):
        enter_fn = lambda rid=room_id, rc=room_code, n=name: self._on_group_list_room_click(rid, n, rc)
        delete_fn = lambda rid=room_id: self._remove_group_list_room(rid)

        item = ctk.CTkFrame(
            self.group_list_scroll, height=60, corner_radius=8,
            fg_color=self.theme["beige"],
            border_width=1,
            border_color=self.theme["sand"],
            cursor="hand2",
        )
        item.pack(fill="x", pady=4, padx=2)
        item.pack_propagate(False)
        item.bind("<Button-1>", lambda e, fn=enter_fn: fn())

        name_lbl = ctk.CTkLabel(
            item,
            text=name,
            font=self._make_font(14),
            anchor="w",
            cursor="hand2",
            text_color=self.theme["text"],
        )
        name_lbl.pack(side="left", padx=16)
        name_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())

        # 공부 시간 / 목표 시간 표시 (서버 조회 후 업데이트)
        study_lbl = ctk.CTkLabel(
            item,
            text="--:--:-- / --:--:--",
            font=self._make_font(11),
            text_color=self.theme["text_muted"],
        )
        study_lbl.pack(side="left", padx=(8, 0))
        study_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())
        setattr(self, f"_room_study_lbl_{room_code}", study_lbl)

        delete_btn = ctk.CTkButton(
            item,
            text="X",
            width=32,
            height=32,
            command=delete_fn,
            font=self._make_font(13),
            fg_color="transparent",
            hover_color=self.theme["sand"],
            text_color=self.theme["text_muted"],
            border_width=0,
        )
        delete_btn.pack(side="right", padx=12)

    def _remove_group_list_room(self, room_id: int):
        room_manager.remove_room(room_id)
        self._refresh_group_list()

    def _on_group_list_room_click(self, room_id: int, name: str, room_code: str):
        self.group_list_error_label.configure(text="")

        def on_result(result, error):
            if error:
                self.group_list_error_label.configure(text=f"서버 오류: {error}")
                return
            if not result.get("ok"):
                err_map = {
                    "room_not_found": "방을 찾을 수 없습니다. 방 이름과 코드를 확인해주세요.",
                    "name_and_code_required": "방 이름과 참가 코드를 확인해주세요.",
                }
                self.group_list_error_label.configure(
                    text=err_map.get(result.get("error", ""), "참가 검증에 실패했습니다.")
                )
                return
            self._start_group_room_flow(room_code, name, room_id)

        self._call_api("/rooms/join", {"name": name, "room_code": room_code}, on_result)

    # ──────────────────────────────────────────────
    # screen_group_join : 단체방 참가 (GROUP_JOIN)
    # ──────────────────────────────────────────────

    def _build_screen_group_join(self):
        frame = self.screen_group_join

        # 상단바: 테두리/둥근 모서리/여백 없이 사각형
        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="단체방 참가하기", anchor="w", font=self._make_font(20), text_color=self.theme["text"]).pack(side="left", padx=16)
        ctk.CTkButton(top, text="뒤로가기", width=80, height=36, command=lambda: self.show_screen(GROUP_LIST),
              font=self._make_font(14), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        self._join_wrap = ctk.CTkFrame(frame, fg_color="transparent")
        self._join_wrap.pack(fill="both", expand=True)
        self._join_wrap.grid_columnconfigure(0, weight=1)
        self._join_wrap.grid_rowconfigure(0, weight=1)
        self._join_wrap.grid_rowconfigure(2, weight=1)
        wrap = self._join_wrap

        self._join_form = ctk.CTkFrame(wrap, **self._surface_style())
        self._join_form.grid(row=1, column=0, padx=40, pady=20)
        form = self._join_form

        ctk.CTkLabel(form, text="방 이름", font=self._make_font(13), anchor="w", text_color=self.theme["text"]).pack(
            pady=(24, 4), padx=28, anchor="w")
        self.join_name_entry = ctk.CTkEntry(
            form,
            placeholder_text="단체방 이름 입력",
            height=42,
            width=380,
            font=self._make_font(13),
            **self._entry_style(),
        )
        self.join_name_entry.pack(padx=28)
        self.join_name_entry.bind("<Button-1>", lambda e: self._show_keyboard(self.join_name_entry))

        ctk.CTkLabel(form, text="참가 코드", font=self._make_font(13), anchor="w", text_color=self.theme["text"]).pack(
            pady=(16, 4), padx=28, anchor="w")
        self.join_code_entry = ctk.CTkEntry(
            form,
            placeholder_text="참가 코드 입력",
            height=42,
            width=380,
            font=self._make_font(13),
            **self._entry_style(),
        )
        self.join_code_entry.pack(padx=28)
        self.join_code_entry.bind("<Button-1>", lambda e: self._show_keyboard(self.join_code_entry))

        self.join_error_label = ctk.CTkLabel(
            form, text="", font=self._make_font(12), width=380, **self._error_text_style())
        self.join_error_label.pack(pady=(10, 0), padx=28)

        self.join_submit_btn = ctk.CTkButton(
            form, text="참가하기", height=46, width=380,
            command=self._on_join_submit, font=self._make_font(15), **self._primary_button_style())
        self.join_submit_btn.pack(pady=(12, 28), padx=28)

    def _on_join_submit(self):
        name = self.join_name_entry.get().strip()
        code = self.join_code_entry.get().strip()
        if not name or not code:
            self.join_error_label.configure(text="방 이름과 참가 코드를 모두 입력해주세요.")
            return

        self.join_submit_btn.configure(state="disabled", text="확인 중...")
        self.join_error_label.configure(text="")

        def on_result(result, error):
            if error:
                self.join_submit_btn.configure(state="normal", text="참가하기")
                self.join_error_label.configure(text=f"서버 오류: {error}")
                return
            if not result.get("ok"):
                self.join_submit_btn.configure(state="normal", text="참가하기")
                err_map = {
                    "room_not_found": "방을 찾을 수 없습니다. 방 이름과 코드를 확인해주세요.",
                    "name_mismatch": "방 이름이 올바르지 않습니다.",
                    "name_and_code_required": "방 이름과 참가 코드를 입력해주세요.",
                }
                self.join_error_label.configure(text=err_map.get(result.get("error", ""), "참가에 실패했습니다."))
                return
            room_manager.add_room(name, code, result["id"])
            self._start_group_room_flow(code, name, result["id"])

        self._call_api("/rooms/join", {"name": name, "room_code": code}, on_result)

    # ──────────────────────────────────────────────
    # screen_group_create : 단체방 생성 (GROUP_CREATE)
    # ──────────────────────────────────────────────

    def _build_screen_group_create(self):
        frame = self.screen_group_create

        # 상단바: 테두리/둥근 모서리/여백 없이 사각형
        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="단체방 생성하기", anchor="w", font=self._make_font(20), text_color=self.theme["text"]).pack(side="left", padx=16)
        ctk.CTkButton(top, text="뒤로가기", width=80, height=36, command=lambda: self.show_screen(GROUP_LIST),
              font=self._make_font(14), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        self._create_wrap = ctk.CTkFrame(frame, fg_color="transparent")
        self._create_wrap.pack(fill="both", expand=True)
        self._create_wrap.grid_columnconfigure(0, weight=1)
        self._create_wrap.grid_rowconfigure(0, weight=1)
        self._create_wrap.grid_rowconfigure(2, weight=1)
        wrap = self._create_wrap

        self._create_form = ctk.CTkFrame(wrap, **self._surface_style())
        self._create_form.grid(row=1, column=0, padx=40, pady=20)
        form = self._create_form

        ctk.CTkLabel(form, text="방 이름", font=self._make_font(13), anchor="w", text_color=self.theme["text"]).pack(
            pady=(24, 4), padx=28, anchor="w")
        self.create_name_entry = ctk.CTkEntry(
            form,
            placeholder_text="단체방 이름 입력",
            height=42,
            width=380,
            font=self._make_font(13),
            **self._entry_style(),
        )
        self.create_name_entry.pack(padx=28)
        self.create_name_entry.bind("<Button-1>", lambda e: self._show_keyboard(self.create_name_entry))

        ctk.CTkLabel(form, text="참가 코드", font=self._make_font(13), anchor="w", text_color=self.theme["text"]).pack(
            pady=(16, 4), padx=28, anchor="w")
        self.create_code_entry = ctk.CTkEntry(
            form,
            placeholder_text="다른 사람이 입력할 코드 설정",
            height=42,
            width=380,
            font=self._make_font(13),
            **self._entry_style(),
        )
        self.create_code_entry.pack(padx=28)
        self.create_code_entry.bind("<Button-1>", lambda e: self._show_keyboard(self.create_code_entry))

        self.create_error_label = ctk.CTkLabel(
            form, text="", font=self._make_font(12), width=380, **self._error_text_style())
        self.create_error_label.pack(pady=(10, 0), padx=28)

        self.create_submit_btn = ctk.CTkButton(
            form, text="생성하기", height=46, width=380,
            command=self._on_create_submit, font=self._make_font(15), **self._primary_button_style())
        self.create_submit_btn.pack(pady=(12, 28), padx=28)

    def _on_create_submit(self):
        name = self.create_name_entry.get().strip()
        code = self.create_code_entry.get().strip()
        if not name or not code:
            self.create_error_label.configure(text="방 이름과 참가 코드를 모두 입력해주세요.")
            return

        self.create_submit_btn.configure(state="disabled", text="생성 중...")
        self.create_error_label.configure(text="")

        def on_result(result, error):
            if error:
                self.create_submit_btn.configure(state="normal", text="생성하기")
                self.create_error_label.configure(text=f"서버 오류: {error}")
                return
            if not result.get("ok"):
                self.create_submit_btn.configure(state="normal", text="생성하기")
                err_map = {
                    "room_name_exists": "이미 존재하는 단체방 이름입니다. 다른 이름을 입력해주세요.",
                    "name_and_code_required": "방 이름과 참가 코드를 입력해주세요.",
                }
                self.create_error_label.configure(text=err_map.get(result.get("error", ""), "생성에 실패했습니다."))
                return
            # 새 방 생성 성공: 로컈 daily_goal 초기화
            from services.study_time import clear_daily_goal
            clear_daily_goal(str(result["id"]))
            room_manager.add_room(name, code, result["id"])
            self.show_screen(GROUP_LIST)

        self._call_api("/rooms/create", {"name": name, "room_code": code}, on_result)

    # ──────────────────────────────────────────────
    # 화상 키보드 헬퍼
    # ──────────────────────────────────────────────

    def _show_keyboard(self, entry):
        """Entry 클릭 시 화상 키보드를 오른쪽 열에 표시하고 폼을 왼쪽으로 이동"""
        kb = getattr(self, "onscreen_keyboard", None)
        if kb is None:
            return
        # 이미 같은 Entry에 열려있으면 무시
        if kb.is_visible and kb._target_entry is entry:
            return
        # 현재 화면의 폼을 왼쪽으로 이동
        self._shift_form_left()
        kb._on_hide_callback = self._restore_form_center  # 바깥 클릭 닫힘 시 폼 복원
        # 현재 화면의 wrap(상단바 아래 영역)을 부모로 지정
        parent_wrap = self._get_active_wrap()
        kb.show(entry, parent=parent_wrap)

    def _hide_keyboard(self):
        """화상 키보드 숨기고 폼을 중앙으로 복원"""
        kb = getattr(self, "onscreen_keyboard", None)
        if kb is not None and kb.is_visible:
            kb.hide()
        self._restore_form_center()

    def _get_active_wrap(self):
        """현재 표시 중인 화면의 wrap 프레임 반환"""
        for wrap in (getattr(self, "_join_wrap", None), getattr(self, "_create_wrap", None)):
            if wrap is not None and wrap.winfo_ismapped():
                return wrap
        # 캐릭터 생성 화면일 때
        char_create = getattr(self, "screen_char_create", None)
        if char_create is not None and char_create.winfo_ismapped():
            return char_create
        return None

    def _shift_form_left(self):
        """키보드 표시 시 폼을 왼쪽으로 밀기"""
        for form in (getattr(self, "_join_form", None), getattr(self, "_create_form", None)):
            if form is not None and form.winfo_ismapped():
                form.grid_configure(padx=(4, 0), sticky="w")

    def _restore_form_center(self):
        """키보드 숨김 시 폼을 중앙으로 복원"""
        for form in (getattr(self, "_join_form", None), getattr(self, "_create_form", None)):
            if form is not None and form.winfo_ismapped():
                form.grid_configure(padx=40, sticky="")