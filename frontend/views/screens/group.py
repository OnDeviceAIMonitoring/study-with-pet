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
            font=self._make_font(20, "bold"),
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

        for room in rooms:
            self._add_room_item(room["name"], room["room_code"])

    def _add_room_item(self, name: str, room_code: str):
        enter_fn = lambda rc=room_code, n=name: self._start_group_room_flow(rc, n)

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
            font=self._make_font(14, "bold"),
            anchor="w",
            cursor="hand2",
            text_color=self.theme["text"],
        )
        name_lbl.pack(side="left", padx=16)
        name_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())

        code_lbl = ctk.CTkLabel(item, text=f"#{room_code}", font=self._make_font(12),
                                 text_color=self.theme["text_muted"], cursor="hand2")
        code_lbl.pack(side="right", padx=16)
        code_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())

        arrow_lbl = ctk.CTkLabel(item, text="›", font=self._make_font(20), cursor="hand2", text_color=self.theme["text"])
        arrow_lbl.pack(side="right", padx=4)
        arrow_lbl.bind("<Button-1>", lambda e, fn=enter_fn: fn())

    # ──────────────────────────────────────────────
    # screen_group_join : 단체방 참가 (GROUP_JOIN)
    # ──────────────────────────────────────────────

    def _build_screen_group_join(self):
        frame = self.screen_group_join

        # 상단바: 테두리/둥근 모서리/여백 없이 사각형
        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="단체방 참가하기", anchor="w", font=self._make_font(20, "bold"), text_color=self.theme["text"]).pack(side="left", padx=16)
        ctk.CTkButton(top, text="뒤로가기", width=80, height=36, command=lambda: self.show_screen(GROUP_LIST),
              font=self._make_font(14), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        wrap = ctk.CTkFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(wrap, **self._surface_style())
        form.grid(row=1, column=0, padx=40, pady=20)

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

        self.join_error_label = ctk.CTkLabel(
            form, text="", font=self._make_font(12), width=380, **self._error_text_style())
        self.join_error_label.pack(pady=(10, 0), padx=28)

        self.join_submit_btn = ctk.CTkButton(
            form, text="참가하기", height=46, width=380,
            command=self._on_join_submit, font=self._make_font(15, "bold"), **self._primary_button_style())
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

        # 상단바: 테두리/둥근 모서리/여백 없이 사각형
        top = ctk.CTkFrame(frame, fg_color=self.theme["beige"], border_width=0, corner_radius=0, height=60)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        ctk.CTkLabel(top, text="단체방 생성하기", anchor="w", font=self._make_font(20, "bold"), text_color=self.theme["text"]).pack(side="left", padx=16)
        ctk.CTkButton(top, text="뒤로가기", width=80, height=36, command=lambda: self.show_screen(GROUP_LIST),
              font=self._make_font(14), **self._exit_button_style()).pack(side="right", padx=(0, 16), pady=0)

        wrap = ctk.CTkFrame(frame, fg_color="transparent")
        wrap.pack(fill="both", expand=True)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(0, weight=1)
        wrap.grid_rowconfigure(2, weight=1)

        form = ctk.CTkFrame(wrap, **self._surface_style())
        form.grid(row=1, column=0, padx=40, pady=20)

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

        self.create_error_label = ctk.CTkLabel(
            form, text="", font=self._make_font(12), width=380, **self._error_text_style())
        self.create_error_label.pack(pady=(10, 0), padx=28)

        self.create_submit_btn = ctk.CTkButton(
            form, text="생성하기", height=46, width=380,
            command=self._on_create_submit, font=self._make_font(15, "bold"), **self._primary_button_style())
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