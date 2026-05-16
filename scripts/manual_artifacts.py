from __future__ import annotations

from pathlib import Path
from tempfile import gettempdir

import cv2
import numpy as np


def _default_output_dir() -> Path:
    return Path(gettempdir()) / "printpuf-artifacts"


def save_bytes(content: bytes, filename: str, output_dir: Path | None = None) -> Path:
    if not isinstance(content, (bytes, bytearray)):
        raise TypeError("content must be bytes")

    target_dir = output_dir or _default_output_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / filename
    output_path.write_bytes(bytes(content))
    return output_path


def save_png_bytes(content: bytes, filename: str, output_dir: Path | None = None) -> Path:
    if not filename.lower().endswith(".png"):
        filename = f"{filename}.png"
    return save_bytes(content, filename, output_dir=output_dir)


def save_image_array(image: np.ndarray, filename: str, output_dir: Path | None = None) -> Path:
    if not isinstance(image, np.ndarray):
        raise TypeError("image must be a numpy array")

    target_dir = output_dir or _default_output_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    output_path = target_dir / filename

    if not cv2.imwrite(str(output_path), image):
        raise ValueError(f"Unable to write image to {output_path}")
    return output_path
