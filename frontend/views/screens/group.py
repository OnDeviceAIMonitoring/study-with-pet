"""
단체방 관련 슬라이드 Mixin
- screen_group_list           : 단체방 목록 (GROUP_LIST)
- screen_group      : 단체방 공부 화면 (GROUP_ROOM)
- screen_group_join : 단체방 참가 (GROUP_JOIN)
- screen_group_create : 단체방 생성 (GROUP_CREATE)
"""
import json
import threading

import customtkinter as ctk

from config import MAIN, GROUP_LIST, GROUP_CREATE, GROUP_JOIN, GROUP_ROOM, SELECT_CHAR
from services import socketio_client
from services import room_manager


class GroupScreenMixin:

    # ──────────────────────────────────────────────
    # screen_group : 단체방 공부 화면 (GROUP_ROOM)
    # ──────────────────────────────────────────────

    def _build_screen_group(self):
        frame = self.screen_group
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        self.group_screen_title = ctk.CTkLabel(top, text="단체 공부", anchor="w", font=self._make_font(18))
        self.group_screen_title.pack(side="left")
        ctk.CTkButton(top, text="← 방 목록", width=90, command=self._on_group_back,
                      font=self._make_font(12)).pack(side="right")

        self.group_img_label = ctk.CTkLabel(frame, text="")
        self.group_img_label.pack(fill="both", expand=True, padx=10, pady=10)

        # 개인방과 동일한 캐릭터 UI
        char_area = ctk.CTkFrame(frame, fg_color="transparent")
        char_area.place(relx=0.05, rely=0.7, anchor="w")
        self._group_char_label = ctk.CTkLabel(char_area, text="", fg_color="transparent")
        self._group_char_label.pack()
        self._group_char_growth = ctk.CTkProgressBar(char_area, width=120)
        self._group_char_growth.pack(pady=(2, 0))

    def _on_group_back(self):
        self._socket_generation += 1
        self._group_char_anim_running = False
        self._stop_group_study_session(save=True)
        self.stop_camera()
        with self.lock:
            self.frame_map.clear()
        self.show_screen(GROUP_LIST)

    def _on_group_study(self):
        self.show_screen(GROUP_LIST)

    # ──────────────────────────────────────────────
    # screen_group_list : 단체방 목록 (GROUP_LIST)
    # ──────────────────────────────────────────────

    def _build_screen_group_list(self):
        frame = self.screen_group_list

        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="단체 공부", anchor="w", font=self._make_font(20, "bold")).pack(side="left")
        ctk.CTkButton(top, text="←", width=40, command=lambda: self.show_screen(MAIN),
                      font=self._make_font(14)).pack(side="right")

        self.group_list_scroll = ctk.CTkScrollableFrame(
            frame, label_text="내 단체방 목록", label_font=self._make_font(13)
        )
        self.group_list_scroll.pack(fill="both", expand=True, padx=20, pady=(8, 4))

        bottom = ctk.CTkFrame(frame, fg_color="transparent")
        bottom.pack(fill="x", padx=20, pady=(4, 20))
        bottom.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            bottom, text="참가하기", height=46,
            command=lambda: self.show_screen(GROUP_JOIN),
            font=self._make_font(15),
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            text_color=("gray10", "gray90"),
        ).grid(row=0, column=0, padx=(0, 6), sticky="ew")

        ctk.CTkButton(
            bottom, text="생성하기", height=46,
            command=lambda: self.show_screen(GROUP_CREATE),
            font=self._make_font(15),
        ).grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def _refresh_group_list(self):
        for widget in self.group_list_scroll.winfo_children():
            widget.destroy()

        rooms = room_manager.load_rooms()
        if not rooms:
            ctk.CTkLabel(
                self.group_list_scroll,
                text="참가한 단체방이 없습니다.\n아래 버튼으로 방에 참가하거나 새로 생성하세요.",
                font=self._make_font(13),
                text_color=("gray50", "gray60"),
                justify="center",
            ).pack(pady=48)
            return

        for room in rooms:
            self._add_room_item(room["name"], room["room_code"])

    def _add_room_item(self, name: str, room_code: str):
        enter_fn = lambda rc=room_code, n=name: self._start_group_room_flow(rc, n)

        item = ctk.CTkFrame(
            self.group_list_scroll, height=60, corner_radius=8,
            fg_color=("gray85", "gray22"), cursor="hand2",
        )
        item.pack(fill="x", pady=4, padx=2)
        item.pack_propagate(False)
        item.bind("<Button-1>", lambda e, fn=enter_fn: fn())

        name_lbl = ctk.CTkLabel(item, text=name, font=self._make_font(14, "bold"), anchor="w", cursor="hand2")
        name_lbl.pack(side="left", padx=16)
        name_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())

        code_lbl = ctk.CTkLabel(item, text=f"#{room_code}", font=self._make_font(12),
                                 text_color=("gray50", "gray60"), cursor="hand2")
        code_lbl.pack(side="right", padx=16)
        code_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())

        arrow_lbl = ctk.CTkLabel(item, text="›", font=self._make_font(20), cursor="hand2")
        arrow_lbl.pack(side="right", padx=4)
        arrow_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())

    # ──────────────────────────────────────────────
    # screen_group_join : 단체방 참가 (GROUP_JOIN)
    # ──────────────────────────────────────────────

    def _build_screen_group_join(self):
        frame = self.screen_group_join

        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="단체방 참가하기", anchor="w", font=self._make_font(20, "bold")).pack(side="left")
        ctk.CTkButton(top, text="←", width=40, command=lambda: self.show_screen(GROUP_LIST),
                      font=self._make_font(14)).pack(side="right")

        wrap = ctk.CTkFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(wrap, corner_radius=12)
        form.grid(row=1, column=0, padx=40, pady=20)

        ctk.CTkLabel(form, text="방 이름", font=self._make_font(13), anchor="w").pack(
            pady=(24, 4), padx=28, anchor="w")
        self.join_name_entry = ctk.CTkEntry(
            form, placeholder_text="단체방 이름 입력", height=42, width=380, font=self._make_font(13))
        self.join_name_entry.pack(padx=28)

        ctk.CTkLabel(form, text="참가 코드", font=self._make_font(13), anchor="w").pack(
            pady=(16, 4), padx=28, anchor="w")
        self.join_code_entry = ctk.CTkEntry(
            form, placeholder_text="참가 코드 입력", height=42, width=380, font=self._make_font(13))
        self.join_code_entry.pack(padx=28)

        self.join_error_label = ctk.CTkLabel(
            form, text="", text_color="#ef4444", font=self._make_font(12), width=380)
        self.join_error_label.pack(pady=(10, 0), padx=28)

        self.join_submit_btn = ctk.CTkButton(
            form, text="참가하기", height=46, width=380,
            command=self._on_join_submit, font=self._make_font(15, "bold"))
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
            room_manager.add_room(name, code)
            self._start_group_room_flow(code, name)

        self._call_api("/rooms/join", {"name": name, "room_code": code}, on_result)

    # ──────────────────────────────────────────────
    # screen_group_create : 단체방 생성 (GROUP_CREATE)
    # ──────────────────────────────────────────────

    def _build_screen_group_create(self):
        frame = self.screen_group_create

        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="단체방 생성하기", anchor="w", font=self._make_font(20, "bold")).pack(side="left")
        ctk.CTkButton(top, text="←", width=40, command=lambda: self.show_screen(GROUP_LIST),
                      font=self._make_font(14)).pack(side="right")

        wrap = ctk.CTkFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(wrap, corner_radius=12)
        form.grid(row=1, column=0, padx=40, pady=20)

        ctk.CTkLabel(form, text="방 이름", font=self._make_font(13), anchor="w").pack(
            pady=(24, 4), padx=28, anchor="w")
        self.create_name_entry = ctk.CTkEntry(
            form, placeholder_text="단체방 이름 입력", height=42, width=380, font=self._make_font(13))
        self.create_name_entry.pack(padx=28)

        ctk.CTkLabel(form, text="참가 코드", font=self._make_font(13), anchor="w").pack(
            pady=(16, 4), padx=28, anchor="w")
        self.create_code_entry = ctk.CTkEntry(
            form, placeholder_text="다른 사람이 입력할 코드 설정", height=42, width=380, font=self._make_font(13))
        self.create_code_entry.pack(padx=28)

        self.create_error_label = ctk.CTkLabel(
            form, text="", text_color="#ef4444", font=self._make_font(12), width=380)
        self.create_error_label.pack(pady=(10, 0), padx=28)

        self.create_submit_btn = ctk.CTkButton(
            form, text="생성하기", height=46, width=380,
            command=self._on_create_submit, font=self._make_font(15, "bold"))
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
                    "room_code_exists": "이미 사용 중인 참가 코드입니다. 다른 코드를 입력해주세요.",
                    "name_and_code_required": "방 이름과 참가 코드를 입력해주세요.",
                }
                self.create_error_label.configure(text=err_map.get(result.get("error", ""), "생성에 실패했습니다."))
                return
            room_manager.add_room(name, code)
            self._start_group_room_flow(code, name)

        self._call_api("/rooms/create", {"name": name, "room_code": code}, on_result)

    # ──────────────────────────────────────────────
    # 공통 유틸리티
    # ──────────────────────────────────────────────

    def _start_group_room_flow(self, room_code: str, room_name: str):
        """캐릭터 선택 화면을 거쳐 단체방에 입장합니다."""
        self._pending_group_room = (room_code, room_name)
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
