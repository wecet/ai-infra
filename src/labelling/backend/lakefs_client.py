"""Small lakeFS API client for publishing immutable labelling snapshots."""
import os
from pathlib import Path
from urllib.parse import quote

import httpx


def _settings():
    values = {}
    path = Path(os.environ.get('LAKEFS_ENV_FILE', '/app/lakefs.env'))
    if path.is_file():
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    for key in ('LAKEFS_ENDPOINT', 'LAKEFS_ACCESS_KEY_ID', 'LAKEFS_SECRET_ACCESS_KEY',
                'LAKEFS_REPOSITORY', 'LAKEFS_BRANCH', 'LAKEFS_STORAGE_NAMESPACE'):
        values[key] = os.environ.get(key, values.get(key, ''))
    values['LAKEFS_ENDPOINT'] = values['LAKEFS_ENDPOINT'].rstrip('/')
    return values


def push_snapshot(objects, message, metadata):
    config = _settings()
    required = ('LAKEFS_ENDPOINT', 'LAKEFS_ACCESS_KEY_ID', 'LAKEFS_SECRET_ACCESS_KEY',
                'LAKEFS_REPOSITORY', 'LAKEFS_BRANCH')
    if any(not config[key] for key in required):
        raise ValueError('LakeFS credentials or repository settings are missing')
    endpoint, repository, branch = (config['LAKEFS_ENDPOINT'], config['LAKEFS_REPOSITORY'],
                                    config['LAKEFS_BRANCH'])
    auth = (config['LAKEFS_ACCESS_KEY_ID'], config['LAKEFS_SECRET_ACCESS_KEY'])
    try:
        with httpx.Client(auth=auth, timeout=30) as client:
            repo_url = f'{endpoint}/repositories/{quote(repository, safe="")}'
            response = client.get(repo_url)
            if response.status_code == 404:
                namespace = config['LAKEFS_STORAGE_NAMESPACE']
                if not namespace:
                    raise ValueError('LakeFS storage namespace is required to create the repository')
                response = client.post(f'{endpoint}/repositories', json={
                    'name': repository, 'storage_namespace': namespace, 'default_branch': branch})
            response.raise_for_status()
            object_url = f'{repo_url}/branches/{quote(branch, safe="")}/objects'
            for path, content, _content_type in objects:
                response = client.post(object_url, params={'path': path}, content=content,
                                       headers={'Content-Type': 'application/octet-stream'})
                response.raise_for_status()
            response = client.post(f'{repo_url}/branches/{quote(branch, safe="")}/commits',
                                   json={'message': message, 'metadata': metadata})
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get('message', '')
        except (ValueError, AttributeError):
            detail = ''
        raise ValueError(detail or f'LakeFS rejected the request ({exc.response.status_code})') from exc
    except httpx.RequestError as exc:
        raise ValueError('LakeFS is unavailable') from exc
    return {'commit_id': result.get('id', ''), 'repository': repository, 'branch': branch}
