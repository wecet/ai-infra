export function filterPredictions(rows, { query = "", category = "", confidence = 0, failures = false, errorType = "" } = {}) {
  return rows.filter((row) => (!errorType || row.errors?.includes(errorType)) && (!failures || row.failed) && row.source_path.toLowerCase().includes(query.toLowerCase()) &&
    (!category || row.predictions.some((p) => p.class_name === category) || row.ground_truth.some((p) => (typeof p === "string" ? p : p.class_name) === category)) &&
    (!confidence || row.predictions.some((p) => (p.score ?? 0) >= confidence)));
}
