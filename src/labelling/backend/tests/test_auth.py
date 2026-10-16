"""Run MySQL integration with AUTH_TEST_SETTINGS pointing to isolated connection JSON."""
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import auth
import app as service


def test_password_hashes_are_salted():
    first = auth.password_hash('correct password 123')
    assert first != auth.password_hash('correct password 123')
    assert auth.password_matches('correct password 123',first)
    assert not auth.password_matches('wrong password',first)


@pytest.mark.skipif(not os.getenv('AUTH_TEST_SETTINGS'),reason='Requires isolated MySQL')
def test_mysql_users_teams_and_repository_permissions(tmp_path, monkeypatch):
    settings = json.loads(Path(os.environ['AUTH_TEST_SETTINGS']).read_text())
    assert settings['AUTH_MYSQL_DATABASE'].endswith('_test'), 'Never run integration against a live identity database'
    for key,value in settings.items(): monkeypatch.setenv(key,value)
    with auth.database() as db:
        db.execute('SET FOREIGN_KEY_CHECKS=0')
        try:
            for table in ('repository_teams','repository_users','repositories','team_members','teams','sessions','users'):
                db.execute('DROP TABLE IF EXISTS ' + table)
        finally:
            db.execute('SET FOREIGN_KEY_CHECKS=1')
    monkeypatch.setattr(service,'DATA',tmp_path)
    monkeypatch.setattr(service.common,'DATA',tmp_path)
    service.common.init_db()
    legacy_id='e'*32
    with service.common.database() as db:
        db.execute('INSERT INTO projects(id,name,classes) VALUES (?,?,?)', (legacy_id,'Existing dataset','[]'))
    monkeypatch.setattr(service.training,'resume_jobs',lambda:None)
    monkeypatch.setattr(service.models,'resume_evaluations',lambda:None)
    with TestClient(service.app) as admin:
        assert admin.get('/api/projects').status_code == 401
        for path in (f'/api/projects/{legacy_id}/images', f'/api/projects/{legacy_id}/versions',
                     f'/api/projects/{legacy_id}/training/jobs', '/api/admin/users'):
            assert admin.get(path).status_code==401
        assert not admin.get('/api/auth/status').json()['setup_required']
        assert not (tmp_path/'owner-setup-token').exists()
        signed = admin.post('/api/auth/login',json={'username':'admin','password':'admin'})
        assert signed.status_code==200 and signed.json()['must_change_password']
        admin.headers['x-csrf-token']=signed.json()['csrf_token']
        assert admin.get('/api/projects').status_code==403
        assert admin.post('/api/auth/password',json={'current_password':'admin','password':'original password 123'}).status_code==200
        signed = admin.post('/api/auth/login',json={'username':'admin','password':'original password 123'})
        assert signed.status_code==200
        assert 'HttpOnly' in signed.headers['set-cookie'] and 'SameSite=strict' in signed.headers['set-cookie']
        admin.headers['x-csrf-token']=signed.json()['csrf_token']
        aid=signed.json()['id']
        assert admin.get(f'/api/projects/{legacy_id}').json()['owner_id']==aid
        assert all('password_hash' not in person for person in admin.get('/api/admin/users').json())
        csrf=admin.headers.pop('x-csrf-token')
        assert admin.post('/api/projects',json={'name':'Denied','classes':['cat']}).status_code==403
        admin.headers['x-csrf-token']=csrf
        assert admin.post('/api/projects',headers={'origin':'https://evil.example'},json={'name':'Denied','classes':['cat']}).status_code==403
        project=admin.post('/api/projects',json={'name':'Private','classes':['cat']}).json()
        pid=project['id']
        assert project['owner_id']==aid and project['permission']=='owner'
        ids={}
        for name in ('alice','bob'):
            result=admin.post('/api/admin/users',json={'username':name,'display_name':name.title(),'password':'temporary password 123'})
            assert result.status_code==201,result.text
            ids[name]=result.json()['id']
        team=admin.post('/api/admin/teams',json={'name':'Vision'}).json()['id']
        assert admin.put(f'/api/admin/teams/{team}/members',json={'user_ids':[ids['alice']]}).status_code==200
        with TestClient(service.app) as alice:
            login=alice.post('/api/auth/login',json={'username':'alice','password':'temporary password 123'})
            alice.headers['x-csrf-token']=login.json()['csrf_token']
            assert alice.get('/api/projects').status_code==403  # forced first password change
            assert alice.post('/api/auth/password',json={'current_password':'temporary password 123','password':'permanent password 456'}).status_code==200
            assert alice.get('/api/auth/me').status_code==401
            login=alice.post('/api/auth/login',json={'username':'alice','password':'permanent password 456'})
            alice.headers['x-csrf-token']=login.json()['csrf_token']
            assert alice.get('/api/projects').json()==[]
            assert alice.get(f'/api/projects/{pid}').status_code==404
            assert alice.get('/api/admin/users').status_code==403
            assert admin.put(f'/api/projects/{pid}/access',json={'kind':'team','subject_id':team,'permission':'read'}).status_code==200
            assert alice.get(f'/api/projects/{pid}').json()['permission']=='read'
            assert alice.put(f'/api/projects/{pid}',json={'name':'Cannot edit'}).status_code==403
            assert alice.delete(f'/api/projects/{pid}').status_code==403
            assert alice.get(f'/api/projects/{pid}/access').status_code==403
            assert alice.post(f'/api/projects/{pid}/publish').status_code==403
            assert alice.post(f'/api/projects/{pid}/training/jobs',json={}).status_code==403
            for suffix in ('models/missing/evaluation', 'models/missing/evaluation/cancel', 'models/missing/review-tasks', 'imports/preview', 'augmentation-preview', 'training/jobs/missing/cancel'):
                assert alice.post(f'/api/projects/{pid}/{suffix}', json={}).status_code == 403
            assert alice.put(f'/api/projects/{pid}/review-tasks/missing', json={'status':'open'}).status_code == 403
            for suffix in ('readiness', 'review-tasks', 'activity'):
                assert alice.get(f'/api/projects/{pid}/{suffix}').status_code == 200
            assert admin.put(f'/api/projects/{pid}/access',json={'kind':'user','subject_id':ids['alice'],'permission':'write'}).status_code==200
            assert alice.get(f'/api/projects/{pid}').json()['permission']=='write'
            assert alice.put(f'/api/projects/{pid}',json={'name':'Editable'}).status_code==200
            assert alice.put(f'/api/projects/{pid}/owner',json={'owner_id':ids['alice']}).status_code==403
            private=alice.post('/api/projects',json={'name':'Alice private','classes':['cat']}).json()
            assert private['owner_id']==ids['alice']
            assert admin.put(f'/api/projects/{pid}/owner',json={'owner_id':ids['bob']}).status_code==200
            assert admin.delete(f'/api/projects/{pid}/access/user/{ids["alice"]}').status_code==200
            assert alice.get(f'/api/projects/{pid}').json()['permission']=='read'
            assert admin.put(f'/api/admin/teams/{team}/members',json={'user_ids':[]}).status_code==200
            assert alice.get(f'/api/projects/{pid}').status_code==404
            # Hidden source repository cannot be merged by a user with no source ownership.
            assert alice.post(f'/api/projects/{private["id"]}/merge',json={'source_project_id':pid}).status_code==404
            assert admin.post(f'/api/admin/users/{ids["alice"]}/password',json={'password':'reset password 789'}).status_code==200
            assert alice.get('/api/auth/me').status_code==401
        assert admin.put(f'/api/admin/users/{aid}',json={'role':'member','active':True}).status_code==409
        assert admin.put(f'/api/admin/users/{ids["bob"]}',json={'role':'member','active':False}).status_code==409
        assert admin.put(f'/api/admin/users/{ids["bob"]}',json={'role':'owner','active':True}).status_code==200
        with TestClient(service.app) as bob:
            login=bob.post('/api/auth/login',json={'username':'bob','password':'temporary password 123'})
            bob.headers['x-csrf-token']=login.json()['csrf_token']
            bob.post('/api/auth/password',json={'current_password':'temporary password 123','password':'bob permanent password'})
            login=bob.post('/api/auth/login',json={'username':'bob','password':'bob permanent password'})
            bob.headers['x-csrf-token']=login.json()['csrf_token']
            assert bob.get('/api/admin/users').status_code==200
            assert bob.put(f'/api/admin/users/{aid}',json={'role':'member','active':True}).status_code==200
            assert admin.get('/api/auth/me').status_code==401
        with auth.database() as db:
            db.execute('SELECT password_hash FROM users')
            assert all(row['password_hash'].startswith('pbkdf2_sha256$') for row in db.fetchall())
