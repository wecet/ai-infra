import React, { useEffect, useState } from "react";
import { api } from "../api";

function Versions({ project }) {
  const [versions, setVersions] = useState(null); const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api(`/projects/${project.id}/versions`).then(setVersions).catch((e) => setError(e.message)); }, [project.id]);
  async function open(item) {
    try { setSelected(await api(`/projects/${project.id}/versions/${item.id}`)); }
    catch (e) { setError(e.message); }
  }
  return <div><div className="page-heading"><div><h2>Published versions</h2>
    <p className="muted">Immutable snapshots created from Dashboard.</p></div></div>
    {error && <div className="alert">{error}</div>}
    {versions && !versions.length && <div className="empty"><h2>No published versions</h2><p>Use Publish on Dashboard to freeze the current dataset state.</p></div>}
    {!!versions?.length && <div className="panel table-wrap"><table><thead><tr><th>VERSION</th><th>SAMPLES</th><th>PUBLISHED BY</th><th>DATE</th><th></th></tr></thead>
      <tbody>{versions.map((item) => <tr key={item.id}><td><strong>{item.name}</strong></td><td>{item.sample_count}</td>
        <td>{item.author}</td><td>{new Date(`${item.created_at}${item.created_at.endsWith("Z") ? "" : "Z"}`).toLocaleString()}</td>
        <td><button className="text-button" onClick={() => open(item)}>View snapshot</button></td></tr>)}</tbody></table></div>}
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

