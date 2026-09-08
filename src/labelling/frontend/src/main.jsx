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
              <button className="primary" onClick={() => setCreating(true)}>
                ＋ New project
              </button>
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
      <footer className="app-footer">OpenIIoT · Labelling Studio</footer>
    </div>
  );
}

function CreateProject({ onCancel, onCreated }) {
  const [name, setName] = useState("");
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
          body: JSON.stringify({ name, classes }),
        }),
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="panel create-form" onSubmit={submit}>
      <div className="eyebrow">NEW PROJECT</div>
      <h2>Set up your dataset</h2>
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
  );
}

function Project({ project, onLock, onRefresh }) {
  const [tab, setTab] = useState("annotate");
  const [images, setImages] = useState([]);
  const [index, setIndex] = useState(0);
  const [locked, setLocked] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
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
    for (let i = 0; i < files.length; i++) {
      setProgress(`Importing ${i + 1} of ${files.length} · ${files[i].name}`);
      const body = new FormData();
      body.append(
        "file",
        files[i],
        files[i].webkitRelativePath || files[i].name,
      );
      try {
        await api(`/projects/${project.id}/images`, { method: "POST", body });
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
  const current = images[index];
  return (
    <div className="page project-page">
      <div className="page-heading">
        <div>
          <h1>{project.name}</h1>
          <p className="muted">
            {images.length} images <span className="separator">/</span>{" "}
            {project.classes.length} classes
          </p>
        </div>
        <div className="import-actions">
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
          ▥ KPIs & export
        </button>
        <span>
          {images.filter((i) => i.completed).length} / {images.length} complete
        </span>
      </div>
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
          uploading={uploading}
          onLock={lock}
          onNavigate={setIndex}
          onSaved={(saved) => {
            setImages((list) =>
              list.map((i) =>
                i.id === saved.id ? { ...i, completed: saved.completed } : i,
              ),
            );
            onRefresh();
          }}
        />
      )}
    </div>
  );
}

function Editor({
  project,
  image,
  index,
  total,
  images,
  uploading,
  onLock,
  onNavigate,
  onSaved,
}) {
  const [data, setData] = useState(null);
  const [category, setCategory] = useState(project.classes[0].id);
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [zoom, setZoom] = useState(1);
  const svg = useRef(null);
  const gesture = useRef(null);
  const inFlight = useRef(false);
  const path = `/projects/${project.id}/images/${image.id}`;
  useEffect(() => {
    const controller = new AbortController();
    api(path, { signal: controller.signal })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [path]);
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
  async function persist(next) {
    if (inFlight.current) return false;
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
    if (disabled || dirty || e.button !== 0) return;
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
      <div className="editor">
        <section className="canvas-panel">
          <div className="canvas-toolbar">
            <span className="truncate">{image.source_path}</span>
            <span className="muted">
              {image.width} × {image.height}
            </span>
            <div className="zoom-controls">
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
            </div>
          </div>
          <div className="canvas-scroll">
            <div className="image-surface" style={{ width: `${zoom * 100}%` }}>
              <img
                src={`/api${path}/file`}
                alt={image.source_path}
                draggable="false"
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
                style={{ cursor: disabled || dirty ? "wait" : "crosshair" }}
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
              {saving
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
            <p className="muted small">Select a class, then drag to draw.</p>
            <div className="class-list">
              {project.classes.map((c) => (
                <button
                  key={c.id}
                  className={`class-choice ${category === c.id ? "chosen" : ""}`}
                  disabled={disabled || dirty || !!draft}
                  onClick={() => setCategory(c.id)}
                >
                  <span
                    className="small-dot"
                    style={{ background: color(c.id) }}
                  />
                  {c.name}
                  <span>{category === c.id ? "●" : ""}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="panel-section objects">
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
              {boxes.length ? "Complete & next →" : "No objects · complete →"}
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
              Boxes save automatically. Mark an image complete to include it in
              KPIs and export.
            </p>
          </div>
        </aside>
      </div>
      <p className="editor-hint">
        Drag a box to move it. Select a box and drag its bottom-right handle to
        resize. Zoom in for finer detail.
      </p>
    </>
  );
}

function Stats({ project }) {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);
  const [showExport, setShowExport] = useState(false);
  const [filename, setFilename] = useState("annotations");
  const [train, setTrain] = useState(80);
  async function load() {
    try {
      setStats(await api(`/projects/${project.id}/stats`));
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
      const response = await fetch(`/api/projects/${project.id}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename, train_percent: train }),
      });
      if (!response.ok) {
        const body = await response.json();
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : "Invalid export settings",
        );
      }
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = `${filename.replace(/\.(zip|json)$/i, "")}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      setShowExport(false);
    } catch (e) {
      setError(e.message);
    } finally {
      setExporting(false);
    }
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
                A clear picture of your labelling progress.
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
              ["BOUNDING BOXES", stats.boxes, "On completed images"],
            ].map(([label, value, note]) => (
              <div className="panel kpi" key={label}>
                <div className="eyebrow">{label}</div>
                <strong>{value}</strong>
                <span className="muted small">{note}</span>
              </div>
            ))}
          </div>
          <div className="panel representation">
            <h2>Class representation</h2>
            <p className="muted">
              Bounding boxes and distinct images for each class, on completed
              images only.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>CLASS</th>
                    <th>DISTRIBUTION OF BOXES</th>
                    <th>BOXES</th>
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
                                width: `${stats.boxes ? (c.boxes / stats.boxes) * 100 : 0}%`,
                                background: color(c.id),
                              }}
                            />
                          </div>
                          <span>
                            {stats.boxes
                              ? Math.round((c.boxes / stats.boxes) * 100)
                              : 0}
                            %
                          </span>
                        </div>
                      </td>
                      <td>{c.boxes}</td>
                      <td>{c.images}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {showExport && (
            <div className="modal-backdrop">
              <form
                className="panel export-modal"
                role="dialog"
                aria-modal="true"
                aria-labelledby="export-title"
                onSubmit={download}
              >
                <div className="eyebrow">COCO DATASET</div>
                <h2 id="export-title">Export your annotations</h2>
                <p className="muted">
                  Download a ZIP with train/test images and a COCO JSON file for
                  each split. Only completed images are included.
                </p>
                <label>
                  File name
                  <input
                    autoFocus
                    required
                    maxLength={96}
                    pattern="[A-Za-z0-9][A-Za-z0-9._\-]*"
                    value={filename}
                    onChange={(e) => setFilename(e.target.value)}
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
                    {exporting ? "Preparing export…" : "Download export ↓"}
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
