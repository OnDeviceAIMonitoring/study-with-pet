"""
카메라 슬라이드 및 카메라 제어 Mixin
- slide_camera : 개인 공부 카메라 화면 (PERSONAL_CAMERA)
"""
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

        self.img_label = ctk.CTkLabel(frame, text="")
        self.img_label.pack(fill="both", expand=True, padx=10, pady=10)

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
