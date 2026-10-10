import React, { useEffect, useRef } from "react";

export default function TrainingErrorDialog({ error, onClose }) {
  const dialog = useRef(null);
  useEffect(() => {
    if (error && !dialog.current.open) dialog.current.showModal();
    if (!error && dialog.current.open) dialog.current.close();
  }, [error]);
  return <dialog ref={dialog} className="config-help training-error" aria-labelledby="training-error-title" aria-describedby="training-error-message"
    onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <div className="config-help-heading"><h2 id="training-error-title">{error?.jobId ? "Training failed" : "Could not start training"}</h2>
      <button type="button" onClick={onClose}>Close</button></div>
    {error?.jobId && <p className="muted">Job: {error.jobId}</p>}
    <p id="training-error-message">{error?.message}</p>
    <p className="muted">Close this message to review your configuration and try again.</p>
  </dialog>;
}
