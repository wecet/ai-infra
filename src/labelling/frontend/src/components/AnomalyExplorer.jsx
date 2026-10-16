import React, { useMemo, useState } from "react";

export default function AnomalyExplorer({ project, model, rows }) {
  const ranked = useMemo(() => rows.map((row) => ({ ...row, score: row.predictions[0]?.anomaly_score })).filter((row) => Number.isFinite(row.score)).sort((a, b) => b.score - a.score), [rows]);
  const [threshold, setThreshold] = useState(0);
  if (!ranked.length) return null;
  const low = ranked.at(-1).score, high = ranked[0].score;
  const bins = Array.from({ length: 10 }, () => 0);
  ranked.forEach((row) => bins[Math.min(9, Math.floor((row.score - low) / (high - low || 1) * 10))]++);
  const flagged = ranked.filter((row) => row.score > threshold);
  return <section className="panel"><h3>Explore anomaly threshold</h3><p>Exploratory only. Saved model flags and evaluation metrics remain unchanged. These samples have no verified anomaly labels.</p>
    <label>Score threshold<input type="number" step="any" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /></label>
    <input aria-label="Explore score threshold" type="range" min={low} max={high || 1} step={(high - low) / 1000 || .001} value={Math.min(high, Math.max(low, threshold))} onChange={(e) => setThreshold(Number(e.target.value))} />
    <p>{flagged.length} / {ranked.length} flagged ({(flagged.length / ranked.length * 100).toFixed(1)}%)</p>
    <svg viewBox="0 0 500 120" role="img" aria-label={`Score histogram from ${low.toFixed(4)} to ${high.toFixed(4)}`} style={{ maxWidth: 600 }}>{bins.map((count, i) => <g key={i}><rect x={i * 50 + 2} y={100 - count / Math.max(...bins) * 80} width="44" height={count / Math.max(...bins) * 80} fill="currentColor"><title>{count} scores in bin {i + 1}</title></rect><text x={i * 50 + 18} y="118" fontSize="12" fill="currentColor">{count}</text></g>)}</svg>
    <details><summary>Highest scores</summary><div className="evaluation-grid">{ranked.slice(0, 24).map((row) => <figure key={row.image_id}><img loading="lazy" width="160" src={`/api/projects/${project.id}/versions/${model.version_id}/images/${row.image_id}/file`} alt={row.source_path}/><figcaption>{row.source_path}: {row.score.toFixed(4)} {row.score > threshold ? '· flagged' : ''}</figcaption></figure>)}</div></details>
  </section>;
}
