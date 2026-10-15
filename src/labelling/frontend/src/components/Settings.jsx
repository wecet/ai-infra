import RepositoryAccess from "./RepositoryAccess";
import React, { useState } from "react";
import { api, color } from "../api";

function Settings({ project, onUpdated }) {
  const anomaly = project.annotation_type === "anomaly_detection";
  const [form, setForm] = useState({ name: project.name, description: project.description || "",
    labelling_instructions: project.labelling_instructions || "", ai_instructions: project.ai_instructions || "",
    export_train_percent: project.export_train_percent ?? 80 });
  const [saving, setSaving] = useState(false); const [message, setMessage] = useState("");
  const [newClass, setNewClass] = useState(""); const [newColor, setNewColor] = useState("#2b702e");
  const [classBusy, setClassBusy] = useState(false);
  function field(name) { return { value: form[name], onChange: (e) => setForm({ ...form,
    [name]: e.target.type === "number" ? Number(e.target.value) : e.target.value }) }; }
  async function submit(e) {
    e.preventDefault(); setSaving(true); setMessage("");
    try { const saved = await api(`/projects/${project.id}`, { method: "PUT", body: JSON.stringify(form) });
      onUpdated(saved); setMessage("Project settings saved."); }
    catch (e) { setMessage(e.message); } finally { setSaving(false); }
  }
  async function updateCategory(item, changes) {
    setClassBusy(true); setMessage("");
    try { onUpdated(await api(`/projects/${project.id}/classes/${item.id}`, { method: "PUT",
      body: JSON.stringify({ name: item.name, color: item.color || color(item.id), archived: !!item.archived, ...changes }) })); }
    catch (e) { setMessage(e.message); } finally { setClassBusy(false); }
  }
  async function addCategory(e) {
    e.preventDefault(); setClassBusy(true); setMessage("");
    try { onUpdated(await api(`/projects/${project.id}/classes`, { method: "POST",
      body: JSON.stringify({ name: newClass, color: newColor }) })); setNewClass(""); }
    catch (e) { setMessage(e.message); } finally { setClassBusy(false); }
  }
  async function mergeCategory(source, targetId) {
    if (!targetId || !window.confirm(`Merge “${source.name}” into the selected class? Existing annotations will be remapped.`)) return;
    setClassBusy(true); setMessage("");
    try { onUpdated(await api(`/projects/${project.id}/classes/${source.id}/merge`, { method: "POST",
      body: JSON.stringify({ target_category_id: Number(targetId) }) })); }
    catch (e) { setMessage(e.message); } finally { setClassBusy(false); }
  }
  return <><RepositoryAccess project={project} onUpdated={onUpdated} /><form className="panel settings-form" onSubmit={submit}><div><h2>Project settings</h2>
    <p className="muted">{anomaly ? "Set dataset details and the split frozen into future published versions." : "Guidance is shared with labellers. AI guidance is also included in automatic suggestions."}</p></div>
    <fieldset className="settings-fields" disabled={project.permission === "read"}>
    <label>Project name<input required maxLength="150" {...field("name")} /></label>
    <label>Description<textarea rows="3" maxLength="2000" placeholder="Purpose, source, and scope of this dataset." {...field("description")} /></label>
    {!anomaly && <label>Labelling instructions<textarea rows="5" maxLength="4000" placeholder="Rules labellers should follow." {...field("labelling_instructions")} /></label>}
    {project.annotation_type === "object_detection" && <label>AI instructions<textarea rows="5" maxLength="4000"
      placeholder="Project-specific criteria for AI-generated boxes." {...field("ai_instructions")} /></label>}
    <label>Default train split (%)<input type="number" min="0" max="100" {...field("export_train_percent")} /></label>
    {!anomaly && <section className="class-management"><div><h3>Classes</h3><p className="muted">Rename, recolour, archive, or merge classes. Existing annotations follow merged classes.</p></div>
      {project.classes.map((item) => <div className={`managed-class ${item.archived ? "archived" : ""}`} key={item.id}>
        <input type="color" aria-label={`${item.name} colour`} value={item.color || color(item.id)} disabled={classBusy}
          onChange={(e) => updateCategory(item, { color: e.target.value })} />
        <input aria-label={`Rename ${item.name}`} defaultValue={item.name} disabled={classBusy}
          onBlur={(e) => { if (e.target.value.trim() && e.target.value.trim() !== item.name) updateCategory(item, { name: e.target.value }); }} />
        <button type="button" disabled={classBusy} onClick={() => updateCategory(item, { archived: !item.archived })}>
          {item.archived ? "Restore" : "Archive"}</button>
        <select aria-label={`Merge ${item.name}`} defaultValue="" disabled={classBusy}
          onChange={(e) => { mergeCategory(item, e.target.value); e.target.value = ""; }}><option value="">Merge into…</option>
          {project.classes.filter((target) => target.id !== item.id).map((target) => <option key={target.id} value={target.id}>{target.name}</option>)}</select>
      </div>)}
      <div className="managed-class add-class"><input type="color" aria-label="New class colour" value={newColor}
        onChange={(e) => setNewColor(e.target.value)} /><input placeholder="New class name" maxLength="100" value={newClass}
        onChange={(e) => setNewClass(e.target.value)} /><button type="button" className="primary" disabled={classBusy || !newClass.trim()}
        onClick={addCategory}>Add class</button></div>
    </section>}
    {message && <div className={message.endsWith("saved.") ? "notice" : "alert"}>{message}</div>}
    <div className="actions"><button className="primary" disabled={saving}>{saving ? "Saving…" : "Save settings"}</button></div>
    </fieldset>
  </form></>;
}

export default Settings;

