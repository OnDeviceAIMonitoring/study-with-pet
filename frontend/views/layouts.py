"""
비디오 그리드 및 단체 레이아웃 구성 모듈

원본의 `compose_grid`와 `compose_group`를 분리했습니다.
"""

from typing import Dict, Optional

import numpy as np
import cv2

from .frame_utils import fit_frame, draw_label, build_waiting_frame


def _alpha_blit(dst_bgr: np.ndarray, src_rgba: np.ndarray, x: int, y: int) -> None:
    """RGBA 이미지를 BGR 캔버스 위에 알파 블렌딩합니다."""
    h, w = src_rgba.shape[:2]
    if h <= 0 or w <= 0:
        return

    y0 = max(0, y)
    x0 = max(0, x)
    y1 = min(dst_bgr.shape[0], y + h)
    x1 = min(dst_bgr.shape[1], x + w)
    if y0 >= y1 or x0 >= x1:
        return

    src_y0 = y0 - y
    src_x0 = x0 - x
    src_y1 = src_y0 + (y1 - y0)
    src_x1 = src_x0 + (x1 - x0)

    src = src_rgba[src_y0:src_y1, src_x0:src_x1]
    alpha = (src[:, :, 3:4].astype(np.float32) / 255.0)
    src_bgr = src[:, :, :3][:, :, ::-1].astype(np.float32)
    dst = dst_bgr[y0:y1, x0:x1].astype(np.float32)
    blended = (src_bgr * alpha) + (dst * (1.0 - alpha))
    dst_bgr[y0:y1, x0:x1] = blended.astype(np.uint8)


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

    main_tile = fit_frame(main_info["frame"], main_width, main_height)  # compose_grid는 기본 검정 배경 유지
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
    character_overlay: Optional[dict] = None,
    bg_color: tuple = (0, 0, 0),
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

    full_canvas = np.full((canvas_height, canvas_width, 3), bg_color, dtype=np.uint8)
    # 왼쪽 reserved 영역에 캐릭터 오버레이 렌더링
    if character_overlay:
        left_canvas = full_canvas[:, :left_reserved_width]
        char_frame = character_overlay.get("frame")
        growth_percent = int(character_overlay.get("growth_percent", 0))
        bar_w = 120
        bar_h = 12
        bar_x = max(0, (left_reserved_width - bar_w) // 2)
        bar_y = canvas_height - 40

        if isinstance(char_frame, np.ndarray) and char_frame.ndim == 3 and char_frame.shape[2] == 4:
            h, w = char_frame.shape[:2]
            cx = max(0, (left_reserved_width - w) // 2)
            cy = max(50, (canvas_height - h) // 2)
            _alpha_blit(left_canvas, char_frame, cx, cy)
            # 개인방처럼 이미지 바로 아래에 진행바 배치
            bar_y = min(canvas_height - 40, cy + h + 8)

        bar_bg = tuple(max(0, c - 30) for c in bg_color)
        cv2.rectangle(left_canvas, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), bar_bg, -1)
        fill_w = int(bar_w * max(0, min(100, growth_percent)) / 100)
        cv2.rectangle(left_canvas, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), (70, 170, 255), -1)

    right_canvas = full_canvas[:, left_reserved_width:]

    if not frame_map:
        waiting = build_waiting_frame(right_total_width, canvas_height, bg_color=bg_color, text_color=(80, 70, 60))
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

    main_tile = fit_frame(main_info["frame"], center_w, canvas_height, bg_color=bg_color)
    main_tile = draw_label(
        main_tile,
        main_nickname,
        main_info["is_main"],
        main_info["updated_at"],
        draw_border=False,
        label_style="group",
    )

    center_area = np.full((canvas_height, center_w, 3), bg_color, dtype=np.uint8)
    m_h, m_w = main_tile.shape[:2]
    y_off = (canvas_height - m_h) // 2
    x_off = 0
    center_area[y_off:y_off + m_h, x_off:x_off + m_w] = main_tile

    col_area = np.full((canvas_height, right_col_w, 3), bg_color, dtype=np.uint8)
    max_display = max(1, canvas_height // sub_height)
    display_items = others[:max_display]
    total_h = len(display_items) * sub_height
    start_y = (canvas_height - total_h) // 2
    for idx, (nick, info) in enumerate(display_items):
        tile = fit_frame(info["frame"], sub_width, sub_height, bg_color=bg_color)
        tile = draw_label(
            tile,
            nick,
            info["is_main"],
            info["updated_at"],
            draw_border=False,
            label_style="group",
        )
        y0 = start_y + idx * sub_height
        col_area[y0:y0 + sub_height, 0:sub_width] = tile

    right_canvas[:, :center_w] = center_area
    right_canvas[:, center_w:center_w + right_col_w] = col_area

    return full_canvas


def compose_others_column(
    others: list,
    col_width: int,
    col_height: int,
    sub_width: int,
    sub_height: int,
    bg_color: tuple = (0, 0, 0),
) -> np.ndarray:
    """다른 참가자 카메라를 세로 컬럼으로 합성합니다."""
    col_area = np.full((col_height, col_width, 3), bg_color, dtype=np.uint8)
    if not others:
        return col_area
    max_display = max(1, col_height // sub_height)
    display_items = others[:max_display]
    total_h = len(display_items) * sub_height
    start_y = (col_height - total_h) // 2
    for idx, (nick, info) in enumerate(display_items):
        tile = fit_frame(info["frame"], sub_width, sub_height, bg_color=bg_color)
        tile = draw_label(
            tile, nick, info["is_main"], info["updated_at"],
            draw_border=False, label_style="group",
        )
        y0 = start_y + idx * sub_height
        col_area[y0:y0 + sub_height, 0:sub_width] = tile
    return col_area
