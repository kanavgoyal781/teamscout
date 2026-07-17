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
  cross_encoder?: number;
  required_years?: number | null;
  soft_boost?: number;
  final_score: number;
  matched_skills: string[];
  missing_skills: string[];
  rationale: string;
  /** 0–1 calibrated P(good match) when backend has Platt fit with ≥50 labels; else null. */
  match_likelihood?: number | null;
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
  source_quality?: "direct_ats" | "aggregator" | "feed";
  seniority?: string | null;
  remote_mode?: string | null;
  employment_type?: string | null;
  salary_min?: number | null;
  salary_unknown?: boolean;
  duplicates_count?: number;
  salary_bucket?: string | null;
  posted_age_bucket?: string | null;
};

export type RankedJob = {
  job: Job;
  match_score: number;
  score_breakdown: ScoreBreakdown;
};

export type PrefMode = "hard" | "soft";
export type RemoteMode = "remote" | "hybrid" | "onsite" | "any";
export type EmploymentType = "fulltime" | "contractor" | "any";
export type DateWindow = "day" | "3days" | "week" | "month";
export type SeniorityLevel = "intern" | "junior" | "mid" | "senior" | "lead" | "any";

export type SearchParams = {
  remote_mode?: RemoteMode;
  remote_mode_pref?: PrefMode;
  employment_type?: EmploymentType;
  employment_type_pref?: PrefMode;
  date_window?: DateWindow;
  seniority?: SeniorityLevel;
  seniority_pref?: PrefMode;
  min_salary?: number | null;
  min_salary_pref?: PrefMode;
  use_expand?: boolean;
};

export type FacetBucket = {
  value: string;
  count: number;
};

export type JobFacets = {
  company: FacetBucket[];
  seniority: FacetBucket[];
  remote_mode: FacetBucket[];
  salary_bucket: FacetBucket[];
  posted_age: FacetBucket[];
  source?: FacetBucket[];
};

export type SourceCounts = {
  fetched: number;
  kept_after_filters: number;
  deduped_away: number;
  errors: number;
};

export type SearchResponse = {
  search_id: string;
  resume_id: string;
  results: RankedJob[];
  facets?: JobFacets;
  dropped_counts?: Record<string, number>;
  queries?: string[];
  per_source_counts?: Record<string, SourceCounts>;
  source_errors?: string[];
  /** Context-aware strip lines (quota, partial source fail, widen date window). */
  pool_notices?: string[];
  /** When results empty: filters | partial_sources */
  pool_empty_reason?: string | null;
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
  cluster_id?: string | null;
  cluster_label?: string | null;
  cluster_size?: number | null;
};

export type LibraryResumeListResponse = {
  resumes: LibraryResume[];
  total: number;
  distinct_versions?: number;
};

export type IngestFileResult = {
  filename: string;
  status: "cached" | "parsed" | "failed" | "skipped";
  resume_id?: string | null;
  /** Plain-language reason for failed/skipped files (no secrets). */
  reason?: string | null;
};

export type DriveSyncResponse = {
  folder_id: string;
  files_seen: number;
  files_parsed: number;
  files_skipped: number;
  files_ignored: number;
  files_failed?: number;
  resumes: LibraryResume[];
  distinct_versions?: number;
  units_indexed?: boolean | null;
  units_index_warning?: string | null;
  file_results?: IngestFileResult[];
};

export type LibraryUploadResponse = {
  files_received: number;
  files_parsed: number;
  files_skipped: number;
  files_ignored: number;
  resumes: LibraryResume[];
  distinct_versions?: number;
  units_indexed?: boolean | null;
  units_index_warning?: string | null;
  file_results?: IngestFileResult[];
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

export type EvidenceStrength = "none" | "weak" | "solid" | "strong";

export type AlignmentRow = {
  requirement: string;
  kind: string;
  category: string;
  weight: number;
  evidence_unit: string | null;
  evidence_score: number;
  strength?: EvidenceStrength;
  status: "hit" | "miss";
};

export type TournamentRecord = {
  ran: boolean;
  comparisons: number;
  cache_hits: number;
  cost_usd: number | null;
  wins: number;
  contested: boolean;
  /** True when tournament reordering differed from pure coverage order. */
  overrode_coverage?: boolean;
  /** Borda points (decisive=1.0, slight=0.5); may diverge from win count. */
  borda_score?: number;
  reasons: string[];
  /** Panel mean agreement 0–1 when JUDGE_PANEL_MODELS set. */
  judge_agreement?: number | null;
  /** e.g. "3/3 judges agree" or "2/3 split". */
  judge_agreement_label?: string | null;
};

export type AdversarialCritique = {
  side_a_resume_id: string;
  side_a_filename: string;
  side_a_model: string;
  side_a_argument: string;
  side_b_resume_id: string;
  side_b_filename: string;
  side_b_model: string;
  side_b_argument: string;
  verdict_winner_resume_id: string;
  verdict_winner_filename: string;
  verdict_model: string;
  verdict_reason: string;
  verdict_margin?: string;
};

export type RankedResumeRecommendation = {
  resume_id: string;
  filename: string;
  match_score: number;
  score_breakdown: ScoreBreakdown;
  coverage: RequirementCoverage[];
  coverage_score?: number;
  /** Must-haves with evidence above floor — prefer "X of N" over rescaled %. */
  must_haves_hit?: number;
  must_haves_total?: number;
  alignment?: AlignmentRow[];
  cluster_id?: string | null;
  cluster_label?: string | null;
  cluster_size?: number | null;
  tournament?: TournamentRecord | null;
  /** Resume content hash for feedback provenance when present. */
  content_hash?: string | null;
  /** ok | limited_evidence | fallback (alignment-derived text after grounding reject). */
  justification_status?: string;
};

export type RecommendResumesResponse = {
  job_id: string;
  recommendations: RankedResumeRecommendation[];
  tournament_comparisons?: number;
  tournament_ran?: boolean;
  tournament_judge_agreement?: number | null;
  tournament_judge_agreement_label?: string | null;
  adversarial_critique?: AdversarialCritique | null;
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
  tournament_comparisons?: number;
  tournament_ran?: boolean;
  tournament_judge_agreement?: number | null;
  tournament_judge_agreement_label?: string | null;
  adversarial_critique?: AdversarialCritique | null;
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


export type FeedbackKind =
  | "thumbs_up"
  | "thumbs_down"
  | "apply_click"
  | "find_team_click"
  | "compose_opened";
export type FeedbackTargetType = "job_match" | "resume_pick" | "contact";

export type OutreachDraftResponse = {
  contact_id: string;
  subject: string;
  body: string;
  email: string;
};

export type FeedbackCreate = {
  kind: FeedbackKind;
  target_type: FeedbackTargetType;
  target_id: string;
  secondary_id?: string | null;
  profile_hash?: string | null;
  jd_hash?: string | null;
  score_shown?: number | null;
  shown_rank?: number | null;
  score_components?: Record<string, number> | null;
};

export type FeedbackResponse = {
  id: string;
  kind: string;
  target_type: string;
  target_id: string;
  created_at?: string | null;
};


export type FieldConfidence = "high" | "medium" | "low";

export type JobMetadata = {
  title: string | null;
  company: string | null;
  location: string | null;
  remote_mode: "remote" | "hybrid" | "onsite" | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_currency: string | null;
  seniority: string | null;
  department: string | null;
  confidence: Partial<Record<string, FieldConfidence>>;
};

export type ExtractMetadataResponse = {
  metadata: JobMetadata;
  cache_hit: boolean;
  content_hash: string;
};
