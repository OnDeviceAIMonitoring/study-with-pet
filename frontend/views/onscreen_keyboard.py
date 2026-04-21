"""
화상 키보드(On-Screen Keyboard) 위젯

CTkEntry를 클릭하면 화면 오른쪽 열에 키보드가 오버레이되어
마우스/터치로 텍스트를 입력할 수 있다.
"""

import customtkinter as ctk


# 키 레이아웃 (행 단위)
_LAYOUT_LOWER = [
    list("1234567890"),
    list("qwertyuiop"),
    list("asdfghjkl"),
    ["⇧"] + list("zxcvbnm") + ["⌫"],
    ["한/영", "SPACE", "완료"],
]
_LAYOUT_UPPER = [
    list("!@#$%^&*()"),
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    ["⇧"] + list("ZXCVBNM") + ["⌫"],
    ["한/영", "SPACE", "완료"],
]
_LAYOUT_KO = [
    list("1234567890"),
    list("ㅂㅈㄷㄱㅅㅛㅕㅑㅐㅔ"),
    list("ㅁㄴㅇㄹㅎㅗㅓㅏㅣ"),
    ["⇧"] + list("ㅋㅌㅊㅍㅠㅜㅡ") + ["⌫"],
    ["한/영", "SPACE", "완료"],
]
_LAYOUT_KO_SHIFT = [
    list("!@#$%^&*()"),
    list("ㅃㅉㄸㄲㅆㅛㅕㅑㅒㅖ"),
    list("ㅁㄴㅇㄹㅎㅗㅓㅏㅣ"),
    ["⇧"] + list("ㅋㅌㅊㅍㅠㅜㅡ") + ["⌫"],
    ["한/영", "SPACE", "완료"],
]

# 키보드 패널 폭 (px)
KB_WIDTH = 570


class OnScreenKeyboard(ctk.CTkFrame):
    """화면 오른쪽 열에 place()로 오버레이되는 가상 키보드"""

    def __init__(self, master, theme: dict, make_font, **kwargs):
        super().__init__(master, **kwargs)
        self._theme = theme
        self._make_font = make_font
        self._target_entry = None  # 현재 입력 대상 Entry
        self._shifted = False
        self._korean = False
        self._key_buttons = []
        self._dismiss_bind_id = None  # 바깥 클릭 바인딩 ID
        self._on_hide_callback = None  # 키보드 닫힐 때 호출되는 콜백
        self.configure(width=KB_WIDTH)
        self._build_keys()

    def _get_layout(self):
        """현재 모드에 맞는 키 레이아웃 반환"""
        if self._korean:
            return _LAYOUT_KO_SHIFT if self._shifted else _LAYOUT_KO
        return _LAYOUT_UPPER if self._shifted else _LAYOUT_LOWER

    def _build_keys(self):
        """키 버튼 생성"""
        for btn in self._key_buttons:
            btn.destroy()
        self._key_buttons.clear()
        for child in self.winfo_children():
            child.destroy()

        layout = self._get_layout()

        # 세로 중앙 정렬을 위한 상단 스페이서
        ctk.CTkFrame(self, fg_color="transparent", height=0).pack(expand=True)

        for row_keys in layout:
            row_frame = ctk.CTkFrame(self, fg_color="transparent")
            row_frame.pack(pady=3, anchor="center")

            for key in row_keys:
                if key == "SPACE":
                    w, text = 200, " "
                elif key == "⌫":
                    w, text = 56, "⌫"
                elif key == "⇧":
                    w, text = 56, "⇧"
                elif key == "완료":
                    w, text = 76, "완료"
                elif key == "한/영":
                    w, text = 76, "한/영"
                else:
                    w, text = 48, key

                btn = ctk.CTkButton(
                    row_frame,
                    text=text,
                    width=w,
                    height=44,
                    font=self._make_font(14),
                    fg_color=self._theme["white"],
                    hover_color=self._theme["sand"],
                    text_color=self._theme["text"],
                    border_width=1,
                    border_color=self._theme["sand"],
                    corner_radius=6,
                    command=lambda k=key: self._on_key(k),
                )
                btn.pack(side="left", padx=2)
                self._key_buttons.append(btn)

        # 세로 중앙 정렬을 위한 하단 스페이서
        ctk.CTkFrame(self, fg_color="transparent", height=0).pack(expand=True)

    def _on_key(self, key: str):
        """키 입력 처리"""
        entry = self._target_entry
        if entry is None:
            return

        if key == "⌫":
            current = entry.get()
            if current:
                entry.delete(len(current) - 1, "end")
        elif key == "⇧":
            self._shifted = not self._shifted
            self._build_keys()
        elif key == "한/영":
            self._korean = not self._korean
            self._shifted = False
            self._build_keys()
        elif key == "완료":
            self.hide()
        elif key == "SPACE":
            entry.insert("end", " ")
        else:
            entry.insert("end", key)

    def _on_root_click(self, event):
        """루트 윈도우 클릭 — 키보드 바깥이면 닫기"""
        if not self.is_visible:
            return
        # 클릭된 위젯이 키보드 내부인지 확인
        try:
            w = event.widget
            # 파괴된 위젯(Shift/한영 전환으로 재생성된 버튼)은 무시
            if not w.winfo_exists():
                return
            while w is not None:
                if w is self:
                    return  # 키보드 내부 클릭 → 무시
                # 타겟 Entry 클릭도 무시
                if w is self._target_entry:
                    return
                w = w.master
        except Exception:
            return  # 위젯 계층 탐색 실패 시 닫지 않음
        self.hide()

    def show(self, target_entry, parent=None):
        """Entry 오른쪽 열에 키보드를 place()로 표시. parent가 주어지면 해당 프레임 기준 배치."""
        self._target_entry = target_entry
        self._shifted = False
        self._korean = False
        self._build_keys()

        # place: 지정된 부모(또는 원래 부모) 오른쪽에 고정, 세로 중앙
        self.configure(width=KB_WIDTH)
        if parent is not None:
            self.place(in_=parent, relx=1.0, rely=0.5, anchor="e", relheight=0.95)
        else:
            self.place(relx=1.0, rely=0.5, anchor="e", relheight=0.95)
        self.lift()  # 다른 위젯 위에 표시

        # 바깥 클릭 감지 바인딩
        root = self.winfo_toplevel()
        if self._dismiss_bind_id is None:
            self._dismiss_bind_id = root.bind("<Button-1>", self._on_root_click, add="+")

    def hide(self):
        """키보드 숨기기"""
        self._target_entry = None
        self.place_forget()
        # 바깥 클릭 바인딩 해제
        if self._dismiss_bind_id is not None:
            try:
                root = self.winfo_toplevel()
                root.unbind("<Button-1>", self._dismiss_bind_id)
            except Exception:
                pass
            self._dismiss_bind_id = None
        # 닫힘 콜백 호출 (폼 위치 복원 등)
        if self._on_hide_callback is not None:
            self._on_hide_callback()

    @property
    def is_visible(self):
        return self.winfo_ismapped()
