import React, { useEffect, useRef, useState } from "react";
import { api } from "../api";

export default function ImportStaging({ project, files, onClose, onImported }) {
  const dialog = useRef(null); const started = useRef(false);
  const [rows, setRows] = useState(files.map((file) => ({ file, status: 'checking', selected: true, error: '' })));
  const [busy, setBusy] = useState(true); const batch = useRef(null);
  const body = (file) => { const data = new FormData(); data.append('file', file, file.webkitRelativePath || file.name); return data; };
  useEffect(() => {
    dialog.current.showModal();
    if (started.current) return; started.current = true;
    (async () => {
      for (let i = 0; i < files.length; i++) {
        try { const preview = await api(`/projects/${project.id}/imports/preview`, { method: 'POST', body: body(files[i]) }); setRows((rows) => rows.map((row, index) => index === i ? { ...row, ...preview } : row)); }
        catch (e) { setRows((rows) => rows.map((row, index) => index === i ? { ...row, status: 'rejected', selected: false, error: e.message } : row)); }
      }
      setBusy(false);
    })();
  }, [files]);
  async function commit() {
    setBusy(true);
    try {
      if (!batch.current) batch.current = (await api(`/projects/${project.id}/batches`, { method: 'POST', body: JSON.stringify({ kind: 'new_additions' }) })).id;
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i]; if (!row.selected || ['imported','rejected','existing'].includes(row.status)) continue;
        try { await api(`/projects/${project.id}/images?batch_id=${batch.current}`, { method: 'POST', body: body(row.file) }); setRows((rows) => rows.map((r, index) => index === i ? { ...r, status: 'imported', error: '' } : r)); }
        catch (e) { setRows((rows) => rows.map((r, index) => index === i ? { ...r, status: 'failed', error: e.message } : r)); }
      }
      await onImported();
    } finally { setBusy(false); }
  }
  return <dialog ref={dialog} className="model-evaluation" aria-labelledby="import-preview-title" onCancel={(e) => { if (busy) e.preventDefault(); else onClose(); }}><div className="modal-heading"><h2 id="import-preview-title">Review image import</h2><button disabled={busy} onClick={onClose}>Close</button></div><p>Choose accepted samples before importing. Retrying skips successful and identical existing samples.</p>
    <ul>{rows.map((row, i) => <li key={i}><label><input type="checkbox" checked={row.selected} disabled={busy || ['rejected','imported','existing'].includes(row.status)} onChange={(e) => setRows((rows) => rows.map((r, index) => index === i ? { ...r, selected: e.target.checked } : r))}/>{row.file.webkitRelativePath || row.file.name}</label> · {row.status} {row.width && `${row.width} × ${row.height}`} {row.error}</li>)}</ul>
    <button disabled={busy || !rows.some((r) => r.selected && ['accepted','failed'].includes(r.status))} onClick={commit}>{busy ? 'Processing…' : 'Import selected / retry failed'}</button>
  </dialog>;
}
