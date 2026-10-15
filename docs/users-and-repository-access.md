# Users, teams and repository access

AI Studio now requires sign-in. MySQL stores accounts, salted password hashes, sessions, teams, memberships, repository owners and access grants. Existing dataset records and files remain in the Studio SQLite/data volume; this change does not move or rewrite them.

## Initial setup

Set unique `AUTH_MYSQL_PASSWORD` and `AUTH_MYSQL_ROOT_PASSWORD` values in your private `.env`. The Compose stack starts MySQL 8.4 without publishing its port. Never use the database root account as the Studio account.

```bash
docker compose up -d mysql
docker compose up -d --no-deps --build labelling
```

On a fresh identity database, Studio generates a random, owner-only setup-token file. Read it locally:

```bash
docker compose exec labelling cat /data/owner-setup-token
```

Open Studio and enter that token on **Create the first owner**, together with your username, display name and chosen password (at least 12 characters). The first owner is created once; the setup token is removed. Sign in with the credentials you chose. There is no default password and no public self-registration.

On upgrade, existing projects are assigned to this first owner. New projects and imported ZIP repositories belong to their creator. Subsequent startups reconcile any dataset records missing an identity record to the earliest active system owner; retain both databases when backing up or restoring.

## System roles

| Role | Capabilities |
| --- | --- |
| Owner | Manage users, system roles, password resets, teams and every repository, including ownership and access |
| Member | Create repositories and use repositories they own or that are shared directly or through teams |

The role dropdown in **Users & teams → Users → Manage** is available only to system owners. The last active system owner cannot be demoted or disabled. Repository owners do not automatically become system owners.

Owners can create users with a temporary password, promote/demote users, disable/re-enable accounts, and reset passwords. Disabling an account requires transferring its owned repositories first. Role changes, account-status changes and password resets invalidate that user's existing sessions. User records are retained rather than hard-deleted.

The user must replace a temporary/reset password before opening repositories or administration. Users can change their own password from the header's **Password** button. A password change signs out all of their sessions, including the current one.

## Teams

Open **Users & teams → Teams** to create a named team. Add active users through its member dropdown; remove members with the adjacent action. Owners control team membership. Changes affect repository access on the next request, without requiring users to sign in again.

## Repository permissions

Open a project's **Manage → Settings → Repository access** section. Its owner or any system owner can:

- Select **User** or **Team**, choose an entry from the dropdown, select Read/Write and save access.
- Change a grant by selecting the same user/team and saving its new permission.
- Remove an existing grant.
- Transfer ownership to an active user using **Transfer ownership**.

| Permission | Capabilities |
| --- | --- |
| Read | Inspect repository metadata, images, history, published datasets, lineage and training results; download datasets/artifacts and view model evaluations |
| Write | Read plus annotation/review, imports, classes/settings, publishing, lakeFS uploads and training |
| Repository owner | Write plus grant/revoke access, transfer ownership, delete and merge repositories |

System owners have owner access to every repository. Other users see only repositories they can access. Unknown/inaccessible repository IDs return 404. Known read-only repositories reject mutation requests with 403. A merge requires ownership of both source and destination.

Direct and team grants combine using the highest permission. Removing a direct grant does not remove access inherited through a team, and removing a team grant does not remove another direct/team grant. The named owner always retains owner access until ownership is transferred. Transferring ownership does not erase explicit grants; the previous owner may lose access if they have no other grant.

Permissions apply on the server to project API routes, including file downloads, ZIP exports, training and evaluation; hiding a UI control is not the access boundary. Reviewers, comment authors and publishing/lakeFS authors come from the authenticated session. Forwarded username headers cannot impersonate another user.

## Sessions and deployment

Passwords use random salts and PBKDF2-HMAC-SHA256 (600,000 iterations); raw passwords are not stored. Session cookies are HttpOnly and SameSite=Strict, expire after 12 hours, and reference a hashed token stored in MySQL. Mutating authenticated API calls require the session's CSRF header. Five failed account logins temporarily lock the account for five minutes. Owners can reset the password to clear its lock.

Use HTTPS and set `AUTH_COOKIE_SECURE=true` when deploying beyond local HTTP development. Studio API responses are not cached. MySQL availability is required for login and authorization; authentication does not silently disable itself if MySQL fails.

This protects the Studio portal/API. lakeFS, MLflow, TensorBoard and compute-agent endpoints are separate services with their own deployment boundaries. Do not expose their direct ports to untrusted clients as a substitute for Studio repository access. They are not automatically protected by Studio session cookies. MFA, SSO, email password delivery, fine-grained trainer/labeller roles and a dedicated administrative audit log are not included in this first iteration.

## Persistence and configuration

| Variable | Default / purpose |
| --- | --- |
| `AUTH_MYSQL_DATABASE` | `studio_auth` |
| `AUTH_MYSQL_USER` | `studio` |
| `AUTH_MYSQL_PASSWORD` | Required private application DB password |
| `AUTH_MYSQL_ROOT_PASSWORD` | Required private MySQL initialization password |
| `AUTH_MYSQL_VOLUME` | `ai-infra_auth_mysql` |
| `AUTH_COOKIE_SECURE` | `false` for local HTTP; set `true` with HTTPS |
| `AUTH_MYSQL_HOST` / `AUTH_MYSQL_PORT` | Native backend connection; Compose supplies `mysql:3306` |

Back up MySQL together with the existing Studio data, training-runs and tracking volumes. Changing MySQL password environment values does not rotate passwords in an already initialized MySQL volume; perform a database credential rotation deliberately. Do not delete the MySQL volume to troubleshoot a login issue.

## Verification

Existing dataset tests isolate the identity layer; the security integration test uses a real disposable MySQL database. Set `AUTH_TEST_SETTINGS` to a private JSON file of native `AUTH_MYSQL_*` connection values, with a database name ending in `_test`, then run:

```bash
AUTH_TEST_SETTINGS=/path/to/test-settings.json PYTHONPATH=src/labelling/backend \
  tests/.venv/bin/python -m pytest src/labelling/backend/tests/test_auth.py -q
```

The integration test replaces its test database tables. Never point it at a live database. It checks first-owner setup, sign-in, CSRF, temporary passwords, hidden repositories, direct/team permissions, ownership, password/session revocation and last-owner protection.
