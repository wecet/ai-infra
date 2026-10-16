import React, { useState } from "react";
import { api } from "../api";
export default function AnnotationImport({ project, onImported }) {
  const [file, setFile] = useState(null); const [preview, setPreview] = useState(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const body = (source) => { const value = new FormData(); value.append('file', source); return value; };
  async function inspect(source) { setFile(source); setPreview(null); if (!source) return; setBusy(true); try { setPreview(await api(`/projects/${project.id}/annotations/preview`, { method: 'POST', body: body(source) })); setError(""); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  async function commit() { setBusy(true); try { const result = await api(`/projects/${project.id}/annotations/import`, { method: 'POST', body: body(file) }); setError(`Import complete: ${JSON.stringify(result)}`); setPreview(null); await onImported(); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  return <section className="panel workspace-panel"><h2>Import COCO annotations</h2><p>Preview class mappings and sample matches before applying JSON or a COCO ZIP.</p><input aria-label="Annotation file" type="file" accept=".json,.zip" disabled={busy || project.permission === 'read'} onChange={(e) => inspect(e.target.files[0])}/>{error && <p role="status">{error}</p>}
    {preview && <><ul>{preview.class_mapping.map((mapping, i) => <li key={i}>{mapping.source} → {mapping.target || 'Missing class: add it in Settings first'}</li>)}</ul><p>{preview.samples.length} samples · {preview.samples.filter((s) => s.status === 'matched').length} match existing images</p><details><summary>Sample matching</summary><pre>{JSON.stringify(preview.samples, null, 2)}</pre></details><button disabled={busy || !preview.can_import} onClick={commit}>Apply annotations</button></>}
  </section>;
}
