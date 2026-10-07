"""Auditable comparison of two immutable dataset versions."""
import math
import random
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from PIL import Image

from common import DATA, hamming, perceptual_hash
from routes.versions import version_detail

router = APIRouter()


def _split(snapshot):
    images = sorted(snapshot["images"], key=lambda item: item["id"])
    random.Random(42).shuffle(images)
    cut = math.floor(len(images) * snapshot["project"].get("export_train_percent", 80) / 100 + .5)
    return {item["source_path"]: "train" if index < cut else "test" for index, item in enumerate(images)}


def _hashes(project_id, version_id, snapshot):
    values = {}
    for item in snapshot["images"]:
        value = item.get("perceptual_hash")
        if not value:
            path = DATA / "versions" / project_id / version_id / item["stored_name"]
            if path.is_file():
                with Image.open(path) as source: value = perceptual_hash(source)
        if value: values[item["source_path"]] = value
    return values


def _duplicate_metrics(project_id, version_id, snapshot, split):
    hashes = _hashes(project_id, version_id, snapshot)
    paths = sorted(hashes); parent = list(range(len(paths)))
    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]; item = parent[item]
        return item
    def union(left, right):
        left, right = find(left), find(right)
        if left != right: parent[right] = left
    approximate = len(paths) > 1000
    if not approximate:
        for left in range(len(paths)):
            for right in range(left + 1, len(paths)):
                if hamming(hashes[paths[left]], hashes[paths[right]]) <= 6: union(left, right)
    else:
        exact = defaultdict(list)
        for index, path in enumerate(paths): exact[hashes[path]].append(index)
        for indexes in exact.values():
            for index in indexes[1:]: union(indexes[0], index)
    groups = defaultdict(list)
    for index, path in enumerate(paths): groups[find(index)].append(path)
    groups = [items for items in groups.values() if len(items) > 1]
    leakage = sum(len({split[path] for path in group if path in split}) > 1 for group in groups)
    return {"groups": len(groups), "images": sum(map(len, groups)), "cross_split_groups": leakage,
            "approximate": approximate}


def _quality(snapshot, duplicate):
    classes = snapshot["project"]["classes"]; counts = {item["id"]: 0 for item in classes}
    missing = small = invalid = 0
    review = defaultdict(int)
    for image in snapshot["images"]:
        review[image.get("review_status", "draft")] += 1
        boxes, labels = image.get("boxes", []), image.get("labels", [])
        if image.get("completed") and not boxes and not labels: missing += 1
        for category in labels: counts[category] = counts.get(category, 0) + 1
        for box in boxes:
            counts[box["category_id"]] = counts.get(box["category_id"], 0) + 1
            if box["width"] * box["height"] < image["width"] * image["height"] * .001: small += 1
            if (box["x"] < 0 or box["y"] < 0 or box["width"] <= 0 or box["height"] <= 0 or
                    box["x"] + box["width"] > image["width"] + .001 or
                    box["y"] + box["height"] > image["height"] + .001): invalid += 1
    represented = [value for value in counts.values() if value]
    return {"samples": len(snapshot["images"]), "annotations": sum(counts.values()),
            "missing_annotations": missing, "small_boxes": small, "invalid_boxes": invalid,
            "empty_classes": sum(not counts.get(item["id"]) for item in classes),
            "class_imbalance": int(len(represented) > 1 and max(represented) > min(represented) * 5),
            "duplicate_groups": duplicate["groups"], "duplicate_images": duplicate["images"],
            "cross_split_groups": duplicate["cross_split_groups"],
            "approved": review["approved"], "rejected": review["rejected"],
            "ready_for_review": review["ready_for_review"]}


@router.get("/api/projects/{project_id}/versions/compare")
def compare_versions(project_id: str, left_id: str, right_id: str):
    if left_id == right_id: raise HTTPException(422, "Choose two different versions")
    left, right = version_detail(project_id, left_id), version_detail(project_id, right_id)
    left_snapshot, right_snapshot = left["snapshot"], right["snapshot"]
    left_images = {item["source_path"]: item for item in left_snapshot["images"]}
    right_images = {item["source_path"]: item for item in right_snapshot["images"]}
    left_split, right_split = _split(left_snapshot), _split(right_snapshot)
    left_duplicates = _duplicate_metrics(project_id, left_id, left_snapshot, left_split)
    right_duplicates = _duplicate_metrics(project_id, right_id, right_snapshot, right_split)
    changes = []
    for path in sorted(left_images.keys() & right_images.keys()):
        before, after = left_images[path], right_images[path]
        annotation_changed = before.get("boxes", []) != after.get("boxes", []) or before.get("labels", []) != after.get("labels", [])
        review_changed = before.get("review_status", "draft") != after.get("review_status", "draft")
        split_changed = left_split[path] != right_split[path]
        if annotation_changed or review_changed or split_changed:
            changes.append({"source_path": path, "left_image_id": before["id"], "right_image_id": after["id"],
                "annotation_changed": annotation_changed, "review_changed": review_changed,
                "split_changed": split_changed, "left_review": before.get("review_status", "draft"),
                "right_review": after.get("review_status", "draft"), "left_split": left_split[path],
                "right_split": right_split[path], "left_boxes": before.get("boxes", []),
                "right_boxes": after.get("boxes", []), "left_labels": before.get("labels", []),
                "right_labels": after.get("labels", []), "width": after["width"], "height": after["height"]})
    def classes(snapshot): return {item["id"]: item for item in snapshot["project"]["classes"]}
    left_classes, right_classes = classes(left_snapshot), classes(right_snapshot)
    class_changes = {"added": [right_classes[key] for key in right_classes.keys() - left_classes.keys()],
                     "removed": [left_classes[key] for key in left_classes.keys() - right_classes.keys()],
                     "changed": [{"before": left_classes[key], "after": right_classes[key]} for key in left_classes.keys() & right_classes.keys()
                                 if left_classes[key] != right_classes[key]]}
    left_quality, right_quality = _quality(left_snapshot, left_duplicates), _quality(right_snapshot, right_duplicates)
    return {"left": {key: left[key] for key in ("id", "name", "sample_count", "created_at")},
            "right": {key: right[key] for key in ("id", "name", "sample_count", "created_at")},
            "images": {"added": sorted(right_images.keys() - left_images.keys()),
                       "removed": sorted(left_images.keys() - right_images.keys()), "changed": changes},
            "classes": class_changes | {"left_catalog": list(left_classes.values()),
                                        "right_catalog": list(right_classes.values())},
            "quality": {"left": left_quality, "right": right_quality,
                        "delta": {key: right_quality[key] - left_quality[key] for key in left_quality}},
            "summary": {"added": len(right_images.keys() - left_images.keys()),
                        "removed": len(left_images.keys() - right_images.keys()),
                        "annotation_changes": sum(item["annotation_changed"] for item in changes),
                        "review_changes": sum(item["review_changed"] for item in changes),
                        "split_changes": sum(item["split_changed"] for item in changes)}}
