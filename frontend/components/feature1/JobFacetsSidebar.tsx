"use client";

import type { JobFacets } from "../../lib/types";

export type FacetSelection = {
  company: string | null;
  seniority: string | null;
  remote_mode: string | null;
  salary_bucket: string | null;
  posted_age: string | null;
  source: string | null;
};

export const EMPTY_FACET_SELECTION: FacetSelection = {
  company: null,
  seniority: null,
  remote_mode: null,
  salary_bucket: null,
  posted_age: null,
  source: null,
};

type Props = {
  facets: JobFacets | null | undefined;
  selection: FacetSelection;
  onChange: (next: FacetSelection) => void;
  droppedCounts?: Record<string, number>;
};

function FacetGroup({
  title,
  buckets,
  selected,
  onSelect,
}: {
  title: string;
  buckets: { value: string; count: number }[];
  selected: string | null;
  onSelect: (value: string | null) => void;
}) {
  if (!buckets.length) return null;
  return (
    <div className="facet-group">
      <h4>{title}</h4>
      <ul>
        <li>
          <button
            type="button"
            className={selected === null ? "facet-active" : ""}
            onClick={() => onSelect(null)}
          >
            All
          </button>
        </li>
        {buckets.map((b) => (
          <li key={b.value}>
            <button
              type="button"
              className={selected === b.value ? "facet-active" : ""}
              onClick={() => onSelect(selected === b.value ? null : b.value)}
            >
              <span>{b.value}</span>
              <span className="font-num facet-count">{b.count}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function JobFacetsSidebar({ facets, selection, onChange, droppedCounts }: Props) {
  if (!facets) return null;
  const droppedEntries = Object.entries(droppedCounts ?? {}).filter(([, n]) => n > 0);

  return (
    <aside className="facets-sidebar" data-testid="facets-sidebar">
      <h3>Facets</h3>
      <p className="meta">
        Counts reflect the full post-filter fetch pool (not only top matches). Client filter applies to
        currently shown results only — no re-fetch.
      </p>
      <FacetGroup
        title="Company"
        buckets={facets.company}
        selected={selection.company}
        onSelect={(v) => onChange({ ...selection, company: v })}
      />
      <FacetGroup
        title="Seniority"
        buckets={facets.seniority}
        selected={selection.seniority}
        onSelect={(v) => onChange({ ...selection, seniority: v })}
      />
      <FacetGroup
        title="Remote"
        buckets={facets.remote_mode}
        selected={selection.remote_mode}
        onSelect={(v) => onChange({ ...selection, remote_mode: v })}
      />
      <FacetGroup
        title="Salary"
        buckets={facets.salary_bucket}
        selected={selection.salary_bucket}
        onSelect={(v) => onChange({ ...selection, salary_bucket: v })}
      />
      <FacetGroup
        title="Posted"
        buckets={facets.posted_age}
        selected={selection.posted_age}
        onSelect={(v) => onChange({ ...selection, posted_age: v })}
      />
      <FacetGroup
        title="Source"
        buckets={facets.source ?? []}
        selected={selection.source}
        onSelect={(v) => onChange({ ...selection, source: v })}
      />
      {droppedEntries.length > 0 ? (
        <div className="dropped-counts" data-testid="dropped-counts">
          <h4>Excluded</h4>
          <ul>
            {droppedEntries.map(([cause, n]) => (
              <li key={cause}>
                <span>{cause.replace(/_/g, " ")}</span>
                <span className="font-num">{n}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </aside>
  );
}

/** Client-side facet match helpers (mirror backend buckets loosely). */
export function salaryBucket(job: {
  salary_unknown?: boolean;
  salary_min?: number | null;
}): string {
  if (job.salary_unknown !== false || job.salary_min == null) return "unknown";
  const annual = job.salary_min;
  if (annual < 80_000) return "<80k";
  if (annual < 120_000) return "80k-120k";
  if (annual < 160_000) return "120k-160k";
  if (annual < 200_000) return "160k-200k";
  return "200k+";
}

export function postedAgeBucket(postedAt: string | null, now = Date.now()): string {
  if (!postedAt) return "unknown";
  const ageDays = Math.max((now - new Date(postedAt).getTime()) / 86400000, 0);
  if (ageDays < 1) return "24h";
  if (ageDays < 3) return "3d";
  if (ageDays < 7) return "7d";
  if (ageDays < 14) return "14d";
  if (ageDays < 30) return "30d";
  return "30d+";
}
