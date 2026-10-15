import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";

function UserEditor({ person, onSaved, onClose }) {
  const dialog = useRef(null);
  const [role, setRole] = useState(person.role);
  const [active, setActive] = useState(!!person.active);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { dialog.current.showModal(); }, []);
  async function update(event) {
    event.preventDefault(); setBusy(true); setError("");
    try { await api(`/admin/users/${person.id}`, { method: "PUT", body: JSON.stringify({ role, active }) }); await onSaved(); onClose(); }
    catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  async function reset(event) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    const form = event.currentTarget;
    try { await api(`/admin/users/${person.id}/password`, { method: "POST", body: JSON.stringify({ password: new FormData(form).get("password") }) }); form.reset(); setMessage("Temporary password set. Share it securely; the user must change it at sign-in."); await onSaved(); }
    catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  return <dialog className="account-dialog" ref={dialog} onCancel={onClose} aria-labelledby="user-editor-title">
    <div className="modal-heading"><div><h2 id="user-editor-title">Manage {person.username}</h2><p className="muted">{person.display_name}</p></div><button onClick={onClose}>Close</button></div>
    <form onSubmit={update} className="account-form"><label>System role<select value={role} onChange={(e) => setRole(e.target.value)}><option value="member">Member</option><option value="owner">Owner</option></select></label>
      <label className="checkbox-label"><input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />Account enabled</label>
      <p className="muted small">System owners administer all users and repositories. Saving changes signs out this user. Transfer their repositories before disabling their account.</p><button disabled={busy} className="primary">Save account</button></form>
    <form onSubmit={reset} className="account-form account-section"><h3>Reset password</h3><label>New temporary password<input name="password" type="password" required minLength="12" maxLength="1024" autoComplete="new-password" /></label><button disabled={busy}>Set temporary password</button></form>
    {error && <p className="alert" role="alert">{error}</p>}{message && <p className="notice" role="status">{message}</p>}
  </dialog>;
}

function TeamEditor({ team, users, onSaved }) {
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(ids) {
    setBusy(true); setError("");
    try { await api(`/admin/teams/${team.id}/members`, { method: "PUT", body: JSON.stringify({ user_ids: ids }) }); setSelected(""); await onSaved(); }
    catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  return <section className="panel team-card"><div><h3>{team.name}</h3><p className="muted small">{team.user_ids.length} members · repository grants apply to the whole team</p></div>
    <ul className="access-list">{team.user_ids.map((id) => <li key={id}><span>{users.find((person) => person.id === id)?.username || "Unavailable user"}</span><button disabled={busy} onClick={() => save(team.user_ids.filter((value) => value !== id))} aria-label={`Remove ${users.find((person) => person.id === id)?.username} from ${team.name}`}>Remove</button></li>)}</ul>
    <form className="access-grant" onSubmit={(e) => { e.preventDefault(); save([...team.user_ids, selected]); }}><label>Add member<select required value={selected} onChange={(e) => setSelected(e.target.value)}><option value="">Choose a user…</option>{users.filter((person) => person.active && !team.user_ids.includes(person.id)).map((person) => <option key={person.id} value={person.id}>{person.display_name} (@{person.username})</option>)}</select></label><button disabled={busy || !selected}>Add member</button></form>
    {error && <p className="alert" role="alert">{error}</p>}
  </section>;
}

export default function Administration() {
  const [users, setUsers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [tab, setTab] = useState("users");
  const [person, setPerson] = useState(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  async function refresh() {
    const [people, groups] = await Promise.all([api("/admin/users"), api("/admin/teams")]); setUsers(people); setTeams(groups);
  }
  useEffect(() => { refresh().catch((error) => setError(error.message)); }, []);
  async function create(event, kind) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    const form = event.currentTarget;
    try { await api(`/admin/${kind}`, { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(form))) }); form.reset(); setCreating(false); setMessage(kind === "users" ? "User created. Share their temporary password securely." : "Team created."); await refresh(); }
    catch (error) { setError(error.message); } finally { setBusy(false); }
  }
  return <div className="page administration"><div className="page-heading"><div><div className="page-kicker">SYSTEM OWNER</div><h1>Users & teams</h1><p className="muted">Manage identities here. Assign repository access from each project’s Manage page.</p></div></div>
    <nav className="section-tabs" aria-label="Administration"><button className={tab === "users" ? "selected" : ""} onClick={() => { setTab("users"); setCreating(false); }}>Users ({users.length})</button><button className={tab === "teams" ? "selected" : ""} onClick={() => { setTab("teams"); setCreating(false); }}>Teams ({teams.length})</button></nav>
    {error && <p className="alert" role="alert">{error}</p>}{message && <p className="notice" role="status">{message}</p>}
    {tab === "users" ? <section className="panel account-section"><div className="account-toolbar"><label>Find user<input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Name or username" /></label><button className="primary" onClick={() => setCreating(!creating)}>{creating ? "Cancel" : "Create user"}</button></div>
      {creating && <form className="account-create" onSubmit={(e) => create(e, "users")}><label>Display name<input name="display_name" required maxLength="150" /></label><label>Username<input name="username" required pattern="[a-zA-Z0-9_.\-]+" maxLength="80" autoComplete="off" /></label><label>System role<select name="role" defaultValue="member"><option value="member">Member</option><option value="owner">Owner</option></select></label><label>Temporary password<input name="password" type="password" required minLength="12" maxLength="1024" autoComplete="new-password" /></label><p className="muted small">At least 12 characters. The user must choose a new password at first sign-in.</p><button className="primary" disabled={busy}>Create user</button></form>}
      <div className="account-table-wrap"><table className="account-table"><thead><tr><th>User</th><th>System role</th><th>Status</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{users.filter((person) => `${person.display_name} ${person.username}`.toLowerCase().includes(search.toLowerCase())).map((person) => <tr key={person.id}><td><strong>{person.display_name}</strong><span className="muted small">@{person.username}</span></td><td><span className={`role-badge role-${person.role}`}>{person.role}</span></td><td>{!person.active ? "Disabled" : person.must_change_password ? "Password change required" : "Active"}</td><td><button onClick={() => setPerson(person)}>Manage</button></td></tr>)}</tbody></table></div>{!users.length && <p className="muted">Loading users…</p>}
    </section> : <><form className="panel access-grant" onSubmit={(e) => create(e, "teams")}><label>Team name<input name="name" required maxLength="150" placeholder="For example, Vision research" /></label><button className="primary" disabled={busy}>Create team</button></form><div className="team-grid">{teams.map((team) => <TeamEditor key={team.id} team={team} users={users} onSaved={refresh} />)}</div>{!teams.length && <div className="empty"><h2>No teams yet</h2><p>Create a team to grant a group of users repository access together.</p></div>}</>}
    {person && <UserEditor person={person} onSaved={refresh} onClose={() => setPerson(null)} />}
  </div>;
}
