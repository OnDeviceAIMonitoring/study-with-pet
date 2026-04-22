"""
이름 입력용 화상 키보드 (영어 전용)

바탕화면 런처 스크립트에서 호출되어,
사용자가 이름을 입력하면 stdout으로 출력하고 종료한다.
종료 코드: 0=정상(이름 출력), 1=취소
"""

import tkinter as tk
import sys


# ── 키 레이아웃 ──────────────────────────────────
_LAYOUT_LOWER = [
    list("qwertyuiop"),
    list("asdfghjkl"),
    ["⇧"] + list("zxcvbnm") + ["⌫"],
    ["OK"],
]
_LAYOUT_UPPER = [
    list("QWERTYUIOP"),
    list("ASDFGHJKL"),
    ["⇧"] + list("ZXCVBNM") + ["⌫"],
    ["OK"],
]


class NameInputKeyboard:
    """이름 입력용 화상 키보드 윈도우"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("이름 입력")
        self.root.configure(bg="#F6F2EA")
        self.root.resizable(False, False)

        # 결과 저장
        self._result = None
        self._shifted = False

        # ── 안내 라벨 ──
        tk.Label(
            self.root, text="이름을 입력하세요",
            font=("Sans", 16, "bold"), bg="#F6F2EA", fg="#2F2A24",
        ).pack(pady=(18, 6))

        # ── 입력 필드 ──
        self.entry = tk.Entry(
            self.root, font=("Sans", 18), width=30,
            relief="solid", bd=1, justify="center",
        )
        self.entry.pack(pady=(0, 12), padx=24)

        # ── 키보드 프레임 ──
        self._kb_frame = tk.Frame(self.root, bg="#F6F2EA")
        self._kb_frame.pack(pady=(0, 14))

        self._build_keys()

        # 윈도우 중앙 배치
        self.root.update_idletasks()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

        # 닫기 버튼(X) 클릭 → 취소
        self.root.protocol("WM_DELETE_WINDOW", self._on_cancel)

    # ── 키 생성 ──────────────────────────────────

    def _build_keys(self):
        for child in self._kb_frame.winfo_children():
            child.destroy()

        layout = _LAYOUT_UPPER if self._shifted else _LAYOUT_LOWER

        for row_keys in layout:
            row = tk.Frame(self._kb_frame, bg="#F6F2EA")
            row.pack(pady=3)
            for key in row_keys:
                if key == "SPACE":
                    w, text = 18, " "
                elif key == "OK":
                    w, text = 8, "OK"
                elif key == "⌫":
                    w, text = 5, "⌫"
                elif key == "⇧":
                    w, text = 5, "⇧"
                else:
                    w, text = 4, key

                bg = "#F9DFDF" if key == "OK" else "#FFFDF8"
                btn = tk.Button(
                    row, text=text, width=w, height=2,
                    font=("Sans", 12), relief="solid", bd=1,
                    bg=bg, activebackground="#E3D9C8",
                    command=lambda k=key: self._on_key(k),
                )
                btn.pack(side="left", padx=2)

    # ── 키 이벤트 ────────────────────────────────

    def _on_key(self, key: str):
        if key == "⌫":
            cur = self.entry.get()
            if cur:
                self.entry.delete(len(cur) - 1, "end")
        elif key == "⇧":
            self._shifted = not self._shifted
            self._build_keys()
        elif key == "OK":
            self._on_ok()
        else:
            # 영문자만 허용
            if key.isalpha():
                self.entry.insert("end", key)

    def _on_ok(self):
        name = self.entry.get().strip()
        if name:
            self._result = name
            self.root.destroy()

    def _on_cancel(self):
        self._result = None
        self.root.destroy()

    # ── 실행 ─────────────────────────────────────

    def run(self) -> str | None:
        self.root.mainloop()
        return self._result


if __name__ == "__main__":
    app = NameInputKeyboard()
    name = app.run()
    if name:
        print(name)
        sys.exit(0)
    else:
        sys.exit(1)
