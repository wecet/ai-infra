"""Run isolated suites (both services have an app.py) and the production UI build."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def run(command, cwd=ROOT, pythonpath=None):
    env = dict(os.environ)
    env.setdefault('AUTH_MYSQL_PASSWORD', 'verification-only')
    env.setdefault('AUTH_MYSQL_ROOT_PASSWORD', 'verification-only')
    if pythonpath: env['PYTHONPATH'] = str(ROOT / pythonpath)
    subprocess.run(command, cwd=cwd, env=env, check=True)

if __name__ == '__main__':
    run([sys.executable, '-m', 'pytest', '-q', 'src/labelling/backend/tests'], pythonpath='src/labelling/backend')
    run([sys.executable, '-m', 'pytest', '-q', 'src/training_agent'], pythonpath='src/training_agent')
    run([sys.executable, '-m', 'pytest', '-q', 'tests/test_augmentations.py', 'tests/test_gradcam.py'], pythonpath='tests')
    run([sys.executable, '-m', 'pytest', '-q', 'tools'])
    run([sys.executable, 'tests/smoke.py'])
    frontend = ROOT / 'src/labelling/frontend'
    run(['npm', 'ci'], cwd=frontend)
    run(['npm', 'test'], cwd=frontend)
    run(['npm', 'run', 'build'], cwd=frontend)
    run(['docker', 'compose', '--env-file', '.env.example', 'config', '--quiet'])
