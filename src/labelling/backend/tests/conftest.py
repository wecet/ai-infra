"""Existing dataset tests isolate identity; test_auth exercises the real MySQL boundary."""
import pytest
from fastapi import Request
import auth
import app as service


@pytest.fixture(autouse=True)
def dataset_identity(request, monkeypatch):
    if request.module.__name__.endswith('test_auth'):
        yield
        return
    user = {'id':'0'*32,'username':'admin','display_name':'Test owner','role':'owner','must_change_password':False,'csrf_token':'test'}
    def identity(request: Request):
        request.state.user = user
        return user
    def permissions(person):
        with service.common.database() as db:
            return {row['id']: {'owner_id':user['id'],'owner_username':'admin','permission':'owner'} for row in db.execute('SELECT id FROM projects')}
    monkeypatch.setattr(auth,'init_auth',lambda:None)
    monkeypatch.setattr(auth,'permission_map',permissions)
    monkeypatch.setattr(auth,'require_repository',lambda *args: {'owner_id':user['id'],'owner_username':'admin','permission':'owner'})
    monkeypatch.setattr(auth,'repository_created',lambda *args:None)
    monkeypatch.setattr(auth,'repository_deleted',lambda *args:None)
    service.app.dependency_overrides[auth.current_user] = identity
    yield
    service.app.dependency_overrides.pop(auth.current_user,None)
