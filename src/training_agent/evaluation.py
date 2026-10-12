"""Evaluate vision artifacts on a supplied, immutable held-out partition."""
import json
import math
import zipfile
from pathlib import Path

from PIL import Image, ImageStat


def iou(left, right):
    x = max(left[0], right[0]); y = max(left[1], right[1])
    width = max(0, min(left[0] + left[2], right[0] + right[2]) - x)
    height = max(0, min(left[1] + left[3], right[1] + right[3]) - y)
    intersection = width * height
    union = left[2] * left[3] + right[2] * right[3] - intersection
    return intersection / union if union else 0


def evaluate(manifest, directory, report, find_workbench, load_model):
    root = directory / 'evaluation-data'
    with zipfile.ZipFile(directory / 'dataset.zip') as bundle:
        if any(Path(name).is_absolute() or '..' in Path(name).parts for name in bundle.namelist()):
            raise ValueError('Unsafe evaluation archive')
        bundle.extractall(root)
    documents = list((root / 'annotations').glob('*.json'))
    if len(documents) != 1: raise ValueError('Expected one evaluation manifest')
    dataset = json.loads(documents[0].read_text())
    if not dataset['images']: raise ValueError('The held-out partition is empty')
    names = {category['id']: category['name'] for category in dataset['categories']}
    annotations = {}
    for item in dataset.get('annotations', []):
        annotations.setdefault(item['image_id'], []).append({'class_name': names[item['category_id']], 'bbox': item['bbox']})
    task = manifest['annotation_type']; key = manifest['base_model']
    artifact = directory / 'input-model'
    model = None; payload = None
    if key.startswith('workspace:'):
        workbench = find_workbench(key)
        if not workbench or workbench['task'] != task: raise ValueError('Model workbench is unavailable or incompatible')
        model_class = load_model(workbench)
        config = model_class.config_type.model_validate(manifest['config'])
        model = model_class(config.model_copy(update={'devices': ('cpu',), 'output_path': directory}))
        model.load(artifact)
    else:
        payload = json.loads(artifact.read_text())
    tp = fp = fn = exact = flagged_count = 0
    rows = []; failures = []; flagged = []; scores = []
    report(phase='evaluating', message=f"Evaluating {len(dataset['images'])} held-out images")
    for index, record in enumerate(dataset['images'], 1):
        path = (root / record['file_name']).resolve()
        path.relative_to((root / 'images').resolve())
        if model:
            predictions = list(model.predict(path))
        else:
            with Image.open(path) as image:
                rgb = ImageStat.Stat(image.convert('RGB').resize((32, 32))).mean
                width, height = image.size
            if task == 'image_classification':
                distances = {category: math.dist(rgb, centroid) for category, centroid in payload['centroids'].items()}
                best = min(distances, key=distances.get) if distances else None
                predictions = [{'class_name': names[int(best)], 'score': 1 / (1 + distances[best] / 255)}] if best else []
            elif task == 'object_detection':
                predictions = [{'class_name': names[int(category)], 'score': 1.0,
                    'bbox': [box[0] * width, box[1] * height, box[2] * width, box[3] * height]}
                    for category, box in payload['priors'].items()]
            else:
                score = math.dist([value / 255 for value in rgb], payload['centroid'])
                predictions = [{'anomaly_score': score, 'is_anomaly': score > payload['threshold']}]
        # Validate workbench predictions before storing or calculating metrics.
        predictions = json.loads(json.dumps(predictions, allow_nan=False))
        truth = annotations.get(record['id'], []) if task == 'object_detection' else [names[category] for category in record.get('category_ids', [])]
        failed = False
        if task == 'image_classification':
            predicted = {item['class_name'] for item in predictions if item.get('score', 1) >= 0.5}
            expected = set(truth)
            tp += len(predicted & expected); fp += len(predicted - expected); fn += len(expected - predicted)
            exact += predicted == expected; failed = predicted != expected
        elif task == 'object_detection':
            unmatched = list(truth); sample_fp = 0
            for prediction in sorted(predictions, key=lambda item: item.get('score', 1), reverse=True):
                if prediction.get('score', 1) < 0.5: continue
                candidates = [(iou(prediction['bbox'], item['bbox']), position) for position, item in enumerate(unmatched)
                              if item['class_name'] == prediction['class_name']]
                overlap, position = max(candidates, default=(0, -1))
                if overlap >= 0.5: tp += 1; unmatched.pop(position)
                else: fp += 1; sample_fp += 1
            fn += len(unmatched); failed = bool(unmatched or sample_fp)
        else:
            score = float(predictions[0]['anomaly_score'])
            if not math.isfinite(score): raise ValueError('Anomaly score is not finite')
            scores.append(score)
            flagged_count += bool(predictions[0].get("is_anomaly"))
        row = {'image_id': record.get('studio_image_id'), 'source_path': record.get('source_path', record['file_name']),
               'width': record['width'], 'height': record['height'], 'predictions': predictions,
               'ground_truth': truth, 'failed': failed}
        if len(rows) < 100: rows.append(row)
        if failed and len(failures) < 50: failures.append(row)
        if task == 'anomaly_detection' and predictions[0].get('is_anomaly') and len(flagged) < 50: flagged.append(row)
        report(phase='evaluating', step=index, total_steps=len(dataset['images']))
    metrics = {'evaluated_samples': len(dataset['images'])}
    if task == 'anomaly_detection':
        metrics.update(mean_anomaly_score=sum(scores) / len(scores), max_anomaly_score=max(scores))
        metrics["flagged_fraction"] = flagged_count / len(scores)
    else:
        precision = tp / (tp + fp) if tp + fp else 0
        recall = tp / (tp + fn) if tp + fn else 0
        metrics.update(precision=precision, recall=recall, f1=2 * precision * recall / (precision + recall) if precision + recall else 0,
                       true_positives=tp, false_positives=fp, false_negatives=fn)
        if task == 'image_classification': metrics['exact_match_accuracy'] = exact / len(dataset['images'])
    return {'metrics': metrics, 'predictions': rows, 'failure_examples': failures, 'flagged_examples': flagged,
            'sample_count': len(dataset['images']), 'display_limit': 100, 'task': task,
            'metric_policy': {'image_classification': 'Multi-label exact match and micro precision/recall/F1 at score ≥ 0.5.',
                'object_detection': 'Class-matched precision/recall/F1 at score ≥ 0.5 and IoU ≥ 0.5; greedy matching, not mAP.',
                'anomaly_detection': 'Unlabelled anomaly scores and model-supplied flags; no ground-truth accuracy.'}[task]}
