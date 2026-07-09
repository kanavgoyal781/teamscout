/** Types mirroring backend Pydantic schemas (jobs, resume, team, library). */

export type WorkExperience = {
  title: string;
  company: string;
  bullets: string[];
};

export type ResumeProfile = {
  name: string;
  title: string;
  years_of_experience: number;
  location: string;
  skills: string[];
  work_experience: WorkExperience[];
  summary: string;
};

export type ResumeUploadResponse = {
  id: string;
  filename: string;
  content_hash: string;
  confirmed: boolean;
  profile: ResumeProfile;
};

export type ScoreBreakdown = {
  llm_fit: number;
  rrf_normalized: number;
  dense_rank_score?: number;
  skill_jaccard: number;
  recency: number;
  experience_fit?: number | null;
  requirements_met?: number | null;
  required_years?: number | null;
  final_score: number;
  matched_skills: string[];
  missing_skills: string[];
  rationale: string;
};

export type Job = {
  id: string;
  source: string;
  source_job_id: string;
  title: string;
  company: string;
  location: string;
  description: string;
  apply_url: string;
  posted_at: string | null;
  skills: string[];
};

export type RankedJob = {
  job: Job;
  match_score: number;
  score_breakdown: ScoreBreakdown;
};

export type SearchResponse = {
  search_id: string;
  resume_id: string;
  results: RankedJob[];
};

export type ApiErrorBody = {
  error: string;
  message: string;
  details?: Record<string, unknown>;
};

export type TeamExtraction = {
  team_name: string;
  department: string;
  likely_hiring_titles: string[];
};

export type TeamExtractionResponse = {
  job_id: string;
  extraction_id: string;
  extraction: TeamExtraction;
};

export type Contact = {
  id: string;
  full_name: string;
  title: string | null;
  company: string | null;
  team: string | null;
  seniority: string | null;
  sumble_person_id: string | null;
  email_revealed: boolean;
  email: string | null;
};

export type FindTeamResponse = {
  job_id: string;
  contacts: Contact[];
  credits_used: number;
  team_searched: boolean;
  search_path?: string | null;
};

export type TeamListResponse = {
  job_id: string;
  contacts: Contact[];
  extraction_id: string | null;
  extraction: TeamExtraction | null;
  team_searched: boolean;
  search_path?: string | null;
};

export type EmailRevealResponse = {
  contact_id: string;
  cost_credits: number | null;
  cached: boolean;
  email: string | null;
  status: string;
};

export type LibraryResume = {
  id: string;
  filename: string;
  content_hash: string;
  source: string;
  profile: ResumeProfile;
  created_at: string | null;
};

export type LibraryResumeListResponse = {
  resumes: LibraryResume[];
  total: number;
};

export type DriveSyncResponse = {
  folder_id: string;
  files_seen: number;
  files_parsed: number;
  files_skipped: number;
  files_ignored: number;
  resumes: LibraryResume[];
};

export type LibraryUploadResponse = {
  files_received: number;
  files_parsed: number;
  files_skipped: number;
  files_ignored: number;
  resumes: LibraryResume[];
};

export type IntentSearchRequest = {
  role: string;
  years_of_experience: number;
  location: string;
  remote_preference: "remote" | "hybrid" | "onsite" | "any";
};

export type IntentSearchResponse = {
  search_id: string;
  results: RankedJob[];
};

export type RequirementCoverage = {
  requirement: string;
  status: "hit" | "miss";
  evidence: string | null;
};

export type RankedResumeRecommendation = {
  resume_id: string;
  filename: string;
  match_score: number;
  score_breakdown: ScoreBreakdown;
  coverage: RequirementCoverage[];
};

export type RecommendResumesResponse = {
  job_id: string;
  recommendations: RankedResumeRecommendation[];
};

export type RecommendFromJdRequest = {
  job_description: string;
  title?: string;
  company?: string;
  location?: string;
  apply_url?: string;
};

export type RecommendFromJdResponse = {
  job_id: string;
  job_title: string;
  job_company: string;
  recommendations: RankedResumeRecommendation[];
};

export type IngestJobFromTextRequest = {
  description: string;
  title?: string;
  company?: string;
  location?: string;
  apply_url?: string;
};

export type IngestJobFromTextResponse = {
  job_id: string;
  title: string;
  company: string;
  location: string;
  description_preview: string;
};

export type CheckStatus = "configured" | "missing" | "failing";

export type HealthResponse = {
  ok: boolean;
  version?: string;
  checks: Record<string, CheckStatus>;
  required_checks?: string[];
  optional_checks?: string[];
  db?: boolean;
};

/** Maps health check keys → env var names for precise banner copy. */
export const HEALTH_ENV_HINTS: Record<string, string[]> = {
  llm: ["LLM_API_KEY", "LLM_API_BASE"],
  embeddings: ["EMBEDDINGS_API_KEY", "EMBEDDINGS_API"],
  jobs_api: ["JOBS_API_KEY", "JOBS_API_BASE"],
  sumble: ["SUMBLE_API_KEY"],
  google_drive: ["GOOGLE_DRIVE_API_KEY", "or GOOGLE_DRIVE_CLIENT_* OAuth"],
};
