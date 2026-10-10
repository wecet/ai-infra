import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { managedFields, resolveSchema, schemaDefaults, normalizeParams, liveMetricsEnabled } from "../training-config";

const defaults = { epochs: 1, batch_size: 32, learning_rate: 0.001, image_size: 224 };

function dashboardUrl(caps) {
  if (!caps?.tensorboard?.available) return null;
  try {
    const url = new URL(caps.tensorboard.url);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}

function ConfigField({ name, schema, value, required, onChange }) {
  const label = schema.title || name.replaceAll("_", " ");
  const hint = schema.description && <small className="muted">{schema.description}</small>;
  if (schema.enum) return <label>{label}<select value={value ?? schema.default ?? ""} required={required} onChange={(e) => onChange(e.target.value)}>
    {schema.default !== undefined && <option value="">Use default ({String(schema.default)})</option>}
    {schema.enum.map((option) => <option key={String(option)} value={option}>{String(option)}</option>)}</select>{hint}</label>;
  if (schema.type === "array" && schema.items?.enum) return <label>{label}<select multiple size={Math.min(5, schema.items.enum.length + 1)}
    value={(value ?? schema.default ?? []).length ? (value ?? schema.default) : [""]}
    onChange={(e) => onChange(Array.from(e.target.selectedOptions, (option) => option.value).filter(Boolean))}>
    <option value="">None</option>{schema.items.enum.map((option) => <option key={option} value={option}>{option}</option>)}</select>{hint}
    <small className="muted">Cmd/Ctrl-click to select multiple callbacks.</small></label>;
  if (schema.type === "boolean") return <label className="checkbox-label config-checkbox"><input type="checkbox" checked={Boolean(value ?? schema.default)} onChange={(e) => onChange(e.target.checked)} /> {label}</label>;
  if (["object", "array"].includes(schema.type)) return <label className="config-structured">{label}<textarea rows="5" required={required}
    value={typeof value === "string" ? value : JSON.stringify(value ?? schema.default ?? (schema.type === "array" ? [] : {}), null, 2)}
    placeholder={JSON.stringify(schema.default ?? {}, null, 2)} onChange={(e) => onChange(e.target.value)} />{hint}
    {schema.properties && <details><summary>Supported options</summary>{Object.entries(schema.properties).map(([key, property]) =>
      <div key={key}><strong>{key}</strong>: {property.enum?.join(" / ") || property.type}
        {property.minimum !== undefined && ` (${property.minimum}–${property.maximum ?? "∞"})`} — {property.description}</div>)}</details>}</label>;
  if (schema.type === "integer" || schema.type === "number") return <label>{label}<input type="number" value={value ?? schema.default ?? ""}
    min={schema.minimum} max={schema.maximum} step={schema.type === "integer" ? 1 : "any"} required={required}
    placeholder={schema.default === undefined ? "" : `Default: ${schema.default}`} onChange={(e) => onChange(e.target.value)} />{hint}</label>;
  return <label>{label}<textarea rows="2" value={value ?? schema.default ?? ""} required={required} onChange={(e) => onChange(e.target.value)} />{hint}</label>;
}

export default function Training({ project }) {
  const [versions, setVersions] = useState([]); const [jobs, setJobs] = useState([]);
  const [caps, setCaps] = useState(null); const [version, setVersion] = useState("");
  const [model, setModel] = useState(""); const [params, setParams] = useState(defaults);
  const [kind, setKind] = useState("local"); const [cpu, setCpu] = useState(true);
  const [gpu, setGpu] = useState(false); const [endpoint, setEndpoint] = useState("");
  const [template, setTemplate] = useState(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [probe, setProbe] = useState("");
  const tensorboardUrl = dashboardUrl(caps);
  const models = useMemo(() => [
    ...Object.values(caps?.models || {}).flat(), ...(caps?.workbenches || []),
  ], [caps]);
  const compatibleModels = models.filter((item) => item.available !== false && item.task === project.annotation_type);
  const selectedModel = useMemo(() => models.find((item) => item.key === model), [models, model]);
  async function load() {
    try {
      const [nextVersions, nextJobs, nextCaps] = await Promise.all([
        api(`/projects/${project.id}/versions`), api(`/projects/${project.id}/training/jobs`), api("/training/capabilities"),
      ]);
      setVersions(nextVersions); setJobs(nextJobs); setCaps(nextCaps);
      setVersion((value) => value || nextVersions[0]?.id || "");
      setModel((current) => {
        const candidates = [...Object.values(nextCaps.models || {}).flat(), ...(nextCaps.workbenches || [])];
        if (candidates.some((item) => item.key === current && item.available !== false && item.task === project.annotation_type)) return current;
        return candidates.find((item) => item.available !== false && item.task === project.annotation_type)?.key || "";
      });
    } catch (e) { setError(e.message); }
  }
  async function refreshJobs() {
    try { setJobs(await api(`/projects/${project.id}/training/jobs`)); }
    catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); const timer = setInterval(refreshJobs, 4000); return () => clearInterval(timer); }, [project.id]);
  useEffect(() => {
    if (!version) { setTemplate(null); return; }
    api(`/projects/${project.id}/training/template?version_id=${encodeURIComponent(version)}`)
      .then(setTemplate).catch((e) => setError(e.message));
  }, [project.id, version]);
  useEffect(() => { if (selectedModel) setParams(schemaDefaults(selectedModel)); }, [model, selectedModel]);
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
    }) }); await refreshJobs(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <div className="training-layout">
    <div className="page-heading"><div><h2>Model training</h2><p className="muted">Train against an immutable dataset version and track the run in MLflow.</p></div>
      {tensorboardUrl && liveMetricsEnabled(params, selectedModel) && <a className="button" href={tensorboardUrl} target="_blank" rel="noopener noreferrer">View live metrics</a>}</div>
    {error && <div className="alert">{error}</div>}
    <form className="panel training-form" onSubmit={submit}>
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
      <section><div className="eyebrow">MODEL CONFIGURATION</div><div className="training-grid training-params">
        {Object.entries(selectedModel?.config_schema?.properties || {}).filter(([key]) => !managedFields.has(key)).map(([key, property]) =>
          <ConfigField key={key} name={key} schema={resolveSchema(property, selectedModel.config_schema)} value={params[key]} required={selectedModel.config_schema.required?.includes(key)}
            onChange={(value) => setParams((current) => ({ ...current, [key]: value }))} />)}</div>
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
    </form>
    <div className="page-heading jobs-heading"><div><h2>Training jobs</h2><p className="muted">Jobs continue on the selected compute agent when you leave this page.</p></div></div>
    {!jobs.length ? <div className="empty"><h2>No training jobs yet</h2><p>Publish a dataset version, choose a model, and start your first run.</p></div> :
      <div className="panel table-wrap"><table><thead><tr><th>STATUS</th><th>MODEL</th><th>VERSION</th><th>COMPUTE</th><th>RESULT</th></tr></thead><tbody>{jobs.map((job) =>
        <tr key={job.id}><td><span className={`job-status ${job.status}`}>{job.status}</span></td><td>{job.base_model}</td><td>{versions.find((v) => v.id === job.version_id)?.name || job.version_id.slice(0,8)}</td>
          <td>{job.compute_target.kind}{job.compute_target.gpu ? " · GPU" : " · CPU"}</td><td>{job.error || Object.entries(job.metrics).map(([k,v]) => `${k}: ${v}`).join(" · ") || "-"}
            {job.artifact_available && <> · <a href={`/api/projects/${project.id}/training/jobs/${job.id}/artifact`}>model</a></>}{job.mlflow_url && <> · <a href={job.mlflow_url} target="_blank" rel="noreferrer">MLflow</a></>}</td></tr>)}</tbody></table></div>}
  </div>;
}
