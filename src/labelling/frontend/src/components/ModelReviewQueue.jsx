import React, { useEffect, useState } from "react";
import { api } from "../api";

function TaskActions({ project, task, onSaved }) {
  const [assignee, setAssignee] = useState(task.assignee); const [status, setStatus] = useState(task.status); const [reason, setReason] = useState(task.resolution); const [error, setError] = useState("");
  return <form className="review-task-form" onSubmit={async (e) => { e.preventDefault(); try { await api(`/projects/${project.id}/review-tasks/${task.id}`, { method: 'PUT', body: JSON.stringify({ assignee, status, resolution: reason }) }); await onSaved(); setError(""); } catch (e) { setError(e.message); } }}><label>Assign to username<input value={assignee} onChange={(e) => setAssignee(e.target.value)}/></label><label>Status<select value={status} onChange={(e) => setStatus(e.target.value)}>{['open','needs_changes','resolved'].map((v) => <option key={v}>{v}</option>)}</select></label><label>Reason / resolution<textarea required={status !== 'open'} value={reason} onChange={(e) => setReason(e.target.value)}/></label><button>Save review task</button>{error && <p role="alert">{error}</p>}</form>;
}

export default function ModelReviewQueue({ project, onEdit }) {
  const [tasks, setTasks] = useState([]); const [error, setError] = useState("");
  async function load() { try { setTasks(await api(`/projects/${project.id}/review-tasks`)); } catch (e) { setError(e.message); } }
  useEffect(() => { load(); }, [project.id]);
  return <section className="panel workspace-panel"><h2>Model review queue</h2><p>Predictions are suggestions. Editing live annotations does not change the frozen evaluation dataset. Publish a new version before retraining.</p>{error && <p role="alert">{error}</p>}{!tasks.length && <p>Send failure examples here from a saved model.</p>}
    {tasks.map((task) => <article className="review-task" key={task.id}><h3>{task.source_path || task.prediction.source_path}</h3><p>{task.status} · created by {task.created_by} · model {task.model_id.slice(0, 8)}</p><details><summary>Saved model prediction</summary><pre>{JSON.stringify(task.prediction, null, 2)}</pre></details>
      {project.permission !== "read" && <TaskActions project={project} task={task} onSaved={load} />}
      <button disabled={!task.source_path || project.permission === "read"} onClick={() => onEdit(task.image_id)}>Edit current annotation</button></article>)}
  </section>;
}
