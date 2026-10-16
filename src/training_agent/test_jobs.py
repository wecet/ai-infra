import threading
import time
import jobs


def wait_for(predicate):
    deadline = time.monotonic() + 3
    while not predicate():
        assert time.monotonic() < deadline
        time.sleep(.01)


def test_capacity_keeps_second_job_queued(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, 'MAX_CONCURRENT', 1)
    gate = threading.Event()
    def handler(*args):
        gate.wait(3)
        return {'metrics': {}}
    try:
        jobs.start(tmp_path, 'first', {}, b'zip', handler)
        wait_for(lambda: jobs.status(tmp_path, 'first')['status'] == 'running')
        jobs.start(tmp_path, 'second', {}, b'zip', handler)
        assert jobs.status(tmp_path, 'second')['status'] == 'queued'
        assert jobs.capacity()['queued'] == 1
    finally: gate.set()
    wait_for(lambda: jobs.status(tmp_path, 'second')['status'] == 'succeeded')


def test_cancel_waiting_and_cooperative_running_job(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, 'MAX_CONCURRENT', 1)
    gate = threading.Event()
    def handler(manifest, directory, report):
        gate.wait(3)
        report(phase='epoch')
        return {}
    try:
        jobs.start(tmp_path, 'running', {}, b'', handler)
        wait_for(lambda: jobs.status(tmp_path, 'running')['status'] == 'running')
        jobs.start(tmp_path, 'waiting', {}, b'', handler)
        assert jobs.cancel(tmp_path, 'waiting')['status'] == 'cancelled'
        assert jobs.cancel(tmp_path, 'running')['status'] == 'cancelling'
    finally: gate.set()
    wait_for(lambda: jobs.status(tmp_path, 'running')['status'] == 'cancelled')


def test_streamed_artifact_result_has_binary_download_metadata(tmp_path):
    import io
    def handler(manifest, directory, report):
        artifact = directory / 'produced.pt'
        artifact.write_bytes(b'weights')
        return {'artifact': {'filename': 'model.pt', 'local_path': str(artifact)}}
    jobs.start(tmp_path, 'binary', {}, io.BytesIO(b'archive'), handler)
    wait_for(lambda: jobs.status(tmp_path, 'binary')['status'] == 'succeeded')
    assert (tmp_path / 'binary' / 'dataset.zip').read_bytes() == b'archive'
    result = jobs.result(tmp_path, 'binary', binary=True)
    assert result['artifact'] == {'filename': 'model.pt'}
    assert (tmp_path / 'binary' / 'model.bin').read_bytes() == b'weights'
