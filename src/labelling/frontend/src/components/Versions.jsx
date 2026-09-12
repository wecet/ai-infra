import React, { useEffect, useState } from "react";
import { api } from "../api";

function LakeFSIcon() {
  return <svg className="lakefs-icon" viewBox="0 0 32 32" aria-hidden="true">
    <path d="M5 9.5 16 4l11 5.5L16 15 5 9.5Zm0 6L16 21l11-5.5M5 21.5 16 27l11-5.5" />
    <path d="M16 15v6" />
  </svg>;
}

function Versions({ project }) {
  const [versions, setVersions] = useState(null); const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState("");
  const [pushing, setPushing] = useState(""); const [notice, setNotice] = useState("");
  useEffect(() => { api(`/projects/${project.id}/versions`).then(setVersions).catch((e) => setError(e.message)); }, [project.id]);
  async function open(item) {
    try { setSelected(await api(`/projects/${project.id}/versions/${item.id}`)); }
    catch (e) { setError(e.message); }
  }
  async function download(item) {
    setExporting(item.id); setError("");
    try {
      const response = await fetch(`/api/projects/${project.id}/versions/${item.id}/export`);
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Version export failed");
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url;
      link.download = `${project.name.replace(/[^A-Za-z0-9._-]+/g, "_")}_${item.name}.zip`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { setError(e.message); } finally { setExporting(""); }
  }
  async function pushToLakeFS(item) {
    setPushing(item.id); setError(""); setNotice("");
    try {
      const result = await api(`/projects/${project.id}/versions/${item.id}/lakefs`, { method: "POST" });
      setNotice(`${item.name} pushed to ${result.repository}/${result.branch}.`);
    } catch (e) { setError(e.message); } finally { setPushing(""); }
  }
  return <div><div className="page-heading"><div><h2>Published versions</h2>
    <p className="muted">Immutable snapshots created from Dashboard.</p></div></div>
    {error && <div className="alert">{error}</div>}
    {notice && <div className="success-alert">{notice}</div>}
    {versions && !versions.length && <div className="empty"><h2>No published versions</h2><p>Use Publish on Dashboard to freeze the current dataset state.</p></div>}
    {!!versions?.length && <div className="panel table-wrap"><table><thead><tr><th>VERSION</th><th>SAMPLES</th><th>PUBLISHED BY</th><th>DATE</th><th></th></tr></thead>
      <tbody>{versions.map((item) => <tr key={item.id}><td><strong>{item.name}</strong></td><td>{item.sample_count}</td>
        <td>{item.author}</td><td>{new Date(`${item.created_at}${item.created_at.endsWith("Z") ? "" : "Z"}`).toLocaleString()}</td>
        <td><div className="version-actions"><button onClick={() => open(item)}>View</button>
          <button className="primary" disabled={!!exporting} onClick={() => download(item)}>
            {exporting === item.id ? "Exporting…" : "Export ZIP"}</button>
          <button className="lakefs-button" disabled={!!pushing} onClick={() => pushToLakeFS(item)}
            aria-label={`Push ${item.name} to LakeFS`} title="Push to LakeFS">
            {pushing === item.id ? <span aria-hidden="true">…</span> : <LakeFSIcon />}
          </button></div></td></tr>)}</tbody></table></div>}
    {selected && <div className="modal-backdrop"><div className="panel version-modal"><div className="modal-heading"><div>
      <div className="eyebrow">IMMUTABLE DATASET SNAPSHOT</div><h2>{selected.name}</h2></div><button onClick={() => setSelected(null)}>Close</button></div>
      <p className="muted">{selected.sample_count} samples · {selected.snapshot.project.classes.length} classes · published by {selected.author}</p>
      <div className="version-grid">{selected.snapshot.images.map((image) => <figure key={image.id}>
        <img src={`/api/projects/${project.id}/versions/${selected.id}/images/${image.id}/file`} alt={image.source_path} />
        <figcaption title={image.source_path}>{image.source_path}<span>{image.completed ? "Complete" : "Draft"} · {image.boxes.length + image.labels.length} annotations</span></figcaption>
      </figure>)}</div></div></div>}
  </div>;
}

export default Versions;
