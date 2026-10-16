import React, { useState } from "react";
import { api } from "../api";

export default function RunComparison({ project, models }) {
  const [left, setLeft] = useState(""); const [right, setRight] = useState("");
  const [result, setResult] = useState(null); const [error, setError] = useState("");
  async function compare() {
    try { setResult(await api(`/projects/${project.id}/model-comparison?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`)); setError(""); } catch (e) { setError(e.message); }
  }
  return <section className="panel"><h2>Compare saved models</h2><div className="training-grid">{[["Left model", left, setLeft], ["Right model", right, setRight]].map(([label, value, change]) => <label key={label}>{label}<select value={value} onChange={(e) => { change(e.target.value); setResult(null); }}><option value="">Select model</option>{models.map((model) => <option key={model.id} value={model.id}>{model.run_name || model.name}</option>)}</select></label>)}</div>
    <button disabled={!left || !right || left === right} onClick={compare}>Compare</button>{error && <p role="alert">{error}</p>}
    {result && <>{!result.compatible && <p className="notice">Comparison unavailable: {result.reasons.join("; ")}</p>}
      {result.compatible && <table><thead><tr><th>Metric</th><th>Left</th><th>Right</th></tr></thead><tbody>{Object.keys(result.metrics[0]).map((key) => <tr key={key}><th>{key}</th><td>{result.metrics[0][key]}</td><td>{result.metrics[1][key] ?? "Unavailable"}</td></tr>)}</tbody></table>}
      <details><summary>Configuration differences</summary><pre>{JSON.stringify(result.config_changes, null, 2)}</pre></details>
      {result.examples.map((pair) => <details key={pair.image_id}><summary>{pair.left.source_path}</summary><div className="training-grid">{[pair.left, pair.right].map((row, i) => <figure key={i}><img width="200" src={`/api/projects/${project.id}/versions/${models.find((m) => m.id === left)?.version_id}/images/${pair.image_id}/file`} alt={row.source_path}/><figcaption>{i ? "Right" : "Left"}: {JSON.stringify(row.predictions)}</figcaption></figure>)}</div></details>)}</>}
  </section>;
}
