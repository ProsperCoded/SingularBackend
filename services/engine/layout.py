from __future__ import annotations

from dataclasses import dataclass


ARUCO_MARKER_IDS = {
    "top_left": 0,
    "top_right": 1,
    "bottom_right": 2,
    "bottom_left": 3,
}


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class TagLayout:
    canvas_width: int
    canvas_height: int
    outer_padding: int
    fiducial_size: int
    fiducial_gap: int
    content_rect: Rect
    qr_panel: Rect
    red_fragment: Rect
    green_fragment: Rect
    blue_fragment: Rect
    aruco_top_left: Rect
    aruco_top_right: Rect
    aruco_bottom_right: Rect
    aruco_bottom_left: Rect
    fragment_gap: int
    qr_gap: int


def build_tag_layout(qr_width: int, qr_height: int) -> TagLayout:
    if qr_width <= 0 or qr_height <= 0:
        raise ValueError("qr_width and qr_height must be positive integers")

    outer_padding = max(8, qr_width // 56)
    fiducial_size = max(24, qr_width // 16)
    fiducial_gap = max(6, qr_width // 72)
    content_x = outer_padding + fiducial_size + fiducial_gap
    content_y = outer_padding + fiducial_size + fiducial_gap

    fragment_width = max(18, qr_width // 11)
    fragment_height = max(28, qr_height // 5)
    fragment_gap = max(8, qr_height // 16)
    qr_gap = max(8, qr_width // 32)

    fragments_height = fragment_height * 3 + fragment_gap * 2
    fragment_y = content_y + max((qr_height - fragments_height) // 2, 0)
    fragment_x = content_x
    qr_x = fragment_x + fragment_width + qr_gap
    qr_y = content_y

    red_fragment = Rect(fragment_x, fragment_y, fragment_width, fragment_height)
    green_fragment = Rect(fragment_x, fragment_y + fragment_height + fragment_gap, fragment_width, fragment_height)
    blue_fragment = Rect(fragment_x, fragment_y + (fragment_height + fragment_gap) * 2, fragment_width, fragment_height)
    qr_panel = Rect(qr_x, qr_y, qr_width, qr_height)

    content_rect = Rect(
        x=content_x - outer_padding,
        y=content_y - outer_padding,
        width=fragment_width + qr_gap + qr_width + outer_padding * 2,
        height=qr_height + outer_padding * 2,
    )
    canvas_width = content_rect.x + content_rect.width + fiducial_size + fiducial_gap + outer_padding
    canvas_height = content_rect.y + content_rect.height + fiducial_size + fiducial_gap + outer_padding

    aruco_top_left = Rect(outer_padding, outer_padding, fiducial_size, fiducial_size)
    aruco_top_right = Rect(canvas_width - outer_padding - fiducial_size, outer_padding, fiducial_size, fiducial_size)
    aruco_bottom_right = Rect(
        canvas_width - outer_padding - fiducial_size,
        canvas_height - outer_padding - fiducial_size,
        fiducial_size,
        fiducial_size,
    )
    aruco_bottom_left = Rect(outer_padding, canvas_height - outer_padding - fiducial_size, fiducial_size, fiducial_size)

    return TagLayout(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        outer_padding=outer_padding,
        fiducial_size=fiducial_size,
        fiducial_gap=fiducial_gap,
        content_rect=content_rect,
        qr_panel=qr_panel,
        red_fragment=red_fragment,
        green_fragment=green_fragment,
        blue_fragment=blue_fragment,
        aruco_top_left=aruco_top_left,
        aruco_top_right=aruco_top_right,
        aruco_bottom_right=aruco_bottom_right,
        aruco_bottom_left=aruco_bottom_left,
        fragment_gap=fragment_gap,
        qr_gap=qr_gap,
    )


def infer_tag_layout(canvas_width: int, canvas_height: int) -> TagLayout:
    if canvas_width <= 0 or canvas_height <= 0:
        raise ValueError("canvas_width and canvas_height must be positive integers")

    best_layout: TagLayout | None = None
    best_error: int | None = None

    for qr_size in range(1, canvas_height + 1):
        layout = build_tag_layout(qr_size, qr_size)
        error = abs(layout.canvas_width - canvas_width) + abs(layout.canvas_height - canvas_height)
        if best_error is None or error < best_error:
            best_layout = layout
            best_error = error
        if error == 0:
            break

    if best_layout is None:
        raise ValueError("unable to infer tag layout")

    return best_layout
