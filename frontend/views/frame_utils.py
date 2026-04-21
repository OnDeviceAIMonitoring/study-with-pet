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
from PIL import Image


CAMERA_BORDER_BGR = (200, 217, 227)  # BGR for #E3D9C8



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
    """프레임에 보더와 업데이트 시간 라벨을 그립니다 (닉네임 표시 제거됨)."""
    # 타임스탬프는 좌상단 기준 고정 위치 (프레임 크기와 무관)
    timestamp_x, timestamp_y = 10, 20
    
    if draw_border:
        draw_rect_border(frame, color=CAMERA_BORDER_BGR, thickness=3)

    # 상단 타이틀 스타일과 동일하게 더 큰 폰트 사용 (크기: 0.5 → 0.7)
    cv2.putText(frame, updated_at, (timestamp_x, timestamp_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    return frame


def build_waiting_frame(width: int, height: int, bg_color=(0, 0, 0), text_color=(255, 255, 255)) -> np.ndarray:
    """투명 대기 프레임 (텍스트 없음)."""
    # 검은 배경을 렌더링하지 않고 그냥 bg_color로 채운 프레임만 반환
    frame = np.full((height, width, 3), bg_color, dtype=np.uint8)
    # "Waiting for frames..." 텍스트 제거 - 그냥 배경만 반환
    return frame
