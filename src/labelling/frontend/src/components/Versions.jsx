import React, { useEffect, useState } from "react";
import { api } from "../api";

function LakeFSIcon() {
  return <svg className="lakefs-icon" viewBox="0 0 145.17 81.68" aria-hidden="true">
    <path className="lakefs-mark-shadow" d="M143.92 40a25.74 25.74 0 0 0-5-9.56c-1.13-5.66-3.54-11-7.52-14.32a21 21 0 0 0-8.64-4.63 1 1 0 0 0-1.15 1.31c1 2.61 2.64 8 1.91 12.21a24.08 24.08 0 0 0-3.24-5.6c-1.87-2.42-2.92-3.77-2.35-6.65.49-2.5 3.81-4.58 7.89-5.29a1 1 0 0 0 .5-1.65C124 3.73 119.2 0 113.55 0c-7.9 0-12.14 4.06-13.34 10.87-1 5.79.55 9.92 1.69 12.94.19.48.35.92.49 1.31-.92-.63-2-1.29-3.11-1.95a53.56 53.56 0 0 0-26.7-6.85 53.54 53.54 0 0 0-26.69 6.85c-1.15.66-2.19 1.32-3.11 1.95.14-.39.3-.83.49-1.31 1.14-3 2.71-7.15 1.69-12.94C43.75 4.06 39.52 0 31.62 0 26 0 21.16 3.73 18.88 5.86a1 1 0 0 0 .5 1.65c4.08.71 7.4 2.79 7.89 5.29.57 2.88-.48 4.23-2.35 6.65a23.73 23.73 0 0 0-3.24 5.6c-.73-4.23.94-9.6 1.91-12.21a1 1 0 0 0-1.16-1.31 21.08 21.08 0 0 0-8.63 4.63c-4 3.36-6.39 8.66-7.52 14.32a25.74 25.74 0 0 0-5 9.56c-1.9 8.07-2.5 16.78 4.59 25.11 4.54 5.34 11.82 8.11 20.82 8.11a23.12 23.12 0 0 1 5.41 1.61c6.91 2.55 18.49 6.81 40.51 6.81s33.61-4.26 40.52-6.81a23.12 23.12 0 0 1 5.41-1.61c9 0 16.27-2.77 20.82-8.11 7.06-8.33 6.46-17.04 4.56-25.11Z" />
    <path className="lakefs-mark-main" d="M118.51 68.36c-6.13 0-15.31 8.42-45.93 8.42s-39.8-8.42-45.92-8.42C2.17 68.36 4.92 45.25 4.92 45.25S9.46 56.79 21 56.79a20.33 20.33 0 0 0 4.16-.44.56.56 0 0 0 0-1.08c-17.84-5.33-18-26.17-7.4-36.2-4.48 19.06 8.88 25 14 26.61a.51.51 0 0 0 .51-.84C29 41.43 21.46 32 28.8 22.44 38 10.5 25.74 5.91 25.74 5.91a19.24 19.24 0 0 1 5.88-1c3.54 0 7.54 1.29 8.51 6.82 1.81 10.23-7 13.81-.66 22.06a.41.41 0 0 0 .66 0s11-12.55 32.45-12.55S105 33.77 105 33.77a.41.41 0 0 0 .66 0c6.37-8.25-2.47-11.83-.66-22.06 1-5.53 5-6.82 8.51-6.82a19.24 19.24 0 0 1 5.88 1s-12.25 4.59-3.07 16.53c7.34 9.54-.18 19-3.49 22.4a.51.51 0 0 0 .51.84c5.13-1.56 18.49-7.55 14-26.61 10.62 10 10.43 30.87-7.4 36.2a.56.56 0 0 0 0 1.08 20.33 20.33 0 0 0 4.16.44c11.52 0 16.05-11.54 16.05-11.54S143 68.36 118.51 68.36Z" />
    <path className="lakefs-mark-detail" d="M52.38 48a4.29 4.29 0 1 0-8.57 0c0 2.36 1.92 3.06 4.28 3.06s4.29-.67 4.29-3.06Zm48.98 0a4.29 4.29 0 1 0-8.57 0c0 2.36 1.92 3.06 4.29 3.06s4.28-.67 4.28-3.06ZM72.58 64.87A39.57 39.57 0 0 1 53.81 60a2 2 0 0 1 1.92-3.46c3.8 2.11 10.08 3.4 16.85 3.4s13-1.29 16.86-3.4A2 2 0 0 1 91.36 60a39.58 39.58 0 0 1-18.78 4.87Z" />
  </svg>;
}

function Versions({ project, initialVersion = "" }) {
  const [versions, setVersions] = useState(null); const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState("");
  const [pushing, setPushing] = useState(""); const [notice, setNotice] = useState("");
  useEffect(() => { api(`/projects/${project.id}/versions`).then(setVersions).catch((e) => setError(e.message)); }, [project.id]);
  useEffect(() => {
    if (initialVersion) api(`/projects/${project.id}/versions/${initialVersion}`).then(setSelected).catch((e) => setError(e.message));
  }, [project.id, initialVersion]);
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
