import React, { useEffect, useState } from "react";
import { api } from "../api";

export default function Readiness({ project, onNavigate }) {
  const [value, setValue] = useState(null);
  const [error, setError] = useState("");
  async function load() { try { setValue(await api(`/projects/${project.id}/readiness`)); setError(""); } catch (e) { setError(e.message); } }
  useEffect(() => { load(); }, [project.id]);
  return <section className="panel workspace-panel readiness-panel">
    <header className="workspace-panel-heading"><h2>Dataset readiness</h2><button onClick={load}>Refresh readiness</button></header>
    {error && <p role="alert">{error}</p>}
    {!value && !error && <p className="muted" role="status">Checking dataset…</p>}
    {value && <><p className="muted">{value.published_samples} samples ready · {Object.entries(value.partitions).map(([name, count]) => `${count} ${name}`).join(" · ")}</p>
      {!value.checks.length && <p>Ready to publish and train.</p>}
      <ul className="readiness-checks">{value.checks.map((check) => <li key={check.code}>
        <div><strong className="readiness-severity">{check.severity}</strong><p>{check.message} <span className="muted">({Number(check.count)})</span></p></div>
        <button onClick={() => onNavigate(check.tab)}>Resolve</button>
      </li>)}</ul></>}
  </section>;
}
