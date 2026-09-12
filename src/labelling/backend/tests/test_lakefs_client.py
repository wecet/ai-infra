import json

import lakefs_client


class Response:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}
        self.content = json.dumps(self._body).encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            request = lakefs_client.httpx.Request('GET', 'http://lakefs.test')
            response = lakefs_client.httpx.Response(self.status_code, request=request, json=self._body)
            raise lakefs_client.httpx.HTTPStatusError('failed', request=request, response=response)

    def json(self):
        return self._body


def test_push_snapshot_creates_repository_uploads_objects_and_commits(monkeypatch, tmp_path):
    config = tmp_path / 'lakefs.env'
    config.write_text('''LAKEFS_ENDPOINT=http://lakefs.test/api/v1
LAKEFS_ACCESS_KEY_ID=access
LAKEFS_SECRET_ACCESS_KEY=secret
LAKEFS_REPOSITORY=datasets
LAKEFS_BRANCH=main
LAKEFS_STORAGE_NAMESPACE=local://datasets
''')
    monkeypatch.setenv('LAKEFS_ENV_FILE', str(config))
    calls = []

    class Client:
        def __init__(self, **kwargs): calls.append(('client', kwargs))
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def get(self, url): calls.append(('get', url)); return Response(404)
        def post(self, url, **kwargs):
            calls.append(('post', url, kwargs))
            return Response(body={'id': 'commit-1'} if url.endswith('/commits') else {})

    monkeypatch.setattr(lakefs_client.httpx, 'Client', Client)
    result = lakefs_client.push_snapshot(
        [('project/version/images/a.png', b'image', 'image/png')], 'Saving v1 at 12-09-26 by owen',
        {'dataset_version': 'v1'})
    assert result == {'commit_id': 'commit-1', 'repository': 'datasets', 'branch': 'main'}
    assert any(call[0] == 'post' and call[1].endswith('/repositories') for call in calls)
    upload = next(call for call in calls if call[0] == 'post' and call[1].endswith('/objects'))
    assert upload[2]['params']['path'] == 'project/version/images/a.png'
    assert upload[2]['headers']['Content-Type'] == 'application/octet-stream'
    commit = next(call for call in calls if call[0] == 'post' and call[1].endswith('/commits'))
    assert commit[2]['json']['message'] == 'Saving v1 at 12-09-26 by owen'
