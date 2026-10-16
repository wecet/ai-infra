import { api } from "../api";
import React, { useState } from "react";

export default function UnlabelledImages({ project, images, onClear, onDeleted }) {
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  async function remove(image) {
    if (!window.confirm(`Remove “${image.source_path}” from this dataset? You can restore it from History.`)) return;
    setBusy(image.id); setError("");
    try { await api(`/projects/${project.id}/images/${image.id}`, { method: "DELETE" }); await onDeleted(image.id); }
    catch (error) { setError(error.message); } finally { setBusy(""); }
  }
  const visible = images.filter((image) => image.source_path.toLowerCase().includes(query.toLowerCase()));
  return <section className="panel">
    <div className="page-heading"><div><h2>Dataset images</h2><p className="muted">Unlabelled images ready for splitting and publishing.</p></div>{onClear && <button onClick={onClear}>Show all images</button>}</div>
    <input aria-label="Search dataset images" placeholder="Search image names…" value={query} onChange={(event) => setQuery(event.target.value)} />
    {error && <p className="alert" role="alert">{error}</p>}
    {!visible.length && <p className="muted">{images.length ? "No images match your search." : "Import a folder or select image files to get started."}</p>}
    <div className="version-grid">{visible.map((image) => <figure key={image.id}>
      <img loading="lazy" src={`/api/projects/${project.id}/images/${image.id}/file`} alt={image.source_path} />
      <figcaption title={image.source_path}>{image.source_path}<span>{image.width} × {image.height}</span></figcaption>
      <button disabled={project.permission === "read" || !!busy} onClick={() => remove(image)}>{busy === image.id ? "Removing…" : "Remove image"}</button>
    </figure>)}</div>
  </section>;
}
