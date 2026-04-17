"""
카메라 슬라이드 및 카메라 제어 Mixin
- slide_camera : 개인 공부 카메라 화면 (PERSONAL_CAMERA)
"""
import os
import json
import time
import threading

import cv2
import customtkinter as ctk

from .slides import MAIN


class CameraSlideMixin:


    def _build_camera_slide(self):
        frame = self.slide_camera
        top = ctk.CTkFrame(frame)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="개인 공부 - 카메라", anchor="w", font=self._make_font(18)).pack(side="left")
        ctk.CTkButton(top, text="돌아가기", width=80, command=self._on_camera_back,
                      font=self._make_font(12)).pack(side="right")

        # 카메라 피드 라벨
        self.img_label = ctk.CTkLabel(frame, text="")
        self.img_label.pack(fill="both", expand=True, padx=10, pady=10)

        # 캐릭터 애니메이션 + 성장도 바 영역
        char_area = ctk.CTkFrame(frame, fg_color="transparent")
        char_area.place(relx=0.05, rely=0.7, anchor="w")

        self._camera_char_label = ctk.CTkLabel(char_area, text="", fg_color="transparent")
        self._camera_char_label.pack()
        self._camera_char_name = ctk.CTkLabel(char_area, text="", font=self._make_font(14, "bold"))
        self._camera_char_name.pack(pady=(4,0))
        self._camera_char_growth = ctk.CTkProgressBar(char_area, width=120)
        self._camera_char_growth.pack(pady=(2,0))

        self._camera_char_frames = []
        self._camera_char_frame_idx = 0
        self._camera_char_anim_running = False

        self._load_camera_character_animation()

    def _load_camera_character_animation(self):
        """선택된 캐릭터의 tail 애니메이션 프레임을 불러와서 self._camera_char_frames에 저장, 성장도/이름도 표시"""
        self._camera_char_frames = []
        self._camera_char_frame_idx = 0
        char_name = getattr(self, '_selected_char', None)
        char_growth = 0.0
        # 인덱스일 경우 실제 이름/성장도로 변환
        if isinstance(char_name, int):
            try:
                with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                    characters = json.load(f)
                char_growth = characters[char_name].get("growth", 0.0)
                char_name = characters[char_name]["name"]
            except Exception:
                char_name = None
        else:
            # 이름으로 직접 선택된 경우 성장도 탐색
            try:
                with open("frontend/user/characters.json", "r", encoding="utf-8") as f:
                    characters = json.load(f)
                for c in characters:
                    if c.get("name") == char_name:
                        char_growth = c.get("growth", 0.0)
                        break
            except Exception:
                pass
        if not char_name or not isinstance(char_name, str):
            self._camera_char_label.configure(image=None)
            self._camera_char_name.configure(text="")
            self._camera_char_growth.set(0.0)
            return
        tail_dir = f"frontend/assets/characters/{char_name}/baby/tail"
        if not os.path.isdir(tail_dir):
            self._camera_char_label.configure(image=None)
            self._camera_char_name.configure(text=char_name)
            self._camera_char_growth.set(char_growth)
            return
        files = sorted([f for f in os.listdir(tail_dir) if f.endswith('.png')])
        from PIL import Image
        for fn in files:
            try:
                pil_img = Image.open(os.path.join(tail_dir, fn)).convert("RGBA")
                target_w, target_h = 120, int(120 * 650 / 430)
                bg = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
                pil_img.thumbnail((target_w, target_h), Image.LANCZOS)
                x = (target_w - pil_img.width) // 2
                y = (target_h - pil_img.height) // 2
                bg.paste(pil_img, (x, y), pil_img)
                ctk_img = ctk.CTkImage(light_image=bg, dark_image=bg, size=(target_w, target_h))
                self._camera_char_frames.append(ctk_img)
            except Exception:
                continue
        self._camera_char_name.configure(text=char_name)
        self._camera_char_growth.set(char_growth)
        if self._camera_char_frames:
            self._camera_char_label.configure(image=self._camera_char_frames[0])
            self._camera_char_anim_running = True
            self._camera_char_anim_update()
        else:
            self._camera_char_label.configure(image=None)
            self._camera_char_anim_running = False

    def _camera_char_anim_update(self):
        if not self._camera_char_anim_running or not self._camera_char_frames:
            return
        self._camera_char_frame_idx = (self._camera_char_frame_idx + 1) % len(self._camera_char_frames)
        self._camera_char_label.configure(image=self._camera_char_frames[self._camera_char_frame_idx])
        self.root.after(350, self._camera_char_anim_update)

    def _on_camera_back(self):
        self.stop_camera()
        self.show_slide(MAIN)

    def start_camera(self, camera_index: int = 0):
        if self.camera_running:
            return
        self.camera_running = True

        def cam_loop():
            cap = cv2.VideoCapture(camera_index)
            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.args.canvas_width - self.args.left_reserved_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.args.canvas_height)
            except Exception:
                pass
            while self.camera_running:
                ret, frame = cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue
                with self.lock:
                    self.latest_frame = frame.copy()
                time.sleep(0.01)
            try:
                cap.release()
            except Exception:
                pass

        self.camera_thread = threading.Thread(target=cam_loop, daemon=True)
        self.camera_thread.start()

    def stop_camera(self):
        if not self.camera_running:
            return
        self.camera_running = False
        if self.camera_thread is not None:
            self.camera_thread.join(timeout=1.0)
            self.camera_thread = None
