from fastapi import HTTPException

def _validate_import_document(document, filename):
    if not isinstance(document, dict):
        raise HTTPException(422, f'{filename}: annotation JSON must be an object')
    images, categories, annotations = (document.get('images'), document.get('categories'),
                                       document.get('annotations', []))
    info = document.get('info', {})
    if not isinstance(info, dict):
        raise HTTPException(422, f'{filename}: info must be an object')
    anomaly = info.get('annotation_type') == 'anomaly_detection'
    if anomaly and (categories or annotations or any(item.get('category_ids') for item in images or [] if isinstance(item, dict))):
        raise HTTPException(422, f'{filename}: anomaly datasets must be unlabelled')
    if not isinstance(images, list) or not isinstance(categories, list) or (not categories and not anomaly):
        raise HTTPException(422, f'{filename}: images and a non-empty categories list are required')
    if not isinstance(annotations, list):
        raise HTTPException(422, f'{filename}: annotations must be a list')
    category_ids = {item.get('id') for item in categories if isinstance(item, dict)}
    if len(category_ids) != len(categories) or None in category_ids:
        raise HTTPException(422, f'{filename}: every category needs a unique id')
    image_ids = set()
    for item in images:
        if not isinstance(item, dict) or item.get('id') is None or not isinstance(item.get('file_name'), str):
            raise HTTPException(422, f'{filename}: every image needs an id and file_name')
        if item['id'] in image_ids:
            raise HTTPException(422, f'{filename}: image ids must be unique')
        image_ids.add(item['id'])
    has_boxes = False
    for item in annotations:
        if not isinstance(item, dict) or item.get('image_id') not in image_ids:
            raise HTTPException(422, f'{filename}: annotation refers to an unknown image')
        if item.get('category_id') not in category_ids:
            raise HTTPException(422, f'{filename}: annotation refers to an unknown category')
        bbox = item.get('bbox')
        if not isinstance(bbox, list) or len(bbox) != 4 or any(
                not isinstance(value, (int, float)) or isinstance(value, bool) for value in bbox):
            raise HTTPException(422, f'{filename}: every annotation must contain a numeric four-value bbox')
        if bbox[0] < 0 or bbox[1] < 0 or bbox[2] <= 0 or bbox[3] <= 0:
            raise HTTPException(422, f'{filename}: bounding boxes must have a non-negative origin and positive size')
        has_boxes = True
    if not has_boxes:
        for item in images:
            labels = item.get('category_ids', [])
            if not isinstance(labels, list) or any(label not in category_ids for label in labels):
                raise HTTPException(422, f'{filename}: category_ids must be a list of known category ids')
    return 'anomaly_detection' if anomaly else ('object_detection' if has_boxes else 'image_classification')

