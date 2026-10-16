import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { classColor } from "../visuals";
import { filterPredictions } from "../evaluation-filters";
import AnomalyExplorer from "./AnomalyExplorer";
import AnnotationBox from "./AnnotationBox";

export default function ModelEvaluation({ project, model, onClose }) {
  const dialog = useRef(null);
  const [evaluation, setEvaluation] = useState(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState(""); const [category, setCategory] = useState("");
  const [confidence, setConfidence] = useState(0); const [page, setPage] = useState(0);
  const [filter, setFilter] = useState("all");
  async function refresh(start = false) {
    try {
      let value = await api(`/projects/${project.id}/models/${model.id}/evaluation`);
      if (start && project.permission !== "read" && model.evaluation_available && value.status === "not_started")
        value = await api(`/projects/${project.id}/models/${model.id}/evaluation`, { method: "POST" });
      setEvaluation(value);
    }
    catch (error) { setError(error.message); }
  }
  useEffect(() => {
    dialog.current.showModal(); refresh(true);
    const timer = setInterval(() => refresh(), 3000);
    return () => clearInterval(timer);
  }, [model.id]);
  async function evaluate() {
    setError("");
    try { setEvaluation(await api(`/projects/${project.id}/models/${model.id}/evaluation`, { method: "POST" })); }
    catch (error) { setError(error.message); }
  }
  const result = evaluation?.result || {};
  const anomaly = project.annotation_type === "anomaly_detection";
  const sourceImages = filter === "failures" ? result.failure_examples : filter === "flagged" ? result.flagged_examples : result.predictions;
  const categories = project.classes || [];
  const filteredImages = filterPredictions(sourceImages || [], { query, category, confidence });
  const images = filteredImages.slice(page * 24, (page + 1) * 24);
  useEffect(() => { setPage(0); }, [query, category, confidence, filter]);
  return <dialog ref={dialog} className="model-evaluation" onCancel={onClose} aria-labelledby="model-evaluation-title">
    <div className="modal-heading"><div><div className="eyebrow">SAVED MODEL · V{model.model_version}</div><h2 id="model-evaluation-title">{model.run_name || model.name}</h2></div><button onClick={onClose}>Close</button></div>
    <p className="muted">{model.partition_recorded ? "Evaluate on the fixed held-out partition of its training dataset. These images were excluded from fitting." : "Inspect this saved model and its evaluation availability."}</p>
    {!model.partition_recorded ? <div className="notice">This model predates held-out tracking. Train a new run to evaluate a verified held-out partition.</div> : !model.evaluation_available ? <div className="notice">No evaluation is available: this run has no held-out images or its artifact is missing.</div> :
      <div className="evaluation-actions"><span>Dataset: {model.version_name || model.version_id} · {model.held_out_samples} held-out images</span><button disabled={project.permission === "read" || ["queued", "running", "cancelling", "succeeded"].includes(evaluation?.status)} onClick={evaluate}>{["queued", "running"].includes(evaluation?.status) ? "Evaluating…" : evaluation?.status === "succeeded" ? "Evaluation saved" : "Evaluate model"}</button></div>}
    {project.permission !== "read" && ["queued", "running", "cancelling"].includes(evaluation?.status) && <button onClick={async () => { try { await api(`/projects/${project.id}/models/${model.id}/evaluation/cancel`, { method: 'POST' }); await refresh(); } catch (e) { setError(e.message); } }}>Request evaluation cancellation</button>}
    {error && <p className="alert" role="alert">{error}</p>}
    {evaluation?.error && <p className="alert" role="alert">{evaluation.error}</p>}
    {["queued", "running"].includes(evaluation?.status) && <p role="status">Evaluation continues if you close this window.</p>}
    {evaluation?.status === "succeeded" && <>
      {anomaly && <AnomalyExplorer project={project} model={model} rows={result.predictions || []} />}
      <dl className="evaluation-metrics">{Object.entries(result.metrics).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "number" ? Number(value.toPrecision(5)) : value}</dd></div>)}</dl>
      <p className="muted small">{result.metric_policy} {anomaly && "Flags are not verified failures: this dataset has no ground-truth anomaly labels."}</p>
      <div className="evaluation-actions"><label>Examples<select value={filter} onChange={(event) => setFilter(event.target.value)}>
        <option value="all">Predictions</option>{anomaly ? <option value="flagged">Flagged examples</option> : <option value="failures">Failure examples</option>}
      </select></label><span className="muted">Evaluated {result.sample_count} images · 24 examples per page</span></div>
      <div className="training-grid"><label>Search images<input value={query} onChange={(e) => setQuery(e.target.value)} /></label>
        {!anomaly && <><label>Class<select value={category} onChange={(e) => setCategory(e.target.value)}><option value="">All classes</option>{categories.map((c) => <option key={c.id}>{c.name}</option>)}</select></label>
        <label>Minimum prediction confidence<input type="number" min="0" max="1" step="0.05" value={confidence} onChange={(e) => setConfidence(Number(e.target.value))} /></label></>}
      </div><p className="muted">Filters change displayed examples; saved metrics stay fixed.</p>
      <div className="evaluation-actions"><button disabled={!page} onClick={() => setPage(page - 1)}>Previous</button><span>{filteredImages.length} matches · page {page + 1} of {Math.max(1, Math.ceil(filteredImages.length / 24))}</span><button disabled={(page + 1) * 24 >= filteredImages.length} onClick={() => setPage(page + 1)}>Next</button></div>
      {!images?.length && <p className="muted">No examples in this selection.</p>}
      <div className="evaluation-grid">{images?.map((image) => <figure key={image.image_id}>
        <div className="evaluation-image" style={{ aspectRatio: `${image.width}/${image.height}` }}>
          <img loading="lazy" src={`/api/projects/${project.id}/versions/${model.version_id}/images/${image.image_id}/file`} alt={image.source_path}/>
          {project.annotation_type === "object_detection" && <svg viewBox={`0 0 ${image.width} ${image.height}`} preserveAspectRatio="none" aria-label="Predicted bounding boxes">
            {image.predictions.filter((prediction) => prediction.score >= 0.5).map((prediction, index) => {
              const category = categories.find((category) => category.name === prediction.class_name);
              const [x, y, width, height] = prediction.bbox;
              return <AnnotationBox key={index} box={{ x, y, width, height, category_id: category?.id || 1 }} color={classColor(project, category?.id || 1)} label={`${prediction.class_name} ${Number(prediction.score).toFixed(2)}`} imageWidth={image.width} imageHeight={image.height} />;
            })}
          {image.ground_truth.map((truth, index) => {
              const [x, y, width, height] = truth.bbox;
              return <AnnotationBox key={`truth-${index}`} box={{ x, y, width, height }} color="#79c7dd" label={`Expected: ${truth.class_name}`} imageWidth={image.width} imageHeight={image.height} />;
            })}
          </svg>}
        </div><figcaption title={image.source_path}><strong>{image.source_path}</strong>
          <span>Prediction: {image.predictions.map((prediction) => prediction.class_name ? `${prediction.class_name} (${Number(prediction.score).toFixed(2)})` : `score ${Number(prediction.anomaly_score).toFixed(4)}${prediction.is_anomaly ? " · flagged" : ""}`).join(", ") || "None"}</span>
          {!anomaly && <span>Expected: {image.ground_truth.map((item) => typeof item === "string" ? item : item.class_name).join(", ") || "None"}</span>}
          {image.failed && project.permission !== "read" && <button onClick={async () => { try { await api(`/projects/${project.id}/models/${model.id}/review-tasks`, { method: "POST", body: JSON.stringify({ image_ids: [image.image_id] }) }); setError("Added to model review queue."); } catch (e) { setError(e.message); } }}>Send to review queue</button>}
          {image.failed && <span className="warning-text">Prediction differs from ground truth</span>}
        </figcaption>
      </figure>)}</div>
    </>}
  </dialog>;
}
