import { useRef, useState } from "react";
import { api } from "./api";

export function useAnnotationPersistence({ path, data, setData, onSaved }) {
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const undoStack = useRef([]);
  const redoStack = useRef([]);
  async function persist(next, record = true) {
    if (inFlight.current) return false;
    if (record && data) {
      undoStack.current.push(structuredClone(data));
      if (undoStack.current.length > 50) undoStack.current.shift();
      redoStack.current = [];
    }
    inFlight.current = true;
    setData(next);
    setDirty(true);
    setSaving(true);
    setError("");
    try {
      const saved = await api(path, {
        method: "PUT",
        body: JSON.stringify(next),
      });
      setData(saved);
      setDirty(false);
      onSaved(saved);
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    } finally {
      inFlight.current = false;
      setSaving(false);
    }
  }
  const disabled = saving || uploading || !ready || !data;
  return { saving, setSaving, dirty, setDirty, error, setError, inFlight, undoStack, redoStack, persist };
}
