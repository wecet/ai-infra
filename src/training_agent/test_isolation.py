"""Check that jobs reclaim whole worker processes and can stop silent trainers."""
import json
import os
from pathlib import Path
import time

import pytest
import jobs
from isolated_worker import execute
from test_jobs import wait_for


def script(tmp_path, body):
    path = tmp_path / 'worker.py'
    path.write_text('import json,os,sys,time\nfrom pathlib import Path\nroot=Path(sys.argv[1])\n' + body)
    return path


def test_worker_exits_and_forwards_progress(tmp_path):
    directory = tmp_path / 'job'; directory.mkdir()
    jobs.write(directory / 'status.json', {'status': 'running'})
    worker = script(tmp_path, """allocation=bytearray(64*1024*1024)
(root/'worker-progress.jsonl').write_text(json.dumps({'phase':'training','metrics':{'loss':.25}})+'\\n')
(root/'worker-result.json').write_text(json.dumps({'pid':os.getpid(),'bytes':len(allocation)}))
""")
    events = []
    result = execute({}, directory, lambda **values: events.append(values), tmp_path, worker)
    assert result['pid'] != os.getpid() and result['bytes'] == 64*1024*1024
    assert events == [{'phase': 'training', 'metrics': {'loss': .25}}]
    with pytest.raises(ProcessLookupError): os.kill(result['pid'], 0)


def test_cancellation_terminates_worker_without_progress_callbacks(tmp_path):
    worker = script(tmp_path, "(root/'pid').write_text(str(os.getpid()))\ntime.sleep(30)\n")
    def handler(manifest, directory, report):
        return execute(manifest, directory, report, tmp_path, worker)
    jobs.start(tmp_path, 'silent', {}, b'', handler)
    directory = tmp_path / 'silent'
    wait_for(lambda: (directory / 'pid').is_file())
    pid = int((directory / 'pid').read_text())
    jobs.cancel(tmp_path, 'silent')
    wait_for(lambda: jobs.status(tmp_path, 'silent')['status'] == 'cancelled')
    with pytest.raises(ProcessLookupError): os.kill(pid, 0)


def test_worker_failure_keeps_model_error(tmp_path):
    directory = tmp_path / 'failure'; directory.mkdir()
    jobs.write(directory / 'status.json', {'status': 'running'})
    worker = script(tmp_path, "(root/'worker-result.json').write_text(json.dumps({'error':'Invalid training labels'}))\nsys.exit(1)\n")
    with pytest.raises(RuntimeError, match='Invalid training labels'):
        execute({}, directory, lambda **_: None, tmp_path, worker)
