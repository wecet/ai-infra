import React, { useEffect, useState } from "react";
import { api } from "../api";

function DiffPreview({ project, version, imageId, boxes, labels, width, height, classes, title }) {
  const names = Object.fromEntries(classes.map((item) => [item.id, item.name]));
  return <article className="diff-preview"><header><strong>{title}</strong><span>{version.name}</span></header>
    <div className="diff-image">{imageId ? <div className="diff-canvas" style={{ aspectRatio: `${width} / ${height}` }}><img src={`/api/projects/${project.id}/versions/${version.id}/images/${imageId}/file`} alt={`Frozen sample in ${version.name}`} />
      {!!boxes?.length && <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" aria-label={`${boxes.length} annotations`}>{boxes.map((box, index) => <g key={index}>
        <rect x={box.x} y={box.y} width={box.width} height={box.height} style={{ stroke: classes.find((item) => item.id === box.category_id)?.color || "#e76f51" }} />
        <text x={box.x + 4} y={Math.max(14, box.y + 14)}>{names[box.category_id]}</text></g>)}</svg>}
      {!!labels?.length && <div className="diff-labels">{labels.map((id) => <span key={id}>{names[id] || id}</span>)}</div>}</div> : <div className="diff-missing">Image is not present</div>}</div>
  </article>;
}

export default function VersionComparison({ project }) {
  const [versions, setVersions] = useState([]); const [left, setLeft] = useState(""); const [right, setRight] = useState("");
  const [comparison, setComparison] = useState(null); const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false); const [error, setError] = useState("");
  useEffect(() => { api(`/projects/${project.id}/versions`).then((items) => { setVersions(items); setRight(items[0]?.id || ""); setLeft(items[1]?.id || ""); }).catch((e) => setError(e.message)); }, [project.id]);
  async function compare() {
    if (!left || !right || left === right) return;
    setLoading(true); setError(""); setSelected(null);
    try { const result = await api(`/projects/${project.id}/versions/compare?left_id=${encodeURIComponent(left)}&right_id=${encodeURIComponent(right)}`); setComparison(result); setSelected(result.images.changed[0] || null); }
    catch (e) { setError(e.message); } finally { setLoading(false); }
  }
  return <div className="comparison-page"><div className="page-heading"><div><h2>Compare dataset versions</h2><p className="muted">Audit membership, annotations, classes, review decisions, data splits, and quality.</p></div></div>
    <div className="panel comparison-controls"><label>Earlier version<select value={left} onChange={(e) => setLeft(e.target.value)}><option value="">Choose version</option>{versions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <span className="comparison-arrow">→</span><label>Later version<select value={right} onChange={(e) => setRight(e.target.value)}><option value="">Choose version</option>{versions.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <button className="primary" disabled={loading || !left || !right || left === right} onClick={compare}>{loading ? "Comparing…" : "Compare"}</button></div>
    {versions.length === 1 && <div className="notice">Publish another version before running a comparison.</div>}
    {error && <div className="alert">{error}</div>}
    {comparison && <>
      <div className="comparison-summary">{Object.entries(comparison.summary).map(([key, value]) => <div key={key}><strong>{value}</strong><span>{key.replaceAll("_", " ")}</span></div>)}</div>
      <div className="comparison-columns">
        <section className="panel comparison-block"><h3>Membership</h3><div className="membership-columns"><div><strong>Added ({comparison.images.added.length})</strong>{comparison.images.added.map((path) => <span key={path}>+ {path}</span>)}</div><div><strong>Removed ({comparison.images.removed.length})</strong>{comparison.images.removed.map((path) => <span key={path}>- {path}</span>)}</div></div></section>
        <section className="panel comparison-block"><h3>Class changes</h3><div className="class-change-list"><span>Added: {comparison.classes.added.map((item) => item.name).join(", ") || "None"}</span><span>Removed: {comparison.classes.removed.map((item) => item.name).join(", ") || "None"}</span><span>Modified: {comparison.classes.changed.map((item) => `${item.before.name} → ${item.after.name}`).join(", ") || "None"}</span></div></section>
      </div>
      <section className="panel comparison-block"><h3>Quality metric changes</h3><div className="quality-diff-grid">{Object.keys(comparison.quality.left).map((key) => <div key={key}><span>{key.replaceAll("_", " ")}</span><strong>{comparison.quality.left[key]} <i>→</i> {comparison.quality.right[key]}</strong><small className={comparison.quality.delta[key] > 0 ? "warning-text" : comparison.quality.delta[key] < 0 ? "accent" : "muted"}>{comparison.quality.delta[key] > 0 ? "+" : ""}{comparison.quality.delta[key]}</small></div>)}</div>
        {(comparison.duplicates.left.approximate || comparison.duplicates.right.approximate) && <p className="muted small">Duplicate comparison used exact hashes because one version exceeds 1,000 images.</p>}</section>
      <section className="panel comparison-block"><div className="section-heading"><div><h3>Image-level changes</h3><p className="muted">Select an image for a side-by-side annotation diff.</p></div><strong>{comparison.images.changed.length}</strong></div>
        {!comparison.images.changed.length ? <div className="comparison-none">No annotation, review, or split changes.</div> : <div className="change-list">{comparison.images.changed.map((item) => <button key={item.source_path} className={selected?.source_path === item.source_path ? "selected" : ""} onClick={() => setSelected(item)}><strong>{item.source_path}</strong><span>{[item.annotation_changed && "annotations", item.review_changed && "review", item.split_changed && "split"].filter(Boolean).join(" · ")}</span></button>)}</div>}
      </section>
      {selected && <section className="annotation-diff"><div className="diff-meta"><strong>{selected.source_path}</strong><span>{selected.left_review} / {selected.left_split} → {selected.right_review} / {selected.right_split}</span></div><div className="diff-grid">
        <DiffPreview project={project} version={comparison.left} imageId={selected.left_image_id} boxes={selected.left_boxes} labels={selected.left_labels} width={selected.width} height={selected.height} classes={comparison.classes.left_catalog} title="Before" />
        <DiffPreview project={project} version={comparison.right} imageId={selected.right_image_id} boxes={selected.right_boxes} labels={selected.right_labels} width={selected.width} height={selected.height} classes={comparison.classes.right_catalog} title="After" />
      </div></section>}
    </>}
  </div>;
}
