"""Validated human/model assessments and face replacement proposals."""

import json
from pathlib import Path


def apply_review(photos, path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("photos"), list):
        raise ValueError("复核文件需要 version: 1 和 photos 数组")
    by_path = {p["path"]: p for p in photos}
    seen = set()
    updates = []
    for entry in data["photos"]:
        if not isinstance(entry, dict) or entry.get("path") not in by_path:
            raise ValueError("复核文件包含未扫描的照片；请使用当前电脑生成的报告")
        if entry["path"] in seen:
            raise ValueError("复核文件中的照片重复")
        seen.add(entry["path"])
        photo = by_path[entry["path"]]
        group = entry.get("group")
        if group is not None and (not isinstance(group, str) or not group.strip() or len(group) > 80):
            raise ValueError("场景编号必须是 1 到 80 字符的字符串")
        selected = entry.get("selected")
        if selected is not None and not isinstance(selected, bool):
            raise ValueError("selected 必须是 true、false 或 null")
        faces = entry.get("faces", [])
        if not isinstance(faces, list):
            raise ValueError("faces 必须是数组")
        face_updates = []
        face_seen = set()
        people_seen = set()
        for face in faces:
            if not isinstance(face, dict):
                raise ValueError("人脸判断必须是对象")
            index = face.get("index")
            if type(index) is not int or not 0 <= index < len(photo["faces"]) or index in face_seen:
                raise ValueError("人脸编号不存在或重复")
            face_seen.add(index)
            person = face.get("person", "")
            eyes = face.get("eyes", "unknown")
            expression = face.get("expression", "unknown")
            if not isinstance(person, str) or len(person) > 80:
                raise ValueError("人物编号必须是最多 80 字符的字符串")
            if eyes not in {"open", "closed", "unknown"} or expression not in {"good", "bad", "unknown"}:
                raise ValueError("眼睛或表情状态无效")
            if person.strip():
                if person.strip() in people_seen:
                    raise ValueError("同一照片中的人物编号不能重复")
                people_seen.add(person.strip())
            face_updates.append((index, {"person": person.strip(), "eyes": eyes, "expression": expression}))
        updates.append((photo, group, selected, face_updates))
    # Validate the whole file before changing any photo.
    for photo, group, selected, faces in updates:
        if group is not None:
            photo["group_override"] = group.strip()
        photo["selected_override"] = selected
        for index, assessment in faces:
            photo["faces"][index].update(assessment)


def regroup(groups):
    result = {}
    for number, group in enumerate(groups, 1):
        for photo in group:
            label = photo.get("group_override", f"scene-{number}")
            result.setdefault(label, []).append(photo)
    return list(result.items())


def face_quality(face):
    import math

    score = min(1.0, math.log1p(face["sharpness"]) / math.log1p(1000))
    if face.get("eyes") == "closed":
        score *= 0.2
    if face.get("expression") == "bad":
        score *= 0.5
    return score


def composite_plans(labeled_groups, selected_by_group):
    plans = []
    for label, group in labeled_groups:
        candidates = [p for p in group if p["path"] in selected_by_group[label] and p["faces"]]
        if not candidates:
            continue
        base = max(candidates, key=lambda p: (len(p["faces"]), min(face_quality(f) for f in p["faces"])))
        replacements = []
        for index, face in enumerate(base["faces"]):
            person = face.get("person")
            if not person:
                continue
            alternatives = [(p, i, f) for p in group for i, f in enumerate(p["faces"])
                            if p["path"] != base["path"] and f.get("person") == person
                            and f.get("eyes") != "closed" and f.get("expression") != "bad"]
            if not alternatives:
                continue
            source, source_index, best = max(alternatives, key=lambda item: face_quality(item[2]))
            if face_quality(best) > face_quality(face) + 0.15:
                replacements.append({"person": person, "target_face": index,
                                     "source": source["path"], "source_face": source_index,
                                     "reason": "同人物的来源人脸评分更高；需要检查姿态、光线与遮挡"})
        if replacements:
            plans.append({"group": label, "base": base["path"], "status": "needs_confirmation",
                          "replacements": replacements})
    return plans
