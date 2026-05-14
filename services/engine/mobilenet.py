from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
import torchvision
from PIL import Image
from torchvision import transforms


_TORCH_CACHE_DIR = Path(__file__).resolve().parents[2] / ".torch-cache"
_TORCH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
torch.hub.set_dir(str(_TORCH_CACHE_DIR))

_MODEL: torch.nn.Module | None = None

_TRANSFORM = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ]
)


def get_model() -> torch.nn.Module:
    global _MODEL

    if _MODEL is None:
        loaded_model = torchvision.models.mobilenet_v2(
            weights=torchvision.models.MobileNet_V2_Weights.DEFAULT
        )
        loaded_model.classifier = torch.nn.Identity()
        loaded_model.eval()
        _MODEL = loaded_model

    return _MODEL


def extract_mobilenet(image_array: np.ndarray) -> np.ndarray:
    if not isinstance(image_array, np.ndarray):
        raise TypeError("image_array must be a numpy array")
    if image_array.ndim != 2:
        raise ValueError("image_array must be a 2D grayscale array")

    rgb = np.stack([image_array] * 3, axis=-1).astype(np.uint8)
    pil_image = Image.fromarray(rgb, mode="RGB")
    tensor = _TRANSFORM(pil_image).unsqueeze(0)
    loaded_model = get_model()

    with torch.inference_mode():
        features = loaded_model(tensor)

    return features.squeeze().cpu().numpy().astype(np.float32)
