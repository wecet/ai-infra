import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api";

const stages = [
  { key: "batch", title: "Dataset events" },
  { key: "version", title: "Published versions" },
  { key: "execution", title: "Commits & runs", types: ["lakefs", "training"] },
  { key: "model", title: "Registered models" },
  { key: "deployment", title: "Deployments" },
];

function nodeLabel(node) {
  if (node.subtype === "images_deleted") return "Deleted";
  if (node.subtype === "images_restored") return "Restored";
  return node.type === "lakefs" ? "lakeFS commit" : node.type.replaceAll("_", " ");
}

export default function Lineage({ project, onNavigate }) {
  const [lineage, setLineage] = useState(null); const [error, setError] = useState("");
  async function load() { try { setLineage(await api(`/projects/${project.id}/lineage`)); setError(""); } catch (e) { setError(e.message); } }
  useEffect(() => { load(); }, [project.id]);
  const byStage = useMemo(() => {
    const result = {};
    stages.forEach((stage) => { result[stage.key] = lineage?.nodes.filter((node) => stage.types ? stage.types.includes(node.type) : node.type === stage.key) || []; });
    return result;
  }, [lineage]);
  function open(node) {
    const target = node.target || {};
    if (target.kind === "external" && target.url) window.open(target.url, "_blank", "noopener,noreferrer");
    else if (target.kind === "version") onNavigate("versions", target.id);
    else if (target.kind === "history") onNavigate("history", target.id);
    else if (target.kind === "training") onNavigate("training", target.id);
  }
  return <div className="lineage-page">
    <div className="page-heading"><div><h2>Dataset lineage</h2><p className="muted">Trace data from ingestion and review through versions, experiments, models, and deployments.</p></div><button onClick={load}>Refresh</button></div>
    {error && <div className="alert">{error}<button onClick={load}>Retry</button></div>}
    {!lineage ? <div className="empty">Loading lineage…</div> : <>
      <div className="lineage-counts">{Object.entries(lineage.counts).map(([key, value]) => <div key={key}><strong>{value}</strong><span>{key.replaceAll("_", " ")}</span></div>)}</div>
      <div className="lineage-root"><span className="lineage-kind">Project</span><strong>{project.name}</strong></div>
      <div className="lineage-flow">{stages.map((stage, stageIndex) => <section className="lineage-stage" key={stage.key}>
        <header><span>{stageIndex + 1}</span><strong>{stage.title}</strong></header>
        <div className="lineage-stage-nodes">{byStage[stage.key].length ? byStage[stage.key].map((node) =>
          <button key={node.id} className={`lineage-node lineage-${node.type} lineage-${node.subtype || ""} ${node.status || ""}`} onClick={() => open(node)} disabled={!node.target}>
            <span className="lineage-kind">{nodeLabel(node)}</span><strong>{node.title}</strong><small>{node.subtitle}</small><time>{new Date(`${node.created_at}${node.created_at?.endsWith("Z") ? "" : "Z"}`).toLocaleString()}</time>
          </button>) : <div className="lineage-empty">No {stage.title.toLowerCase()} yet</div>}</div>
      </section>)}</div>
      <p className="muted small lineage-note">Select a node to open its dataset history, immutable version, lakeFS commit, training job, or MLflow run.</p>
    </>}
  </div>;
}
