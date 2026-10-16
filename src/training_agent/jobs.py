"""Agent-owned jobs: HTTP clients observe work; they do not own its lifetime."""
import base64
import json
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException

_lock = threading.RLock()
_active = set()
_pending = {}
MAX_CONCURRENT = max(1, int(os.getenv("TRAINING_MAX_CONCURRENT_JOBS", "1")))


def now():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, allow_nan=False))
    temporary.replace(path)


def status(root, job_id):
    with _lock:
        path = root / job_id / 'status.json'
        if not path.is_file(): raise HTTPException(404, 'Agent job not found')
        return json.loads(path.read_text())


def start(root, job_id, manifest, dataset, handler, artifact=None):
    directory = root / job_id
    with _lock:
        if directory.exists():
            existing = status(root, job_id)
            previous = json.loads((directory / 'manifest.json').read_text())
            if previous != manifest: raise HTTPException(409, 'Job ID belongs to a different request')
            return existing
        directory.mkdir(parents=True)
        try:
            write(directory / 'manifest.json', manifest)
            with (directory / 'dataset.zip').open('wb') as output:
                if hasattr(dataset, 'read'): shutil.copyfileobj(dataset, output)
                else: output.write(dataset)
            if artifact is not None:
                with (directory / 'input-model').open('wb') as output:
                    if hasattr(artifact, 'read'): shutil.copyfileobj(artifact, output)
                    else: output.write(artifact)
            write(directory / 'status.json', {'id': job_id, 'kind': manifest.get('kind', 'training'),
                'status': 'queued', 'phase': 'queued', 'created_at': now(), 'started_at': None,
                'completed_at': None, 'heartbeat_at': now(), 'metrics': {}, 'latest_metric': None,
                'logs': [{'time': now(), 'message': 'Job accepted by compute agent'}], 'error': ''})
        except Exception:
            import shutil
            shutil.rmtree(directory, ignore_errors=True)
            raise
        launch(root, job_id, handler)
    return status(root, job_id)


def capacity():
    with _lock:
        return {'limit': MAX_CONCURRENT, 'running': len(_active), 'queued': len(_pending)}


def launch(root, job_id, handler):
    key = (str(root.resolve()), job_id)
    with _lock:
        if key in _active or key in _pending: return
        _pending[key] = (root, job_id, handler)
        drain()


def drain():
    # Called with the reentrant lock held; queued jobs do not consume threads.
    while _pending and len(_active) < MAX_CONCURRENT:
        key = next(iter(_pending))
        args = _pending.pop(key)
        _active.add(key)
        threading.Thread(target=run, args=args, daemon=True).start()


class Cancelled(Exception):
    pass


def cancel(root, job_id):
    with _lock:
        value = status(root, job_id)
        if value['status'] in ('succeeded', 'failed', 'cancelled'): return value
        key = (str(root.resolve()), job_id)
        if key in _pending:
            _pending.pop(key)
            value.update(status='cancelled', phase='cancelled', completed_at=now())
        else:
            value.update(status='cancelling', phase='cancelling')
        write(root / job_id / 'status.json', value)
        return value


def run(root, job_id, handler):
    directory = root / job_id
    finished = threading.Event()
    def report(phase=None, message=None, metrics=None, **progress):
        with _lock:
            value = status(root, job_id)
            if value['status'] == 'cancelling' and (phase or message or metrics or progress): raise Cancelled('Cancelled by user')
            value.update(progress, heartbeat_at=now())
            if phase: value['phase'] = phase
            if message:
                value['logs'] = (value['logs'] + [{'time': now(), 'message': str(message)[:2000]}])[-200:]
            if metrics:
                value['metrics'].update(metrics)
                key = 'validation_loss' if 'validation_loss' in metrics else next(iter(metrics))
                value['latest_metric'] = {'name': key, 'value': metrics[key]}
            write(directory / 'status.json', value)
    def heartbeat():
        while not finished.wait(5): report()
    try:
        report(status='running', started_at=now(), phase='preparing', message='Preparing dataset and model')
        threading.Thread(target=heartbeat, daemon=True).start()
        manifest = json.loads((directory / 'manifest.json').read_text())
        result = handler(manifest, directory, report)
        if 'artifact' in result:
            artifact = result['artifact']
            if 'local_path' in artifact:
                Path(artifact.pop('local_path')).replace(directory / 'model.bin')
            else: (directory / 'model.bin').write_bytes(base64.b64decode(artifact.pop('content_base64'), validate=True))
        write(directory / 'result.json', result)
        report(status='succeeded', completed_at=now(), phase='completed', metrics=result.get('metrics'), message='Job completed')
    except Cancelled:
        with _lock:
            value = status(root, job_id)
            value.update(status='cancelled', phase='cancelled', completed_at=now(), error='')
            write(directory / 'status.json', value)
    except Exception as error:
        detail = error.detail if isinstance(error, HTTPException) else f'{type(error).__name__}: {error}'
        report(status='failed', completed_at=now(), phase='failed', error=str(detail)[:2000], message=str(detail))
    finally:
        finished.set()
        with _lock:
            _active.discard((str(root.resolve()), job_id))
            drain()


def result(root, job_id, binary=False):
    value = status(root, job_id)
    if value['status'] != 'succeeded': raise HTTPException(409, 'Agent job has not succeeded')
    directory = root / job_id
    value = json.loads((directory / 'result.json').read_text())
    if 'artifact' in value and not binary:
        value['artifact']['content_base64'] = base64.b64encode((directory / 'model.bin').read_bytes()).decode()
    return value


def recover(root, handlers):
    if not root.is_dir(): return
    for path in root.glob('*/status.json'):
        value = json.loads(path.read_text())
        with _lock:
            if (str(root.resolve()), path.parent.name) in _active: continue
        if value['status'] == 'queued': launch(root, path.parent.name, handlers[value['kind']])
        elif value['status'] in ('running', 'cancelling'):
            value.update(status='failed', phase='interrupted', completed_at=now(),
                         error='Compute agent restarted during execution. Retry as a new job.')
            value['logs'].append({'time': now(), 'message': value['error']})
            write(path, value)
