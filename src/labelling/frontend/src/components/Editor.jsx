import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAnnotationPersistence } from "../editor-persistence";
import { imagePoint, useUnsavedGuard } from "../editor-interactions";
import AnnotationBox from "./AnnotationBox";
import { classColor } from "../visuals";

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
  const activeClasses = project.classes.filter((item) => !item.archived);
  const [data, setData] = useState(null);
  const [category, setCategory] = useState(activeClasses[0]?.id ?? 1);
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState(null);
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
  const path = `/projects/${project.id}/images/${image.id}`;
  const { saving, setSaving, dirty, setDirty, error, setError, inFlight, undoStack, redoStack, persist } = useAnnotationPersistence({ path, data, setData, onSaved });
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
  const disabled = saving || uploading || !ready || !data;
  useUnsavedGuard(saving || dirty || uploading);
  function point(e) { return imagePoint(e, svg.current.getBoundingClientRect(), image); }
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
      else if (/^[1-9]$/.test(e.key) && activeClasses[Number(e.key) - 1]) setCategory(activeClasses[Number(e.key) - 1].id);
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
              <button className={`toolbar-text ${panMode ? "chosen" : ""}`} aria-pressed={panMode}
                onClick={() => setPanMode((value) => !value)}>Pan</button>
              <button
                aria-label="Zoom out"
                disabled={zoom <= 1}
                onClick={() => setZoom(Math.max(1, zoom - 0.25))}
              >
                −
              </button>
              <button className="toolbar-text" onClick={() => setZoom(1)}>
                {Math.round(zoom * 100)}%
              </button>
              <button
                aria-label="Zoom in"
                disabled={zoom >= 3}
                onClick={() => setZoom(Math.min(3, zoom + 0.25))}
              >
                ＋
              </button>
              <button className="toolbar-text" onClick={() => editorElement.current?.requestFullscreen()}>Fullscreen</button>
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
                    <AnnotationBox box={b} color={classColor(project, b.category_id)}
                      label={project.classes.find((c) => c.id === b.category_id)?.name}
                      imageWidth={image.width} imageHeight={image.height} selected={selected === i}
                      onPointerDown={(e) => start(e, i)} />
                    {selected === i && (
                      <rect
                        x={b.x + b.width - image.width / 100}
                        y={b.y + b.height - image.width / 100}
                        width={image.width / 100}
                        height={image.width / 100}
                        fill={classColor(project, b.category_id)}
                        stroke="#161a22" strokeWidth="2" vectorEffect="non-scaling-stroke"
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
              CLASSES <span>{activeClasses.length}</span>
            </div>
            <p className="muted small">{classification ? "Select all classes present in this image." : "Select a class, then drag to draw."}</p>
            <div className="class-list">
              {activeClasses.map((c) => (
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
                    style={{ background: classColor(project, c.id) }}
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
                  <span style={{ color: classColor(project, b.category_id) }}>□</span> {i + 1}
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
                  {activeClasses.map((c) => (
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

export default Editor;

