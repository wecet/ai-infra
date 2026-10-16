import React, { useEffect, useState } from "react";
import { api } from "../api";
import { formatDate } from "../dates";
export default function Activity({ project }) {
  const [rows, setRows] = useState([]); const [error, setError] = useState("");
  async function load(more = false) { try { const value = await api(`/projects/${project.id}/activity${more && rows.length ? `?before=${rows.at(-1).id}` : ''}`); setRows((old) => more ? [...old, ...value] : value); } catch (e) { setError(e.message); } }
  useEffect(() => { load(); }, [project.id]);
  return <section className="panel workspace-panel"><h2>Project activity</h2><button onClick={() => load()}>Refresh</button>{error && <p role="alert">{error}</p>}<ul>{rows.map((row) => <li key={row.id}>{formatDate(row.created_at)} · {row.actor} · {row.action}</li>)}</ul>{rows.length > 0 && <button onClick={() => load(true)}>Load earlier activity</button>}</section>;
}
