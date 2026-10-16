import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { classColor } from "../visuals";
import AnnotationBox from "./AnnotationBox";

export default function ModelEvaluation({ project, model, onClose }) {
  const dialog = useRef(null);
  const [evaluation, setEvaluation] = useState(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  async function refresh(start = false) {
    try {
      let value = await api(`/projects/${project.id}/models/${model.id}/evaluation`);
      if (start && model.evaluation_available && value.status === "not_started")
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
  const images = filter === "failures" ? result.failure_examples : filter === "flagged" ? result.flagged_examples : result.predictions;
  const categories = project.classes || [];
  return <dialog ref={dialog} className="model-evaluation" onCancel={onClose} aria-labelledby="model-evaluation-title">
    <div className="modal-heading"><div><div className="eyebrow">SAVED MODEL · V{model.model_version}</div><h2 id="model-evaluation-title">{model.run_name || model.name}</h2></div><button onClick={onClose}>Close</button></div>
    <p className="muted">{model.partition_recorded ? "Evaluate on the fixed held-out partition of its training dataset. These images were excluded from fitting." : "Inspect this saved model and its evaluation availability."}</p>
    {!model.partition_recorded ? <div className="notice">This model predates held-out tracking. Train a new run to evaluate a verified held-out partition.</div> : !model.evaluation_available ? <div className="notice">No evaluation is available: this run has no held-out images or its artifact is missing.</div> :
      <div className="evaluation-actions"><span>Dataset: {model.version_name || model.version_id} · {model.held_out_samples} held-out images</span><button disabled={["queued", "running", "succeeded"].includes(evaluation?.status)} onClick={evaluate}>{["queued", "running"].includes(evaluation?.status) ? "Evaluating…" : evaluation?.status === "succeeded" ? "Evaluation saved" : "Evaluate model"}</button></div>}
    {error && <p className="alert" role="alert">{error}</p>}
    {evaluation?.error && <p className="alert" role="alert">{evaluation.error}</p>}
    {["queued", "running"].includes(evaluation?.status) && <p role="status">Evaluation continues if you close this window.</p>}
    {evaluation?.status === "succeeded" && <>
      <dl className="evaluation-metrics">{Object.entries(result.metrics).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{typeof value === "number" ? Number(value.toPrecision(5)) : value}</dd></div>)}</dl>
      <p className="muted small">{result.metric_policy} {anomaly && "Flags are not verified failures: this dataset has no ground-truth anomaly labels."}</p>
      <div className="evaluation-actions"><label>Examples<select value={filter} onChange={(event) => setFilter(event.target.value)}>
        <option value="all">Predictions</option>{anomaly ? <option value="flagged">Flagged examples</option> : <option value="failures">Failure examples</option>}
      </select></label><span className="muted">Evaluated {result.sample_count} images · displaying up to {filter === "all" ? 100 : 50}</span></div>
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
          {image.failed && <span className="warning-text">Prediction differs from ground truth</span>}
        </figcaption>
      </figure>)}</div>
    </>}
  </dialog>;
}
