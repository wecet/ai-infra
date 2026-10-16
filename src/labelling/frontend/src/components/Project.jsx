import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import UnlabelledImages from "./UnlabelledImages";
import Review from "./Review";
import Settings from "./Settings";
import History from "./History";
import Versions from "./Versions";
import Editor from "./Editor";
import Readiness from "./Readiness";
import ModelReviewQueue from "./ModelReviewQueue";
import DatasetExplorer from "./DatasetExplorer";
import ImportStaging from "./ImportStaging";
import Activity from "./Activity";
import AnnotationImport from "./AnnotationImport";
import Dashboard from "./Dashboard";
import Training from "./Training";
import Lineage from "./Lineage";
import VersionComparison from "./VersionComparison";

const sections = [
  { label: "Label", tabs: [["annotate", "Annotate"], ["review", "Review"], ["model-review", "Model review"]] },
  { label: "Dataset", tabs: [["stats", "Dashboard"], ["explore", "Explore"], ["history", "History"], ["versions", "Versions"], ["compare", "Compare"], ["lineage", "Lineage"], ["activity", "Activity"]] },
  { label: "Training", tabs: [["training", "Training"]] },
  { label: "Manage", tabs: [["settings", "Settings"]] },
];

function Project({ project, onLock, onRefresh, onUpdated, onDeleted }) {
  const readOnly = project.permission === "read";
  const anomaly = project.annotation_type === "anomaly_detection";
  const baseSections = readOnly ? sections.filter((section) => section.label !== "Label") : sections;
  const projectSections = anomaly ? sections.filter((section) => section.label !== "Label").map((section) => section.label === "Dataset" ? { ...section, tabs: [["stats", "Dashboard"], ["images", "Images"], ...section.tabs.slice(1)] } : section) : baseSections;
  const [tab, setTab] = useState(() => {
    const remembered = window.sessionStorage.getItem(`studio-project-tab:${project.id}`);
    return projectSections.some((section) => section.tabs.some(([id]) => id === remembered)) ? remembered : anomaly || readOnly ? "stats" : "annotate";
  });
  useEffect(() => { window.sessionStorage.setItem(`studio-project-tab:${project.id}`, tab); }, [project.id, tab]);
  const [stagedFiles, setStagedFiles] = useState(null);
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
  const [selectedModelId, setSelectedModelId] = useState("");
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
  function upload(e) {
    const files = [...e.target.files]; e.target.value = "";
    if (files.length) setStagedFiles(files);
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
  const activeSection = projectSections.find((section) => section.tabs.some(([id]) => id === tab)) || projectSections[0];
  function navigate(nextTab) {
    setSelectedModelId("");
    if (nextTab === "review") setReviewImages(null);
    setTab(nextTab);
  }
  return (
    <div className="page project-page">
      {readOnly && <p className="notice">Read-only repository · owned by @{project.owner_username}. Ask the owner for write access to make changes.</p>}
      <div className="page-heading">
        <div>
          <h1>{project.name}</h1>
          <p className="muted">
            {anomaly ? "Anomaly detection · Unsupervised" : classification ? "Image classification" : "Object detection"} ·{" "}
            {images.length} images <span className="separator">/</span>{" "}
            {anomaly ? "No labels required" : `${project.classes.length} classes`}
          </p>
        </div>
        <div className="import-actions">
          <button
            className="danger"
            disabled={locked || project.permission !== "owner"}
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
              disabled={locked || readOnly}
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
              disabled={locked || readOnly}
              onChange={upload}
            />
          </label>
        </div>
      </div>
      {stagedFiles && <ImportStaging project={project} files={stagedFiles} onClose={() => setStagedFiles(null)} onImported={() => refresh(true)} />}
      <nav className="project-navigation" aria-label="Project pages">
        <div className="tabs section-tabs">
          {projectSections.map((section) => <button key={section.label} disabled={locked}
            className={section === activeSection ? "selected" : ""}
            onClick={() => navigate(section.tabs[0][0])}>{section.label}</button>)}
          <span>{anomaly ? `${images.length} images ready` : `${images.filter((i) => i.completed).length} / ${images.length} complete`}</span>
        </div>
        {activeSection.tabs.length > 1 && <div className="project-subtabs" aria-label={`${activeSection.label} pages`}>
          {activeSection.tabs.map(([id, label]) => <button key={id} disabled={locked}
            className={tab === id ? "selected" : ""} onClick={() => navigate(id)}>{label}</button>)}
        </div>}
      </nav>
      {!anomaly && !classification && tab === "annotate" && (
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
      {tab === "activity" ? <Activity project={project} /> : tab === "explore" ? <DatasetExplorer project={project} images={images} onEdit={(id) => { setIndex(images.findIndex((image) => image.id === id)); setTab("annotate"); }} /> : tab === "model-review" ? <ModelReviewQueue project={project} onEdit={(id) => { const next = images.findIndex((image) => image.id === id); if (next >= 0) { setIndex(next); setTab("annotate"); } }} /> : tab === "stats" ? (
        <div className="dataset-dashboard"><div className="dataset-preparation"><Readiness project={project} onNavigate={setTab} />{!anomaly && <AnnotationImport project={project} onImported={() => refresh()} />}</div><Dashboard project={project} onConfigure={() => setTab("settings")} onPublished={() => setTab("versions")} /></div>
      ) : tab === "images" ? (
        <UnlabelledImages project={project} images={reviewImages || images} onDeleted={async (id) => { if (reviewImages) setReviewImages((list) => list.filter((image) => image.id !== id)); await refresh(); }} onClear={reviewImages ? () => setReviewImages(null) : null} />
      ) : tab === "settings" ? (
        <Settings project={project} onUpdated={onUpdated} />
      ) : tab === "versions" ? (
        <Versions project={project} initialVersion={selectedVersion} />
      ) : tab === "training" ? (
        <Training project={project} initialModelId={selectedModelId} />
      ) : tab === "lineage" ? (
        <Lineage project={project} onNavigate={(nextTab, id) => { if (nextTab === "versions") setSelectedVersion(id || ""); if (nextTab === "training") setSelectedModelId(id || ""); setTab(nextTab); }} />
      ) : tab === "compare" ? (
        <VersionComparison project={project} />
      ) : tab === "history" ? (
        <History project={project} onRestored={() => refresh()}
          onView={(list) => { setReviewImages(list); setTab(anomaly ? "images" : "review"); }} />
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
