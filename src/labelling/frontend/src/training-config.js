export const managedFields = new Set(["dataset_path", "output_path", "mlflow_url", "project_id", "dataset_version_id", "class_names", "devices"]);

export function resolveSchema(property, schema) {
  const referenced = property.$ref?.startsWith("#/$defs/") ? schema?.$defs?.[property.$ref.slice(8)] : null;
  return { ...referenced, ...property };
}

export function schemaDefaults(model) {
  const values = { ...(model?.defaults || {}) };
  Object.entries(model?.config_schema?.properties || {}).forEach(([key, property]) => {
    const field = resolveSchema(property, model.config_schema);
    if (!managedFields.has(key) && field.default !== undefined) values[key] = field.default;
  });
  return values;
}

export function normalizeParams(values, model) {
  const result = {};
  for (const [key, property] of Object.entries(model?.config_schema?.properties || {})) {
    if (managedFields.has(key)) continue;
    const field = resolveSchema(property, model.config_schema);
    let value = values[key];
    if (value === undefined || value === null || (typeof value === "string" && value.trim() === "")) {
      value = field.default ?? model.defaults?.[key];
      if (value === undefined) continue;
    }
    if (["object", "array"].includes(field.type)) {
      if (typeof value === "string") {
        try { value = JSON.parse(value); }
        catch { throw new Error(`${field.title || key} must be valid JSON.`); }
      }
      if (field.type === "array" ? !Array.isArray(value) : value === null || Array.isArray(value) || typeof value !== "object") {
        throw new Error(`${field.title || key} must be a JSON ${field.type}.`);
      }
    }
    if (["integer", "number"].includes(field.type)) {
      value = Number(value);
      if (!Number.isFinite(value) || (field.type === "integer" && !Number.isInteger(value))) {
        throw new Error(`${field.title || key} must be a valid ${field.type}.`);
      }
    }
    result[key] = value;
  }
  return result;
}

export function liveMetricsEnabled(values, model) {
  const callbacks = values.callbacks ?? schemaDefaults(model).callbacks;
  return Array.isArray(callbacks) && callbacks.includes("tensorboard") && callbacks.includes("gradcam");
}
