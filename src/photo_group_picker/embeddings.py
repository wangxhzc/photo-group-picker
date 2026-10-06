"""Optional local DINOv2 inference; imported only for the ML backend."""

import numpy as np
from PIL import Image, ImageOps


def add_embeddings(photos, model_name, device, batch_size, offline):
    try:
        import torch
        from transformers import AutoImageProcessor, AutoModel
    except ImportError as error:
        raise ImportError("请按 README 安装 requirements-ml.txt 和 PyTorch") from error
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA 不可用；检查 NVIDIA 驱动与 PyTorch CUDA 版本，或使用 --device cpu")
    processor = AutoImageProcessor.from_pretrained(model_name, local_files_only=offline, use_fast=False)
    model = AutoModel.from_pretrained(model_name, local_files_only=offline, use_safetensors=True).to(device).eval()
    if model.config.model_type != "dinov2":
        raise ValueError("当前特征提取只支持 DINOv2 模型")
    print(f"DINOv2：{model_name}，设备 {device}，批次 {batch_size}", flush=True)
    for start in range(0, len(photos), batch_size):
        batch = photos[start:start + batch_size]
        images = []
        for photo in batch:
            with Image.open(photo["path"]) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((1600, 1600))
                images.append(image)
        inputs = processor(images=images, return_tensors="pt").to(device)
        with torch.inference_mode():
            vectors = model(**inputs).last_hidden_state[:, 0, :]
            vectors = torch.nn.functional.normalize(vectors.float(), dim=1).cpu().numpy()
        if not np.isfinite(vectors).all():
            raise RuntimeError("模型返回了无效特征")
        for photo, vector in zip(batch, vectors):
            photo["embedding"] = vector
        print(f"特征提取 {min(start + batch_size, len(photos))}/{len(photos)}", flush=True)
