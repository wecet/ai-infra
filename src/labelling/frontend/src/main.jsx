import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, color } from "./api";
import "./style.css";

function App() {
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [locked, setLocked] = useState(false);
  const [importingProject, setImportingProject] = useState(false);
  const [importProjectError, setImportProjectError] = useState("");
  const [pendingImportFile, setPendingImportFile] = useState(null);
  const [importProjectName, setImportProjectName] = useState("");
  async function refresh() {
    try {
      setProjects(await api("/projects"));
    } catch (e) {
      setError(e.message);
    }
  }
  useEffect(() => {
    refresh();
  }, []);
  async function open(id) {
    try {
      setProject(await api(`/projects/${id}`));
      setCreating(false);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }
  function chooseImportProject(e) {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    setPendingImportFile(file);
    setImportProjectName(file.name.replace(/\.zip$/i, ""));
    setImportProjectError("");
  }
  async function importProject(e) {
    e.preventDefault();
    if (!pendingImportFile || !importProjectName.trim()) return;
    setImportingProject(true); setError(""); setImportProjectError("");
    const body = new FormData();
    body.append("name", importProjectName.trim());
    body.append("file", pendingImportFile);
    try {
      const result = await api("/projects/import", { method: "POST", body });
      await refresh();
      setProject(result.project);
      setCreating(false);
      setPendingImportFile(null);
      setImportProjectName("");
    } catch (e) { setImportProjectError(e.message); }
    finally { setImportingProject(false); }
  }
  return (
    <div className="app-shell">
      <header className="masthead">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            if (!locked) {
              setProject(null);
              setCreating(false);
              refresh();
            }
          }}
        >
          <span className="brand-wordmark">OPENIIOT</span>
          <span>Labelling Studio</span>
        </a>
        <span className="tag">IMAGE ANNOTATION</span>
      </header>
      <nav className="workspace-bar" aria-label="Workspace navigation">
        <label className="workspace-selector">
          <span>PROJECT</span>
          <select
            aria-label="Select project"
            value={project?.id || ""}
            disabled={locked}
            onChange={(e) => {
              if (e.target.value) open(e.target.value);
              else {
                setProject(null);
                setCreating(false);
                refresh();
              }
            }}
          >
            <option value="">All projects</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <span className="workspace-summary">
          {project
            ? `${project.classes.length} classes`
            : `${projects.length} projects`}
        </span>
        <div className="workspace-actions">
          <button
            className={!project && !creating ? "active" : ""}
            disabled={locked}
            onClick={() => {
              setProject(null);
              setCreating(false);
              refresh();
            }}
          >
            All projects
          </button>
          <button
            className={creating ? "active" : ""}
            disabled={locked}
            onClick={() => {
              setProject(null);
              setCreating(true);
            }}
          >
            New project
          </button>
        </div>
      </nav>
      <main>
        {error && (
          <div className="alert" role="alert">
            {error}
            <button onClick={refresh}>Retry</button>
          </div>
        )}
        {project ? (
          <Project
            key={project.id}
            project={project}
            onLock={setLocked}
            onRefresh={refresh}
            onUpdated={(next) => { setProject(next); refresh(); }}
            onDeleted={() => {
              setProject(null);
              setLocked(false);
              refresh();
            }}
          />
        ) : (
          <div className="page">
            <div className="page-heading">
              <div>
                <h1>Projects</h1>
                <p className="muted">
                  Create and manage image annotation projects. Progress is saved
                  automatically.
                </p>
              </div>
              <div className="homepage-actions">
                <label className={`button ${importingProject ? "disabled" : ""}`}>
                  {importingProject ? "Importing project…" : "↑ Import Project"}
                  <input type="file" accept=".zip" hidden disabled={importingProject} onChange={chooseImportProject} />
                </label>
                <button className="primary" disabled={importingProject} onClick={() => setCreating(true)}>
                  ＋ New project
                </button>
              </div>
            </div>
            {creating && (
              <CreateProject
                onCancel={() => setCreating(false)}
                onCreated={(p) => {
                  setProject(p);
                  setCreating(false);
                  refresh();
                }}
              />
            )}
            <div className="project-grid">
              {projects.map((p) => (
                <button
                  className="project-card"
                  key={p.id}
                  onClick={() => open(p.id)}
                >
                  <div className="card-top">
                    <span className="folder-icon">▱</span>
                    <span className="tag">
                      {p.total && p.completed === p.total
                        ? "COMPLETE"
                        : "IN PROGRESS"}
                    </span>
                  </div>
                  <h2>{p.name}</h2>
                  <p>
                    {p.total} images{" "}
                    <span className="muted">· {p.completed} labelled</span>
                  </p>
                  <div className="progress-track">
                    <span
                      style={{
                        width: `${p.total ? (p.completed / p.total) * 100 : 0}%`,
                      }}
                    />
                  </div>
                  <div className="card-bottom">
                    <span>
                      {p.total ? Math.round((p.completed / p.total) * 100) : 0}%
                      complete
                    </span>
                    <span>Open project ↗</span>
                  </div>
                </button>
              ))}
            </div>
            {!projects.length && !creating && (
              <div className="empty">
                <div className="empty-icon">⌗</div>
                <h2>A home for your datasets</h2>
                <p>
                  Create a project, define your classes, and import a folder of
                  images.
                </p>
                <button className="primary" onClick={() => setCreating(true)}>
                  Create your first project
                </button>
              </div>
            )}
          </div>
        )}
      </main>
      {pendingImportFile && !importProjectError && (
        <div className="modal-backdrop">
          <form className="panel import-name-dialog" role="dialog" aria-modal="true"
            aria-labelledby="import-name-title" onSubmit={importProject}>
            <div className="eyebrow">IMPORT PROJECT</div>
            <h2 id="import-name-title">Name this project</h2>
            <p className="muted">Choose the name that will appear in the project repository.</p>
            <label>Project name
              <input autoFocus required maxLength="150" value={importProjectName}
                disabled={importingProject} onChange={(e) => setImportProjectName(e.target.value)} />
            </label>
            <p className="muted small truncate" title={pendingImportFile.name}>ZIP: {pendingImportFile.name}</p>
            <div className="actions">
              <button type="button" disabled={importingProject} onClick={() => {
                setPendingImportFile(null); setImportProjectName("");
              }}>Cancel</button>
              <button className="primary" disabled={importingProject || !importProjectName.trim()}>
                {importingProject ? "Importing project…" : "Import project"}
              </button>
            </div>
          </form>
        </div>
      )}
      {importProjectError && (
        <div className="modal-backdrop">
          <div className="panel import-error-dialog" role="alertdialog" aria-modal="true"
            aria-labelledby="import-error-title" aria-describedby="import-error-description">
            <div className="eyebrow">PROJECT IMPORT FAILED</div>
            <h2 id="import-error-title">Check the ZIP folder structure</h2>
            <p id="import-error-description" className="alert">{importProjectError}</p>
            <p>Your ZIP must contain these folders at its root:</p>
            <pre className="zip-tree">{`project.zip
├── annotations/
│   └── annotations.json
└── images/
    ├── image-001.jpg
    └── image-002.png`}</pre>
            <p className="muted small">The annotation JSON must contain COCO-compatible <code>images</code>, <code>categories</code>, and <code>annotations</code> fields. Image paths in the JSON must match files in the <code>images/</code> folder.</p>
            <div className="actions"><button className="primary" autoFocus
              onClick={() => { setImportProjectError(""); setPendingImportFile(null); setImportProjectName(""); }}>
              Close and try again</button></div>
          </div>
        </div>
      )}
      <footer className="app-footer">OpenIIoT · Labelling Studio</footer>
    </div>
  );
}

function CreateProject({ onCancel, onCreated }) {
  const [name, setName] = useState("");
  const [annotationType, setAnnotationType] = useState("object_detection");
  const [classes, setClasses] = useState([""]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onCreated(
        await api("/projects", {
          method: "POST",
          body: JSON.stringify({ name, classes, annotation_type: annotationType }),
        }),
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop">
    <form className="panel create-form" role="dialog" aria-modal="true" aria-labelledby="create-title" onSubmit={submit}>
      <div className="eyebrow">NEW PROJECT</div>
      <h2 id="create-title">Set up your dataset</h2>
      <fieldset className="task-selection">
        <legend>Annotation type — choose one</legend>
        {[["object_detection", "Object detection"], ["image_classification", "Image classification"]].map(([value, label]) => (
          <label className="checkbox-label" key={value}>
            <input type="checkbox" checked={annotationType === value} disabled={busy}
              onChange={() => setAnnotationType(value)} />
            {label}
          </label>
        ))}
      </fieldset>
      <label>
        Project name
        <input
          autoFocus
          required
          maxLength={150}
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Warehouse object detection"
        />
      </label>
      <label>
        Classes <span className="muted">— one name per class</span>
      </label>
      <div className="class-inputs">
        {classes.map((c, i) => (
          <div className="class-input" key={i}>
            <span className="small-dot" style={{ background: color(i + 1) }} />
            <input
              required
              maxLength={100}
              aria-label={`Class ${i + 1}`}
              value={c}
              onChange={(e) =>
                setClasses(
                  classes.map((v, j) => (i === j ? e.target.value : v)),
                )
              }
              placeholder={`Class ${i + 1}`}
            />
            <button
              type="button"
              aria-label={`Remove class ${i + 1}`}
              disabled={classes.length === 1 || busy}
              onClick={() => setClasses(classes.filter((_, j) => i !== j))}
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        className="text-button"
        disabled={busy}
        onClick={() => setClasses([...classes, ""])}
      >
        ＋ Add class
      </button>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <div className="actions">
        <button type="button" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
        <button className="primary" disabled={busy}>
          {busy ? "Creating…" : "Create project →"}
        </button>
      </div>
    </form>
    </div>
  );
}

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
        <Stats project={project} />
      ) : tab === "settings" ? (
        <Settings project={project} onUpdated={onUpdated} />
      ) : tab === "history" ? (
        <History project={project} onRestored={() => refresh()}
          onView={(list) => { setReviewImages(list); setTab("review"); }} />
      ) : tab === "review" ? (
        <Review project={project} images={reviewImages || images.filter((item) => item.completed)}
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
                  review_comment: saved.review_comment, reviewed_by: saved.reviewed_by, reviewed_at: saved.reviewed_at } : i,
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
            width={box.width} height={box.height} fill={color(box.category_id)} fillOpacity=".12"
            stroke={color(box.category_id)} strokeWidth="2" vectorEffect="non-scaling-stroke" />)}
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
  const [rejecting, setRejecting] = useState(null);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const visible = status === "all" ? images : images.filter((image) => image.review_status === status);
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
  return (
    <div>
      <div className="page-heading">
        <div><h2>Review annotations</h2><p className="muted">
          {filtered ? `${images.length} images from this history entry.` : `${images.length} completed images ready for review.`}
        </p></div>
        <div className="review-actions"><select aria-label="Filter review status" value={status}
          onChange={(e) => setStatus(e.target.value)}>
          <option value="all">All statuses</option><option value="ready_for_review">Ready for review</option>
          <option value="approved">Approved</option><option value="rejected">Rejected</option>
        </select>{filtered && <button onClick={onClear}>Show all completed</button>}</div>
      </div>
      {error && <div className="alert">{error}</div>}
      {!visible.length ? <div className="empty"><h2>No annotations to review</h2>
        <p>Complete an image or open a history entry containing images.</p></div> :
        <div className="review-grid">{visible.map((image) =>
          <article className="panel review-card" key={image.id}>
            <AnnotationPreview project={project} image={image} />
            <div className="review-card-footer"><div className="truncate"><strong>{image.source_path}</strong>
              <div className="muted small">{image.width} × {image.height} · {(image.review_status || "draft").replaceAll("_", " ")}</div>
              {image.review_comment && <div className="small warning-text">{image.review_comment}</div>}</div>
              <div className="review-actions"><button onClick={() => onEdit(image.id)}>Edit</button>
                <button disabled={busy === image.id} onClick={() => setRejecting(image)}>Reject</button>
                <button className="primary" disabled={busy === image.id || image.review_status === "approved"}
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

function Settings({ project, onUpdated }) {
  const [form, setForm] = useState({ name: project.name, description: project.description || "",
    labelling_instructions: project.labelling_instructions || "", ai_instructions: project.ai_instructions || "",
    export_train_percent: project.export_train_percent ?? 80 });
  const [saving, setSaving] = useState(false); const [message, setMessage] = useState("");
  function field(name) { return { value: form[name], onChange: (e) => setForm({ ...form,
    [name]: e.target.type === "number" ? Number(e.target.value) : e.target.value }) }; }
  async function submit(e) {
    e.preventDefault(); setSaving(true); setMessage("");
    try { const saved = await api(`/projects/${project.id}`, { method: "PUT", body: JSON.stringify(form) });
      onUpdated(saved); setMessage("Project settings saved."); }
    catch (e) { setMessage(e.message); } finally { setSaving(false); }
  }
  return <form className="panel settings-form" onSubmit={submit}><div><h2>Project settings</h2>
    <p className="muted">Guidance is shared with labellers. AI guidance is also included in automatic suggestions.</p></div>
    <label>Project name<input required maxLength="150" {...field("name")} /></label>
    <label>Description<textarea rows="3" maxLength="2000" placeholder="Purpose, source, and scope of this dataset." {...field("description")} /></label>
    <label>Labelling instructions<textarea rows="5" maxLength="4000" placeholder="Rules labellers should follow." {...field("labelling_instructions")} /></label>
    {project.annotation_type === "object_detection" && <label>AI instructions<textarea rows="5" maxLength="4000"
      placeholder="Project-specific criteria for AI-generated boxes." {...field("ai_instructions")} /></label>}
    <label>Default train split (%)<input type="number" min="0" max="100" {...field("export_train_percent")} /></label>
    {message && <div className={message.endsWith("saved.") ? "notice" : "alert"}>{message}</div>}
    <div className="actions"><button className="primary" disabled={saving}>{saving ? "Saving…" : "Save settings"}</button></div>
  </form>;
}

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
      <td>v{entry.version}</td><td>{entry.kind === "project_created" ? "Project Created" : entry.kind === "images_deleted" ? "Images Deleted" : entry.kind === "images_restored" ? "Images Restored" : "New Additions"}</td>
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

function Editor({
  project,
  image,
  index,
  total,
  images,
  uploading,
  aiEnabled,
  aiAttempts,
  onAIError,
  onLock,
  onNavigate,
  onSaved,
  onDeleted,
}) {
  const [data, setData] = useState(null);
  const [category, setCategory] = useState(project.classes[0].id);
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [aiWorking, setAiWorking] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [brightness, setBrightness] = useState(100);
  const [contrast, setContrast] = useState(100);
  const [panMode, setPanMode] = useState(false);
  const svg = useRef(null);
  const editorElement = useRef(null);
  const canvasScroll = useRef(null);
  const panGesture = useRef(null);
  const gesture = useRef(null);
  const inFlight = useRef(false);
  const undoStack = useRef([]);
  const redoStack = useRef([]);
  const path = `/projects/${project.id}/images/${image.id}`;
  const classification = project.annotation_type === "image_classification";
  useEffect(() => {
    const controller = new AbortController();
    api(path, { signal: controller.signal })
      .then((next) => { setData(next); undoStack.current = []; redoStack.current = []; })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [path]);
  useEffect(() => {
    if (!aiEnabled || classification || !data || data.revision !== 0 || data.completed || data.boxes.length ||
        dirty || uploading || inFlight.current || aiAttempts.current.has(image.id)) return;
    aiAttempts.current.add(image.id);
    inFlight.current = true;
    setAiWorking(true);
    setSaving(true);
    api(`${path}/ai`, { method: "POST", body: JSON.stringify({ revision: data.revision }) })
      .then((saved) => { setData(saved); onSaved(saved); })
      .catch((e) => { onAIError(e.message); })
      .finally(() => { inFlight.current = false; setSaving(false); setAiWorking(false); });
  }, [aiEnabled, data, path, dirty, uploading, classification]);
  useEffect(() => {
    onLock(saving || dirty || uploading || !!draft);
  }, [saving, dirty, uploading, !!draft]);
  useEffect(() => {
    function prevent(e) {
      if (saving || dirty || uploading) {
        e.preventDefault();
        e.returnValue = "";
      }
    }
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [saving, dirty, uploading]);
  async function persist(next, record = true) {
    if (inFlight.current) return false;
    if (record && data) {
      undoStack.current.push(structuredClone(data));
      if (undoStack.current.length > 50) undoStack.current.shift();
      redoStack.current = [];
    }
    inFlight.current = true;
    setData(next);
    setDirty(true);
    setSaving(true);
    setError("");
    try {
      const saved = await api(path, {
        method: "PUT",
        body: JSON.stringify(next),
      });
      setData(saved);
      setDirty(false);
      onSaved(saved);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }
  const disabled = saving || uploading || !ready || !data;
  function point(e) {
    const rect = svg.current.getBoundingClientRect();
    return {
      x: Math.max(
        0,
        Math.min(
          image.width,
          ((e.clientX - rect.left) / rect.width) * image.width,
        ),
      ),
      y: Math.max(
        0,
        Math.min(
          image.height,
          ((e.clientY - rect.top) / rect.height) * image.height,
        ),
      ),
    };
  }
  function start(e, boxIndex = null, resize = false) {
    if (classification || disabled || dirty || inFlight.current || e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const p = point(e);
    svg.current.setPointerCapture(e.pointerId);
    gesture.current = {
      start: p,
      index: boxIndex,
      resize,
      original: boxIndex !== null ? { ...data.boxes[boxIndex] } : null,
    };
    setSelected(boxIndex);
    setDraft(
      boxIndex !== null
        ? { ...data.boxes[boxIndex] }
        : { category_id: category, x: p.x, y: p.y, width: 0, height: 0 },
    );
  }
  function move(e) {
    const g = gesture.current;
    if (!g) return;
    const p = point(e);
    if (g.original) {
      const b = g.original;
      setDraft(
        g.resize
          ? {
              ...b,
              width: Math.max(1, p.x - b.x),
              height: Math.max(1, p.y - b.y),
            }
          : {
              ...b,
              x: Math.max(
                0,
                Math.min(image.width - b.width, b.x + p.x - g.start.x),
              ),
              y: Math.max(
                0,
                Math.min(image.height - b.height, b.y + p.y - g.start.y),
              ),
            },
      );
    } else
      setDraft({
        category_id: category,
        x: Math.min(p.x, g.start.x),
        y: Math.min(p.y, g.start.y),
        width: Math.abs(p.x - g.start.x),
        height: Math.abs(p.y - g.start.y),
      });
  }
  function end() {
    const g = gesture.current;
    if (!g) return;
    gesture.current = null;
    setDraft(null);
    if (!draft || draft.width < 1 || draft.height < 1) return;
    const boxes =
      g.index === null
        ? [...data.boxes, draft]
        : data.boxes.map((b, i) => (i === g.index ? draft : b));
    setSelected(g.index === null ? boxes.length - 1 : g.index);
    persist({ ...data, boxes });
  }
  async function complete() {
    if (await persist({ ...data, completed: true })) {
      if (index < total - 1) onNavigate(index + 1);
    }
  }
  async function deleteCurrentImage() {
    if (!window.confirm(`Delete “${image.source_path}” from this dataset? Its annotations will also be removed.`)) return;
    setSaving(true); setError("");
    try {
      await api(path, { method: "DELETE" });
      onDeleted(image.id);
    } catch (e) { setError(e.message); setSaving(false); }
  }
  async function undo() {
    if (!undoStack.current.length || disabled || dirty) return;
    const previous = undoStack.current.pop();
    redoStack.current.push(structuredClone(data));
    if (!(await persist({ ...previous, revision: data.revision }, false))) {
      undoStack.current.push(previous); redoStack.current.pop();
    }
  }
  async function redo() {
    if (!redoStack.current.length || disabled || dirty) return;
    const next = redoStack.current.pop();
    undoStack.current.push(structuredClone(data));
    if (!(await persist({ ...next, revision: data.revision }, false))) {
      redoStack.current.push(next); undoStack.current.pop();
    }
  }
  function deleteSelected() {
    if (selected === null || classification || disabled || dirty) return;
    persist({ ...data, boxes: data.boxes.filter((_, i) => i !== selected) });
    setSelected(null);
  }
  useEffect(() => {
    function shortcut(e) {
      if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;
      const modifier = e.ctrlKey || e.metaKey;
      if (modifier && e.key.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
      if (modifier && e.key.toLowerCase() === "y") { e.preventDefault(); redo(); return; }
      if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); deleteSelected(); }
      else if (e.key === "ArrowLeft" && index > 0 && !saving && !dirty) onNavigate(index - 1);
      else if (e.key === "ArrowRight" && index < total - 1 && !saving && !dirty) onNavigate(index + 1);
      else if (e.key === "Enter" && !disabled && !dirty) complete();
      else if ((e.key === "+" || e.key === "=") && zoom < 3) setZoom((value) => Math.min(3, value + .25));
      else if (e.key === "-" && zoom > 1) setZoom((value) => Math.max(1, value - .25));
      else if (/^[1-9]$/.test(e.key) && project.classes[Number(e.key) - 1]) setCategory(project.classes[Number(e.key) - 1].id);
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [data, selected, disabled, dirty, saving, index, total, zoom]);
  const boxes = data?.boxes || [];
  const displayBoxes = boxes.map((b, i) =>
    draft && gesture.current?.index === i ? draft : b,
  );
  if (draft && gesture.current?.index === null) displayBoxes.push(draft);
  return (
    <>
      {error && (
        <div className="alert" role="alert">
          {error}{" "}
          {dirty && (
            <button disabled={saving} onClick={() => persist(data)}>
              Retry save
            </button>
          )}
          <button
            disabled={saving}
            onClick={() => {
              if (
                !dirty ||
                window.confirm("Discard unsaved changes and reload this image?")
              ) {
                api(path)
                  .then((d) => {
                    setData(d);
                    setDirty(false);
                    setError("");
                  })
                  .catch((e) => setError(e.message));
              }
            }}
          >
            Reload image
          </button>
        </div>
      )}
      <div className="editor" ref={editorElement}>
        <section className="canvas-panel">
          <div className="canvas-toolbar">
            <span className="truncate">{image.source_path}</span>
            <span className="muted">
              {image.width} × {image.height}
            </span>
            <div className="zoom-controls">
              <button aria-label="Undo" disabled={!undoStack.current.length || disabled || dirty} onClick={undo}>↶</button>
              <button aria-label="Redo" disabled={!redoStack.current.length || disabled || dirty} onClick={redo}>↷</button>
              <button className={panMode ? "chosen" : ""} aria-pressed={panMode}
                onClick={() => setPanMode((value) => !value)}>Pan</button>
              <button
                aria-label="Zoom out"
                disabled={zoom <= 1}
                onClick={() => setZoom(Math.max(1, zoom - 0.25))}
              >
                −
              </button>
              <button onClick={() => setZoom(1)}>
                {Math.round(zoom * 100)}%
              </button>
              <button
                aria-label="Zoom in"
                disabled={zoom >= 3}
                onClick={() => setZoom(Math.min(3, zoom + 0.25))}
              >
                ＋
              </button>
              <button onClick={() => editorElement.current?.requestFullscreen()}>Fullscreen</button>
            </div>
          </div>
          <div className="image-adjustments">
            <label>Brightness <input type="range" min="25" max="200" value={brightness}
              onChange={(e) => setBrightness(Number(e.target.value))} /><span>{brightness}%</span></label>
            <label>Contrast <input type="range" min="25" max="200" value={contrast}
              onChange={(e) => setContrast(Number(e.target.value))} /><span>{contrast}%</span></label>
            <button onClick={() => { setBrightness(100); setContrast(100); }}>Reset image</button>
          </div>
          <div className="canvas-scroll" ref={canvasScroll}
            onPointerDown={(e) => { if (!panMode) return; panGesture.current = { x: e.clientX, y: e.clientY,
              left: canvasScroll.current.scrollLeft, top: canvasScroll.current.scrollTop }; e.currentTarget.setPointerCapture(e.pointerId); }}
            onPointerMove={(e) => { if (!panGesture.current) return; canvasScroll.current.scrollLeft = panGesture.current.left - e.clientX + panGesture.current.x;
              canvasScroll.current.scrollTop = panGesture.current.top - e.clientY + panGesture.current.y; }}
            onPointerUp={() => { panGesture.current = null; }}>
            <div className="image-surface" style={{ width: `${zoom * 100}%` }}>
              <img
                src={`/api${path}/file`}
                alt={image.source_path}
                draggable="false"
                style={{ filter: `brightness(${brightness}%) contrast(${contrast}%)` }}
                onLoad={() => setReady(true)}
                onError={() => {
                  setReady(false);
                  setError("Image could not load. Reload the page to retry.");
                }}
              />
              <svg
                ref={svg}
                viewBox={`0 0 ${image.width} ${image.height}`}
                preserveAspectRatio="none"
                onPointerDown={(e) => start(e)}
                onPointerMove={move}
                onPointerUp={end}
                onPointerCancel={() => {
                  gesture.current = null;
                  setDraft(null);
                }}
                aria-label="Image annotation canvas"
                style={{ pointerEvents: panMode ? "none" : "auto", cursor: disabled || dirty ? "wait" : classification ? "default" : "crosshair" }}
              >
                {displayBoxes.map((b, i) => (
                  <g key={i}>
                    <rect
                      x={b.x}
                      y={b.y}
                      width={b.width}
                      height={b.height}
                      fill={color(b.category_id)}
                      fillOpacity={selected === i ? ".2" : ".08"}
                      stroke={color(b.category_id)}
                      strokeWidth={selected === i ? 3 : 2}
                      vectorEffect="non-scaling-stroke"
                      onPointerDown={(e) => start(e, i)}
                      style={{ cursor: "move" }}
                    />
                    <text
                      x={b.x + 3}
                      y={Math.max(12, b.y - 5)}
                      fill={color(b.category_id)}
                      fontSize={Math.max(12, image.width / 70)}
                      paintOrder="stroke"
                      stroke="#111"
                      strokeWidth="2"
                      pointerEvents="none"
                    >
                      {
                        project.classes.find((c) => c.id === b.category_id)
                          ?.name
                      }
                    </text>
                    {selected === i && (
                      <rect
                        x={b.x + b.width - image.width / 100}
                        y={b.y + b.height - image.width / 100}
                        width={image.width / 100}
                        height={image.width / 100}
                        fill={color(b.category_id)}
                        onPointerDown={(e) => start(e, i, true)}
                        style={{ cursor: "nwse-resize" }}
                      />
                    )}
                  </g>
                ))}
              </svg>
            </div>
          </div>
          <div className="canvas-footer">
            <span
              className={dirty && !saving ? "warning-text" : "muted"}
              role="status"
            >
              {aiWorking ? "AI is suggesting boxes…" : saving
                ? "Saving…"
                : dirty
                  ? "Unsaved changes"
                  : data
                    ? "✓ All changes saved"
                    : "Loading…"}
            </span>
            <div className="image-navigation">
              <button
                aria-label="Previous image"
                disabled={
                  index === 0 || saving || dirty || uploading || !!draft
                }
                onClick={() => onNavigate(index - 1)}
              >
                ←
              </button>
              <select
                aria-label="Choose image"
                value={index}
                disabled={saving || dirty || uploading || !!draft}
                onChange={(e) => {
                  setSelected(null);
                  onNavigate(Number(e.target.value));
                }}
              >
                {images.map((im, i) => (
                  <option key={im.id} value={i}>
                    {i + 1} / {total} {im.completed ? "✓" : "○"} —{" "}
                    {im.source_path}
                  </option>
                ))}
              </select>
              <button
                aria-label="Next image"
                disabled={
                  index === total - 1 || saving || dirty || uploading || !!draft
                }
                onClick={() => onNavigate(index + 1)}
              >
                →
              </button>
            </div>
          </div>
        </section>
        <aside className="annotation-panel">
          <div className="panel-section">
            <div className="section-title">
              CLASSES <span>{project.classes.length}</span>
            </div>
            <p className="muted small">{classification ? "Select all classes present in this image." : "Select a class, then drag to draw."}</p>
            <div className="class-list">
              {project.classes.map((c) => (
                <button
                  key={c.id}
                  className={`class-choice ${(classification ? data?.labels?.includes(c.id) : category === c.id) ? "chosen" : ""}`}
                  aria-pressed={classification ? !!data?.labels?.includes(c.id) : category === c.id}
                  disabled={disabled || dirty || !!draft}
                  onClick={() => classification ? persist({ ...data,
                    labels: data.labels.includes(c.id) ? data.labels.filter((id) => id !== c.id) : [...data.labels, c.id],
                    completed: false,
                  }) : setCategory(c.id)}
                >
                  <span
                    className="small-dot"
                    style={{ background: color(c.id) }}
                  />
                  {c.name}
                  <span>{(classification ? data?.labels?.includes(c.id) : category === c.id) ? "●" : ""}</span>
                </button>
              ))}
            </div>
          </div>
          {!classification && <div className="panel-section objects">
            <div className="section-title">
              BOUNDING BOXES <span>{boxes.length}</span>
            </div>
            {!boxes.length && (
              <p className="muted small">
                No boxes yet. Draw around an object to add one.
              </p>
            )}
            {boxes.map((b, i) => (
              <div
                className={`box-row ${selected === i ? "chosen" : ""}`}
                key={i}
              >
                <button
                  disabled={disabled || dirty || !!draft}
                  onClick={() => setSelected(i)}
                >
                  <span style={{ color: color(b.category_id) }}>□</span> {i + 1}
                </button>
                <select
                  aria-label={`Class for box ${i + 1}`}
                  value={b.category_id}
                  disabled={disabled || dirty || !!draft}
                  onChange={(e) =>
                    persist({
                      ...data,
                      boxes: boxes.map((item, j) =>
                        i === j
                          ? { ...item, category_id: Number(e.target.value) }
                          : item,
                      ),
                    })
                  }
                >
                  {project.classes.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
                <button
                  aria-label={`Delete box ${i + 1}`}
                  disabled={disabled || dirty || !!draft}
                  onClick={() => {
                    setSelected(null);
                    persist({
                      ...data,
                      boxes: boxes.filter((_, j) => i !== j),
                    });
                  }}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
          }
          <div className="panel-section complete-section">
            <span
              className={`completion-label ${data?.completed ? "accent" : ""}`}
            >
              {data?.completed ? "✓ Image complete" : "○ Awaiting completion"}
            </span>
            <button
              className="primary"
              disabled={disabled || dirty || !!draft}
              onClick={complete}
            >
              {classification ? (data?.labels?.length ? "Complete & next →" : "No classes · complete →") :
                boxes.length ? "Complete & next →" : "No objects · complete →"}
            </button>
            {data?.completed && (
              <button
                className="text-button"
                disabled={disabled || dirty || !!draft}
                onClick={() => persist({ ...data, completed: false })}
              >
                Mark as incomplete
              </button>
            )}
            <p className="muted small">
              {classification ? "Classes" : "Boxes"} save automatically. Mark an image complete to include it in
              the Dashboard and export.
            </p>
            <button className="danger delete-image-button" disabled={saving || uploading || !!draft}
              onClick={deleteCurrentImage}>Delete image from dataset</button>
          </div>
        </aside>
      </div>
      <p className="editor-hint">
        {classification ? "Choose image classes in the sidebar, then complete and move to the next image." :
          "Drag a box to move it. Resize with its handle. Shortcuts: ←/→ navigate, 1–9 class, Delete box, Enter complete, Ctrl/Cmd+Z undo, +/− zoom."}
      </p>
    </>
  );
}

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
        <button className="primary" disabled={posting || !body.trim()}>{posting ? "Posting…" : "Post update"}</button></div>
    </form>
    {error && <div className="alert">{error}<button onClick={load}>Retry</button></div>}
    {comments && !comments.length && <div className="comment-empty">No updates yet. Start the discussion.</div>}
    <div className="comment-thread">{comments?.map((comment) => <article className="comment" key={comment.id}>
      <div className="comment-avatar" aria-hidden="true">{comment.author.slice(0, 1).toUpperCase()}</div>
      <div><header><strong>{comment.author}</strong><time dateTime={comment.created_at}>
        {new Date(`${comment.created_at}${comment.created_at.endsWith("Z") ? "" : "Z"}`).toLocaleString()}
      </time></header><p>{comment.body}</p></div>
    </article>)}</div>
  </section>;
}

function Stats({ project }) {
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
                {project.description || "A clear picture of your labelling progress."}
              </p>
            </div>
            <button
              className="primary"
              disabled={!stats.completed || exporting}
              onClick={() => setShowExport(true)}
            >
              ↓ Export dataset
            </button>
          </div>
          <div className="kpi-grid">
            {[
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
            ].map(([label, value, note, clickable]) => {
              const Component = clickable ? "button" : "div";
              const tone = label === "LABELLED" || label === "APPROVED" ? "positive" :
                label === "REMAINING" || label === "READY FOR REVIEW" || label === "SIMILAR IMAGES" ? "attention" : "neutral";
              return <Component className={`panel kpi kpi-${tone} ${clickable ? "kpi-button" : ""}`} key={label}
                disabled={clickable && !value} onClick={clickable ? openDuplicates : undefined}>
                <div className="eyebrow">{label}</div>
                <strong>{value}</strong>
                <span className="muted small">{note}</span>
              </Component>;
            })}
          </div>
          {quality && <section className="panel quality-panel"><div className="section-heading"><div>
            <h2>Dataset quality</h2><p className="muted">Automatic checks for annotation and split problems.</p>
          </div><span className="tag">{quality.checks_run} CHECKS</span></div>
            {!quality.issues.length ? <div className="notice">No quality issues found.</div> :
              <div className="quality-list">{quality.issues.map((issue) => <article key={issue.code}
                className={`quality-issue ${issue.severity}`}><strong>{issue.title}</strong>
                <span className="quality-count">{issue.count}</span><p>{issue.detail}</p></article>)}</div>}
          </section>}
          <div className="panel representation">
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
                          style={{ background: color(c.id) }}
                        />
                        {c.name}
                      </td>
                      <td>
                        <div className="distribution">
                          <div className="progress-track">
                            <span
                              style={{
                                width: `${(classification ? stats.labels : stats.boxes) ? ((classification ? c.labels : c.boxes) / (classification ? stats.labels : stats.boxes)) * 100 : 0}%`,
                                background: color(c.id),
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
                <div className="eyebrow">{classification ? "CLASSIFICATION DATASET" : "COCO DATASET"}</div>
                <h2 id="export-title">Export your annotations</h2>
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

createRoot(document.getElementById("root")).render(<App />);
