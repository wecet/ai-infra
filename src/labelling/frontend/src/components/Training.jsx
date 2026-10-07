import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api";

const defaults = { epochs: 1, batch_size: 32, learning_rate: 0.001, image_size: 224 };

export default function Training({ project }) {
  const [versions, setVersions] = useState([]); const [jobs, setJobs] = useState([]);
  const [caps, setCaps] = useState(null); const [version, setVersion] = useState("");
  const [model, setModel] = useState(""); const [params, setParams] = useState(defaults);
  const [kind, setKind] = useState("local"); const [cpu, setCpu] = useState(true);
  const [gpu, setGpu] = useState(false); const [endpoint, setEndpoint] = useState("");
  const [template, setTemplate] = useState(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const [probe, setProbe] = useState("");
  const models = caps?.models?.[project.annotation_type] || [];
  const selectedModel = useMemo(() => models.find((item) => item.key === model), [models, model]);
  async function load() {
    try {
      const [nextVersions, nextJobs, nextCaps] = await Promise.all([
        api(`/projects/${project.id}/versions`), api(`/projects/${project.id}/training/jobs`), api("/training/capabilities"),
      ]);
      setVersions(nextVersions); setJobs(nextJobs); setCaps(nextCaps);
      setVersion((value) => value || nextVersions[0]?.id || "");
      if (!model && nextCaps.models?.[project.annotation_type]?.[0]) setModel(nextCaps.models[project.annotation_type][0].key);
    } catch (e) { setError(e.message); }
  }
  useEffect(() => { load(); const timer = setInterval(load, 4000); return () => clearInterval(timer); }, [project.id]);
  useEffect(() => {
    if (!version) { setTemplate(null); return; }
    api(`/projects/${project.id}/training/template?version_id=${encodeURIComponent(version)}`)
      .then(setTemplate).catch((e) => setError(e.message));
  }, [project.id, version]);
  useEffect(() => { if (selectedModel) setParams({ ...defaults, ...selectedModel.defaults }); }, [model]);
  async function testRemote() {
    setProbe("Testing…"); setError("");
    try { const result = await api("/training/probe", { method: "POST", body: JSON.stringify({ kind: "remote", endpoint, cpu: true, gpu: false }) });
      setCaps(result); setProbe(`Connected · CPU ${result.cpu.available ? "ready" : "unavailable"} · GPU ${result.gpu.available ? "ready" : "unavailable"}`);
    } catch (e) { setProbe(""); setError(e.message); }
  }
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError("");
    try { await api(`/projects/${project.id}/training/jobs`, { method: "POST", body: JSON.stringify({
      version_id: version, base_model: model, hyperparameters: params,
      compute: { kind, cpu: kind === "local" ? cpu : true, gpu: kind === "local" ? gpu : false, endpoint },
    }) }); await load(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  return <div className="training-layout">
    <div className="page-heading"><div><h2>Model training</h2><p className="muted">Train against an immutable dataset version and track the run in MLflow.</p></div></div>
    {error && <div className="alert">{error}</div>}
    <form className="panel training-form" onSubmit={submit}>
      <section><div className="eyebrow">DATA &amp; MODEL</div>
        <div className="training-grid"><label>Published version<select value={version} required onChange={(e) => setVersion(e.target.value)}>
          <option value="">Select a version</option>{versions.map((v) => <option key={v.id} value={v.id}>{v.name} · {v.sample_count} samples</option>)}</select></label>
          <label>Base model<select value={model} required onChange={(e) => setModel(e.target.value)}>{models.map((m) => <option key={m.key} value={m.key}>{m.name}</option>)}</select></label></div>
        {selectedModel && <p className="muted">{selectedModel.description}</p>}
        {template && <details className="run-template"><summary>Prefilled run configuration</summary>
          <dl><div><dt>Dataset</dt><dd>{template.dataset_path}</dd></div>
            <div><dt>Classes</dt><dd>{template.class_names.join(", ")}</dd></div>
            <div><dt>Output</dt><dd>{template.output_path}</dd></div>
            <div><dt>MLflow</dt><dd>{template.mlflow_url}</dd></div></dl>
          <p className="muted small">These infrastructure fields come from the published version and are locked for reproducibility.</p>
        </details>}
      </section>
      <section><div className="eyebrow">HYPERPARAMETERS</div><div className="training-grid training-params">
        {[['epochs','Epochs'],['batch_size','Batch size'],['learning_rate','Learning rate'],['image_size','Image size']].map(([key,label]) =>
          <label key={key}>{label}<input type="number" min={key === 'learning_rate' ? '0.000001' : '1'} step={key === 'learning_rate' ? '0.000001' : '1'} value={params[key]}
            onChange={(e) => setParams({ ...params, [key]: Number(e.target.value) })} /></label>)}</div></section>
      <section><div className="eyebrow">COMPUTE TARGET</div><div className="compute-choice">
        <label className={`compute-card ${kind === 'local' ? 'selected' : ''}`}><input type="radio" name="target" checked={kind === 'local'} onChange={() => { setKind('local'); load(); }} /><span><strong>Local agent</strong><small>Bundled with this Compose stack</small></span></label>
        <label className={`compute-card ${kind === 'remote' ? 'selected' : ''}`}><input type="radio" name="target" checked={kind === 'remote'} onChange={() => setKind('remote')} /><span><strong>Remote agent</strong><small>Connect to another machine by IP</small></span></label></div>
        {kind === "local" ? <div className="device-row">
          <label className="checkbox-label"><input type="checkbox" checked={cpu} onChange={(e) => setCpu(e.target.checked)} /> CPU</label>
          <label className={`checkbox-label ${!caps?.gpu?.available ? 'device-disabled' : ''}`} title={caps?.gpu?.reason || ''}><input type="checkbox" checked={gpu} disabled={!caps?.gpu?.available} onChange={(e) => setGpu(e.target.checked)} /> GPU</label>
          {!caps?.gpu?.available && <span className="muted small">{caps?.gpu?.reason || "Checking GPU availability…"}</span>}
        </div> : <div className="remote-row"><label>Agent IP address<input value={endpoint} required placeholder="192.168.1.20:8090" onChange={(e) => setEndpoint(e.target.value)} /></label><button type="button" onClick={testRemote}>Test connection</button><span className="muted">{probe}</span></div>}
      </section>
      <div className="training-submit"><button className="primary" disabled={busy || !version || !model || (kind === 'local' && !cpu && !gpu)}>{busy ? "Queuing…" : "Start training"}</button></div>
    </form>
    <div className="page-heading jobs-heading"><div><h2>Training jobs</h2><p className="muted">Jobs continue on the selected compute agent when you leave this page.</p></div></div>
    {!jobs.length ? <div className="empty"><h2>No training jobs yet</h2><p>Publish a dataset version, choose a model, and start your first run.</p></div> :
      <div className="panel table-wrap"><table><thead><tr><th>STATUS</th><th>MODEL</th><th>VERSION</th><th>COMPUTE</th><th>RESULT</th></tr></thead><tbody>{jobs.map((job) =>
        <tr key={job.id}><td><span className={`job-status ${job.status}`}>{job.status}</span></td><td>{job.base_model}</td><td>{versions.find((v) => v.id === job.version_id)?.name || job.version_id.slice(0,8)}</td>
          <td>{job.compute_target.kind}{job.compute_target.gpu ? " · GPU" : " · CPU"}</td><td>{job.error || Object.entries(job.metrics).map(([k,v]) => `${k}: ${v}`).join(" · ") || "-"}
            {job.artifact_available && <> · <a href={`/api/projects/${project.id}/training/jobs/${job.id}/artifact`}>model</a></>}{job.mlflow_url && <> · <a href={job.mlflow_url} target="_blank" rel="noreferrer">MLflow</a></>}</td></tr>)}</tbody></table></div>}
  </div>;
}
