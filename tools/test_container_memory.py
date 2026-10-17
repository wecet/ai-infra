"""Guard the local stack's idle-worker and memory budget configuration."""
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_compose_memory_budgets_and_unused_mlflow_workers():
    environment = {**os.environ, 'AUTH_MYSQL_PASSWORD': 'verification-only', 'AUTH_MYSQL_ROOT_PASSWORD': 'verification-only'}
    result = subprocess.run(['docker', 'compose', '--env-file', '.env.example', 'config', '--format', 'json'], cwd=ROOT,
        env=environment, text=True, capture_output=True, check=True)
    services = json.loads(result.stdout)['services']
    names = ('labelling', 'training-agent', 'mysql', 'mlflow', 'lakefs', 'tensorboard')
    for name in names:
        assert 0 < int(services[name]['mem_limit']) == int(services[name]['memswap_limit'])
    assert sum(int(services[name]['mem_limit']) for name in names) <= 5 * 1024**3
    command = services['mlflow']['command']
    assert command[command.index('--workers') + 1] == '1'
    assert services['mlflow']['environment']['MLFLOW_SERVER_ENABLE_JOB_EXECUTION'] == 'false'
    assert '--performance-schema=OFF' in services['mysql']['command']
    assert '--innodb-buffer-pool-size=64M' in services['mysql']['command']
