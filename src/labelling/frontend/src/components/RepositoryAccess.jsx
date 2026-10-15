import React, { useEffect, useState } from "react";
import { api } from "../api";

export default function RepositoryAccess({ project, onUpdated }) {
  const [access, setAccess] = useState(null);
  const [kind, setKind] = useState("user");
  const [subject, setSubject] = useState("");
  const [permission, setPermission] = useState("read");
  const [newOwner, setNewOwner] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function refresh() { setAccess(await api(`/projects/${project.id}/access`)); }
  useEffect(() => { if (project.permission === "owner") refresh().catch((e) => setError(e.message)); }, [project.id, project.permission]);
  async function change(path, method, values) {
    setBusy(true); setError(""); setMessage("");
    try { const result = await api(`/projects/${project.id}/${path}`, { method, ...(values ? { body: JSON.stringify(values) } : {}) }); setMessage(result.message); setSubject(""); if (path === "owner") window.dispatchEvent(new Event("studio-repositories-changed")); else await refresh(); }
    catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  if (project.permission !== "owner") return <section className="panel account-section"><h2>Repository access</h2><p>Owned by @{project.owner_username}. Your access: {project.permission}.</p><p className="muted">Only repository owners and system owners can change access.</p></section>;
  const choices = kind === "user" ? access?.users || [] : access?.teams || [];
  return <section className="panel account-section"><div><h2>Repository access</h2><p className="muted">Private to its owner and the users or teams listed below. System owners can administer every repository.</p></div>
    {error && <p className="alert" role="alert">{error}</p>}{message && <p className="notice" role="status">{message}</p>}
    {access && <><div className="repository-owner"><span><span className="role-badge role-owner">Repository owner</span> @{access.owner_username}</span></div>
    <form className="access-grant" onSubmit={(e) => { e.preventDefault(); change("access", "PUT", { kind, subject_id: subject, permission }); }}>
      <label>Grant access to<select value={kind} onChange={(e) => { setKind(e.target.value); setSubject(""); }}><option value="user">User</option><option value="team">Team</option></select></label>
      <label>{kind === "user" ? "User" : "Team"}<select required value={subject} onChange={(e) => setSubject(e.target.value)}><option value="">Choose a {kind}…</option>{choices.filter((item) => item.id !== access.owner_id).map((item) => <option key={item.id} value={item.id}>{kind === "user" ? `${item.display_name} (@${item.username})` : item.name}</option>)}</select></label>
      <label>Permission<select value={permission} onChange={(e) => setPermission(e.target.value)}><option value="read">Read</option><option value="write">Write</option></select></label><button className="primary" disabled={busy || !subject}>Save access</button>
    </form><p className="muted small">Read lets users inspect and download datasets. Write also allows labelling, imports, publishing and training. Ownership is required to delete, merge or change access. Direct and team access combine; removing one grant does not remove access through another.</p>
    <ul className="access-list">{access.grants.map((grant) => <li key={`${grant.kind}-${grant.subject_id}`}><span><span className="role-badge">{grant.kind}</span> {grant.kind === "user" ? access.users.find((item) => item.id === grant.subject_id)?.username || "Disabled user" : access.teams.find((item) => item.id === grant.subject_id)?.name} <span className="muted">· {grant.permission}</span></span><button disabled={busy} onClick={() => change(`access/${grant.kind}/${grant.subject_id}`, "DELETE")}>Remove</button></li>)}</ul>
    {!access.grants.length && <p className="muted">No additional access granted.</p>}
    <details className="account-section"><summary>Transfer ownership</summary><p className="muted small">The new owner can manage access. Your access may change immediately after transfer.</p><form className="access-grant" onSubmit={(e) => { e.preventDefault(); change("owner", "PUT", { owner_id: newOwner }); }}><label>New repository owner<select required value={newOwner} onChange={(e) => setNewOwner(e.target.value)}><option value="">Choose a user…</option>{access.users.filter((item) => item.id !== access.owner_id).map((item) => <option key={item.id} value={item.id}>{item.display_name} (@{item.username})</option>)}</select></label><button disabled={busy || !newOwner}>Transfer ownership</button></form></details></>}
  </section>;
}
