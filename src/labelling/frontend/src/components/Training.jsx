import React, { useEffect, useMemo, useState, useId, useRef } from "react";
import ModelEvaluation from "./ModelEvaluation";
import { elapsedTime, heartbeatText } from "../training-status";
import TrainingErrorDialog from "./TrainingErrorDialog";
import { newTrainingFailures } from "../training-errors";
import { api } from "../api";
import { managedFields, resolveSchema, schemaDefaults, normalizeParams, liveMetricsEnabled, dashboardUrl } from "../training-config";

const defaults = { epochs: 1, batch_size: 32, learning_rate: 0.001, image_size: 224 };

function ConfigField({ name, schema, value, required, onChange }) {
  const id = useId();
  const dialog = useRef(null);
  const title = schema.title || name.replaceAll("_", " ");
  const inputProps = { id, required };
  let control;
  if (schema.enum) control = <select {...inputProps} value={value ?? schema.default ?? ""} onChange={(e) => onChange(e.target.value)}>
    {schema.default !== undefined && <option value="">Use default ({String(schema.default)})</option>}
    {schema.enum.map((option) => <option key={String(option)} value={option}>{String(option)}</option>)}</select>;
  else if (schema.type === "array" && schema.items?.enum) control = <select id={id} multiple size={Math.min(5, schema.items.enum.length + 1)}
    value={(value ?? schema.default ?? []).length ? (value ?? schema.default) : [""]}
    onChange={(e) => onChange(Array.from(e.target.selectedOptions, (option) => option.value).filter(Boolean))}>
    <option value="">None</option>{schema.items.enum.map((option) => <option key={option} value={option}>{option}</option>)}</select>;
  else if (schema.type === "boolean") control = <input id={id} type="checkbox" checked={Boolean(value ?? schema.default)} onChange={(e) => onChange(e.target.checked)} />;
  else if (["object", "array"].includes(schema.type)) control = <textarea {...inputProps} rows="5"
    value={typeof value === "string" ? value : JSON.stringify(value ?? schema.default ?? (schema.type === "array" ? [] : {}), null, 2)}
    placeholder={JSON.stringify(schema.default ?? {}, null, 2)} onChange={(e) => onChange(e.target.value)} />;
  else if (schema.type === "integer" || schema.type === "number") control = <input {...inputProps} type="number" value={value ?? schema.default ?? ""}
    min={schema.minimum} max={schema.maximum} step={schema.type === "integer" ? 1 : "any"}
    placeholder={schema.default === undefined ? "" : `Default: ${schema.default}`} onChange={(e) => onChange(e.target.value)} />;
  else control = <textarea {...inputProps} rows="2" value={value ?? schema.default ?? ""} onChange={(e) => onChange(e.target.value)} />;
  return <div className={`config-field ${schema.type === "object" ? "config-structured" : ""}`}>
    <div className="config-field-heading"><label htmlFor={id}>{title}</label>
      <button type="button" className="config-info" aria-label={`Information about ${title}`} aria-haspopup="dialog" onClick={() => dialog.current.showModal()}>i</button></div>
    {control}
    <dialog ref={dialog} className="config-help" aria-labelledby={`${id}-help-title`} aria-describedby={`${id}-help-description`}>
      <div className="config-help-heading"><h2 id={`${id}-help-title`}>{title}</h2><button type="button" onClick={() => dialog.current.close()}>Close</button></div>
      <p id={`${id}-help-description`}>{schema.description?.trim() || "No description defined"}</p>
      {schema.type === "array" && schema.items?.enum && <p className="muted">Cmd/Ctrl-click to select multiple options. Select None to disable all options.</p>}
      {(schema.properties || schema.propertyNames?.enum) && <div className="config-help-options"><h3>Supported options</h3>{(schema.propertyNames?.enum ? schema.propertyNames.enum.map((key) => [key, schema.properties?.[key] || schema.additionalProperties || {}]) : Object.entries(schema.properties)).map(([key, property]) =>
        <p key={key}><strong>{key}</strong>: {property.enum?.join(" / ") || property.type}
          {property.minimum !== undefined && ` (${property.minimum}–${property.maximum ?? "∞"})`}<br />{property.description?.trim() || "No description defined"}</p>)}</div>}
    </dialog>
  </div>;
}

export default function Training({ project, initialModelId = "" }) {
  const openedModel = useRef("");
  const configuredModel = useRef("");
  const [savedModels, setSavedModels] = useState([]);
  const [viewModel, setViewModel] = useState(null);
  const [clock, setClock] = useState(Date.now());
  const [retryConfig, setRetryConfig] = useState(null);
  const [versions, setVersions] = useState([]); const [jobs, setJobs] = useState([]);
  const [caps, setCaps] = useState(null); const [version, setVersion] = useState("");
  const [model, setModel] = useState(""); const [params, setParams] = useState(defaults);
  const [kind, setKind] = useState("local"); const [cpu, setCpu] = useState(true);
  const [gpu, setGpu] = useState(false); const [endpoint, setEndpoint] = useState("");
  const [template, setTemplate] = useState(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [probe, setProbe] = useState("");
  const [trainingErrors, setTrainingErrors] = useState([]);
  const seenJobs = useRef(null);
  function updateJobs(nextJobs) {
    const failures = newTrainingFailures(nextJobs, seenJobs.current);
    seenJobs.current = new Map(nextJobs.map((job) => [job.id, job.status]));
    setJobs(nextJobs);
    if (failures.length) setTrainingErrors((current) => [...current, ...failures]);
  }
  const models = useMemo(() => [
    ...Object.values(caps?.models || {}).flat(), ...(caps?.workbenches || []),
  ], [caps]);
  const compatibleModels = models.filter((item) => item.available !== false && item.task === project.annotation_type);
  const selectedModel = useMemo(() => models.find((item) => item.key === model), [models, model]);
  async function load() {
    const results = await Promise.allSettled([
      api(`/projects/${project.id}/versions`).then((value) => { setVersions(value); setVersion((current) => current || value[0]?.id || ""); }),
      refreshJobs(),
      api("/training/capabilities").then((nextCaps) => {
        setCaps(nextCaps);
        setModel((current) => {
          const candidates = [...Object.values(nextCaps.models || {}).flat(), ...(nextCaps.workbenches || [])];
          if (candidates.some((item) => item.key === current && item.available !== false && item.task === project.annotation_type)) return current;
          return candidates.find((item) => item.available !== false && item.task === project.annotation_type)?.key || "";
        });
      }),
    ]);
    for (const result of results) if (result.status === "rejected") setError(result.reason.message);
  }
  async function refreshJobs() {
    try {
      const [nextJobs, nextModels] = await Promise.all([api(`/projects/${project.id}/training/jobs`), api(`/projects/${project.id}/models`)]);
      updateJobs(nextJobs); setSavedModels(nextModels);
    } catch (error) { setError(error.message); }
  }
  useEffect(() => {
    seenJobs.current = null; setTrainingErrors([]); load();
    const timer = setInterval(refreshJobs, 4000);
    const clockTimer = setInterval(() => setClock(Date.now()), 1000);
    const visible = () => { if (!document.hidden) refreshJobs(); };
    document.addEventListener("visibilitychange", visible); window.addEventListener("focus", visible);
    return () => { clearInterval(timer); clearInterval(clockTimer); document.removeEventListener("visibilitychange", visible); window.removeEventListener("focus", visible); };
  }, [project.id]);
  useEffect(() => {
    const item = savedModels.find((item) => item.id === initialModelId);
    if (item && openedModel.current !== initialModelId) { openedModel.current = initialModelId; setViewModel(item); }
  }, [initialModelId, savedModels]);
  useEffect(() => {
    if (!version) { setTemplate(null); return; }
    api(`/projects/${project.id}/training/template?version_id=${encodeURIComponent(version)}`)
      .then(setTemplate).catch((e) => setError(e.message));
  }, [project.id, version]);
  useEffect(() => {
    if (selectedModel && configuredModel.current !== model) { configuredModel.current = model; setParams(retryConfig?.base_model === model ? retryConfig.hyperparameters : schemaDefaults(selectedModel)); setRetryConfig(null); }
  }, [model, selectedModel]);
  function cloneJob(job) {
    setVersion(job.version_id); setKind(job.compute_target.kind); setEndpoint(job.compute_target.endpoint || "");
    setCpu(job.compute_target.cpu); setGpu(job.compute_target.gpu);
    if (job.base_model === model) setParams(job.hyperparameters);
    else { setRetryConfig(job); setModel(job.base_model); }
    if (job.compute_target.kind === "remote") { setCaps(null); setProbe("Test the saved remote agent before starting a new run."); }
    document.querySelector(".training-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  async function testRemote() {
    setProbe("Testing…"); setError("");
    try { const result = await api("/training/probe", { method: "POST", body: JSON.stringify({ kind: "remote", endpoint, cpu: true, gpu: false }) });
      setCaps(result); setProbe(`Connected · CPU ${result.cpu.available ? "ready" : "unavailable"} · GPU ${result.gpu.available ? "ready" : "unavailable"}`);
    } catch (e) { setProbe(""); setError(e.message); }
  }
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError("");
    try { const hyperparameters = normalizeParams(params, selectedModel);
      await api(`/projects/${project.id}/training/jobs`, { method: "POST", body: JSON.stringify({
      version_id: version, base_model: model, hyperparameters,
      compute: { kind, cpu: kind === "local" ? cpu : true, gpu: kind === "local" ? gpu : false, endpoint },
    }) }); await refreshJobs(); } catch (e) { setTrainingErrors((current) => [...current, { message: e.message || "Training could not be started." }]); } finally { setBusy(false); }
  }
  return <div className="training-layout">
    {viewModel && <ModelEvaluation project={project} model={{ ...viewModel, version_name: versions.find((item) => item.id === viewModel.version_id)?.name }} onClose={() => setViewModel(null)} />}
    <TrainingErrorDialog error={trainingErrors[0]} onClose={() => setTrainingErrors((current) => current.slice(1))} />
    <div className="page-heading"><div><h2>Model training</h2><p className="muted">Train against an immutable dataset version and track the run in MLflow.</p></div>
      </div>
    {error && <div className="alert">{error}</div>}
    <form className="panel training-form" onSubmit={submit}><fieldset className="training-fields" disabled={project.permission === "read"}>
      <section><div className="eyebrow">DATA &amp; MODEL</div>
        <div className="training-grid"><label>Published version<select value={version} required onChange={(e) => setVersion(e.target.value)}>
          <option value="">Select a version</option>{versions.map((v) => <option key={v.id} value={v.id}>{v.name} · {v.sample_count} samples</option>)}</select></label>
          <label>Model workbench<select value={model} required onChange={(e) => setModel(e.target.value)}>{models.map((m) => {
            const disabled = m.available === false || m.task !== project.annotation_type;
            return <option key={m.key} value={m.key} disabled={disabled}>{m.workspace || "Bundled"} / {m.name}{disabled ? ` - ${m.available === false ? "unavailable" : m.task.replaceAll("_", " ")}` : ""}</option>;
          })}</select></label></div>
        {selectedModel && <p className="muted">{selectedModel.description}{selectedModel.path ? ` · ${selectedModel.path}` : ""}</p>}
        {template && <details className="run-template"><summary>Prefilled run configuration</summary>
          <dl><div><dt>Dataset</dt><dd>{template.dataset_path}</dd></div>
            <div><dt>Classes</dt><dd>{template.class_names.join(", ")}</dd></div>
            <div><dt>Output</dt><dd>{template.output_path}</dd></div>
            <div><dt>MLflow</dt><dd>{template.mlflow_url}</dd></div></dl>
          <p className="muted small">These infrastructure fields come from the published version and are locked for reproducibility.</p>
        </details>}
      </section>
      <section><div className="eyebrow">MODEL CONFIGURATION</div>
        <p className="muted config-intro">Defaults are prefilled. Leave a field blank to use its default.</p>
        {[false, true].map((expanded) => {
          const fields = Object.entries(selectedModel?.config_schema?.properties || {}).filter(([key]) => !managedFields.has(key))
            .map(([key, property]) => [key, resolveSchema(property, selectedModel.config_schema)])
            .filter(([, schema]) => ["object", "array", "string"].includes(schema.type) === expanded);
          return fields.length > 0 && <div key={String(expanded)} className={`training-grid ${expanded ? "training-editors" : "training-params"}`}>
            {fields.map(([key, schema]) => <ConfigField key={key} name={key} schema={schema} value={params[key]} required={selectedModel.config_schema.required?.includes(key)}
              onChange={(value) => setParams((current) => ({ ...current, [key]: value }))} />)}</div>;
        })}
        {!selectedModel?.config_schema && <p className="muted">This model does not expose a configurable Pydantic schema.</p>}
      </section>
      <section><div className="eyebrow">COMPUTE TARGET</div><div className="compute-choice">
        <label className={`compute-card ${kind === 'local' ? 'selected' : ''}`}><input type="radio" name="target" checked={kind === 'local'} onChange={() => { setKind('local'); load(); }} /><span><strong>Local agent</strong><small>Bundled with this Compose stack</small></span></label>
        <label className={`compute-card ${kind === 'remote' ? 'selected' : ''}`}><input type="radio" name="target" checked={kind === 'remote'} onChange={() => { setKind("remote"); setCaps(null); setProbe(""); }} /><span><strong>Remote agent</strong><small>Connect to another machine by IP</small></span></label></div>
        {kind === "local" ? <div className="device-row">
          <label className="checkbox-label"><input type="checkbox" checked={cpu} onChange={(e) => setCpu(e.target.checked)} /> CPU</label>
          <label className={`checkbox-label ${!caps?.gpu?.available ? 'device-disabled' : ''}`} title={caps?.gpu?.reason || ''}><input type="checkbox" checked={gpu} disabled={!caps?.gpu?.available} onChange={(e) => setGpu(e.target.checked)} /> GPU</label>
          {!caps?.gpu?.available && <span className="muted small">{caps?.gpu?.reason || "Checking GPU availability…"}</span>}
        </div> : <div className="remote-row"><label>Agent IP address<input value={endpoint} required placeholder="192.168.1.20:8090" onChange={(e) => { setEndpoint(e.target.value); setCaps(null); setProbe(""); }} /></label><button type="button" onClick={testRemote}>Test connection</button><span className="muted">{probe}</span></div>}
      </section>
      <div className="training-submit"><span className="muted small">{compatibleModels.length} compatible · {models.length - compatibleModels.length} visible but unavailable</span><button className="primary" disabled={busy || !version || !model || (kind === 'local' && !cpu && !gpu)}>{busy ? "Queuing…" : "Start training"}</button></div>
    </fieldset></form>
    <div className="page-heading jobs-heading"><div><h2>Training jobs</h2><p className="muted">Compute-agent jobs continue when you refresh or close this page. Status and logs are restored automatically.</p></div><button onClick={refreshJobs}>Refresh status</button></div>
    {!jobs.length ? <div className="empty"><h2>No training jobs yet</h2><p>Publish a dataset version, choose a model, and start your first run.</p></div> :
      <div className="training-job-list">{jobs.map((job) => <article className="panel training-job-card" key={job.id}>
        <header><div><strong>{job.run_name || job.base_model}</strong><p className="muted small">{job.base_model} · {versions.find((value) => value.id === job.version_id)?.name || job.version_id.slice(0, 8)} · {job.compute_target.kind} {job.compute_target.gpu ? "GPU" : "CPU"}</p></div><span className={`job-status ${job.status}`}>{job.status}</span></header>
        <dl className="training-job-facts"><div><dt>Phase</dt><dd>{job.phase || job.status}</dd></div><div><dt>Elapsed</dt><dd>{elapsedTime(job, clock)}</dd></div><div><dt>Heartbeat</dt><dd>{heartbeatText(job, clock)}</dd></div><div><dt>Latest metric</dt><dd>{job.latest_metric?.name ? `${job.latest_metric.name.replaceAll("_", " ")}: ${Number(job.latest_metric.value).toPrecision(4)}` : "Waiting for metrics"}</dd></div></dl>
        {job.error && <p className={job.status === "failed" ? "warning-text" : "muted"}>{job.error}</p>}
        <div className="training-job-actions">
          {["queued", "running", "succeeded"].includes(job.status) && liveMetricsEnabled(job.hyperparameters, models.find((item) => item.key === job.base_model)) && dashboardUrl(caps, job) &&
            <a className="button" href={dashboardUrl(caps, job)} target="_blank" rel="noopener noreferrer"><span aria-hidden="true">▥</span> View live metrics</a>}
          {job.artifact_available && <a className="button" href={`/api/projects/${project.id}/training/jobs/${job.id}/artifact`}><span aria-hidden="true">↓</span> Download Model</a>}
          {savedModels.some((item) => item.training_job_id === job.id) && <button onClick={() => setViewModel(savedModels.find((item) => item.training_job_id === job.id))}>View model</button>}
          {["failed", "succeeded"].includes(job.status) && <button onClick={() => cloneJob(job)}>{job.status === "failed" ? "Retry configuration" : "Clone configuration"}</button>}
          {job.mlflow_url && <a className="button" href={job.mlflow_url} target="_blank" rel="noopener noreferrer"><span aria-hidden="true">↗</span> View on MLflow</a>}
        </div>
        <details className="training-job-logs"><summary>Latest logs ({job.logs?.length || 0})</summary><pre aria-label={`Logs for ${job.run_name || job.id}`}>{job.logs?.length ? job.logs.map((line) => `${new Date(line.time).toLocaleTimeString()}  ${line.message}`).join("\n") : "Waiting for agent logs. Older agents only report their final result."}</pre></details>
        {Object.keys(job.metrics).length > 0 && <details><summary>All metrics</summary><dl className="training-metrics">{Object.entries(job.metrics).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{Number(value).toPrecision(5)}</dd></div>)}</dl></details>}
      </article>)}</div>}
    <div className="page-heading"><div><h2>Saved models</h2><p className="muted">Open a model to inspect predictions and evaluate its recorded held-out dataset.</p></div></div>
    {!savedModels.length ? <p className="muted">Saved models appear after successful training.</p> : <div className="saved-model-grid">{savedModels.map((item) => <button className="panel saved-model-card" key={item.id} onClick={() => setViewModel(item)}>
      <strong>{item.run_name || item.name}</strong><span className="muted">Model v{item.model_version} · {item.held_out_samples} held-out images</span><span>View predictions ↗</span>
    </button>)}</div>}
  </div>;
}
