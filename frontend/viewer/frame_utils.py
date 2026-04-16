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


def decode_frame(jpeg_base64: str):
    """Base64로 인코딩된 JPEG를 디코딩하여 BGR 프레임을 반환합니다."""
    raw = base64.b64decode(jpeg_base64)
    encoded = np.frombuffer(raw, dtype=np.uint8)
    frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Failed to decode JPEG frame.")
    return frame


def fit_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """프레임을 주어진 박스에 맞게 비율 유지하며 리사이즈하고 중앙 배치합니다."""
    src_h, src_w = frame.shape[:2]
    scale = min(width / src_w, height / src_h)
    dst_w = max(1, int(src_w * scale))
    dst_h = max(1, int(src_h * scale))
    resized = cv2.resize(frame, (dst_w, dst_h))

    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    y_offset = (height - dst_h) // 2
    x_offset = (width - dst_w) // 2
    canvas[y_offset:y_offset + dst_h, x_offset:x_offset + dst_w] = resized
    return canvas


def draw_label(frame: np.ndarray, nickname: str, is_main: bool, updated_at: str) -> np.ndarray:
    """프레임 상단에 닉네임과 하단에 업데이트 시간 라벨을 그립니다."""
    label = nickname
    if is_main:
        label += " [MAIN]"

    cv2.rectangle(frame, (0, 0), (frame.shape[1], 34), (25, 25, 25), -1)
    cv2.putText(frame, label, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(frame, updated_at, (10, frame.shape[0] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 180, 180), 1)
    return frame


def build_waiting_frame(width: int, height: int) -> np.ndarray:
    """프레임 수신 전 표시할 대기 이미지(간단한 텍스트)."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.putText(frame, "Waiting for frames...", (20, height // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
    return frame
