import React, { useEffect, useState } from "react";
import { api } from "../api";

export default function Readiness({ project, onNavigate }) {
  const [value, setValue] = useState(null);
  const [error, setError] = useState("");
  async function load() { try { setValue(await api(`/projects/${project.id}/readiness`)); setError(""); } catch (e) { setError(e.message); } }
  useEffect(() => { load(); }, [project.id]);
  return <section className="panel"><h2>Dataset readiness</h2>{error && <p role="alert">{error}</p>}
    {value && <><p>{value.published_samples} samples ready · {Object.entries(value.partitions).map(([name, count]) => `${count} ${name}`).join(" · ")}</p>
      {!value.checks.length && <p>Ready to publish and train.</p>}
      <ul>{value.checks.map((check) => <li key={check.code}><strong>{check.severity}: </strong>{check.message} ({Number(check.count)}) <button onClick={() => onNavigate(check.tab)}>Resolve</button></li>)}</ul></>}
    <button onClick={load}>Refresh readiness</button>
  </section>;
}
