import React, { useEffect, useState } from "react";
import { api } from "../api";

export default function ModelReviewQueue({ project, onEdit }) {
  const [tasks, setTasks] = useState([]); const [error, setError] = useState("");
  async function load() { try { setTasks(await api(`/projects/${project.id}/review-tasks`)); } catch (e) { setError(e.message); } }
  useEffect(() => { load(); }, [project.id]);
  return <section className="panel"><h2>Model review queue</h2><p>Predictions are suggestions. Editing live annotations does not change the frozen evaluation dataset. Publish a new version before retraining.</p>{error && <p role="alert">{error}</p>}{!tasks.length && <p>Send failure examples here from a saved model.</p>}
    {tasks.map((task) => <article key={task.id}><h3>{task.source_path || task.prediction.source_path}</h3><p>{task.status} · created by {task.created_by} · model {task.model_id.slice(0, 8)}</p><details><summary>Saved model prediction</summary><pre>{JSON.stringify(task.prediction, null, 2)}</pre></details>
      <button disabled={!task.source_path || project.permission === "read"} onClick={() => onEdit(task.image_id)}>Edit current annotation</button></article>)}
  </section>;
}
