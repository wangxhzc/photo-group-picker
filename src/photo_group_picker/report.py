"""Portable report, editable review data, and local AI inspection assets."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .review import composite_plans, regroup


def write_report(groups, errors, output, top):
    from .cli import quality, select

    output.mkdir(parents=True, exist_ok=True)
    for directory in ("thumbnails", "faces", "sheets"):
        (output / directory).mkdir(exist_ok=True)
    labeled = regroup(groups)
    selected = {label: select(group, top) for label, group in labeled}
    records, tasks = [], []
    index = 0
    for group_index, (label, group) in enumerate(labeled, 1):
        sheet = Image.new("RGB", (800, 240 * ((len(group) + 3) // 4)), "white")
        draw = ImageDraw.Draw(sheet)
        task_photos = []
        for offset, photo in enumerate(group):
            index += 1
            thumb = f"thumbnails/{index:05d}.jpg"
            with Image.open(photo["path"]) as original:
                image = ImageOps.exif_transpose(original).convert("RGB")
                thumbnail = image.copy()
                thumbnail.thumbnail((600, 450))
                thumbnail.save(output / thumb, quality=85)
                tile = ImageOps.contain(thumbnail, (200, 200))
                x, y = offset % 4 * 200, offset // 4 * 240
                sheet.paste(tile, (x + (200 - tile.width) // 2, y))
                draw.text((x + 8, y + 205), f"Photo {index}", fill="black")
                faces = []
                analyzed_w, analyzed_h = photo.get("analyzed_size", image.size)
                for face_index, face in enumerate(photo["faces"]):
                    bx, by, bw, bh = face["box"]
                    sx, sy = image.width / analyzed_w, image.height / analyzed_h
                    bounds = (max(0, int((bx - bw * .2) * sx)), max(0, int((by - bh * .2) * sy)),
                              min(image.width, int((bx + bw * 1.2) * sx)), min(image.height, int((by + bh * 1.2) * sy)))
                    crop = image.crop(bounds)
                    crop.thumbnail((256, 256))
                    crop_path = f"faces/{index:05d}-{face_index}.jpg"
                    crop.save(output / crop_path, quality=92)
                    faces.append(dict(face, index=face_index, crop=crop_path,
                                      person=face.get("person", ""), eyes=face.get("eyes", "unknown"),
                                      expression=face.get("expression", "unknown")))
            record = {k: v for k, v in photo.items() if k not in {"hash", "histogram", "embedding", "faces"}}
            record.update(id=index, group=label, faces=faces, thumbnail=thumb,
                          original_uri=Path(photo["path"]).resolve().as_uri(),
                          score=round(quality(photo), 4), recommended=photo["path"] in selected[label])
            records.append(record)
            task_photos.append({"id": index, "path": photo["path"], "thumbnail": thumb, "faces": faces})
        sheet_path = f"sheets/{group_index:04d}.jpg"
        sheet.save(output / sheet_path, quality=90)
        tasks.append({"group": label, "contact_sheet": sheet_path, "photos": task_photos})
    plans = composite_plans(labeled, selected)
    data = {"version": 1, "photos": records, "errors": errors, "composite_plans": plans}
    template = Path(__file__).with_name("report.html").read_text(encoding="utf-8")
    # Escape HTML-significant characters to keep filenames out of script syntax.
    payload = json.dumps(data, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    (output / "index.html").write_text(template.replace("__PHOTO_DATA__", payload), encoding="utf-8")
    (output / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    review = {"version": 1, "photos": [{"path": p["path"], "group": p["group"],
              "selected": p.get("selected_override"), "faces": [{k: f[k] for k in
              ("index", "person", "eyes", "expression")} for f in p["faces"]]} for p in records]}
    (output / "review-template.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "ai-tasks.json").write_text(json.dumps({"version": 1, "groups": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "composite-plans.json").write_text(json.dumps(plans, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "AI_REVIEW.md").write_text(
        "# 照片复核任务\n\n"
        "读取 ai-tasks.json，查看每组 sheets/ 联系表、thumbnails/ 和 faces/ 人脸裁剪。"
        "先检查分组是否正确，再比较人物表现。保持 review-template.json 的 version、path 和人脸 index 不变，"
        "另存为 review.json。group 相同表示同组；selected 为 true/false/null（选中/排除/自动）。"
        "person 是同组内同一人物的稳定编号；无法确认身份时留空。eyes 使用 open/closed/unknown，"
        "expression 使用 good/bad/unknown；看不清就使用 unknown，不猜测。"
        "不要根据左右位置假定是同一个人。不要修改 box 或 sharpness。"
        "图片保留在本地；调用远程视觉服务前需要用户授权。\n",
        encoding="utf-8")
