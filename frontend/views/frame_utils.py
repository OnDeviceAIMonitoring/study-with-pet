"""
프레임 디코딩 및 기본 처리 유틸리티

모듈 역할:
- JPEG base64 디코딩
- 프레임 크기 조정 및 중앙 배치
- 라벨 그리기 및 대기 프레임 생성

한글 주석을 포함하여 원본 기능을 분리했습니다.
"""

import base64
from typing import Tuple

import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont


CAMERA_BORDER_BGR = (200, 217, 227)  # BGR for #E3D9C8

_LABEL_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_GROUP_LABEL_HEIGHT = 28


def _load_label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in _LABEL_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()



def draw_rect_border(frame: np.ndarray, color=CAMERA_BORDER_BGR, thickness: int = 3) -> np.ndarray:
    """프레임 외곽에 일반 사각형 보더를 그립니다."""
    h, w = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (w - 1, h - 1), color, thickness)
    return frame


def decode_frame(jpeg_base64: str):
    """Base64로 인코딩된 JPEG를 디코딩하여 BGR 프레임을 반환합니다."""
    raw = base64.b64decode(jpeg_base64)
    encoded = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Failed to decode JPEG frame.")
    return frame


def fit_frame(frame: np.ndarray, width: int, height: int, bg_color=(0, 0, 0)) -> np.ndarray:
    """프레임을 주어진 박스에 맞게 비율 유지하며 리사이즈하고 중앙 배치합니다."""
    src_h, src_w = frame.shape[:2]
    scale = min(width / src_w, height / src_h)
    dst_w = max(1, int(src_w * scale))
    dst_h = max(1, int(src_h * scale))
    resized = cv2.resize(frame, (dst_w, dst_h))

    canvas = np.full((height, width, 3), bg_color, dtype=np.uint8)
    y_offset = (height - dst_h) // 2
    x_offset = (width - dst_w) // 2
    canvas[y_offset:y_offset + dst_h, x_offset:x_offset + dst_w] = resized
    return canvas


def draw_label(
    frame: np.ndarray,
    nickname: str,
    is_main: bool,
    updated_at: str,
    draw_border: bool = True,
    label_style: str = "default",
) -> np.ndarray:
    """프레임 상단에 닉네임과 하단에 업데이트 시간 라벨을 그립니다."""
    label = nickname

    if draw_border:
        draw_rect_border(frame, color=CAMERA_BORDER_BGR, thickness=3)

    if label_style == "group":
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (frame.shape[1], _GROUP_LABEL_HEIGHT), (255, 255, 255), -1)
        cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)

        pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        font = _load_label_font(13)
        text_bbox = draw.textbbox((0, 0), label, font=font)
        text_h = text_bbox[3] - text_bbox[1]
        text_y = max(5, (_GROUP_LABEL_HEIGHT - text_h) // 2)
        draw.text((10, text_y), label, fill=(0, 0, 0), font=font)
        frame[:, :] = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    else:
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 34), (25, 25, 25), -1)
        cv2.putText(frame, label, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    cv2.putText(frame, updated_at, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
    return frame


def build_waiting_frame(width: int, height: int, bg_color=(0, 0, 0), text_color=(255, 255, 255)) -> np.ndarray:
    """프레임 수신 전 표시할 대기 이미지(간단한 텍스트)."""
    frame = np.full((height, width, 3), bg_color, dtype=np.uint8)
    cv2.putText(frame, "Waiting for frames...", (20, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.9, text_color, 2)
    return frame
