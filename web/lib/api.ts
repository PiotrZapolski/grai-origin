/**
 * The only contact point between the frontend and the backend: HTTP and SSE.
 * Nothing from Python is imported here and never will be - the contracts from
 * section 12 are transcribed by hand in lib/contracts.ts.
 */

import type {
  AnalyzeRequest,
  AnalyzeResponse,
  AnalyzeResult,
  ExplainResponse,
  StreamEvent,
} from "./contracts";

/** An empty default prefix means "the same origin". Overridden by an env var in dev. */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * The job exists but has no result yet - the backend answers 202 with the shape
 * `{job_id, status: "pending"}`. This is not an `AnalyzeResult` and reading it
 * as one would show an empty ranking, that is "we found nothing" instead of
 * "we are still computing".
 */
export class ResultNotReadyError extends Error {
  constructor(readonly jobId: string) {
    super(`Job '${jobId}' has no result yet`);
    this.name = "ResultNotReadyError";
  }
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    throw new ApiError(`POST ${path} returned ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

/** POST /api/analyze - returns the job identifier. */
export async function analyze(
  url: string,
  candidateSet: string,
  signal?: AbortSignal,
): Promise<string> {
  const payload: AnalyzeRequest = { url, candidate_set: candidateSet };
  const data = await postJson<AnalyzeResponse>("/api/analyze", payload, signal);
  return data.job_id;
}

export interface StreamHandle {
  /** Closes the SSE connection. Call it when the component unmounts. */
  close: () => void;
}

/**
 * GET /api/jobs/{id}/stream - the stream of pipeline stages.
 *
 * The `verdict` event arrives twice: `partial` after level 1 and `final` after
 * level 2, and the class can change in between. The caller has to be able to
 * lift the verdict without reloading the screen (section 12).
 */
export function streamJob(
  jobId: string,
  onEvent: (event: StreamEvent) => void,
  onError?: (error: Error) => void,
): StreamHandle {
  const source = new EventSource(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}/stream`);

  source.onmessage = (message: MessageEvent<string>) => {
    try {
      onEvent(JSON.parse(message.data) as StreamEvent);
    } catch (cause) {
      onError?.(new Error(`Unreadable SSE event: ${String(cause)}`));
    }
  };

  source.onerror = () => {
    // EventSource carries no error body. We close it ourselves so the browser
    // does not keep reopening the connection to a finished job.
    source.close();
    onError?.(new Error("The job stream was interrupted"));
  };

  return { close: () => source.close() };
}

/**
 * GET /api/jobs/{id}/result - the partial or final state.
 *
 * Throws `ResultNotReadyError` on 202 so the caller does not mistake the
 * `{job_id, status: "pending"}` response for a result with an empty ranking.
 */
export async function getResult(jobId: string, signal?: AbortSignal): Promise<AnalyzeResult> {
  const path = `/api/jobs/${encodeURIComponent(jobId)}/result`;
  const response = await fetch(`${API_BASE}${path}`, { signal });
  if (response.status === 202) {
    throw new ResultNotReadyError(jobId);
  }
  if (!response.ok) {
    throw new ApiError(`GET ${path} returned ${response.status}`, response.status);
  }
  return (await response.json()) as AnalyzeResult;
}

/**
 * POST /api/explain - a natural language description. Called exclusively on the
 * user's request, never automatically: this is the only place with a language
 * model and it has to stay off the critical path (section 12).
 */
export async function explain(
  jobId: string,
  candidateId: string,
  signal?: AbortSignal,
): Promise<string> {
  const data = await postJson<ExplainResponse>(
    "/api/explain",
    { job_id: jobId, candidate_id: candidateId },
    signal,
  );
  return data.explanation;
}
