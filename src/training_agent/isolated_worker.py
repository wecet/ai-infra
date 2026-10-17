"""Run each model in a fresh process so framework heaps die with the job."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from jobs import check_cancelled
from fastapi import HTTPException


def stop_process(process):
    # Kill the whole session even if its leader already exited, so a workbench
    # cannot leave dataloader/utility descendants retaining model memory.
    try:
        if os.name == 'posix': os.killpg(process.pid, signal.SIGTERM)
        elif process.poll() is None: process.terminate()
        else: return
    except ProcessLookupError: return
    try: process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name != 'posix': process.kill()
    finally:
        if os.name == 'posix':
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        process.wait()


def execute(manifest, directory, report, runs_root, worker_script=None):
    directory = Path(directory)
    (directory / 'worker-request.json').write_text(json.dumps(manifest))
    progress_path = directory / 'worker-progress.jsonl'
    progress_path.write_text('')
    result_path = directory / 'worker-result.json'
    result_path.unlink(missing_ok=True)
    environment = {**os.environ, 'TRAINING_RUNS_ROOT': str(runs_root)}
    process = None
    try:
        with (directory / 'worker.log').open('w') as logs, progress_path.open() as progress:
            process = subprocess.Popen([sys.executable, str(worker_script or Path(__file__).resolve()), str(directory.resolve())],
                stdout=logs, stderr=logs, env=environment, start_new_session=os.name == 'posix')
            pending = ''
            while True:
                check_cancelled(directory.parent, directory.name)
                exited = process.poll() is not None
                pending += progress.read(65536)
                while '\n' in pending:
                    line, pending = pending.split('\n', 1)
                    if line: report(**json.loads(line))
                if exited:
                    # Drain events still buffered when a fast worker exits.
                    rest = progress.read()
                    if rest:
                        pending += rest
                        for line in pending.splitlines():
                            if line: report(**json.loads(line))
                    break
                time.sleep(.2)
        if process.returncode:
            if result_path.is_file():
                error = json.loads(result_path.read_text())
                if 'status_code' in error: raise HTTPException(error['status_code'], error.get('error', 'Model worker failed'))
                raise RuntimeError(error.get('error', 'Model worker failed'))
            if process.returncode < 0:
                raise RuntimeError(f'Model worker killed by signal {-process.returncode}; check the container memory limit and worker.log')
            raise RuntimeError(f'Model worker exited with code {process.returncode}; see worker.log')
        result = json.loads(result_path.read_text())
        if 'error' in result: raise RuntimeError(result['error'])
        return result
    finally:
        if process is not None: stop_process(process)


def worker(directory):
    import app
    from fastapi import UploadFile
    request = json.loads((directory / 'worker-request.json').read_text())
    if '_workbench' in request:
        selected = request['_workbench']
        app.find_workbench = lambda key: selected if selected and selected['key'] == key else None
    try:
        with (directory / 'worker-progress.jsonl').open('a', buffering=1) as events:
            def report(**values):
                events.write(json.dumps(values, allow_nan=False) + '\n')
                events.flush()
            if request.get('kind', 'training') == 'evaluation':
                from evaluation import evaluate
                result = evaluate(request, directory, report, app.find_workbench, app.load_model)
            else:
                with (directory / 'dataset.zip').open('rb') as stream:
                    result = app.train_model(json.dumps(request), UploadFile(filename='dataset.zip', file=stream), report, binary=True)
        (directory / 'worker-result.json').write_text(json.dumps(result, allow_nan=False))
    except Exception as error:
        detail = getattr(error, 'detail', None) or f'{type(error).__name__}: {error}'
        (directory / 'worker-result.json').write_text(json.dumps({'error': str(detail)[:4000], 'status_code': getattr(error, 'status_code', 500)}))
        raise


if __name__ == '__main__':
    worker(Path(sys.argv[1]))
