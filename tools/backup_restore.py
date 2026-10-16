"""Consistent offline Compose volume backup and isolated restore.

python tools/backup_restore.py backup /path/to/new-backup
python tools/backup_restore.py restore /path/to/backup --prefix studio-restore-test
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile


def command(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def digest(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_data(root):
    """Check database integrity and every retained version/model reference."""
    database = root / 'labelling.sqlite3'
    if not database.is_file(): raise ValueError('Studio database missing')
    with sqlite3.connect(f'{database.as_uri()}?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('SQLite integrity check failed')
        if db.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Broken database relationships')
        for project, stored in db.execute('SELECT project_id,stored_name FROM images'):
            if not (root / 'images' / project / stored).is_file(): raise ValueError('Live image missing')
        for project, version, snapshot in db.execute('SELECT project_id,id,snapshot FROM dataset_versions'):
            for image in json.loads(snapshot)['images']:
                if not (root / 'versions' / project / version / image['stored_name']).is_file(): raise ValueError('Frozen image missing')
        for job, artifact in db.execute("SELECT id,artifact_path FROM training_jobs WHERE status='succeeded'"):
            if artifact and not (root / 'training' / job / Path(artifact).name).is_file(): raise ValueError('Model artifact missing')


def inspect_backup(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('format') != 1: raise ValueError('Unsupported backup format')
    for key, record in manifest['volumes'].items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+', key): raise ValueError('Unsafe volume key')
        path = directory / f'{key}.tar'
        if digest(path) != record['sha256']: raise ValueError(f'Checksum mismatch: {key}')
        with tarfile.open(path) as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if name.is_absolute() or '..' in name.parts or not (member.isfile() or member.isdir()):
                    raise ValueError('Unsafe archive member')
    return manifest


def backup(directory):
    if directory.exists(): raise ValueError('Backup destination must not exist')
    config = json.loads(command('docker', 'compose', 'config', '--format', 'json', capture_output=True, text=True).stdout)
    running = command('docker', 'compose', 'ps', '--status', 'running', '-q', capture_output=True, text=True).stdout.strip()
    if running: raise ValueError('Stop the stack first with docker compose stop (preserve volumes)')
    image = config['services']['labelling']['image']
    directory.mkdir(parents=True)
    manifest = {'format': 1, 'volumes': {}, 'image': image}
    try:
        for key, record in config['volumes'].items():
            name = record['name']
            command('docker', 'volume', 'inspect', name, capture_output=True)
            path = directory / f'{key}.tar'
            script = "import tarfile; t=tarfile.open(fileobj=__import__('sys').stdout.buffer,mode='w|'); t.add('/source',arcname='.'); t.close()"
            with path.open('wb') as output:
                command('docker', 'run', '--rm', '--network', 'none', '--entrypoint', 'python', '--mount', f'type=volume,src={name},dst=/source,readonly', image, '-c', script, stdout=output)
            manifest['volumes'][key] = {'source': name, 'sha256': digest(path)}
        (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        inspect_backup(directory)
    except Exception:
        # Keep incomplete files for diagnosis; no source volume is modified.
        raise


def restore(directory, prefix, image=None):
    if not re.fullmatch(r'[a-z][a-z0-9-]{2,50}', prefix): raise ValueError('Use a distinct lowercase restore prefix')
    manifest = inspect_backup(directory)
    names = {key: f'{prefix}_{key}' for key in manifest['volumes']}
    existing = set(command('docker', 'volume', 'ls', '-q', capture_output=True, text=True).stdout.splitlines())
    if existing & set(names.values()): raise ValueError('Restore refuses to overwrite existing volumes')
    with tempfile.TemporaryDirectory() as temporary:
        local = Path(temporary)
        # Smoke-check restored Studio data before creating any Docker volumes.
        with tarfile.open(directory / 'labelling_data.tar') as archive: archive.extractall(local, filter='data')
        verify_data(local)
    for key, name in names.items():
        command('docker', 'volume', 'create', name, capture_output=True)
        script = "import tarfile,sys; t=tarfile.open(fileobj=sys.stdin.buffer,mode='r|'); t.extractall('/target',filter='data')"
        with (directory / f'{key}.tar').open('rb') as source:
            command('docker', 'run', '--rm', '-i', '--network', 'none', '--entrypoint', 'python', '--mount', f'type=volume,src={name},dst=/target', image or manifest['image'], '-c', script, stdin=source)
    print(json.dumps({'restored_volumes': names, 'studio_reference_check': 'passed'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'verify', 'restore'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--prefix')
    parser.add_argument('--image')
    args = parser.parse_args()
    if args.action == 'backup': backup(args.directory)
    elif args.action == 'verify': inspect_backup(args.directory); print('Archive checksums and paths verified')
    elif not args.prefix: parser.error('restore requires --prefix')
    else: restore(args.directory, args.prefix, args.image)
