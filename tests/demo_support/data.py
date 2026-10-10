"""Read immutable Studio ZIPs without extracting untrusted archive paths."""
import io
import json
from pathlib import PurePosixPath
from zipfile import ZipFile

import torch
from PIL import Image
from torch.utils.data import Dataset
from torchvision.transforms.functional import pil_to_tensor


def image_tensor(image, size=None):
    image = image.convert("RGB")
    if size is not None:
        image = image.resize((size, size))
    return pil_to_tensor(image).float() / 255


class StudioDataset(Dataset):
    def __init__(self, archive, config, task, augmentor=None):
        self.archive, self.config, self.task = archive, config, task
        self.augmentor = augmentor
        with ZipFile(archive) as bundle:
            documents = [name for name in bundle.namelist() if name.startswith("annotations/") and name.endswith(".json")]
            if len(documents) != 1:
                raise ValueError("Expected exactly one annotations/*.json document")
            coco = json.loads(bundle.read(documents[0]))
        by_name = {name: index for index, name in enumerate(config.class_names)}
        self.categories = {item["id"]: by_name[item["name"]] for item in coco["categories"]}
        if len(self.categories) != len(by_name) or len(by_name) != len(config.class_names):
            raise ValueError("Dataset categories must match unique config.class_names")
        self.records = coco["images"]
        if not self.records:
            raise ValueError("Dataset is empty")
        self.annotations = {}
        for annotation in coco.get("annotations", []):
            self.annotations.setdefault(annotation["image_id"], []).append(annotation)

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        record = self.records[index]
        name = record["file_name"]
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not name.startswith("images/"):
            raise ValueError("Image paths must be beneath images/")
        with ZipFile(self.archive) as bundle, Image.open(io.BytesIO(bundle.read(name))) as image:
            width, height = image.size
            tensor = image_tensor(image, self.config.image_size if self.task == "image_classification" else None)
        if self.task == "image_classification":
            target = torch.zeros(len(self.config.class_names))
            for category in record.get("category_ids", []):
                target[self.categories[category]] = 1
            return self.augmentor(tensor, target) if self.augmentor else (tensor, target)
        boxes, labels = [], []
        for annotation in self.annotations.get(record["id"], []):
            x, y, w, h = annotation["bbox"]
            if not (0 <= x < x + w <= width and 0 <= y < y + h <= height):
                raise ValueError("Bounding boxes must have positive area and lie within the image")
            boxes.append([x, y, x + w, y + h])
            labels.append(self.categories[annotation["category_id"]] + 1)
        target = {"boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
                  "labels": torch.tensor(labels, dtype=torch.int64)}
        return self.augmentor(tensor, target) if self.augmentor else (tensor, target)


def collate(batch):
    return tuple(zip(*batch))
