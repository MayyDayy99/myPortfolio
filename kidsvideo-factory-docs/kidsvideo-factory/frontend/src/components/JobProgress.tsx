import { useEffect, useRef, useState } from "react";
import { getJob } from "../api";
import type { Job, JobKind, JobState } from "../types";

/** Hungarian labels for each job kind (CONTRACTS §13, 03-VIDEO-SPEC phases). */
const JOB_KIND_LABELS: Record<JobKind, string> = {
  generate_image: "Képgenerálás",
  cutout: "Kivágás és sziluett",
  clean_audio: "Hangtisztítás",
  render_segment: "Szegmens renderelése",
  assemble: "Videó összefűzése",
};

/** Hungarian labels for each job state. */
const JOB_STATE_LABELS: Record<JobState, string> = {
  queued: "Sorban áll",
  running: "Folyamatban",
  done: "Kész",
  error: "Hiba",
};

const POLL_INTERVAL_MS = 2000;

interface JobProgressProps {
  jobId: number;
  /** Called once when the job reaches a terminal state (done or error). */
  onFinished?: (job: Job) => void;
  /** Optional human label override (otherwise derived from the job kind). */
  label?: string;
}

/**
 * Polls `GET /api/jobs/{id}` every 2 seconds and renders a progress bar with a
 * Hungarian status line and the job's error/log output. Stops polling once the
 * job is done or errored.
 */
export default function JobProgress({
  jobId,
  onFinished,
  label,
}: JobProgressProps) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const finishedRef = useRef(false);
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;

  useEffect(() => {
    // Reset for a new job id.
    finishedRef.current = false;
    setJob(null);
    setError(null);

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const next = await getJob(jobId);
        if (cancelled) {
          return;
        }
        setJob(next);
        setError(null);
        if (next.state === "done" || next.state === "error") {
          if (!finishedRef.current) {
            finishedRef.current = true;
            onFinishedRef.current?.(next);
          }
          return; // terminal: stop polling
        }
      } catch (err) {
        if (cancelled) {
          return;
        }
        setError(
          err instanceof Error
            ? err.message
            : "A job állapota nem kérdezhető le.",
        );
      }
      timer = setTimeout(poll, POLL_INTERVAL_MS);
    };

    void poll();

    return () => {
      cancelled = true;
      if (timer) {
        clearTimeout(timer);
      }
    };
  }, [jobId]);

  const state: JobState = job?.state ?? "queued";
  const percent = Math.round((job?.progress ?? 0) * 100);
  const kindLabel = label ?? (job ? JOB_KIND_LABELS[job.kind] : "Művelet");
  const fillClass =
    state === "done" ? "progress-fill done" : state === "error" ? "progress-fill error" : "progress-fill";

  return (
    <div className="job-progress stack">
      <div className="row between">
        <strong>{kindLabel}</strong>
        <span className={`chip ${state}`}>
          {JOB_STATE_LABELS[state]}
          {state === "running" ? ` — ${percent}%` : ""}
        </span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div
          className={fillClass}
          style={{ width: `${state === "done" ? 100 : percent}%` }}
        />
      </div>
      {error && <div className="error-box">{error}</div>}
      {job && job.log.trim().length > 0 && (
        <pre className="job-log">{job.log}</pre>
      )}
    </div>
  );
}
