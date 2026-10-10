export function newTrainingFailures(jobs, previous) {
  if (previous === null) return [];
  return jobs.filter((job) => job.status === "failed" && previous.get(job.id) !== "failed")
    .map((job) => ({ jobId: job.id, message: job.error || "The trainer failed without providing an error description." }));
}
