import { formatDate } from "../dates";
import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { connectionArrowhead, connectionLabel, connectionPath } from "../lineage-connectors";
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
  const canvas = useRef(null);
  const [connectors, setConnectors] = useState([]);
  const [tooltip, setTooltip] = useState(null);
  const [activeNode, setActiveNode] = useState(null);
  const [lineage, setLineage] = useState(null); const [error, setError] = useState("");
  async function load() { try { setLineage(await api(`/projects/${project.id}/lineage`)); setError(""); } catch (e) { setError(e.message); } }
  useEffect(() => { load(); }, [project.id]);
  const byStage = useMemo(() => {
    const result = {};
    stages.forEach((stage) => { result[stage.key] = lineage?.nodes.filter((node) => stage.types ? stage.types.includes(node.type) : node.type === stage.key) || []; });
    return result;
  }, [lineage]);
  useLayoutEffect(() => {
    if (!lineage || !canvas.current) return;
    const element = canvas.current;
    const measure = () => {
      const origin = element.getBoundingClientRect();
      const boxes = new Map([...element.querySelectorAll("[data-lineage-node]")].map((node) => {
        const rect = node.getBoundingClientRect();
        return [node.dataset.lineageNode, { x: rect.left - origin.left, y: rect.top - origin.top, width: rect.width, height: rect.height }];
      }));
      const nodes = new Map(lineage.nodes.map((node) => [node.id, node]));
      setConnectors(lineage.edges.flatMap((edge, index) => {
        const from = boxes.get(edge.from), to = boxes.get(edge.to);
        return from && to ? [{ ...edge, id: index, path: connectionPath(from, to, nodes.get(edge.from).type === "project"), head: connectionArrowhead(to, from, nodes.get(edge.from).type === "project"),
          label: connectionLabel(nodes.get(edge.from), nodes.get(edge.to), edge.kind) }] : [];
      }));
    };
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    element.querySelectorAll("[data-lineage-node]").forEach((node) => observer.observe(node));
    measure();
    return () => observer.disconnect();
  }, [lineage]);
  function showConnection(event, edge) {
    const rect = event.currentTarget.getBoundingClientRect();
    setTooltip({ id: edge.id, label: edge.label,
      x: Math.min(event.clientX || rect.left + rect.width / 2, window.innerWidth - 310),
      y: Math.min(event.clientY || rect.top + rect.height / 2, window.innerHeight - 90) });
  }
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
      <div className="lineage-graph" onScroll={() => setTooltip(null)}><div className="lineage-canvas" ref={canvas}>
      <svg className="lineage-connectors" aria-label="Lineage connections">
        {connectors.map((edge) => <g key={edge.id} className={`lineage-connection ${edge.kind === "snapshot" ? "snapshot" : ""} ${tooltip?.id === edge.id || activeNode === edge.from || activeNode === edge.to ? "active" : ""}`}>
          <path aria-hidden="true" className="lineage-connection-line" d={edge.path}/>
          <path className="lineage-connection-head" d={edge.head} aria-hidden="true"/>
          <path className="lineage-connection-hit" d={edge.path} tabIndex="0" role="img" aria-label={edge.label}
            onMouseEnter={(event) => showConnection(event, edge)} onMouseLeave={() => setTooltip(null)}
            onFocus={(event) => showConnection(event, edge)} onBlur={() => setTooltip(null)}
            onKeyDown={(event) => { if (event.key === "Escape") setTooltip(null); }}/>
        </g>)}
      </svg>
      <div className="lineage-root" data-lineage-node={`project:${project.id}`}><span className="lineage-kind">Project</span><strong>{project.name}</strong></div>
      <div className="lineage-flow">{stages.map((stage, stageIndex) => <section className="lineage-stage" key={stage.key}>
        <header><span>{stageIndex + 1}</span><strong>{stage.title}</strong></header>
        <div className="lineage-stage-nodes">{byStage[stage.key].length ? byStage[stage.key].map((node) =>
          <button key={node.id} data-lineage-node={node.id} onMouseEnter={() => setActiveNode(node.id)} onMouseLeave={() => setActiveNode(null)} onFocus={() => setActiveNode(node.id)} onBlur={() => setActiveNode(null)} className={`lineage-node lineage-${node.type} lineage-${node.subtype || ""} ${node.status || ""}`} onClick={() => open(node)} disabled={!node.target}>
            <span className="lineage-kind">
              {node.type === "lakefs" && <svg className="lineage-type-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="7" cy="5" r="3"/><circle cx="7" cy="19" r="3"/><circle cx="18" cy="7" r="3"/><path d="M7 8v8m0-3c7 0 11-1 11-3"/></svg>}
              {node.type === "training" && <svg className="lineage-type-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="4"/><path d="m10 7 7 5-7 5Z"/></svg>}
              {nodeLabel(node)}
            </span><strong>{node.title}</strong><small>{node.subtitle}</small><time>{formatDate(node.created_at)}</time>
          </button>) : <div className="lineage-empty">No {stage.title.toLowerCase()} yet</div>}</div>
      </section>)}</div></div></div>
      {tooltip && <div className="lineage-connection-tooltip" role="tooltip" style={{ left: Math.max(8, tooltip.x), top: tooltip.y + 12 }}>{tooltip.label}</div>}
      <p className="muted small lineage-note">Arrows connect specific entries. Hover or focus an arrow to describe its connection. Dashed arrows link a lakeFS snapshot to training on the same dataset version. Select a card to open its details.</p>
    </>}
  </div>;
}
