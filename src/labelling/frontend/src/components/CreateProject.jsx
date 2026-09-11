import React, { useState } from "react";
import { api, color } from "../api";

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

export default CreateProject;

