"""Deterministic partition contract; old snapshots remain readable."""
import math
import random


def partition(snapshot):
    images = sorted(snapshot['images'], key=lambda image: (image['source_path'], image['id']))
    if images and all(image.get('split') in {'train', 'validation', 'test'} for image in images):
        return {split: [image['id'] for image in images if image['split'] == split] for split in ('train', 'validation', 'test')}
    random.Random(42).shuffle(images)
    cut = math.floor(len(images) * snapshot['project'].get('export_train_percent', 80) / 100 + .5)
    return {'train': [image['id'] for image in images[:cut]], 'validation': [], 'test': [image['id'] for image in images[cut:]], 'seed': 42}


def freeze(snapshot):
    selected = partition(snapshot)
    if snapshot['project']['annotation_type'] != 'anomaly_detection':
        fitting = selected['train']
        count = max(1, len(fitting) // 5) if len(fitting) >= 3 else 0
        selected['validation'] = fitting[:count]
        selected['train'] = fitting[count:]
    by_id = {image_id: split for split in ('train', 'validation', 'test') for image_id in selected[split]}
    for image in snapshot['images']: image['split'] = by_id[image['id']]
    snapshot.update(schema_version=2, split_seed=42)
