"""
화상 키보드(On-Screen Keyboard) 위젯

CTkEntry를 클릭하면 화면 오른쪽에 키보드가 표시되어
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


class OnScreenKeyboard(ctk.CTkFrame):
    """화면 오른쪽에 표시되는 가상 키보드"""

    def __init__(self, master, theme: dict, make_font, **kwargs):
        super().__init__(master, **kwargs)
        self._theme = theme
        self._make_font = make_font
        self._target_entry = None  # 현재 입력 대상 Entry
        self._shifted = False
        self._korean = False
        self._key_buttons = []  # 버튼 참조 보관
        self.configure(width=380)
        self._build_keys()

    def _get_layout(self):
        """현재 모드에 맞는 키 레이아웃 반환"""
        if self._korean:
            return _LAYOUT_KO_SHIFT if self._shifted else _LAYOUT_KO
        return _LAYOUT_UPPER if self._shifted else _LAYOUT_LOWER

    def _build_keys(self):
        """키 버튼 생성"""
        # 기존 버튼 제거
        for btn in self._key_buttons:
            btn.destroy()
        self._key_buttons.clear()
        for child in self.winfo_children():
            child.destroy()

        layout = self._get_layout()

        for row_keys in layout:
            row_frame = ctk.CTkFrame(self, fg_color="transparent")
            row_frame.pack(pady=2)

            for key in row_keys:
                # 특수 키 너비 조정 (오른쪽 패널에 맞게 축소)
                if key == "SPACE":
                    w, text = 140, " "
                elif key == "⌫":
                    w, text = 44, "⌫"
                elif key == "⇧":
                    w, text = 44, "⇧"
                elif key == "완료":
                    w, text = 60, "완료"
                elif key == "한/영":
                    w, text = 60, "한/영"
                else:
                    w, text = 32, key

                btn = ctk.CTkButton(
                    row_frame,
                    text=text,
                    width=w,
                    height=34,
                    font=self._make_font(12),
                    fg_color=self._theme["white"],
                    hover_color=self._theme["sand"],
                    text_color=self._theme["text"],
                    border_width=1,
                    border_color=self._theme["sand"],
                    corner_radius=6,
                    command=lambda k=key: self._on_key(k),
                )
                btn.pack(side="left", padx=1)
                self._key_buttons.append(btn)

    def _on_key(self, key: str):
        """키 입력 처리"""
        entry = self._target_entry
        if entry is None:
            return

        if key == "⌫":
            # 백스페이스
            current = entry.get()
            if current:
                entry.delete(len(current) - 1, "end")
        elif key == "⇧":
            # Shift 토글
            self._shifted = not self._shifted
            self._build_keys()
        elif key == "한/영":
            # 한/영 전환
            self._korean = not self._korean
            self._shifted = False
            self._build_keys()
        elif key == "완료":
            # 키보드 닫기
            self.hide()
        elif key == "SPACE":
            entry.insert("end", " ")
        else:
            entry.insert("end", key)

    def show(self, target_entry):
        """특정 Entry에 대해 키보드를 오른쪽에 표시"""
        self._target_entry = target_entry
        self._shifted = False
        self._korean = False
        self._build_keys()
        self.pack_propagate(False)
        self.pack(side="right", fill="y", padx=(4, 10), pady=10)

    def hide(self):
        """키보드 숨기기"""
        self._target_entry = None
        self.pack_forget()

    @property
    def is_visible(self):
        return self.winfo_ismapped()
