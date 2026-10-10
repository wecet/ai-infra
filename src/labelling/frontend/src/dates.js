/** Server timestamps without an explicit offset are UTC (including SQLite dates). */
export function formatDate(value) {
  if (!value) return "Date unavailable";
  const timestamp = String(value).replace(" ", "T");
  const date = new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(timestamp) ? timestamp : `${timestamp}Z`);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleString();
}
