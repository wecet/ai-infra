"""Seeded previews using the selected workbench's actual training augmentor."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import threading

from fastapi import HTTPException
from PIL import Image

_lock = threading.Lock()


def preview(manifest, image_file, find_workbench, load_model):
    import torch
    from torchvision.transforms.functional import pil_to_tensor, to_pil_image
    workbench = find_workbench(manifest['base_model'])
    if not workbench: raise HTTPException(422, 'Preview requires an installed workbench')
    model = load_model(workbench)
    source = Path(workbench['path']) / 'augmentor.py'
    if not source.is_file(): raise HTTPException(422, 'Workbench does not expose augmentor.py:Augmentor')
    spec = importlib.util.spec_from_file_location('preview_augmentor', source)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    config = model.config_type.model_validate(manifest['config'])
    with Image.open(image_file) as original:
        image = original.convert('RGB')
        if workbench['task'] == 'image_classification': image = image.resize((config.image_size, config.image_size))
        tensor = pil_to_tensor(image).float() / 255
    boxes = manifest.get('boxes', [])
    target = {'boxes': torch.tensor([[b['x'], b['y'], b['x'] + b['width'], b['y'] + b['height']] for b in boxes], dtype=torch.float32).reshape(-1, 4),
              'labels': torch.tensor([b['category_id'] for b in boxes], dtype=torch.int64)} if workbench['task'] == 'object_detection' else torch.zeros(len(config.class_names))
    # Preserve RNG state; do not perturb concurrent training in this process.
    with _lock, torch.random.fork_rng(devices=[]):
        torch.manual_seed(manifest.get('seed', 42))
        transformed, target = module.Augmentor(config)(tensor, target)
    def encode(value):
        buffer = io.BytesIO(); value.save(buffer, 'PNG')
        return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()
    transformed_boxes = []
    if isinstance(target, dict):
        for bbox, category in zip(target['boxes'].tolist(), target['labels'].tolist()):
            transformed_boxes.append(dict(x=bbox[0], y=bbox[1], width=bbox[2]-bbox[0], height=bbox[3]-bbox[1], category_id=category))
    return {'before': encode(image), 'after': encode(to_pil_image(transformed)), 'boxes': transformed_boxes, 'seed': manifest.get('seed', 42), 'width': image.width, 'height': image.height}
