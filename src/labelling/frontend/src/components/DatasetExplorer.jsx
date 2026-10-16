import React, { useEffect, useState } from "react";
import { api } from "../api";

export default function DatasetExplorer({ project, images, onEdit }) {
  const [query, setQuery] = useState(""); const [width, setWidth] = useState(0); const [height, setHeight] = useState(0);
  const [status, setStatus] = useState(""); const [category, setCategory] = useState(""); const [annotation, setAnnotation] = useState("");
  const [duplicates, setDuplicates] = useState(null); const [similar, setSimilar] = useState(false); const [error, setError] = useState(""); const [page, setPage] = useState(0);
  async function loadDuplicates() { try { const value = await api(`/projects/${project.id}/duplicates`); setDuplicates(new Set(value.groups.flatMap((g) => g.images.map((i) => i.id)))); } catch (e) { setError(e.message); } }
  useEffect(() => { setPage(0); }, [query, width, height, status, category, annotation, similar]);
  const visible = images.filter((row) => row.source_path.toLowerCase().includes(query.toLowerCase()) && row.width >= width && row.height >= height && (!status || row.review_status === status) && (!category || row.category_ids.includes(Number(category))) && (!annotation || (annotation === 'empty' ? !row.annotation_count : row.annotation_count > 0)) && (!similar || duplicates?.has(row.id)));
  return <section className="panel workspace-panel"><h2>Explore dataset</h2><div className="training-grid"><label>Source/name<input value={query} onChange={(e) => setQuery(e.target.value)} /></label>
    <label>Minimum width<input type="number" min="0" value={width} onChange={(e) => setWidth(Number(e.target.value))} /></label><label>Minimum height<input type="number" min="0" value={height} onChange={(e) => setHeight(Number(e.target.value))} /></label>
    {project.annotation_type !== 'anomaly_detection' && <><label>Review status<select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All</option>{['draft','ready_for_review','approved','rejected'].map((v) => <option key={v}>{v}</option>)}</select></label>
    <label>Class<select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">All</option>{project.classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label><label>Annotations<select value={annotation} onChange={(e) => setAnnotation(e.target.value)}><option value="">All</option><option value="empty">Empty</option><option value="present">Present</option></select></label></>}
    <label className="checkbox-label"><input type="checkbox" checked={similar} onChange={(e) => { setSimilar(e.target.checked); if (!duplicates) loadDuplicates(); }} /> Similar images only</label></div>
    {error && <p role="alert">{error}</p>}<p>{visible.length} matches</p><div className="evaluation-actions"><button disabled={!page} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page + 1}</span><button disabled={(page + 1) * 24 >= visible.length} onClick={() => setPage(page + 1)}>Next</button></div>
    <div className="evaluation-grid">{visible.slice(page * 24, (page + 1) * 24).map((row) => <figure key={row.id}><img width="180" loading="lazy" src={`/api/projects/${project.id}/images/${row.id}/file`} alt={row.source_path}/><figcaption>{row.source_path} · {row.width} × {row.height} · {row.annotation_count} annotations · {row.review_status}</figcaption>{project.annotation_type !== 'anomaly_detection' && project.permission !== 'read' && <button onClick={() => onEdit(row.id)}>Annotate</button>}</figure>)}</div>
  </section>;
}
