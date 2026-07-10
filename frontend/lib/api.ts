/**
 * Typed TeamScout API client.
 * Throws ApiClientError with message + optional requestId from X-Request-ID or body.details.
 */
import type {
  DriveSyncResponse,
  EmailRevealResponse,
  FindTeamResponse,
  HealthResponse,
  LibraryResumeListResponse,
  LibraryUploadResponse,
  IngestJobFromTextRequest,
  IngestJobFromTextResponse,
  RecommendFromJdRequest,
  RecommendFromJdResponse,
  ResumeProfile,
  ResumeUploadResponse,
  SearchParams,
  SearchResponse,
  JobFacets,
  TeamExtractionResponse,
  TeamListResponse,
  FeedbackCreate,
  FeedbackResponse,
} from "./types";

/** Re-exports for UI-used client types only. Retained backend routes (intent-search,
 * recommend-by-job-id) keep schemas in `./types` but are not re-exported here. */
export type {
  ApiErrorBody,
  CheckStatus,
  Contact,
  DriveSyncResponse,
  EmailRevealResponse,
  FindTeamResponse,
  HealthResponse,
  Job,
  LibraryResume,
  LibraryResumeListResponse,
  LibraryUploadResponse,
  RankedJob,
  RankedResumeRecommendation,
  RecommendFromJdRequest,
  RecommendFromJdResponse,
  RequirementCoverage,
  ResumeProfile,
  ResumeUploadResponse,
  ScoreBreakdown,
  SearchResponse,
  TeamExtraction,
  TeamExtractionResponse,
  TeamListResponse,
  WorkExperience,
} from "./types";

export { HEALTH_ENV_HINTS } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class ApiClientError extends Error {
  readonly status: number;
  readonly errorCode: string | null;
  readonly requestId: string | null;
  readonly details: Record<string, unknown> | undefined;

  constructor(
    message: string,
    opts: {
      status: number;
      errorCode?: string | null;
      requestId?: string | null;
      details?: Record<string, unknown>;
    },
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = opts.status;
    this.errorCode = opts.errorCode ?? null;
    this.requestId = opts.requestId ?? null;
    this.details = opts.details;
  }
}

export function formatApiError(error: unknown): string {
  if (error instanceof ApiClientError) {
    const rid = error.requestId ? ` · request ${error.requestId}` : "";
    return `${error.message}${rid}`;
  }
  if (error instanceof Error) return error.message;
  return "Request failed";
}

async function parseError(response: Response): Promise<ApiClientError> {
  const headerId = response.headers.get("X-Request-ID") ?? response.headers.get("x-request-id");
  try {
    const payload = (await response.json()) as {
      error?: string;
      message?: string;
      details?: Record<string, unknown>;
    };
    const detailId =
      payload.details && typeof payload.details.request_id === "string"
        ? payload.details.request_id
        : null;
    return new ApiClientError(payload.message || response.statusText || "Request failed", {
      status: response.status,
      errorCode: payload.error ?? null,
      requestId: headerId ?? detailId,
      details: payload.details,
    });
  } catch {
    return new ApiClientError(response.statusText || "Request failed", {
      status: response.status,
      requestId: headerId,
    });
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    throw await parseError(response);
  }
  return response.json() as Promise<T>;
}

export async function fetchHealth(): Promise<HealthResponse> {
  // Backend returns HTTP 503 when ok=false (missing keys). That is degraded
  // config with a valid JSON body — not "backend unreachable".
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Network error";
    throw new ApiClientError(msg, { status: 0, errorCode: "network_error" });
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiClientError(response.statusText || "Invalid health response", {
      status: response.status,
      requestId: response.headers.get("X-Request-ID"),
    });
  }

  if (
    payload &&
    typeof payload === "object" &&
    "ok" in payload &&
    "checks" in payload &&
    typeof (payload as HealthResponse).checks === "object"
  ) {
    return payload as HealthResponse;
  }

  if (!response.ok) {
    throw await parseError(
      new Response(JSON.stringify(payload), {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      }),
    );
  }

  throw new ApiClientError("Unexpected health response shape", {
    status: response.status,
  });
}

export async function uploadResume(file: File): Promise<ResumeUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<ResumeUploadResponse>("/resumes/upload", { method: "POST", body: form });
}

export async function confirmResume(
  resumeId: string,
  payload: { title: string; location: string; skills: string[] },
): Promise<{ id: string; confirmed: boolean; profile: ResumeProfile }> {
  return request(`/resumes/${resumeId}/confirm`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function createSearch(
  resumeId: string,
  params?: import("./types").SearchParams,
): Promise<SearchResponse> {
  return request<SearchResponse>("/searches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_id: resumeId, params: params ?? {} }),
  });
}

export async function extractTeam(jobId: string): Promise<TeamExtractionResponse> {
  return request<TeamExtractionResponse>(`/jobs/${jobId}/extract-team`, { method: "POST" });
}

export async function findTeam(
  jobId: string,
  payload: { extraction_id: string; search_id?: string | null },
): Promise<FindTeamResponse> {
  return request<FindTeamResponse>(`/jobs/${jobId}/find-team`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function getJobTeam(jobId: string): Promise<TeamListResponse> {
  return request<TeamListResponse>(`/jobs/${jobId}/team`);
}

export async function revealEmail(
  contactId: string,
  confirm = false,
): Promise<EmailRevealResponse> {
  const query = confirm ? "?confirm=true" : "";
  return request<EmailRevealResponse>(`/contacts/${contactId}/reveal-email${query}`, {
    method: "POST",
  });
}

export async function listLibraryResumes(): Promise<LibraryResumeListResponse> {
  return request<LibraryResumeListResponse>("/library/resumes");
}

export async function uploadLibrary(files: File[]): Promise<LibraryUploadResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  return request<LibraryUploadResponse>("/library/upload", { method: "POST", body: form });
}

export async function syncDrive(folderUrl: string): Promise<DriveSyncResponse> {
  return request<DriveSyncResponse>("/library/drive/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ folder_url: folderUrl }),
  });
}

export async function recommendFromJd(
  payload: RecommendFromJdRequest,
): Promise<RecommendFromJdResponse> {
  return request<RecommendFromJdResponse>("/library/recommend-from-jd", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function ingestJobFromText(
  payload: IngestJobFromTextRequest,
): Promise<IngestJobFromTextResponse> {
  return request<IngestJobFromTextResponse>("/jobs/from-text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}



export type PublicStats = {
  jobs_ranked_total: number;
  resumes_parsed_total: number;
  teams_discovered_total: number;
  median_rank_latency_ms: number | null;
  total_llm_cost_usd: number;
};

export async function fetchPublicStats(): Promise<PublicStats> {
  return request<PublicStats>("/stats");
}

export async function postFeedback(payload: FeedbackCreate): Promise<FeedbackResponse> {
  return request<FeedbackResponse>("/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
