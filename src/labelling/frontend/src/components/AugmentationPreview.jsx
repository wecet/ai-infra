import React, { useState } from "react";
import { api } from "../api";

export default function AugmentationPreview({ project, request }) {
  const [seed, setSeed] = useState(42); const [result, setResult] = useState(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function preview() { setBusy(true); try { setResult(await api(`/projects/${project.id}/augmentation-preview`, { method: 'POST', body: JSON.stringify({ ...request(), seed }) })); setError(""); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  return <details><summary>Preview training augmentations</summary><p>Uses the selected workbench's augmentor on the first frozen fitting sample.</p><label>Seed<input type="number" min="0" max="2147483647" value={seed} onChange={(e) => setSeed(Number(e.target.value))}/></label><button type="button" disabled={busy} onClick={preview}>{busy ? 'Previewing…' : 'Generate preview'}</button>{error && <p role="alert">{error}</p>}
    {result && <><p>{result.source_path} · seed {result.seed}</p><div className="training-grid">{['before','after'].map((key) => <figure key={key}><div style={{ position: 'relative' }}><img width="260" src={result[key]} alt={`${key} augmentation`}/>{key === 'after' && <svg style={{ position: 'absolute', inset: 0, width: 260, height: '100%' }} viewBox={`0 0 ${result.width} ${result.height}`}>{result.boxes.map((box, i) => <rect key={i} x={box.x} y={box.y} width={box.width} height={box.height} fill="none" stroke="#ff6347" strokeWidth="2"/>)}</svg>}</div><figcaption>{key}</figcaption></figure>)}</div></>}
  </details>;
}
