/**
 * Typed TeamScout API client.
 * Throws ApiClientError with message + optional requestId from X-Request-ID or body.details.
 */
import type {
  DriveSyncResponse,
  EmailRevealResponse,
  FindTeamResponse,
  HealthResponse,
  IntentSearchRequest,
  IntentSearchResponse,
  LibraryResumeListResponse,
  LibraryUploadResponse,
  RecommendResumesResponse,
  ResumeProfile,
  ResumeUploadResponse,
  SearchResponse,
  TeamExtractionResponse,
  TeamListResponse,
} from "./types";

export type {
  ApiErrorBody,
  CheckStatus,
  Contact,
  DriveSyncResponse,
  EmailRevealResponse,
  FindTeamResponse,
  HealthResponse,
  IntentSearchRequest,
  IntentSearchResponse,
  Job,
  LibraryResume,
  LibraryResumeListResponse,
  LibraryUploadResponse,
  RankedJob,
  RankedResumeRecommendation,
  RecommendResumesResponse,
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
  const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!response.ok) {
    throw await parseError(response);
  }
  return response.json() as Promise<HealthResponse>;
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

export async function createSearch(resumeId: string): Promise<SearchResponse> {
  return request<SearchResponse>("/searches", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_id: resumeId }),
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

export async function intentSearch(payload: IntentSearchRequest): Promise<IntentSearchResponse> {
  return request<IntentSearchResponse>("/library/intent/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function recommendResumes(jobId: string): Promise<RecommendResumesResponse> {
  return request<RecommendResumesResponse>(`/library/jobs/${jobId}/recommend-resumes`, {
    method: "POST",
  });
}
