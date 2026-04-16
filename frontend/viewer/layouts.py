"""
비디오 그리드 및 단체 레이아웃 구성 모듈

원본의 `compose_grid`와 `compose_group`를 분리했습니다.
"""

from typing import Dict

import numpy as np
import cv2

from .frame_utils import fit_frame, draw_label, build_waiting_frame


def compose_grid(
    frame_map: Dict[str, dict],
    canvas_width: int,
    canvas_height: int,
    left_reserved_width: int,
    main_width: int,
    main_height: int,
    sub_width: int,
    sub_height: int,
):
    if left_reserved_width >= canvas_width:
        raise RuntimeError("--left-reserved-width must be smaller than --canvas-width.")

    if main_width + (sub_width * 2) > (canvas_width - left_reserved_width):
        raise RuntimeError("Tile widths exceed the right-side video area width.")

    items = sorted(
        frame_map.items(),
        key=lambda item: (
            not item[1]["is_main"],
            item[0].lower(),
        ),
    )[:6]

    full_canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    full_canvas[:, :left_reserved_width] = (18, 18, 18)
    cv2.putText(
        full_canvas,
        "Character Area",
        (20, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (170, 170, 170),
        2,
    )

    right_width = canvas_width - left_reserved_width
    right_canvas = full_canvas[:, left_reserved_width:]

    if not items:
        waiting = build_waiting_frame(right_width, canvas_height)
        right_canvas[:, :] = waiting
        return full_canvas

    main_nickname, main_info = items[0]
    sub_items = items[1:]

    main_tile = fit_frame(main_info["frame"], main_width, main_height)
    main_tile = draw_label(main_tile, main_nickname, main_info["is_main"], main_info["updated_at"])

    sub_columns = 2
    sub_rows = max(1, (len(sub_items) + sub_columns - 1) // sub_columns)
    sub_panel_w = sub_columns * sub_width
    sub_panel_h = sub_rows * sub_height

    video_area_h = max(main_height, sub_panel_h)
    video_area_w = main_width + sub_panel_w
    video_area = np.zeros((video_area_h, video_area_w, 3), dtype=np.uint8)

    main_y = (video_area_h - main_height) // 2
    video_area[main_y:main_y + main_height, 0:main_width] = main_tile

    for index, (nickname, info) in enumerate(sub_items):
        row = index // sub_columns
        col = index % sub_columns
        tile = fit_frame(info["frame"], sub_width, sub_height)
        tile = draw_label(tile, nickname, info["is_main"], info["updated_at"]) 
        y_start = row * sub_height
        x_start = main_width + (col * sub_width)
        video_area[y_start:y_start + sub_height, x_start:x_start + sub_width] = tile

    right_y = (canvas_height - video_area_h) // 2
    right_x = (right_width - video_area_w) // 2
    right_canvas[
        right_y:right_y + video_area_h,
        right_x:right_x + video_area_w,
    ] = video_area

    return full_canvas


def compose_group(
    frame_map: Dict[str, dict],
    canvas_width: int,
    canvas_height: int,
    left_reserved_width: int,
    main_width: int,
    main_height: int,
    sub_width: int,
    sub_height: int,
):
    """단체 공부용 레이아웃: 중앙에 메인, 오른쪽에 세로로 참가자 타일 배치"""
    if left_reserved_width >= canvas_width:
        raise RuntimeError("--left-reserved-width must be smaller than --canvas-width.")

    right_total_width = canvas_width - left_reserved_width
    if right_total_width <= 0:
        raise RuntimeError("Canvas too small for right area.")

    right_col_w = sub_width
    center_w = right_total_width - right_col_w
    if center_w <= 0:
        raise RuntimeError("Not enough width for center/main area.")

    full_canvas = np.zeros((canvas_height, canvas_width, 3), dtype=np.uint8)
    full_canvas[:, :left_reserved_width] = (18, 18, 18)
    cv2.putText(
        full_canvas,
        "Character Area",
        (20, 34),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (170, 170, 170),
        2,
    )

    right_canvas = full_canvas[:, left_reserved_width:]

    if not frame_map:
        waiting = build_waiting_frame(right_total_width, canvas_height)
        right_canvas[:, :] = waiting
        return full_canvas

    items = sorted(
        frame_map.items(),
        key=lambda item: (
            not item[1]["is_main"],
            item[0].lower(),
        ),
    )

    main_nickname, main_info = items[0]
    others = [it for it in items[1:]]

    main_tile = fit_frame(main_info["frame"], main_width, main_height)
    main_tile = draw_label(main_tile, main_nickname, main_info["is_main"], main_info["updated_at"])

    center_area = np.zeros((canvas_height, center_w, 3), dtype=np.uint8)
    m_h, m_w = main_tile.shape[:2]
    y_off = (canvas_height - m_h) // 2
    x_off = max(0, (center_w - m_w) // 2)
    center_area[y_off:y_off + m_h, x_off:x_off + m_w] = main_tile

    col_area = np.zeros((canvas_height, right_col_w, 3), dtype=np.uint8)
    max_display = max(1, canvas_height // sub_height)
    display_items = others[:max_display]
    total_h = len(display_items) * sub_height
    start_y = (canvas_height - total_h) // 2
    for idx, (nick, info) in enumerate(display_items):
        tile = fit_frame(info["frame"], sub_width, sub_height)
        tile = draw_label(tile, nick, info["is_main"], info["updated_at"])
        y0 = start_y + idx * sub_height
        col_area[y0:y0 + sub_height, 0:sub_width] = tile

    right_canvas[:, :center_w] = center_area
    right_canvas[:, center_w:center_w + right_col_w] = col_area

    return full_canvas
