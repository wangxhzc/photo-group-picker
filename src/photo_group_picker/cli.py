import argparse
import calendar
import math
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from .report import write_report
from .review import apply_review, face_quality, regroup

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}


def analyze(path, detector):
    with Image.open(path) as original:
        exif = original.getexif()
        exif_ifd = exif.get_ifd(0x8769)
        timestamp = exif_ifd.get(36867) or exif.get(306)
        try:
            timestamp = calendar.timegm(datetime.strptime(str(timestamp), "%Y:%m:%d %H:%M:%S").timetuple())
        except (ValueError, TypeError):
            timestamp = None
        width, height = original.size
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((1600, 1600))
        rgb = np.array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(gray, (32, 32)).astype(np.float32)
    dct = cv2.dct(small)[:8, :8].flatten()[1:]
    fingerprint = dct > np.median(dct)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256])
    cv2.normalize(histogram, histogram)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    clipped = float(np.mean((gray < 8) | (gray > 247)))
    exposure = max(0.0, 1 - abs(float(gray.mean()) - 127.5) / 127.5 - clipped)
    faces = []
    for x, y, w, h in detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(32, 32)):
        crop = gray[y:y + h, x:x + w]
        # Standardize crop size so face sharpness is less dependent on face size.
        crop = cv2.resize(crop, (96, 96))
        faces.append({"box": [int(x), int(y), int(w), int(h)],
                      "sharpness": float(cv2.Laplacian(crop, cv2.CV_64F).var())})
    faces.sort(key=lambda f: (f["box"][0], f["box"][1]))
    return {"path": str(path.resolve()), "timestamp": timestamp,
            "width": width, "height": height, "sharpness": sharpness,
            "exposure": exposure, "faces": faces, "analyzed_size": list(image.size),
            "hash": fingerprint, "histogram": histogram}


def similarity(a, b):
    if "embedding" in a and "embedding" in b:
        return float(np.clip(np.dot(a["embedding"], b["embedding"]), -1, 1))
    hash_score = 1 - float(np.mean(a["hash"] != b["hash"]))
    color_score = max(0.0, float(cv2.compareHist(a["histogram"], b["histogram"], cv2.HISTCMP_CORREL)))
    return 0.6 * hash_score + 0.4 * color_score


def group_photos(photos, threshold, gap):
    groups = []
    for photo in photos:
        if not groups:
            groups.append([photo])
            continue
        previous = groups[-1][-1]
        timed = photo["timestamp"] is not None and previous["timestamp"] is not None
        time_ok = not timed or abs(photo["timestamp"] - previous["timestamp"]) <= gap
        # Check the first image too to limit drift through a sequence of scenes.
        visual_ok = (similarity(photo, previous) >= threshold
                     and similarity(photo, groups[-1][0]) >= threshold - 0.08)
        if time_ok and visual_ok:
            groups[-1].append(photo)
        else:
            groups.append([photo])
    return groups


def quality(photo):
    sharp = min(1.0, math.log1p(photo["sharpness"]) / math.log1p(1000))
    overall = 0.75 * sharp + 0.25 * photo["exposure"]
    if photo["faces"]:
        face_score = min(face_quality(f) for f in photo["faces"])
        return 0.55 * overall + 0.45 * face_score
    return overall


def select(group, top):
    chosen = {p["path"] for p in group if p.get("selected_override") is True}
    for portrait in (False, True):
        candidates = [p for p in group if bool(p["faces"]) == portrait
                      and p.get("selected_override") is None]
        explicit = sum(p.get("selected_override") is True for p in group if bool(p["faces"]) == portrait)
        if portrait and candidates:
            # Prefer full group shots over photos where some faces were not detected.
            count = max(len(p["faces"]) for p in candidates)
            candidates = [p for p in candidates if len(p["faces"]) == count]
        def rank(photo):
            closed = sum(f.get("eyes") == "closed" for f in photo["faces"])
            bad = sum(f.get("expression") == "bad" for f in photo["faces"])
            return -closed, -bad, quality(photo)

        chosen.update(p["path"] for p in sorted(candidates, key=rank, reverse=True)[:max(0, top - explicit)])
    return chosen


def main():
    parser = argparse.ArgumentParser(description="本地照片分组与候选筛选（不修改原图）")
    parser.add_argument("input", type=Path, help="照片目录，递归扫描")
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--threshold", type=float, help="相似度阈值，基础版默认 0.72，DINOv2 默认 0.85")
    parser.add_argument("--gap", type=float, default=180, help="同场景最大拍摄间隔（秒）")
    parser.add_argument("--top", type=int, default=2, help="每组每类推荐数量")
    parser.add_argument("--review", type=Path, help="导入人工或 AI 复核 JSON")
    parser.add_argument("--backend", choices=["basic", "dinov2"], default="basic")
    parser.add_argument("--model", default="facebook/dinov2-small", help="模型名称或本地模型目录")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--offline", action="store_true", help="只使用本地模型，不访问模型仓库")
    args = parser.parse_args()
    if args.threshold is None:
        args.threshold = 0.85 if args.backend == "dinov2" else 0.72
    if not args.input.is_dir():
        parser.error("输入必须是存在的目录")
    if not 0 <= args.threshold <= 1 or not math.isfinite(args.gap) or args.gap < 0 or args.top < 1 or args.batch_size < 1:
        parser.error("threshold 必须在 0 到 1 之间，gap 非负，top 至少为 1")
    source, output = args.input.resolve(), args.output.resolve()
    if source == output or source.is_relative_to(output):
        parser.error("输出目录不能是输入目录或其父目录")
    files = sorted(p for p in source.rglob("*") if p.is_file()
                   and p.suffix.lower() in EXTENSIONS and not p.is_relative_to(output))
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if detector.empty():
        parser.error("无法加载 OpenCV 人脸检测器")
    photos, errors = [], []
    for index, path in enumerate(files, 1):
        print(f"[{index}/{len(files)}] {path.name}", flush=True)
        try:
            photos.append(analyze(path, detector))
        except (OSError, ValueError, cv2.error) as error:
            errors.append({"path": str(path), "error": str(error)})
    if not photos:
        parser.error(f"没有可处理的照片（{len(errors)} 个文件读取失败）")
    # Only sort by capture time when all photos supply it; otherwise preserve filename order.
    if all(p["timestamp"] is not None for p in photos):
        photos.sort(key=lambda p: (p["timestamp"], p["path"]))
    if args.backend == "dinov2":
        from .embeddings import add_embeddings

        try:
            add_embeddings(photos, args.model, args.device, args.batch_size, args.offline)
        except (ImportError, RuntimeError, OSError, ValueError) as error:
            parser.error(f"DINOv2 分组失败：{error}")
    if args.review:
        try:
            apply_review(photos, args.review)
        except (OSError, ValueError, TypeError) as error:
            parser.error(f"复核文件无效：{error}")
    groups = group_photos(photos, args.threshold, args.gap)
    write_report(groups, errors, output, args.top)
    print(f"完成：{len(photos)} 张照片，{len(regroup(groups))} 组，{len(errors)} 个失败文件")
    print(f"报告：{output / 'index.html'}")


if __name__ == "__main__":
    main()
