import React, { useEffect, useState } from "react";
import { api } from "../api";

function History({ project, onView, onRestored }) {
  const [history, setHistory] = useState(null);
  const [error, setError] = useState("");
  const [restoring, setRestoring] = useState("");
  async function load() {
    try { setHistory(await api(`/projects/${project.id}/history`)); setError(""); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [project.id]);
  async function view(batch) {
    try { onView(await api(`/projects/${project.id}/batches/${batch.id}/images`)); }
    catch (e) { setError(e.message); }
  }
  async function restore(entry, image) {
    setRestoring(image.id); setError("");
    try {
      await api(`/projects/${project.id}/history/${entry.id}/deleted/${image.id}/restore`, { method: "POST" });
      await load(); await onRestored();
    } catch (e) { setError(e.message); }
    finally { setRestoring(""); }
  }
  return <div>
    <div className="page-heading"><div><h2>Dataset history</h2>
      <p className="muted">Every image addition creates a stable dataset membership version.</p></div></div>
    {error && <div className="alert">{error}<button onClick={load}>Retry</button></div>}
    {history && <div className="panel table-wrap"><table><thead><tr>
      <th>VERSION</th><th>EVENT</th><th>SAMPLE CHANGE</th><th>TOTAL SAMPLES</th><th>DATE</th><th>DETAILS</th>
    </tr></thead><tbody>{history.map((entry) => <tr key={entry.id}>
      <td>v{entry.version}</td><td>{entry.kind === "project_created" ? "Project Created" : entry.kind === "images_deleted" ? "Images Deleted" : entry.kind === "images_restored" ? "Images Restored" : entry.kind === "projects_merged" ? "Projects Merged" : "New Additions"}</td>
      <td className={entry.sample_delta < 0 ? "warning-text" : "accent"}>{entry.sample_delta > 0 ? "+" : ""}{entry.sample_delta}</td>
      <td>{entry.total_samples}</td><td>{new Date(`${entry.created_at}${entry.created_at.endsWith("Z") ? "" : "Z"}`).toLocaleString()}</td>
      <td>{entry.kind === "images_deleted" ? <details><summary>View deleted image</summary>
        <div className="history-details">{entry.details.map((item) => <article key={item.id}>
          {item.restorable && <img src={`/api/projects/${project.id}/history/${entry.id}/deleted/${item.id}/file`}
            alt={item.source_path} />}<div><strong>{item.source_path}</strong>
            <div className="muted small">{item.width} × {item.height} · {item.completed ? "Annotated" : "Incomplete"}</div></div>
          <button className="primary" disabled={!item.restorable || !!restoring}
            onClick={() => restore(entry, item)}>{restoring === item.id ? "Restoring…" : item.restorable ? "Restore image" : "Already restored"}</button>
        </article>)}</div></details> :
        <button className="text-button" disabled={!entry.samples} onClick={() => view(entry)}>View images</button>}</td>
    </tr>)}</tbody></table></div>}
  </div>;
}

export default History;

