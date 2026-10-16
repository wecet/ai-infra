import { formatDate } from "../dates";
import React, { useEffect, useState } from "react";
import { api } from "../api";
import { classColor } from "../visuals";

function Comments({ project }) {
  const [comments, setComments] = useState(null);
  const [body, setBody] = useState("");
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState("");
  async function load() {
    try { setComments(await api(`/projects/${project.id}/comments`)); setError(""); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); }, [project.id]);
  async function submit(e) {
    e.preventDefault();
    if (!body.trim()) return;
    setPosting(true); setError("");
    try {
      const comment = await api(`/projects/${project.id}/comments`, {
        method: "POST", body: JSON.stringify({ body }),
      });
      setComments((current) => [comment, ...(current || [])]);
      setBody("");
    } catch (e) { setError(e.message); }
    finally { setPosting(false); }
  }
  return <section className="panel comments-block">
    <div className="comments-heading"><div><h2>Comments</h2>
      <p className="muted">Share progress updates and notes with the project team.</p></div>
      <span className="tag">{comments?.length || 0} POSTS</span></div>
    <form className="comment-form" onSubmit={submit}>
      <textarea aria-label="New progress update" rows="3" maxLength="4000" required
        placeholder="Write a progress update…" value={body} disabled={posting}
        onChange={(e) => setBody(e.target.value)} />
      <div><span className="muted small">{body.length} / 4000</span>
        <button className="primary" disabled={project.permission === "read" || posting || !body.trim()}>{posting ? "Posting…" : "Post update"}</button></div>
    </form>
    {error && <div className="alert">{error}<button onClick={load}>Retry</button></div>}
    {comments && !comments.length && <div className="comment-empty">No updates yet. Start the discussion.</div>}
    <div className="comment-thread">{comments?.map((comment) => <article className="comment" key={comment.id}>
      <div className="comment-avatar" aria-hidden="true">{comment.author.slice(0, 1).toUpperCase()}</div>
      <div><header><strong>{comment.author}</strong><time dateTime={comment.created_at}>
        {formatDate(comment.created_at)}
      </time></header><p>{comment.body}</p></div>
    </article>)}</div>
  </section>;
}

function Dashboard({ project, onPublished, onConfigure }) {
  const anomaly = project.annotation_type === "anomaly_detection";
  const classification = project.annotation_type === "image_classification";
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [description, setDescription] = useState(project.description || "");
  const [train, setTrain] = useState(project.export_train_percent ?? 80);
  const [quality, setQuality] = useState(null);
  const [duplicates, setDuplicates] = useState(null);
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [publishing, setPublishing] = useState(false);
  async function load() {
    try {
      const [nextStats, nextQuality] = await Promise.all([
        api(`/projects/${project.id}/stats`), api(`/projects/${project.id}/quality`),
      ]);
      setStats(nextStats); setQuality(nextQuality);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => {
    load();
  }, [project.id]);
  async function download(e) {
    e.preventDefault();
    setExporting(true);
    setError("");
    try {
      const splits = [trainCount ? "train" : null, stats.completed - trainCount ? "test" : null].filter(Boolean);
      const exports = await Promise.all(splits.map(async (split) => {
        const response = await fetch(`/api/projects/${project.id}/export`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ description, train_percent: train, split }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(typeof body.detail === "string" ? body.detail : "Invalid export settings");
        }
        return [split, await response.blob()];
      }));
      const base = project.name.replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._-]+|[._-]+$/g, "").slice(0, 80) || "project";
      exports.forEach(([split, blob], index) => {
        const url = URL.createObjectURL(blob);
        setTimeout(() => {
          const a = document.createElement("a"); a.href = url; a.download = `${base}_${split}.zip`;
          document.body.appendChild(a); a.click(); a.remove();
          setTimeout(() => URL.revokeObjectURL(url), 60000);
        }, index * 250);
      });
      setShowExport(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setExporting(false);
    }
  }
  async function openDuplicates() {
    setShowDuplicates(true);
    if (duplicates) return;
    try { setDuplicates(await api(`/projects/${project.id}/duplicates`)); }
    catch (e) { setError(e.message); setShowDuplicates(false); }
  }
  async function publish() {
    setPublishing(true); setError("");
    try { await api(`/projects/${project.id}/publish`, { method: "POST" }); onPublished(); }
    catch (e) { setError(e.message); } finally { setPublishing(false); }
  }
  const trainCount = stats
    ? Math.floor((stats.completed * train) / 100 + 0.5)
    : 0;
  return (
    <div className="stats-page">
      {error && (
        <div className="alert" role="alert">
          {error}
          <button onClick={load}>Retry</button>
        </div>
      )}
      {stats && (
        <>
          <div className="page-heading">
            <div>
              <h2>Dataset overview</h2>
              <p className="muted">
                {project.description || (anomaly ? "Unlabelled data, frozen splits, and anomaly training." : "A clear picture of your labelling progress.")}
              </p>
            </div>
            <div className="actions"><button disabled={project.permission === "read" || publishing || !stats.completed} onClick={publish}>
              {publishing ? "Publishing…" : "◈ Publish"}</button>
              <button className="primary" disabled={!stats.completed || exporting} onClick={() => setShowExport(true)}>
                ↓ Export dataset</button></div>
          </div>
          <div className="kpi-grid">
            {(anomaly ? [
              ["TOTAL IMAGES", stats.total, "Unlabelled images ready to publish"],
              ["TRAIN IMAGES", Math.floor(stats.total * (project.export_train_percent ?? 80) / 100 + 0.5), "Used to fit the anomaly model"],
              ["TEST IMAGES", stats.total - Math.floor(stats.total * (project.export_train_percent ?? 80) / 100 + 0.5), "Held out for anomaly scoring"],
              ["SIMILAR IMAGES", stats.similar_images, `${stats.similar_groups} groups · inspect images`, true],
            ] : [
              ["TOTAL IMAGES", stats.total, "Across this project"],
              [
                "LABELLED",
                stats.completed,
                `${stats.total ? Math.round((stats.completed / stats.total) * 100) : 0}% complete`,
              ],
              ["REMAINING", stats.remaining, "Ready for your attention"],
              ["READY FOR REVIEW", stats.review.ready_for_review, "Completed and awaiting a decision"],
              ["APPROVED", stats.review.approved, `${stats.review.rejected} rejected`],
              [classification ? "IMAGE LABELS" : "BOUNDING BOXES", classification ? stats.labels : stats.boxes, "On completed images"],
              ["SIMILAR IMAGES", stats.similar_images, `${stats.similar_groups} groups · click to review`, true],
            ]).map(([label, value, note, clickable]) => {
              const Component = clickable ? "button" : "div";
              const tone = {
                "TRAIN IMAGES": "data", "TEST IMAGES": "data", "TOTAL IMAGES": "data", "LABELLED": "complete", "REMAINING": "attention",
                "READY FOR REVIEW": "attention", "APPROVED": "complete",
                "IMAGE LABELS": "data", "BOUNDING BOXES": "data", "SIMILAR IMAGES": "attention",
              }[label];

              return <Component className={`panel kpi kpi-${tone} ${clickable ? "kpi-button" : ""}`} key={label}
                disabled={clickable && !value} onClick={clickable ? openDuplicates : undefined}>
                <div className="eyebrow">{label}</div>
                <strong>{value}</strong>
                <span className="muted small">{note}</span>
              </Component>;
            })}
          </div>
          {anomaly && <div className="notice">Unsupervised dataset · {project.export_train_percent ?? 80}% train / {100 - (project.export_train_percent ?? 80)}% test. Publishing freezes this split. <button onClick={onConfigure}>Configure split</button></div>}
          {quality && <section className="panel quality-panel"><div className="section-heading"><div>
            <h2>Dataset quality</h2><p className="muted">{anomaly ? "Checks for similar images and leakage across the saved split." : "Automatic checks for annotation and split problems."}</p>
          </div><span className="tag">{quality.checks_run} CHECKS</span></div>
            {!quality.issues.length ? <div className="notice">No quality issues found.</div> :
              <div className="quality-list">{quality.issues.map((issue) => <article key={issue.code}
                className={`quality-issue ${issue.severity}`}><strong>{issue.title}</strong>
                <span className="quality-count">{issue.count}</span><p>{issue.detail}</p></article>)}</div>}
          </section>}
          {!anomaly && <div className="panel representation">
            <h2>Class representation</h2>
            <p className="muted">
              {classification ? "Image labels" : "Bounding boxes"} and distinct images for each class, on completed
              images only.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>CLASS</th>
                    <th>{classification ? "DISTRIBUTION OF LABELS" : "DISTRIBUTION OF BOXES"}</th>
                    <th>{classification ? "LABELS" : "BOXES"}</th>
                    <th>IMAGES</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.classes.map((c) => (
                    <tr key={c.id}>
                      <td>
                        <span
                          className="small-dot"
                          style={{ background: classColor(project, c.id) }}
                        />
                        {c.name}
                      </td>
                      <td>
                        <div className="distribution">
                          <div className="progress-track">
                            <span
                              style={{
                                width: `${(classification ? stats.labels : stats.boxes) ? ((classification ? c.labels : c.boxes) / (classification ? stats.labels : stats.boxes)) * 100 : 0}%`,
                                background: classColor(project, c.id),
                              }}
                            />
                          </div>
                          <span>
                            {(classification ? stats.labels : stats.boxes)
                              ? Math.round(((classification ? c.labels : c.boxes) / (classification ? stats.labels : stats.boxes)) * 100)
                              : 0}
                            %
                          </span>
                        </div>
                      </td>
                      <td>{classification ? c.labels : c.boxes}</td>
                      <td>{c.images}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          }
          <Comments project={project} />
          {showDuplicates && <div className="modal-backdrop"><div className="panel duplicate-modal"
            role="dialog" aria-modal="true" aria-labelledby="duplicate-title">
            <div className="modal-heading"><div><div className="eyebrow">DATASET QUALITY</div>
              <h2 id="duplicate-title">Similar image groups</h2></div>
              <button onClick={() => setShowDuplicates(false)}>Close</button></div>
            {!duplicates ? <p>Analysing images…</p> : <div className="duplicate-groups">
              {duplicates.groups.map((group, index) => <section key={group.id}>
                <h3>Group {index + 1} <span className="muted small">· {group.images.length} images</span></h3>
                <div className="duplicate-row">{group.images.map((image) => <figure key={image.id}>
                  <img src={`/api/projects/${project.id}/images/${image.id}/file`} alt={image.source_path} />
                  <figcaption title={image.source_path}>{image.source_path}</figcaption></figure>)}</div>
              </section>)}</div>}
          </div></div>}
          {showExport && (
            <div className="modal-backdrop">
              <form
                className="panel export-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="export-title"
                onSubmit={download}
              >
                <div className="eyebrow">{anomaly ? "UNLABELLED ANOMALY DATASET" : classification ? "CLASSIFICATION DATASET" : "COCO DATASET"}</div>
                <h2 id="export-title">{anomaly ? "Export your images" : "Export your annotations"}</h2>
                <p className="muted">
                  Download {trainCount && stats.completed - trainCount ? "separate" : "an"} import-compatible {trainCount && stats.completed - trainCount ? "archives" : "archive"}: {trainCount ? <strong>{project.name}_train.zip</strong> : null}{trainCount && stats.completed - trainCount ? " and " : null}{stats.completed - trainCount ? <strong>{project.name}_test.zip</strong> : null}. Empty splits are skipped.
                </p>
                <label>
                  Description <span className="muted">(optional)</span>
                  <textarea
                    autoFocus
                    maxLength={1000}
                    rows={4}
                    placeholder="Describe the dataset, source, purpose, or labelling criteria."
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </label>
                <div className="split-heading">
                  <label htmlFor="train">Train</label>
                  <strong>
                    {train}%{" "}
                    <span className="muted">· {trainCount} images</span>
                  </strong>
                </div>
                <input
                  id="train"
                  type="range"
                  min="0"
                  max="100"
                  value={train}
                  onChange={(e) => setTrain(Number(e.target.value))}
                />
                <div className="split-heading">
                  <label htmlFor="test">Test</label>
                  <strong>
                    {100 - train}%{" "}
                    <span className="muted">
                      · {stats.completed - trainCount} images
                    </span>
                  </strong>
                </div>
                <input
                  id="test"
                  type="range"
                  min="0"
                  max="100"
                  value={100 - train}
                  onChange={(e) => setTrain(100 - Number(e.target.value))}
                />
                <p className="muted small">
                  Sliders stay linked to total 100%. Images are randomly split
                  with a fixed seed for repeatable exports. Small datasets may
                  produce an empty split.
                </p>
                {error && (
                  <p className="alert" role="alert">
                    {error}
                  </p>
                )}
                <div className="actions">
                  <button
                    type="button"
                    disabled={exporting}
                    onClick={() => setShowExport(false)}
                  >
                    Cancel
                  </button>
                  <button className="primary" disabled={exporting}>
                    {exporting ? "Preparing exports…" : trainCount && stats.completed - trainCount ? "Download train & test ↓" : "Download dataset ↓"}
                  </button>
                </div>
              </form>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default Dashboard;
