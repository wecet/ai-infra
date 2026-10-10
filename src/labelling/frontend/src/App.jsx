import React, { useEffect, useRef, useState } from "react";
import { api } from "./api";
import CreateProject from "./components/CreateProject";
import Project from "./components/Project";

function App() {
  const [theme, setTheme] = useState(() => {
    const saved = window.localStorage.getItem("labelling-theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [projects, setProjects] = useState([]);
  const [project, setProject] = useState(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [locked, setLocked] = useState(false);
  const [importingProject, setImportingProject] = useState(false);
  const [importProjectError, setImportProjectError] = useState("");
  const [pendingImportFile, setPendingImportFile] = useState(null);
  const [importProjectName, setImportProjectName] = useState("");
  const [draggedProject, setDraggedProject] = useState(null);
  const [mergeTarget, setMergeTarget] = useState(null);
  const [reorderTarget, setReorderTarget] = useState(null);
  const [pendingMerge, setPendingMerge] = useState(null);
  const [mergeError, setMergeError] = useState("");
  const [merging, setMerging] = useState(false);
  const dragged = useRef(false);
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
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem("labelling-theme", theme);
  }, [theme]);
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
  function finishDrag() {
    setDraggedProject(null); setMergeTarget(null); setReorderTarget(null);
    setTimeout(() => { dragged.current = false; }, 0);
  }
  function dropProject(target) {
    const source = draggedProject;
    if (!source || source.id === target.id) { finishDrag(); return; }
    if (source.annotation_type !== target.annotation_type) {
      setMergeError("Image Classification and Object Detection projects cannot be merged");
    } else {
      setPendingMerge({ source, target });
    }
    finishDrag();
  }
  function dragIntent(e, target) {
    if (!draggedProject || draggedProject.id === target.id) return { kind: "none" };
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    if (ratio < 0.22) return { kind: "reorder", position: "before" };
    if (ratio > 0.78) return { kind: "reorder", position: "after" };
    return { kind: "merge" };
  }
  function showDragIntent(e, target) {
    const intent = dragIntent(e, target);
    if (intent.kind === "reorder") {
      setReorderTarget({ id: target.id, position: intent.position }); setMergeTarget(null);
    } else if (intent.kind === "merge" && draggedProject.annotation_type === target.annotation_type) {
      setReorderTarget(null); setMergeTarget(target);
    } else {
      setReorderTarget(null); setMergeTarget(null);
    }
  }
  async function reorderProject(source, target, position) {
    const remaining = projects.filter((item) => item.id !== source.id);
    const targetIndex = remaining.findIndex((item) => item.id === target.id);
    remaining.splice(targetIndex + (position === "after" ? 1 : 0), 0, source);
    setProjects(remaining);
    try {
      await api('/projects/order', { method: 'PUT',
        body: JSON.stringify({ project_ids: remaining.map((item) => item.id) }) });
    } catch (e) { setMergeError(e.message); await refresh(); }
    finishDrag();
  }
  async function confirmMerge() {
    if (!pendingMerge) return;
    setMerging(true); setMergeError("");
    try {
      await api(`/projects/${pendingMerge.target.id}/merge`, {
        method: "POST", body: JSON.stringify({ source_project_id: pendingMerge.source.id }),
      });
      setPendingMerge(null); await refresh();
    } catch (e) { setMergeError(e.message); }
    finally { setMerging(false); }
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
          <img className="brand-mark" src="/favicon.svg?v=ai-studio" alt="" aria-hidden="true" />
          <span className="brand-copy">
            <strong>AI Studio</strong>
            <small>Dataset workspace</small>
          </span>
        </a>
        <div className="masthead-actions">
          <span className="tag masthead-status"><span className="status-dot" />Workspace ready</span>
          <button
            type="button"
            className="theme-toggle"
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            aria-pressed={theme === "dark"}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}
          >
            <span className="theme-toggle-track" aria-hidden="true">
              <span className="theme-toggle-thumb" />
            </span>
            <span>{theme === "dark" ? "Light" : "Dark"}</span>
          </button>
        </div>
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
                <div className="page-kicker">Dataset repository</div>
                <h1>Annotation projects</h1>
                <p className="muted">
                  Build, review, and publish versioned image datasets. Your work saves automatically.
                </p>
              </div>
              <div className="homepage-actions">
                <label className={`button ${importingProject ? "disabled" : ""}`}>
                  {importingProject ? "Importing…" : "Import ZIP"}
                  <input type="file" accept=".zip" hidden disabled={importingProject} onChange={chooseImportProject} />
                </label>
                <button className="primary" disabled={importingProject} onClick={() => setCreating(true)}>
                  New project
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
                  className={`project-card project-card-${p.annotation_type === "image_classification" ? "classification" : "detection"} ${draggedProject?.id === p.id ? "dragging" : ""} ${mergeTarget?.id === p.id ? "absorbing" : ""} ${reorderTarget?.id === p.id ? `reorder-${reorderTarget.position}` : ""}`}
                  key={p.id}
                  draggable
                  onDragStart={(e) => {
                    dragged.current = true; setDraggedProject(p); setMergeTarget(null);
                    e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", p.id);
                  }}
                  onDragEnd={finishDrag}
                  onDragEnter={(e) => { e.preventDefault(); showDragIntent(e, p); }}
                  onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move"; showDragIntent(e, p); }}
                  onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) {
                    setMergeTarget(null); setReorderTarget(null);
                  } }}
                  onDrop={(e) => { e.preventDefault(); const intent = dragIntent(e, p);
                    if (intent.kind === "reorder") reorderProject(draggedProject, p, intent.position);
                    else dropProject(p); }}
                  onClick={() => { if (!dragged.current) open(p.id); }}
                >
                  <div className="card-top">
                    <span className="project-type-icon" aria-hidden="true">
                      {p.annotation_type === "image_classification" ? "▦" : "⌗"}
                    </span>
                    <span className="tag">
                      {p.total && p.completed === p.total
                        ? "COMPLETE"
                        : "IN PROGRESS"}
                    </span>
                  </div>
                  <div className="project-type-label">
                    {p.annotation_type === "image_classification" ? "IMAGE CLASSIFICATION" : "OBJECT DETECTION"}
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
                    <span>Open project <span aria-hidden="true">→</span></span>
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
      {pendingMerge && <div className="modal-backdrop"><div className="panel merge-dialog" role="dialog"
        aria-modal="true" aria-labelledby="merge-title"><div className="eyebrow">MERGE PROJECTS</div>
        <h2 id="merge-title">Merge “{pendingMerge.source.name}” into “{pendingMerge.target.name}”?</h2>
        <p>The destination project will keep its name and settings. Images, annotations, classes, and comments from the dragged project will be combined into it. The dragged project will then be removed.</p>
        <div className="notice"><strong>{pendingMerge.target.name}</strong> will be the root project.</div>
        <div className="actions"><button disabled={merging} onClick={() => setPendingMerge(null)}>Cancel</button>
          <button className="primary" disabled={merging} onClick={confirmMerge}>{merging ? "Merging…" : "Merge projects"}</button></div>
      </div></div>}
      {mergeError && <div className="modal-backdrop"><div className="panel ai-dialog" role="alertdialog"
        aria-modal="true" aria-labelledby="merge-error-title"><h2 id="merge-error-title">{mergeError}</h2>
        <button className="primary" autoFocus onClick={() => setMergeError("")}>OK</button></div></div>}
      <footer className="app-footer">AI Studio · Datasets, training and model lineage</footer>
    </div>
  );
}

export default App;
