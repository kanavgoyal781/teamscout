"use client";

import { ChevronDown, ChevronRight, FileText, Upload } from "lucide-react";
import {
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { toast } from "sonner";

import type { IngestFileResult, LibraryResume } from "../../lib/types";
import EmptyState from "../ui/EmptyState";
import { SkeletonLines } from "../ui/Skeleton";

const ROW_HEIGHT = 44;
const VISIBLE_ROWS = 5;
const LIST_MAX_HEIGHT = ROW_HEIGHT * VISIBLE_ROWS;
const SKILLS_VISIBLE = 8;

function SkillsPreview({ skills, resumeId }: { skills: string[]; resumeId: string }) {
  const [open, setOpen] = useState(false);
  if (!skills.length) return null;
  const shown = open ? skills : skills.slice(0, SKILLS_VISIBLE);
  const more = skills.length - SKILLS_VISIBLE;
  // Use <span role="button"> — may nest inside cluster <button> without invalid HTML
  return (
    <span className="library-skills-preview" data-testid={`skills-${resumeId}`}>
      {shown.join(", ")}
      {more > 0 && !open ? (
        <span
          role="button"
          tabIndex={0}
          className="library-skills-more"
          onClick={(e) => {
            e.stopPropagation();
            e.preventDefault();
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              e.stopPropagation();
              setOpen(true);
            }
          }}
          aria-label={`Show ${more} more skills`}
        >
          +{more} more
        </span>
      ) : null}
      {open && more > 0 ? (
        <span
          role="button"
          tabIndex={0}
          className="library-skills-more"
          onClick={(e) => {
            e.stopPropagation();
            e.preventDefault();
            setOpen(false);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              e.stopPropagation();
              setOpen(false);
            }
          }}
        >
          less
        </span>
      ) : null}
    </span>
  );
}

type ClusterGroup = {
  cid: string;
  members: LibraryResume[];
};

type LibraryIngestPanelProps = {
  resumes: LibraryResume[];
  loadingLibrary: boolean;
  libraryError?: string | null;
  uploading: boolean;
  syncing: boolean;
  driveUrl: string;
  syncStatus: string | null;
  distinctVersions?: number;
  /** Per-file cached/parsed results from last ingest. */
  lastIngestResults?: IngestFileResult[] | null;
  /** Resume IDs newly parsed in the last ingest — briefly highlighted. */
  newlyParsedIds?: string[];
  cachedCount?: number;
  parsedCount?: number;
  onDriveUrlChange: (value: string) => void;
  onUpload: (event: FormEvent<HTMLFormElement>) => void;
  onDriveSync: (event: FormEvent<HTMLFormElement>) => void;
};

export default function LibraryIngestPanel({
  resumes,
  loadingLibrary,
  libraryError,
  uploading,
  syncing,
  driveUrl,
  syncStatus,
  distinctVersions,
  lastIngestResults,
  newlyParsedIds = [],
  cachedCount,
  parsedCount,
  onDriveUrlChange,
  onUpload,
  onDriveSync,
}: LibraryIngestPanelProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState(false);
  const [picked, setPicked] = useState<File[]>([]);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [scrollTop, setScrollTop] = useState(0);
  const [highlightIds, setHighlightIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (!newlyParsedIds.length) return;
    setHighlightIds(new Set(newlyParsedIds));
    const t = window.setTimeout(() => setHighlightIds(new Set()), 2400);
    return () => window.clearTimeout(t);
  }, [newlyParsedIds]);

  const statusByResumeId = useMemo(() => {
    const map = new Map<string, "cached" | "parsed">();
    for (const fr of lastIngestResults ?? []) {
      if (fr.resume_id && (fr.status === "cached" || fr.status === "parsed")) {
        map.set(fr.resume_id, fr.status);
      }
    }
    return map;
  }, [lastIngestResults]);

  const groups: ClusterGroup[] = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const byCluster = new Map<string, LibraryResume[]>();
    for (const r of resumes) {
      if (q) {
        const hay = `${r.filename} ${r.profile.title} ${r.profile.skills.join(" ")} ${r.source}`.toLowerCase();
        if (!hay.includes(q)) continue;
      }
      const cid = r.cluster_id || r.id;
      const list = byCluster.get(cid) ?? [];
      list.push(r);
      byCluster.set(cid, list);
    }
    return Array.from(byCluster.entries())
      .map(([cid, members]) => ({ cid, members }))
      .sort((a, b) => a.cid.localeCompare(b.cid));
  }, [resumes, filter]);

  /** Flatten for virtualization: one row per cluster (collapsed) or per member when expanded. */
  type FlatRow =
    | { kind: "cluster"; cid: string; members: LibraryResume[]; count: number }
    | { kind: "member"; cid: string; resume: LibraryResume };

  const flatRows: FlatRow[] = useMemo(() => {
    const rows: FlatRow[] = [];
    for (const g of groups) {
      rows.push({ kind: "cluster", cid: g.cid, members: g.members, count: g.members.length });
      if (expanded.has(g.cid)) {
        for (const m of g.members) {
          rows.push({ kind: "member", cid: g.cid, resume: m });
        }
      }
    }
    return rows;
  }, [groups, expanded]);

  const totalHeight = flatRows.length * ROW_HEIGHT;
  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - 2);
  const endIdx = Math.min(flatRows.length, Math.ceil((scrollTop + LIST_MAX_HEIGHT) / ROW_HEIGHT) + 2);
  const visible = flatRows.slice(startIdx, endIdx);
  const offsetY = startIdx * ROW_HEIGHT;

  const toggleCluster = useCallback((cid: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(cid)) next.delete(cid);
      else next.add(cid);
      return next;
    });
  }, []);

  function onClusterKey(e: KeyboardEvent, cid: string) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggleCluster(cid);
    }
  }

  function acceptFiles(list: FileList | File[] | null) {
    const files = Array.from(list ?? []);
    if (files.length === 0) return;
    setPicked(files);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (picked.length === 0 && !(inputRef.current?.files && inputRef.current.files.length > 0)) {
      toast.error("Choose one or more PDF/DOCX files or a ZIP archive.");
      return;
    }
    onUpload(event);
  }

  const versions =
    distinctVersions ?? new Set(resumes.map((r) => r.cluster_id || r.id)).size;
  const cached = cachedCount ?? lastIngestResults?.filter((r) => r.status === "cached").length ?? 0;
  const parsed = parsedCount ?? lastIngestResults?.filter((r) => r.status === "parsed").length ?? 0;

  return (
    <section className="panel" data-testid="library-ingest">
      <h2>1. Resume library</h2>
      <form className="library-upload-form" onSubmit={handleSubmit}>
        <div
          className={`dropzone${dragging ? " is-dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            acceptFiles(e.dataTransfer.files);
            if (inputRef.current && e.dataTransfer.files) {
              try {
                const dt = new DataTransfer();
                Array.from(e.dataTransfer.files).forEach((f) => dt.items.add(f));
                inputRef.current.files = dt.files;
              } catch {
                /* browsers without DataTransfer still use click picker */
              }
            }
          }}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          role="button"
          tabIndex={0}
          aria-label="Upload library files PDF DOCX or ZIP"
        >
          <Upload size={28} strokeWidth={1.5} aria-hidden style={{ color: "var(--accent)", marginBottom: 8 }} />
          <p className="dropzone-title">Drag & drop resumes</p>
          <p className="meta" style={{ margin: 0 }}>
            PDF, DOCX, or ZIP · multi-file · click to browse
          </p>
          <input
            ref={inputRef}
            name="library-files"
            type="file"
            multiple
            accept=".pdf,.docx,.zip,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/zip"
            aria-label="Upload library files"
            onChange={(e) => acceptFiles(e.target.files)}
          />
        </div>
        {picked.length > 0 ? (
          <div className="file-preview" style={{ marginTop: 12 }}>
            <FileText size={20} aria-hidden />
            <div style={{ flex: 1 }}>
              <strong>
                {picked.length === 1 ? picked[0].name : `${picked.length} files selected`}
              </strong>
              <span className="meta font-num" style={{ display: "block", margin: 0 }}>
                {picked.length === 1
                  ? `${(picked[0].size / 1024).toFixed(1)} KB`
                  : picked
                      .map((f) => f.name)
                      .join(", ")
                      .slice(0, 80)}
              </span>
            </div>
            <button type="submit" className="primary" disabled={uploading}>
              {uploading ? "Uploading…" : "Upload files or ZIP"}
            </button>
          </div>
        ) : (
          <div className="actions" style={{ marginTop: 12 }}>
            <button type="submit" className="primary" disabled={uploading}>
              {uploading ? "Uploading…" : "Upload files or ZIP"}
            </button>
          </div>
        )}
      </form>

      <form className="upload-form library-drive-form" onSubmit={onDriveSync}>
        <input
          value={driveUrl}
          onChange={(event) => onDriveUrlChange(event.target.value)}
          placeholder="https://drive.google.com/drive/folders/..."
          className="drive-input"
          aria-label="Google Drive folder URL"
        />
        <button type="submit" disabled={syncing}>
          {syncing ? "Syncing Drive…" : "Sync Drive folder"}
        </button>
      </form>
      {syncStatus ? <p className="meta font-num">{syncStatus}</p> : null}
      {lastIngestResults && lastIngestResults.some((r) => r.status === "failed") ? (
        <details className="library-sync-failures" data-testid="library-sync-failures">
          <summary className="meta">
            {lastIngestResults.filter((r) => r.status === "failed").length} file
            {lastIngestResults.filter((r) => r.status === "failed").length === 1 ? "" : "s"} need attention
            (expand for reasons)
          </summary>
          <ul className="library-failure-list">
            {lastIngestResults
              .filter((r) => r.status === "failed")
              .map((r) => (
                <li key={`${r.filename}-${r.reason ?? ""}`}>
                  <strong>{r.filename}</strong>
                  <span className="meta"> — {r.reason || "Could not sync"}</span>
                </li>
              ))}
          </ul>
        </details>
      ) : null}

      {loadingLibrary ? (
        <div style={{ marginTop: 16 }} aria-busy="true" aria-label="Loading library">
          <SkeletonLines lines={4} />
        </div>
      ) : libraryError ? (
        <div style={{ marginTop: 16 }}>
          <EmptyState title="Could not load library" instruction={libraryError} />
        </div>
      ) : resumes.length === 0 ? (
        <div style={{ marginTop: 16 }}>
          <EmptyState instruction="No resumes in library yet. Upload files or sync a Drive folder." />
        </div>
      ) : (
        <>
          <div className="library-summary-bar" data-testid="library-stats" role="status">
            <span className="font-num">
              {resumes.length} file{resumes.length === 1 ? "" : "s"} · {versions} version
              {versions === 1 ? "" : "s"}
              {cached + parsed > 0 ? (
                <>
                  {" "}
                  · {cached} cached / {parsed} newly parsed
                </>
              ) : null}
            </span>
          </div>
          <label className="library-filter-label">
            <span className="sr-only">Filter library</span>
            <input
              type="search"
              className="library-filter-input"
              placeholder="Filter by name, title, skill…"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              aria-label="Filter library files"
              data-testid="library-filter"
            />
          </label>
          <div
            ref={listRef}
            className="library-list-virtual"
            data-testid="library-list"
            style={{ maxHeight: LIST_MAX_HEIGHT, height: Math.min(totalHeight, LIST_MAX_HEIGHT) }}
            onScroll={(e) => setScrollTop((e.target as HTMLDivElement).scrollTop)}
            role="list"
            aria-label="Resume library"
            tabIndex={0}
          >
            <div style={{ height: totalHeight, position: "relative" }}>
              <ul
                className="library-list library-list-window"
                style={{ transform: `translateY(${offsetY}px)` }}
              >
                {visible.map((row) => {
                  if (row.kind === "cluster") {
                    const isOpen = expanded.has(row.cid);
                    const primary = row.members[0];
                    const anyNew = row.members.some((m) => highlightIds.has(m.id));
                    const badgeStatus = statusByResumeId.get(primary?.id ?? "");
                    return (
                      <li
                        key={`c-${row.cid}`}
                        className={`library-row library-cluster-row${anyNew ? " library-row-new" : ""}`}
                        style={{ height: ROW_HEIGHT }}
                        role="listitem"
                      >
                        <button
                          type="button"
                          className="library-cluster-toggle"
                          aria-expanded={isOpen}
                          aria-controls={`cluster-${row.cid}`}
                          onClick={() => toggleCluster(row.cid)}
                          onKeyDown={(e) => onClusterKey(e, row.cid)}
                        >
                          {isOpen ? (
                            <ChevronDown size={16} aria-hidden />
                          ) : (
                            <ChevronRight size={16} aria-hidden />
                          )}
                          <strong className="library-row-name">
                            {row.count > 1
                              ? `Base ${row.cid.slice(0, 8)}`
                              : primary?.filename ?? row.cid.slice(0, 8)}
                          </strong>
                          {row.count > 1 ? (
                            <span className="library-count-badge font-num" aria-label={`${row.count} versions`}>
                              {row.count}
                            </span>
                          ) : null}
                          {badgeStatus ? (
                            <span
                              className={`library-cache-badge library-cache-badge--${badgeStatus}`}
                              data-testid={`cache-badge-${primary?.id ?? row.cid}`}
                            >
                              {badgeStatus}
                            </span>
                          ) : null}
                          <span className="meta library-row-meta">
                            <span className="library-row-title" data-testid={`cluster-title-${row.cid}`}>
                              {primary?.profile.title || "Untitled"}
                            </span>
                            {row.count === 1 && primary ? (
                              <>
                                {" · "}
                                <SkillsPreview skills={primary.profile.skills} resumeId={primary.id} />
                              </>
                            ) : (
                              ` · ${row.count} near-dup${row.count === 1 ? "" : "s"}`
                            )}
                          </span>
                        </button>
                      </li>
                    );
                  }
                  const r = row.resume;
                  const badgeStatus = statusByResumeId.get(r.id);
                  return (
                    <li
                      key={`m-${r.id}`}
                      id={row.cid === r.id ? undefined : `cluster-${row.cid}`}
                      className={`library-row library-member-row${highlightIds.has(r.id) ? " library-row-new" : ""}`}
                      style={{ height: ROW_HEIGHT }}
                      role="listitem"
                    >
                      <strong className="library-row-name">{r.filename}</strong>
                      {badgeStatus ? (
                        <span className={`library-cache-badge library-cache-badge--${badgeStatus}`}>
                          {badgeStatus}
                        </span>
                      ) : null}
                      <span className="meta library-row-meta">
                        {r.profile.title || "Untitled"} · {r.source}
                        {r.cluster_label ? ` · ${r.cluster_label}` : ""}
                        {r.profile.skills.length > 0 ? (
                          <>
                            {" · "}
                            <SkillsPreview skills={r.profile.skills} resumeId={r.id} />
                          </>
                        ) : null}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          </div>
          {filter && groups.length === 0 ? (
            <p className="meta" style={{ marginTop: 8 }}>
              No files match “{filter}”.
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
