import React, { useEffect, useState } from "react";
import { api } from "../api";
import { classColor } from "../visuals";

function AnnotationPreview({ project, image }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    api(`/projects/${project.id}/images/${image.id}`, { signal: controller.signal })
      .then(setData).catch(() => {});
    return () => controller.abort();
  }, [project.id, image.id]);
  return (
    <div className="preview-image">
      <img src={`/api/projects/${project.id}/images/${image.id}/file`} alt={image.source_path} />
      {data && project.annotation_type === "object_detection" && (
        <svg viewBox={`0 0 ${image.width} ${image.height}`} preserveAspectRatio="none">
          {data.boxes.map((box, index) => <rect key={index} x={box.x} y={box.y}
            width={box.width} height={box.height} fill={classColor(project, box.category_id)} fillOpacity=".12"
            stroke={classColor(project, box.category_id)} strokeWidth="2" vectorEffect="non-scaling-stroke" />)}
        </svg>
      )}
      {data && project.annotation_type === "image_classification" && (
        <div className="preview-labels">{data.labels.map((id) =>
          <span key={id}>{project.classes.find((item) => item.id === id)?.name}</span>)}</div>
      )}
    </div>
  );
}

function Review({ project, images, filtered, onClear, onEdit, onReviewed }) {
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [completion, setCompletion] = useState("all");
  const [count, setCount] = useState("all");
  const [selected, setSelected] = useState([]);
  const [rejecting, setRejecting] = useState(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const visible = images.filter((image) =>
    (status === "all" || image.review_status === status) &&
    (completion === "all" || image.completed === (completion === "complete")) &&
    (category === "all" || image.category_ids?.includes(Number(category))) &&
    (count === "all" || (count === "empty" ? image.annotation_count === 0 : image.annotation_count > 0)) &&
    image.source_path.toLowerCase().includes(query.trim().toLowerCase()));
  async function decide(image, nextStatus, reason = "") {
    setBusy(image.id); setError("");
    try {
      const saved = await api(`/projects/${project.id}/images/${image.id}/review`, {
        method: "PUT", body: JSON.stringify({ status: nextStatus, comment: reason }),
      });
      onReviewed(saved); setRejecting(null); setComment("");
    } catch (e) { setError(e.message); }
    finally { setBusy(""); }
  }
  async function approveSelected() {
    setBusy("bulk"); setError("");
    try {
      const result = await api(`/projects/${project.id}/review/bulk`, { method: "PUT",
        body: JSON.stringify({ image_ids: selected, status: "approved" }) });
      selected.forEach((id) => onReviewed({ id, review_status: "approved", review_comment: "",
        reviewed_by: result.reviewed_by, reviewed_at: result.reviewed_at }));
      setSelected([]);
    } catch (e) { setError(e.message); } finally { setBusy(""); }
  }
  return (
    <div>
      <div className="page-heading">
        <div><h2>Review annotations</h2><p className="muted">
          {filtered ? `${images.length} images from this history entry.` : `${images.length} project images available to search and review.`}
        </p></div>
        <div className="review-actions"><select aria-label="Filter review status" value={status}
          onChange={(e) => setStatus(e.target.value)}>
          <option value="all">All statuses</option><option value="ready_for_review">Ready for review</option>
          <option value="approved">Approved</option><option value="rejected">Rejected</option>
        </select>{filtered && <button onClick={onClear}>Show all completed</button>}</div>
      </div>
      <div className="panel review-filters">
        <input aria-label="Search images" placeholder="Search filename…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <select aria-label="Filter class" value={category} onChange={(e) => setCategory(e.target.value)}>
          <option value="all">All classes</option>{project.classes.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
        <select aria-label="Filter completion" value={completion} onChange={(e) => setCompletion(e.target.value)}>
          <option value="all">Complete and incomplete</option><option value="complete">Complete</option><option value="incomplete">Incomplete</option>
        </select>
        <select aria-label="Filter annotation count" value={count} onChange={(e) => setCount(e.target.value)}>
          <option value="all">Any annotation count</option><option value="annotated">Has annotations</option><option value="empty">No annotations</option>
        </select>
        <button className="primary" disabled={!selected.length || busy === "bulk"} onClick={approveSelected}>
          {busy === "bulk" ? "Approving…" : `Approve selected (${selected.length})`}</button>
      </div>
      {error && <div className="alert">{error}</div>}
      {!visible.length ? <div className="empty"><h2>No annotations to review</h2>
        <p>Complete an image or open a history entry containing images.</p></div> :
        <div className="review-grid">{visible.map((image) =>
          <article className="panel review-card" key={image.id}>
            <label className="review-select"><input type="checkbox" checked={selected.includes(image.id)}
              disabled={!image.completed} onChange={(e) => setSelected(e.target.checked ? [...selected, image.id] : selected.filter((id) => id !== image.id))} /> Select</label>
            <AnnotationPreview project={project} image={image} />
            <div className="review-card-footer"><div className="truncate"><strong>{image.source_path}</strong>
              <div className="muted small">{image.width} × {image.height} · {(image.review_status || "draft").replaceAll("_", " ")}</div>
              {image.review_comment && <div className="small warning-text">{image.review_comment}</div>}</div>
              <div className="review-actions"><button onClick={() => onEdit(image.id)}>Edit</button>
                <button disabled={!image.completed || busy === image.id} onClick={() => setRejecting(image)}>Reject</button>
                <button className="primary" disabled={!image.completed || busy === image.id || image.review_status === "approved"}
                  onClick={() => decide(image, "approved")}>Approve</button></div></div>
          </article>)}</div>}
      {rejecting && <div className="modal-backdrop"><form className="panel export-modal" onSubmit={(e) => {
        e.preventDefault(); decide(rejecting, "rejected", comment);
      }}><h2>Reject annotation</h2><p className="muted">Explain what should be corrected.</p>
        <textarea autoFocus required maxLength="2000" rows="4" value={comment} onChange={(e) => setComment(e.target.value)} />
        <div className="actions"><button type="button" onClick={() => { setRejecting(null); setComment(""); }}>Cancel</button>
          <button className="danger" disabled={!comment.trim() || !!busy}>Reject</button></div></form></div>}
    </div>
  );
}

export default Review;

