from fastapi import APIRouter
from common import *
from common import _safe_zip_members
from routes.images import upload_image, create_batch, save_annotations

router = APIRouter()

def _match_image(rows, filename):
    normalized = filename.replace('\\', '/').lstrip('./')
    candidates = [normalized]
    for prefix in ('train/images/', 'test/images/', 'valid/images/', 'images/'):
        if normalized.startswith(prefix):
            candidates.append(normalized[len(prefix):])
    exact = [row for row in rows if row['source_path'] in candidates or row['stored_name'] in candidates]
    if len(exact) == 1:
        return exact[0]
    basename = PurePosixPath(normalized).name
    matches = [row for row in rows if PurePosixPath(row['source_path']).name == basename]
    if len(matches) == 1:
        return matches[0]
    suffix_matches = [row for row in rows if row['source_path'].endswith(f'/{normalized}')]
    return suffix_matches[0] if len(suffix_matches) == 1 else None


@router.post('/api/projects/{project_id}/annotations/import')
def import_annotations(project_id: str, file: UploadFile = File(...)):
    raw = file.file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(413, 'Annotation import must be at most 50 MiB')
    archive = None
    documents = []
    yolo_files = []
    images_imported = 0
    try:
        if (file.filename or '').lower().endswith('.json'):
            documents = [(file.filename or 'annotations.json', json.loads(raw))]
        else:
            archive = zipfile.ZipFile(io.BytesIO(raw))
            members = _safe_zip_members(archive)
            documents = [(item.filename, json.loads(archive.read(item))) for item in members
                         if item.filename.lower().endswith('.json')]
            yolo_files = [item.filename for item in members if item.filename.lower().endswith('.txt')
                          and PurePosixPath(item.filename).name.lower() not in {'classes.txt', 'obj.names'}]
            image_members = [item for item in members
                             if PurePosixPath(item.filename).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff'}]
            if image_members:
                with database() as db:
                    get_project(db, project_id)
                    existing_ids = {row['id'] for row in db.execute('SELECT id FROM images WHERE project_id=?', (project_id,))}
                    first_batch = db.execute('SELECT id FROM import_batches WHERE project_id=? ORDER BY rowid LIMIT 1',
                                             (project_id,)).fetchone()['id']
                batch_id = first_batch if not existing_ids else create_batch(project_id, BatchCreate())['id']
                for item in image_members:
                    uploaded = upload_image(project_id, UploadFile(filename=item.filename,
                                            file=io.BytesIO(archive.read(item))), batch_id)
                    if uploaded['id'] not in existing_ids:
                        images_imported += 1
                        existing_ids.add(uploaded['id'])
    except HTTPException:
        raise
    except (json.JSONDecodeError, zipfile.BadZipFile, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f'Invalid COCO JSON or YOLO ZIP: {exc}') from exc
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=?', (project_id,)).fetchall()
        by_id = {row['id']: row for row in rows}
        updates = {}
        unmatched = []
        try:
            for document_name, document in documents:
                if not isinstance(document, dict) or 'images' not in document:
                    continue
                category_names = {c['id']: c.get('name', '') for c in document.get('categories', [])}
                target_by_name = {c['name'].casefold(): c['id'] for c in project['classes']}
                category_map = {source: target_by_name.get(name.casefold()) for source, name in category_names.items()}
                annotations = {}
                for item in document.get('annotations', []):
                    annotations.setdefault(item.get('image_id'), []).append(item)
                for source_image in document['images']:
                    source_filename = source_image.get('file_name', '')
                    row = _match_image(rows, source_filename)
                    if row is None:
                        row = _match_image(rows, str(PurePosixPath(document_name).parent / source_filename))
                    if row is None:
                        unmatched.append(source_image.get('file_name', 'unknown'))
                        continue
                    labels = []
                    boxes = []
                    if project['annotation_type'] == 'image_classification':
                        source_labels = source_image.get('category_ids', [])
                        labels = [category_map.get(item, item if item in {c['id'] for c in project['classes']} else None)
                                  for item in source_labels]
                        if any(item is None for item in labels):
                            raise HTTPException(422, 'One or more imported classes do not exist in this project')
                    else:
                        for item in annotations.get(source_image.get('id'), []):
                            target_id = category_map.get(item.get('category_id'))
                            bbox = item.get('bbox', [])
                            if target_id is None:
                                source_name = category_names.get(item.get('category_id'), item.get('category_id'))
                                raise HTTPException(422, f'Imported class {source_name!r} does not exist in this project')
                            if target_id and len(bbox) == 4:
                                boxes.append({'category_id': target_id, 'x': bbox[0], 'y': bbox[1],
                                              'width': bbox[2], 'height': bbox[3]})
                    updates[row['id']] = (boxes, labels)
            if not documents and yolo_files:
                if project['annotation_type'] != 'object_detection':
                    raise HTTPException(422, 'YOLO imports are supported for object detection projects')
                for name in yolo_files:
                    image_name = str(PurePosixPath(name).with_suffix(''))
                    image_name = re.sub(r'(^|/)(labels)(/)', r'\1images\3', image_name) + '.png'
                    row = _match_image(rows, image_name)
                    if row is None:
                        stem = PurePosixPath(name).stem
                        matches = [item for item in rows if PurePosixPath(item['source_path']).stem == stem]
                        row = matches[0] if len(matches) == 1 else None
                    if row is None:
                        unmatched.append(name)
                        continue
                    boxes = []
                    for line in archive.read(name).decode('utf-8-sig').splitlines():
                        if not line.strip():
                            continue
                        parts = line.split()
                        if len(parts) != 5:
                            raise HTTPException(422, f'Invalid YOLO annotation in {name}')
                        class_index, cx, cy, width, height = map(float, parts)
                        category_id = int(class_index) + 1
                        width *= row['width']; height *= row['height']
                        boxes.append({'category_id': category_id,
                                      'x': cx * row['width'] - width / 2,
                                      'y': cy * row['height'] - height / 2,
                                      'width': width, 'height': height})
                    updates[row['id']] = (boxes, [])
        except (json.JSONDecodeError, zipfile.BadZipFile, UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, f'Invalid COCO JSON or YOLO ZIP: {exc}') from exc
        if not updates:
            raise HTTPException(422, 'No annotations matched images in this project')
        validated = []
        valid_categories = {item['id'] for item in project['classes']}
        for image_id, (boxes, labels) in updates.items():
            row = by_id[image_id]
            try:
                payload = AnnotationSave(boxes=boxes, labels=labels, completed=True, revision=row['revision'])
            except ValidationError as exc:
                raise HTTPException(422, f'Imported annotation is invalid for {row["source_path"]}') from exc
            if any(box.category_id not in valid_categories or
                   box.x + box.width > row['width'] + 0.001 or
                   box.y + box.height > row['height'] + 0.001 for box in payload.boxes):
                raise HTTPException(422, f'Imported annotation is outside {row["source_path"]}')
            validated.append((image_id, payload))
        for image_id, payload in validated:
            # Validate through the ordinary save route while retaining optimistic revisions.
            save_annotations(project_id, image_id, payload)
        return {'updated': len(updates), 'images_imported': images_imported,
                'unmatched': sorted(set(unmatched))[:100]}


@router.get('/api/projects/{project_id}/duplicates')
def duplicate_groups(project_id: str):
    with database() as db:
        get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY source_path,id', (project_id,)).fetchall()
        for row in rows:
            if not row['perceptual_hash']:
                path = DATA / 'images' / project_id / row['stored_name']
                with Image.open(path) as source:
                    value = perceptual_hash(source)
                db.execute('UPDATE images SET perceptual_hash=? WHERE id=?', (value, row['id']))
        rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY source_path,id', (project_id,)).fetchall()
    parent = list(range(len(rows)))
    def find(item):
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item
    def union(left, right):
        left, right = find(left), find(right)
        if left != right:
            parent[right] = left
    distances = {}
    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            distance = hamming(rows[left]['perceptual_hash'], rows[right]['perceptual_hash'])
            if distance <= 6:
                union(left, right)
                distances[(left, right)] = distance
    grouped = {}
    for index, row in enumerate(rows):
        grouped.setdefault(find(index), []).append((index, row))
    result = []
    for items in grouped.values():
        if len(items) < 2:
            continue
        indexes = {index for index, _ in items}
        group_distances = [value for (left, right), value in distances.items()
                           if left in indexes and right in indexes]
        result.append({'id': items[0][1]['id'], 'closest_distance': min(group_distances or [0]),
                       'images': [{k: row[k] for k in ('id', 'source_path', 'width', 'height')} |
                                  {'completed': bool(row['completed'])} for _, row in items]})
    return {'groups': result, 'similar_images': sum(len(group['images']) for group in result)}


@router.get('/api/projects/{project_id}/stats')
def stats(project_id: str):
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT completed,boxes,labels,review_status FROM images WHERE project_id=?',
                          (project_id,)).fetchall()
    extra = {'labels': 0} if project['annotation_type'] == 'image_classification' else {}
    classes = [c | {'boxes': 0, 'images': 0} | extra for c in project['classes']]
    by_id = {c['id']: c for c in classes}
    for row in rows:
        if not row['completed']:
            continue
        represented = set(json.loads(row['labels']))
        for category_id in represented:
            by_id[category_id]['labels'] += 1
        for box in json.loads(row['boxes']):
            by_id[box['category_id']]['boxes'] += 1
            represented.add(box['category_id'])
        for category_id in represented:
            by_id[category_id]['images'] += 1
    completed = sum(row['completed'] for row in rows)
    duplicate_result = duplicate_groups(project_id)
    return {'total': len(rows), 'completed': completed, 'remaining': len(rows) - completed,
            'boxes': sum(c['boxes'] for c in classes),
            'labels': sum(c.get('labels', 0) for c in classes), 'classes': classes,
            'similar_images': duplicate_result['similar_images'],
            'similar_groups': len(duplicate_result['groups']),
            'review': {status: sum(row['review_status'] == status for row in rows)
                       for status in ('draft', 'ready_for_review', 'approved', 'rejected')}}


@router.get('/api/projects/{project_id}/quality')
def quality(project_id: str):
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? ORDER BY id', (project_id,)).fetchall()
    counts = {category['id']: 0 for category in project['classes']}
    missing_labels = small_boxes = invalid_boxes = 0
    for row in rows:
        if not row['completed']:
            continue
        labels, boxes = json.loads(row['labels']), json.loads(row['boxes'])
        if not labels and not boxes:
            missing_labels += 1
        for category_id in labels:
            counts[category_id] = counts.get(category_id, 0) + 1
        for box in boxes:
            counts[box['category_id']] = counts.get(box['category_id'], 0) + 1
            area = box['width'] * box['height']
            if area < row['width'] * row['height'] * 0.001:
                small_boxes += 1
            if (box['x'] < 0 or box['y'] < 0 or box['width'] <= 0 or box['height'] <= 0 or
                    box['x'] + box['width'] > row['width'] + .001 or
                    box['y'] + box['height'] > row['height'] + .001):
                invalid_boxes += 1
    duplicate_result = duplicate_groups(project_id)
    shuffled = [row for row in rows if row['completed']]
    random.Random(42).shuffle(shuffled)
    cut = math.floor(len(shuffled) * project['export_train_percent'] / 100 + .5)
    train_ids = {row['id'] for row in shuffled[:cut]}
    test_ids = {row['id'] for row in shuffled[cut:]}
    cross_split = sum(bool({item['id'] for item in group['images']} & train_ids) and
                      bool({item['id'] for item in group['images']} & test_ids)
                      for group in duplicate_result['groups'])
    issues = []
    def issue(code, title, detail, count, severity='warning'):
        if count:
            issues.append({'code': code, 'title': title, 'detail': detail,
                           'count': count, 'severity': severity})
    issue('missing_labels', 'Completed images without labels',
          'These images are marked complete but contain no class labels or boxes.', missing_labels, 'error')
    issue('invalid_boxes', 'Boxes outside image bounds',
          'Legacy or imported boxes extend outside their source image.', invalid_boxes, 'error')
    issue('small_boxes', 'Unusually small boxes',
          'Boxes cover less than 0.1% of their image and may be accidental.', small_boxes)
    empty_names = [category['name'] for category in project['classes'] if not counts.get(category['id'])]
    issue('empty_classes', 'Classes without annotations',
          'No completed annotations use: ' + ', '.join(empty_names), len(empty_names))
    represented = [value for value in counts.values() if value]
    imbalanced = len(represented) > 1 and max(represented) > min(represented) * 5
    issue('class_imbalance', 'Strong class imbalance',
          'The most common class has more than five times the annotations of the least common represented class.',
          1 if imbalanced else 0)
    issue('similar_images', 'Similar images',
          'Near-duplicate images can overweight scenes during training.', duplicate_result['similar_images'])
    issue('cross_split_duplicates', 'Similar images cross the default split',
          'Related image groups appear in both train and test with the saved export split.', cross_split, 'error')
    return {'issues': issues, 'checks_run': 7, 'cross_split_groups': cross_split}


@router.post('/api/projects/{project_id}/export')
def export_project(project_id: str, payload: ExportRequest):
    with database() as db:
        project = get_project(db, project_id)
        rows = db.execute('SELECT * FROM images WHERE project_id=? AND completed=1 ORDER BY id', (project_id,)).fetchall()
    if not rows:
        raise HTTPException(422, 'Mark at least one image complete before exporting')
    random.Random(42).shuffle(rows)
    cut = math.floor(len(rows) * payload.train_percent / 100 + 0.5)
    subset = rows[:cut] if payload.split == 'train' else rows[cut:]
    if not subset:
        raise HTTPException(422, f'The {payload.split} split is empty and will not be exported')
    filename = re.sub(r'[^A-Za-z0-9._-]+', '_', project['name']).strip('._-')[:80] or 'project'
    archive_name = f'{filename}_{payload.split}'
    exported_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    fd, temp_path = tempfile.mkstemp(suffix='.zip')
    os.close(fd)
    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('annotations/', b'')
            archive.writestr('images/', b'')
            distribution = {category['id']: {
                'category_id': category['id'], 'name': category['name'],
                'annotations': 0, 'annotated_images': 0,
            } for category in project['classes']}
            for row in subset:
                represented = set(json.loads(row['labels']))
                for category_id in represented:
                    distribution[category_id]['annotations'] += 1
                for box in json.loads(row['boxes']):
                    distribution[box['category_id']]['annotations'] += 1
                    represented.add(box['category_id'])
                for category_id in represented:
                    distribution[category_id]['annotated_images'] += 1
            coco = {'info': {
                        'description': payload.description.strip(),
                        'project_name': project['name'],
                        'annotation_type': project['annotation_type'],
                        'date_created': exported_at,
                        'split': payload.split,
                        'images_annotated': len(subset),
                        'total_images_annotated': len(rows),
                        'class_distribution': list(distribution.values()),
                    }, 'licenses': [], 'images': [],
                    'annotations': [], 'categories': [c | {'supercategory': ''} for c in project['classes']]}
            for row in subset:
                # Sequential IDs avoid precision loss and collisions in COCO consumers.
                image_id = len(coco['images']) + 1
                coco['images'].append({'id': image_id, 'file_name': f"images/{row['stored_name']}",
                    'width': row['width'], 'height': row['height'], 'source_path': row['source_path']})
                archive.write(DATA / 'images' / project_id / row['stored_name'], f"images/{row['stored_name']}")
                if project['annotation_type'] == 'image_classification':
                    coco['images'][-1]['category_ids'] = json.loads(row['labels'])
                for box in json.loads(row['boxes']):
                    coco['annotations'].append({'id': len(coco['annotations']) + 1, 'image_id': image_id,
                        'category_id': box['category_id'], 'bbox': [box['x'], box['y'], box['width'], box['height']],
                        'area': box['width'] * box['height'], 'iscrowd': 0, 'segmentation': []})
            archive.writestr(f'annotations/{archive_name}.json', json.dumps(coco, indent=2))
    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        raise
    return FileResponse(temp_path, media_type='application/zip', filename=f'{archive_name}.zip',
                        background=BackgroundTask(lambda: Path(temp_path).unlink(missing_ok=True)))
