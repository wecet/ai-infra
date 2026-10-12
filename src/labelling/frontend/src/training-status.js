function timestamp(value) {
  if (!value) return null;
  const normalized = value.replace(" ", "T");
  const parsed = Date.parse(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized) ? normalized : `${normalized}Z`);
  return Number.isFinite(parsed) ? parsed : null;
}

export function elapsedTime(job, now) {
  const start = timestamp(job.started_at);
  if (start === null) return "Not started";
  const seconds = Math.max(0, Math.floor(((timestamp(job.completed_at) ?? now) - start) / 1000));
  return seconds >= 3600 ? `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function heartbeatText(job, now) {
  if (!["queued", "running"].includes(job.status)) return "Finished";
  const heartbeat = timestamp(job.heartbeat_at);
  if (heartbeat === null) return job.status === "queued" ? "Waiting for agent" : "No heartbeat reported";
  const age = Math.max(0, Math.floor((now - heartbeat) / 1000));
  return `${age}s ago${age > 15 ? " · delayed" : ""}`;
}
