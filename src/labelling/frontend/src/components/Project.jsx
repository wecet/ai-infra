import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import Review from "./Review";
import Settings from "./Settings";
import History from "./History";
import Versions from "./Versions";
import Editor from "./Editor";
import Dashboard from "./Dashboard";
import Training from "./Training";
import Lineage from "./Lineage";
import VersionComparison from "./VersionComparison";

function Project({ project, onLock, onRefresh, onUpdated, onDeleted }) {
  const [tab, setTab] = useState("annotate");
  const [images, setImages] = useState([]);
  const [index, setIndex] = useState(0);
  const [locked, setLocked] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiValidating, setAiValidating] = useState(false);
  const [aiError, setAiError] = useState("");
  const [reviewImages, setReviewImages] = useState(null);
  const [selectedVersion, setSelectedVersion] = useState("");
  const classification = project.annotation_type === "image_classification";
  const aiAttempts = useRef(new Set());
  async function toggleAI(e) {
    if (!e.target.checked) { setAiEnabled(false); return; }
    setAiValidating(true);
    lock(true);
    try {
      await api("/ai/validate", { method: "POST" });
      aiAttempts.current.clear();
      setAiEnabled(true);
    } catch (e) {
      setAiEnabled(false);
      setAiError(e.message);
    } finally {
      setAiValidating(false);
      lock(false);
    }
  }
  function lock(value) {
    setLocked(value);
    onLock(value);
  }
  async function refresh(resume = false) {
    try {
      const list = await api(`/projects/${project.id}/images`);
      setImages(list);
      setLoaded(true);
      if (resume) {
        const next = list.findIndex((i) => !i.completed);
        setIndex(next < 0 ? 0 : next);
      }
      onRefresh();
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => {
    refresh(true);
    return () => onLock(false);
  }, [project.id]);
  async function upload(e) {
    const files = [...e.target.files].filter((f) =>
      /\.(jpe?g|png|webp|bmp|tiff?)$/i.test(f.name),
    );
    e.target.value = "";
    if (!files.length) {
      setError(
        "No supported images found. Choose JPEG, PNG, WebP, BMP or TIFF files.",
      );
      return;
    }
    setUploading(true);
    lock(true);
    setError("");
    const failures = [];
    let batchId = null;
    if (images.length) {
      try {
        batchId = (await api(`/projects/${project.id}/batches`, {
          method: "POST", body: JSON.stringify({ kind: "new_additions" }),
        })).id;
      } catch (e) {
        setError(e.message); setUploading(false); lock(false); return;
      }
    }
    for (let i = 0; i < files.length; i++) {
      setProgress(`Importing ${i + 1} of ${files.length} · ${files[i].name}`);
      const body = new FormData();
      body.append(
        "file",
        files[i],
        files[i].webkitRelativePath || files[i].name,
      );
      try {
        await api(`/projects/${project.id}/images${batchId ? `?batch_id=${batchId}` : ""}`, { method: "POST", body });
      } catch (e) {
        failures.push(`${files[i].name}: ${e.message}`);
      }
    }
    setProgress(
      `${files.length - failures.length} of ${files.length} images imported. Reimporting identical files keeps existing progress.`,
    );
    if (failures.length)
      setError(
        `${failures.length} import(s) failed. ${failures.slice(0, 5).join(" · ")}`,
      );
    await refresh(true);
    setUploading(false);
    lock(false);
  }
  async function deleteProject() {
    if (
      !window.confirm(
        `Delete “${project.name}” and all of its images and annotations? This cannot be undone.`,
      )
    )
      return;
    lock(true);
    setError("");
    try {
      await api(`/projects/${project.id}`, { method: "DELETE" });
      onDeleted();
    } catch (e) {
      setError(e.message);
      lock(false);
    }
  }
  const current = images[index];
  return (
    <div className="page project-page">
      <div className="page-heading">
        <div>
          <h1>{project.name}</h1>
          <p className="muted">
            {classification ? "Image classification" : "Object detection"} ·{" "}
            {images.length} images <span className="separator">/</span>{" "}
            {project.classes.length} classes
          </p>
        </div>
        <div className="import-actions">
          <button
            className="danger"
            disabled={locked}
            onClick={deleteProject}
          >
            Delete project
          </button>
          <label className={`button ${locked ? "disabled" : ""}`}>
            ＋ Import folder
            <input
              type="file"
              webkitdirectory=""
              directory=""
              multiple
              hidden
              disabled={locked}
              onChange={upload}
            />
          </label>
          <label className={`text-button ${locked ? "disabled" : ""}`}>
            or select files
            <input
              type="file"
              accept=".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff"
              multiple
              hidden
              disabled={locked}
              onChange={upload}
            />
          </label>
        </div>
      </div>
      <div className="tabs">
        <button
          disabled={locked}
          className={tab === "annotate" ? "selected" : ""}
          onClick={() => setTab("annotate")}
        >
          ⌗ Annotate
        </button>
        <button
          disabled={locked}
          className={tab === "stats" ? "selected" : ""}
          onClick={() => setTab("stats")}
        >
          ▥ Dashboard
        </button>
        <button disabled={locked} className={tab === "review" ? "selected" : ""}
          onClick={() => { setReviewImages(null); setTab("review"); }}>
          ◫ Review
        </button>
        <button disabled={locked} className={tab === "history" ? "selected" : ""}
          onClick={() => setTab("history")}>
          ◷ History
        </button>
        <button disabled={locked} className={tab === "settings" ? "selected" : ""}
          onClick={() => setTab("settings")}>
          ⚙ Settings
        </button>
        <button disabled={locked} className={tab === "versions" ? "selected" : ""}
          onClick={() => setTab("versions")}>
          ◈ Versions
        </button>
        <button disabled={locked} className={tab === "training" ? "selected" : ""}
          onClick={() => setTab("training")}>
          ◉ Training
        </button>
        <button disabled={locked} className={tab === "lineage" ? "selected" : ""}
          onClick={() => setTab("lineage")}>
          ⎇ Lineage
        </button>
        <button disabled={locked} className={tab === "compare" ? "selected" : ""}
          onClick={() => setTab("compare")}>
          ⇄ Compare
        </button>
        <span>
          {images.filter((i) => i.completed).length} / {images.length} complete
        </span>
      </div>
      {!classification && tab === "annotate" && (
        <div className="notice ai-controls">
          <label className="checkbox-label">
            <input type="checkbox" checked={aiEnabled} disabled={locked || aiValidating}
              onChange={toggleAI} />
            {aiValidating ? "Validating AI credentials…" : "AI-Assisted Labelling"}
          </label>
          <span className="muted small">Sends unannotated images to OpenAI as you open them. Review suggested boxes before completing.</span>
        </div>
      )}
      {tab === "annotate" && project.labelling_instructions && (
        <div className="notice"><strong>Labelling instructions:</strong> {project.labelling_instructions}</div>
      )}
      {aiError && (
        <div className="modal-backdrop">
          <div className="panel ai-dialog" role="alertdialog" aria-modal="true" aria-labelledby="ai-error-title">
            <h2 id="ai-error-title">{aiError}</h2>
            <button className="primary" autoFocus onClick={() => setAiError("")}>OK</button>
          </div>
        </div>
      )}
      {progress && (
        <div className="notice" role="status">
          {uploading && <span className="status-dot" />}
          {progress}
        </div>
      )}
      {error && (
        <div className="alert" role="alert">
          {error}
          <button onClick={() => refresh(true)}>Refresh</button>
        </div>
      )}
      {tab === "stats" ? (
        <Dashboard project={project} onPublished={() => setTab("versions")} />
      ) : tab === "settings" ? (
        <Settings project={project} onUpdated={onUpdated} />
      ) : tab === "versions" ? (
        <Versions project={project} initialVersion={selectedVersion} />
      ) : tab === "training" ? (
        <Training project={project} />
      ) : tab === "lineage" ? (
        <Lineage project={project} onNavigate={(nextTab, id) => { if (nextTab === "versions") setSelectedVersion(id || ""); setTab(nextTab); }} />
      ) : tab === "compare" ? (
        <VersionComparison project={project} />
      ) : tab === "history" ? (
        <History project={project} onRestored={() => refresh()}
          onView={(list) => { setReviewImages(list); setTab("review"); }} />
      ) : tab === "review" ? (
        <Review project={project} images={(reviewImages || images).filter((item) => item.completed)}
          filtered={!!reviewImages} onClear={() => setReviewImages(null)}
          onReviewed={(saved) => setImages((list) => list.map((item) => item.id === saved.id ? { ...item, ...saved } : item))}
          onEdit={(id) => { const next = images.findIndex((item) => item.id === id); if (next >= 0) setIndex(next); setTab("annotate"); }} />
      ) : !loaded ? (
        <div className="empty">Loading images…</div>
      ) : !current ? (
        <div className="empty">
          <div className="empty-icon">▧</div>
          <h2>Bring your images in</h2>
          <p>
            Choose a folder on your computer using “Import folder”.
            <br />
            Subfolders are included. Your originals stay on your machine.
          </p>
          <div className="format-tags">JPEG · PNG · WEBP · BMP · TIFF</div>
        </div>
      ) : (
        <Editor
          key={current.id}
          project={project}
          image={current}
          index={index}
          total={images.length}
          images={images}
          uploading={uploading || aiValidating}
          aiEnabled={aiEnabled}
          aiAttempts={aiAttempts}
          onAIError={(message) => { setAiEnabled(false); setAiError(message); }}
          onLock={lock}
          onNavigate={setIndex}
          onSaved={(saved) => {
            setImages((list) =>
              list.map((i) =>
                i.id === saved.id ? { ...i, completed: saved.completed, review_status: saved.review_status,
                  review_comment: saved.review_comment, reviewed_by: saved.reviewed_by, reviewed_at: saved.reviewed_at,
                  annotation_count: saved.boxes.length + saved.labels.length,
                  category_ids: [...new Set([...saved.labels, ...saved.boxes.map((box) => box.category_id)])] } : i,
              ),
            );
            onRefresh();
          }}
          onDeleted={(id) => {
            setImages((list) => {
              const next = list.filter((item) => item.id !== id);
              setIndex((currentIndex) => Math.max(0, Math.min(currentIndex, next.length - 1)));
              return next;
            });
            onRefresh();
          }}
        />
      )}
    </div>
  );
}

export default Project;
