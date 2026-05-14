from __future__ import annotations

import base64
import hashlib
from io import BytesIO
from math import ceil
from random import Random

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageDraw

from .layout import ARUCO_MARKER_IDS, Rect, build_tag_layout


_CANVAS_BG = (244, 240, 232)
_QR_BG = (252, 250, 246)
_FRAME = (130, 121, 111)
_QR_ERROR_CORRECTION = qrcode.constants.ERROR_CORRECT_M
_RED_FAMILY: tuple[tuple[int, int, int], ...] = (
    (205, 61, 67),
    (228, 106, 78),
    (243, 198, 189),
    (136, 43, 52),
)
_GREEN_FAMILY: tuple[tuple[int, int, int], ...] = (
    (68, 148, 96),
    (114, 181, 138),
    (198, 230, 206),
    (39, 104, 69),
)
_BLUE_FAMILY: tuple[tuple[int, int, int], ...] = (
    (56, 96, 183),
    (94, 138, 213),
    (201, 217, 246),
    (34, 60, 118),
)
_ARUCO_DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)


def _seeded_rng(seed_material: bytes) -> Random:
    digest = hashlib.sha256(seed_material).digest()
    return Random(int.from_bytes(digest[:8], "big"))


def _draw_micro_texture(draw: ImageDraw.ImageDraw, rect: Rect, rng: Random, palette: tuple[tuple[int, int, int], ...]) -> None:
    cols = max(rect.width // 4, 4)
    rows = max(rect.height // 6, 5)
    tile_w = ceil(rect.width / cols)
    tile_h = ceil(rect.height / rows)

    for row in range(rows):
        for col in range(cols):
            x0 = rect.x + col * tile_w
            y0 = rect.y + row * tile_h
            x1 = min(rect.x + rect.width - 1, x0 + tile_w - 1)
            y1 = min(rect.y + rect.height - 1, y0 + tile_h - 1)
            if x1 < x0 or y1 < y0:
                continue

            base = palette[rng.randrange(len(palette))]
            if rng.random() < 0.18:
                base = tuple(min(channel + 22, 255) for channel in base)
            inset = 1 if x1 - x0 > 2 and y1 - y0 > 2 else 0
            draw.rectangle((x0 + inset, y0 + inset, x1 - inset, y1 - inset), fill=base)


def _draw_fragment(draw: ImageDraw.ImageDraw, rect: Rect, seed_material: bytes, palette: tuple[tuple[int, int, int], ...]) -> None:
    rng = _seeded_rng(seed_material)
    draw.rounded_rectangle(
        (rect.x, rect.y, rect.x + rect.width - 1, rect.y + rect.height - 1),
        radius=max(3, rect.width // 4),
        fill=palette[1],
        outline=_FRAME,
        width=1,
    )
    inner = Rect(rect.x + 2, rect.y + 2, rect.width - 4, rect.height - 4)
    _draw_micro_texture(draw, inner, rng, palette)


def _draw_aruco_marker(canvas: Image.Image, rect: Rect, marker_id: int) -> None:
    marker = np.zeros((rect.height, rect.width), dtype=np.uint8)
    cv2.aruco.generateImageMarker(_ARUCO_DICTIONARY, marker_id, rect.width, marker, 1)
    marker_rgb = cv2.cvtColor(marker, cv2.COLOR_GRAY2RGB)
    canvas.paste(Image.fromarray(marker_rgb), (rect.x, rect.y))


def _compose_qr_payload_image(uri: str, box_size: int, border: int) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=_QR_ERROR_CORRECTION,
        box_size=box_size,
        border=border,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color=_QR_BG).convert("RGB")


def generate_qr(
    cbor_payload: bytes,
    product_id: str,
    box_size: int = 7,
    border: int = 4,
) -> bytes:
    if not isinstance(cbor_payload, bytes) or not cbor_payload:
        raise ValueError("cbor_payload must be non-empty bytes")
    if not product_id:
        raise ValueError("product_id must be a non-empty string")
    if box_size <= 0:
        raise ValueError("box_size must be a positive integer")
    if border < 0:
        raise ValueError("border must be zero or greater")

    encoded = base64.urlsafe_b64encode(cbor_payload).decode("ascii")
    uri = f"printpuf://verify?data={encoded}"
    qr_image = _compose_qr_payload_image(uri, box_size=box_size, border=border)
    layout = build_tag_layout(qr_image.width, qr_image.height)
    seed_material = cbor_payload + b":" + product_id.encode("utf-8")

    canvas = Image.new("RGB", (layout.canvas_width, layout.canvas_height), _CANVAS_BG)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (0, 0, layout.canvas_width - 1, layout.canvas_height - 1),
        radius=max(8, layout.outer_padding),
        fill=_CANVAS_BG,
        outline=_FRAME,
        width=2,
    )
    draw.rounded_rectangle(
        (
            layout.content_rect.x,
            layout.content_rect.y,
            layout.content_rect.x + layout.content_rect.width - 1,
            layout.content_rect.y + layout.content_rect.height - 1,
        ),
        radius=max(6, layout.outer_padding),
        fill=_CANVAS_BG,
        outline=_FRAME,
        width=2,
    )

    _draw_aruco_marker(canvas, layout.aruco_top_left, ARUCO_MARKER_IDS["top_left"])
    _draw_aruco_marker(canvas, layout.aruco_top_right, ARUCO_MARKER_IDS["top_right"])
    _draw_aruco_marker(canvas, layout.aruco_bottom_right, ARUCO_MARKER_IDS["bottom_right"])
    _draw_aruco_marker(canvas, layout.aruco_bottom_left, ARUCO_MARKER_IDS["bottom_left"])

    _draw_fragment(draw, layout.red_fragment, seed_material + b":red", _RED_FAMILY)
    _draw_fragment(draw, layout.green_fragment, seed_material + b":green", _GREEN_FAMILY)
    _draw_fragment(draw, layout.blue_fragment, seed_material + b":blue", _BLUE_FAMILY)

    canvas.paste(qr_image, (layout.qr_panel.x, layout.qr_panel.y))
    draw.rectangle(
        (
            layout.qr_panel.x - 1,
            layout.qr_panel.y - 1,
            layout.qr_panel.x + layout.qr_panel.width,
            layout.qr_panel.y + layout.qr_panel.height,
        ),
        outline=_FRAME,
        width=1,
    )

    buffer = BytesIO()
    canvas.save(buffer, format="PNG")
    return buffer.getvalue()
