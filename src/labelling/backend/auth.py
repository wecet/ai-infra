"""MySQL-backed accounts, sessions, teams and repository permissions."""
import hashlib
import hmac
import os
import secrets
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import urlsplit

import pymysql
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

import common

router = APIRouter()
COOKIE = 'studio_session'
SESSION_HOURS = 12
ITERATIONS = 600_000


@contextmanager
def database():
    connection = pymysql.connect(host=os.getenv('AUTH_MYSQL_HOST', 'mysql'),
        port=int(os.getenv('AUTH_MYSQL_PORT', '3306')), user=os.getenv('AUTH_MYSQL_USER', 'studio'),
        password=os.getenv('AUTH_MYSQL_PASSWORD', ''), database=os.getenv('AUTH_MYSQL_DATABASE', 'studio_auth'),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor, connect_timeout=5)
    try:
        with connection.cursor() as cursor:
            yield cursor
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def password_hash(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${digest}'


def password_matches(password, encoded):
    try:
        algorithm, rounds, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256': return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(rounds)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def init_auth():
    statements = [
        '''CREATE TABLE IF NOT EXISTS users (
            id CHAR(32) PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE,
            display_name VARCHAR(150) NOT NULL, password_hash VARCHAR(255) NOT NULL,
            role ENUM('owner','member') NOT NULL DEFAULT 'member', active BOOLEAN NOT NULL DEFAULT 1,
            must_change_password BOOLEAN NOT NULL DEFAULT 1, failed_logins INT NOT NULL DEFAULT 0,
            locked_until DATETIME NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB''',
        '''CREATE TABLE IF NOT EXISTS sessions (
            token_hash CHAR(64) PRIMARY KEY, user_id CHAR(32) NOT NULL,
            csrf_token CHAR(64) NOT NULL, expires_at DATETIME NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE) ENGINE=InnoDB''',
        '''CREATE TABLE IF NOT EXISTS teams (
            id CHAR(32) PRIMARY KEY, name VARCHAR(150) NOT NULL UNIQUE) ENGINE=InnoDB''',
        '''CREATE TABLE IF NOT EXISTS team_members (
            team_id CHAR(32) NOT NULL, user_id CHAR(32) NOT NULL, PRIMARY KEY(team_id,user_id),
            FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE) ENGINE=InnoDB''',
        '''CREATE TABLE IF NOT EXISTS repositories (
            project_id CHAR(32) PRIMARY KEY, owner_id CHAR(32) NOT NULL,
            FOREIGN KEY(owner_id) REFERENCES users(id)) ENGINE=InnoDB''',
        '''CREATE TABLE IF NOT EXISTS repository_users (
            project_id CHAR(32) NOT NULL, user_id CHAR(32) NOT NULL,
            permission ENUM('read','write') NOT NULL, PRIMARY KEY(project_id,user_id),
            FOREIGN KEY(project_id) REFERENCES repositories(project_id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE) ENGINE=InnoDB''',
        '''CREATE TABLE IF NOT EXISTS repository_teams (
            project_id CHAR(32) NOT NULL, team_id CHAR(32) NOT NULL,
            permission ENUM('read','write') NOT NULL, PRIMARY KEY(project_id,team_id),
            FOREIGN KEY(project_id) REFERENCES repositories(project_id) ON DELETE CASCADE,
            FOREIGN KEY(team_id) REFERENCES teams(id) ON DELETE CASCADE) ENGINE=InnoDB''',
    ]
    with database() as db:
        for statement in statements: db.execute(statement)
        db.execute('DELETE FROM sessions WHERE expires_at < UTC_TIMESTAMP()')
        db.execute("SELECT GET_LOCK('studio_owner_setup',10) AS acquired")
        if db.fetchone()['acquired'] != 1:
            raise RuntimeError('Initial owner setup is busy')
        try:
            db.execute('SELECT COUNT(*) AS total FROM users')
            if db.fetchone()['total'] == 0:
                db.execute("""INSERT INTO users(id,username,display_name,password_hash,role,must_change_password)
                    VALUES (%s,'admin','Administrator',%s,'owner',1)""",
                    (uuid.uuid4().hex, password_hash('admin')))
            db.execute("SELECT id FROM users WHERE role='owner' AND active=1 ORDER BY created_at,id LIMIT 1")
            owner = db.fetchone()
            if owner: reconcile_repositories(db, owner['id'])
            db.connection.commit()
        finally:
            db.execute("SELECT RELEASE_LOCK('studio_owner_setup')")
    (common.DATA / 'owner-setup-token').unlink(missing_ok=True)


def reconcile_repositories(db, owner_id):
    # Existing SQLite datasets remain intact; only identity/access records live in MySQL.
    with common.database() as datasets:
        ids = [row['id'] for row in datasets.execute('SELECT id FROM projects')]
    for project_id in ids:
        db.execute('INSERT IGNORE INTO repositories(project_id,owner_id) VALUES (%s,%s)', (project_id, owner_id))


def repository_created(project_id, user):
    with database() as db:
        db.execute('INSERT INTO repositories(project_id,owner_id) VALUES (%s,%s)', (project_id, user['id']))


def repository_deleted(project_id):
    with database() as db: db.execute('DELETE FROM repositories WHERE project_id=%s', (project_id,))


def permission_map(user):
    with database() as db:
        db.execute('''SELECT r.project_id,r.owner_id,u.username AS owner_username FROM repositories r
            JOIN users u ON u.id=r.owner_id''')
        rows = db.fetchall()
        db.execute('''SELECT project_id,permission FROM repository_users WHERE user_id=%s
            UNION ALL SELECT rt.project_id,rt.permission FROM repository_teams rt
            JOIN team_members tm ON tm.team_id=rt.team_id WHERE tm.user_id=%s''', (user['id'], user['id']))
        grants = db.fetchall()
    levels = {}
    for grant in grants:
        if levels.get(grant['project_id']) != 'write': levels[grant['project_id']] = grant['permission']
    result = {}
    for row in rows:
        level = 'owner' if user['role'] == 'owner' or row['owner_id'] == user['id'] else None
        if not level: level = levels.get(row['project_id'])
        if level: result[row['project_id']] = {**row, 'permission': level}
    return result


def require_repository(user, project_id, permission='read'):
    access = permission_map(user).get(project_id)
    if not access: raise HTTPException(404, 'Repository not found')
    if permission == 'owner' and access['permission'] != 'owner' or permission == 'write' and access['permission'] == 'read':
        raise HTTPException(403, f'Repository {permission} access required')
    return access


def same_origin(request):
    origin = request.headers.get('origin')
    if origin and urlsplit(origin).netloc != request.headers.get('host'):
        raise HTTPException(403, 'Cross-origin request rejected')


def current_user(request: Request):
    token = request.cookies.get(COOKIE, '')
    if not token: raise HTTPException(401, 'Sign in to continue')
    with database() as db:
        db.execute('''SELECT u.id,u.username,u.display_name,u.role,u.must_change_password,s.csrf_token
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=%s AND s.expires_at>UTC_TIMESTAMP() AND u.active=1''', (digest(token),))
        user = db.fetchone()
    if not user: raise HTTPException(401, 'Your session expired. Sign in again.')
    if request.method not in ('GET','HEAD','OPTIONS'):
        same_origin(request)
        if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), user['csrf_token']):
            raise HTTPException(403, 'Session verification failed. Refresh and try again.')
    if user['must_change_password'] and request.url.path not in ('/api/auth/me','/api/auth/password','/api/auth/logout'):
        raise HTTPException(403, 'Change your temporary password before continuing')
    request.state.user = user
    return user


def authorize(request: Request, user=Depends(current_user)):
    project_id = request.path_params.get('project_id')
    if project_id:
        path = request.url.path
        needed = 'read' if request.method in ('GET','HEAD') or path.endswith('/export') else 'write'
        if request.method == 'DELETE' and path == f'/api/projects/{project_id}' or path.endswith('/merge') and '/classes/' not in path:
            needed = 'owner'
        request.state.access = require_repository(user, project_id, needed)
    return user


def owner(user=Depends(current_user)):
    if user['role'] != 'owner': raise HTTPException(403, 'System owner role required')
    return user


class Payload(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Login(Payload):
    username: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')
    password: str = Field(min_length=1, max_length=1024)
    # Password whitespace is significant.
    model_config = ConfigDict(extra='forbid')


class NewUser(Payload):
    username: str = Field(min_length=1, max_length=80, pattern=r'^[a-zA-Z0-9_.-]+$')
    display_name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=12, max_length=1024)
    role: Literal['owner','member'] = 'member'
    model_config = ConfigDict(extra='forbid')



class UserUpdate(Payload):
    role: Literal['owner','member']
    active: bool


class ResetPassword(BaseModel):
    password: str = Field(min_length=12, max_length=1024)


class ChangePassword(ResetPassword):
    current_password: str = Field(min_length=1, max_length=1024)


class TeamCreate(Payload):
    name: str = Field(min_length=1, max_length=150)


class Members(Payload):
    user_ids: list[str] = Field(max_length=500)


def public_user(user):
    return {key: user[key] for key in ('id','username','display_name','role','must_change_password')}


@router.get('/api/auth/status')
def status():
    with database() as db:
        db.execute('SELECT COUNT(*) AS total FROM users')
        return {'setup_required': db.fetchone()['total'] == 0}


@router.post('/api/auth/login')
def login(payload: Login, request: Request, response: Response):
    same_origin(request)
    success = False
    with database() as db:
        db.execute('SELECT * FROM users WHERE username=%s FOR UPDATE', (payload.username,))
        user = db.fetchone()
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        locked = user and user['locked_until'] and user['locked_until'] > now
        if user and not locked and user['active'] and password_matches(payload.password, user['password_hash']):
            db.execute('UPDATE users SET failed_logins=0,locked_until=NULL WHERE id=%s', (user['id'],))
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_hex(32)
            db.execute('INSERT INTO sessions(token_hash,user_id,csrf_token,expires_at) VALUES (%s,%s,%s,%s)',
                (digest(token),user['id'],csrf,now+timedelta(hours=SESSION_HOURS)))
            success = True
        elif user and not locked:
            failures = user['failed_logins']+1
            db.execute('UPDATE users SET failed_logins=%s,locked_until=%s WHERE id=%s',
                (failures, now+timedelta(minutes=5) if failures>=5 else None, user['id']))
        elif not user:
            # Comparable password work for unknown usernames.
            hashlib.pbkdf2_hmac('sha256', payload.password.encode(), b'unknown-user-salt', ITERATIONS)
    if not success: raise HTTPException(401, 'Invalid credentials or account temporarily unavailable')
    response.set_cookie(COOKIE,token,max_age=SESSION_HOURS*3600,httponly=True,samesite='strict',
        secure=os.getenv('AUTH_COOKIE_SECURE','false').lower()=='true',path='/')
    response.headers['Cache-Control'] = 'no-store'
    return {**public_user(user), 'csrf_token': csrf}


@router.get('/api/auth/me')
def me(user=Depends(current_user)):
    return {**public_user(user), 'csrf_token': user['csrf_token']}


@router.post('/api/auth/logout')
def logout(request: Request, response: Response, user=Depends(current_user)):
    with database() as db: db.execute('DELETE FROM sessions WHERE token_hash=%s', (digest(request.cookies[COOKIE]),))
    response.delete_cookie(COOKIE,path='/')
    return {'message': 'Signed out'}


@router.post('/api/auth/password')
def change_password(payload: ChangePassword, user=Depends(current_user)):
    with database() as db:
        db.execute('SELECT password_hash FROM users WHERE id=%s FOR UPDATE', (user['id'],))
        if not password_matches(payload.current_password, db.fetchone()['password_hash']):
            raise HTTPException(400, 'Current password is incorrect')
        if payload.current_password == payload.password:
            raise HTTPException(422, 'Choose a different new password')
        db.execute('UPDATE users SET password_hash=%s,must_change_password=0 WHERE id=%s', (password_hash(payload.password),user['id']))
        db.execute('DELETE FROM sessions WHERE user_id=%s', (user['id'],))
    return {'message': 'Password changed. Sign in again.'}


@router.get('/api/admin/users')
def users(user=Depends(owner)):
    with database() as db:
        db.execute('SELECT id,username,display_name,role,active,must_change_password,created_at FROM users ORDER BY username')
        return db.fetchall()


@router.post('/api/admin/users', status_code=201)
def create_user(payload: NewUser, user=Depends(owner)):
    try:
        with database() as db:
            user_id = uuid.uuid4().hex
            db.execute('INSERT INTO users(id,username,display_name,password_hash,role) VALUES (%s,%s,%s,%s,%s)',
                (user_id,payload.username,payload.display_name,password_hash(payload.password),payload.role))
    except pymysql.err.IntegrityError: raise HTTPException(409, 'Username already exists')
    return {'id': user_id}


@router.put('/api/admin/users/{user_id}')
def update_user(user_id: str, payload: UserUpdate, user=Depends(owner)):
    with database() as db:
        # Lock all owners in stable order: concurrent demotions cannot remove the last owner.
        db.execute("SELECT id FROM users WHERE role='owner' AND active=1 ORDER BY id FOR UPDATE")
        owners = [row['id'] for row in db.fetchall()]
        if user_id in owners and len(owners)==1 and (payload.role!='owner' or not payload.active):
            raise HTTPException(409, 'Keep at least one active system owner')
        db.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
        if not db.fetchone(): raise HTTPException(404, 'User not found')
        if not payload.active:
            db.execute('SELECT project_id FROM repositories WHERE owner_id=%s LIMIT 1', (user_id,))
            if db.fetchone(): raise HTTPException(409, 'Transfer this user’s repositories before disabling the account')
        db.execute('UPDATE users SET role=%s,active=%s WHERE id=%s', (payload.role,payload.active,user_id))
        db.execute('DELETE FROM sessions WHERE user_id=%s', (user_id,))
    return {'message': 'User updated'}


@router.post('/api/admin/users/{user_id}/password')
def reset_password(user_id: str, payload: ResetPassword, user=Depends(owner)):
    with database() as db:
        db.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (user_id,))
        if not db.fetchone(): raise HTTPException(404, 'User not found')
        db.execute('UPDATE users SET password_hash=%s,must_change_password=1,failed_logins=0,locked_until=NULL WHERE id=%s',
            (password_hash(payload.password),user_id))
        db.execute('DELETE FROM sessions WHERE user_id=%s', (user_id,))
    return {'message': 'Temporary password set; existing sessions revoked'}


@router.get('/api/admin/teams')
def teams(user=Depends(owner)):
    with database() as db:
        db.execute('SELECT id,name FROM teams ORDER BY name'); result = db.fetchall()
        db.execute('SELECT team_id,user_id FROM team_members'); members = db.fetchall()
    return [{**team,'user_ids':[member['user_id'] for member in members if member['team_id']==team['id']]} for team in result]


@router.post('/api/admin/teams', status_code=201)
def create_team(payload: TeamCreate, user=Depends(owner)):
    try:
        with database() as db:
            team_id = uuid.uuid4().hex
            db.execute('INSERT INTO teams(id,name) VALUES (%s,%s)', (team_id,payload.name))
    except pymysql.err.IntegrityError: raise HTTPException(409, 'Team name already exists')
    return {'id':team_id}


@router.put('/api/admin/teams/{team_id}/members')
def team_members(team_id: str, payload: Members, user=Depends(owner)):
    with database() as db:
        db.execute('SELECT id FROM teams WHERE id=%s FOR UPDATE', (team_id,))
        if not db.fetchone(): raise HTTPException(404, 'Team not found')
        for user_id in set(payload.user_ids):
            db.execute('SELECT id FROM users WHERE id=%s AND active=1', (user_id,))
            if not db.fetchone(): raise HTTPException(422, 'Select active users only')
        db.execute('DELETE FROM team_members WHERE team_id=%s', (team_id,))
        for user_id in set(payload.user_ids):
            db.execute('INSERT INTO team_members(team_id,user_id) VALUES (%s,%s)', (team_id,user_id))
    return {'message':'Team membership saved'}


class Grant(Payload):
    kind: Literal['user','team']
    subject_id: str = Field(min_length=32,max_length=32)
    permission: Literal['read','write'] = 'read'


class Transfer(Payload):
    owner_id: str = Field(min_length=32,max_length=32)


def access_owner(project_id, user):
    with common.database() as db: common.get_project(db,project_id)
    return require_repository(user,project_id,'owner')


@router.get('/api/projects/{project_id}/access')
def repository_access(project_id: str, user=Depends(current_user)):
    access = access_owner(project_id,user)
    with database() as db:
        db.execute('SELECT id,username,display_name FROM users WHERE active=1 ORDER BY username'); people=db.fetchall()
        db.execute('SELECT id,name FROM teams ORDER BY name'); groups=db.fetchall()
        db.execute('SELECT user_id AS subject_id,permission FROM repository_users WHERE project_id=%s', (project_id,)); direct=db.fetchall()
        db.execute('SELECT team_id AS subject_id,permission FROM repository_teams WHERE project_id=%s', (project_id,)); inherited=db.fetchall()
    return {**access,'users':people,'teams':groups,'grants':[
        *[{**row,'kind':'user'} for row in direct], *[{**row,'kind':'team'} for row in inherited]]}


@router.put('/api/projects/{project_id}/access')
def grant_access(project_id: str, payload: Grant, user=Depends(current_user)):
    access_owner(project_id,user)
    table, column, subject = ('repository_users','user_id','users') if payload.kind=='user' else ('repository_teams','team_id','teams')
    with database() as db:
        db.execute(f'SELECT id FROM {subject} WHERE id=%s' + (' AND active=1' if subject=='users' else ''), (payload.subject_id,))
        if not db.fetchone(): raise HTTPException(422, 'Select an existing active user or team')
        db.execute(f'''INSERT INTO {table}(project_id,{column},permission) VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE permission=VALUES(permission)''', (project_id,payload.subject_id,payload.permission))
    return {'message':'Repository access saved'}


@router.delete('/api/projects/{project_id}/access/{kind}/{subject_id}')
def revoke_access(project_id: str, kind: Literal['user','team'], subject_id: str, user=Depends(current_user)):
    access_owner(project_id,user)
    table, column = ('repository_users','user_id') if kind=='user' else ('repository_teams','team_id')
    with database() as db: db.execute(f'DELETE FROM {table} WHERE project_id=%s AND {column}=%s', (project_id,subject_id))
    return {'message':'Access removed'}


@router.put('/api/projects/{project_id}/owner')
def transfer_owner(project_id: str, payload: Transfer, user=Depends(current_user)):
    access_owner(project_id,user)
    with database() as db:
        db.execute('SELECT id FROM users WHERE id=%s AND active=1', (payload.owner_id,))
        if not db.fetchone(): raise HTTPException(422, 'Select an active repository owner')
        db.execute('UPDATE repositories SET owner_id=%s WHERE project_id=%s', (payload.owner_id,project_id))
    return {'message':'Repository ownership transferred'}
