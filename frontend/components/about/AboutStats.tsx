"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchPublicStats, type PublicStats } from "../../lib/api";
import { queryKeys } from "../../lib/query";
import CountUp from "../ui/CountUp";
import { Skeleton } from "../ui/Skeleton";

function StatChip({
  label,
  value,
  suffix = "",
  decimals = 0,
  testId,
}: {
  label: string;
  value: number | null | undefined;
  suffix?: string;
  decimals?: number;
  testId: string;
}) {
  const n = value == null || !Number.isFinite(value) ? null : value;
  return (
    <div className="about-stat-chip" data-testid={testId}>
      <span className="about-stat-value font-num">
        {n == null ? (
          "—"
        ) : (
          <>
            <CountUp value={n} decimals={decimals} />
            {suffix}
          </>
        )}
      </span>
      <span className="about-stat-label">{label}</span>
    </div>
  );
}

export default function AboutStats() {
  const { data, isPending, isError } = useQuery({
    queryKey: queryKeys.stats,
    queryFn: fetchPublicStats,
    staleTime: 60_000,
    retry: false,
  });

  if (isPending) {
    return (
      <div className="about-stats" data-testid="about-stats" aria-busy="true">
        <Skeleton className="about-stat-skel" />
        <Skeleton className="about-stat-skel" />
        <Skeleton className="about-stat-skel" />
        <Skeleton className="about-stat-skel" />
        <Skeleton className="about-stat-skel" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="about-stats about-stats-empty" data-testid="about-stats" role="status">
        <p className="meta">Live stats unavailable — start the API to load aggregates from SQLite.</p>
      </div>
    );
  }

  const s = data as PublicStats;
  return (
    <div className="about-stats" data-testid="about-stats" aria-label="Live product stats">
      <StatChip
        testId="stat-jobs-ranked"
        label="jobs ranked"
        value={s.jobs_ranked_total}
      />
      <StatChip
        testId="stat-resumes-parsed"
        label="resumes parsed"
        value={s.resumes_parsed_total}
      />
      <StatChip
        testId="stat-teams-found"
        label="teams found"
        value={s.teams_discovered_total}
      />
      <StatChip
        testId="stat-median-rank-ms"
        label="median rerank ms"
        value={s.median_rank_latency_ms}
        decimals={0}
      />
      <StatChip
        testId="stat-llm-cost"
        label="LLM $ total"
        value={s.total_llm_cost_usd}
        decimals={4}
      />
      <p className="meta about-stats-note">
        Aggregates from this deploy&apos;s SQLite (searches.results lengths, resumes, team
        lookups, recent rerank latencies, lifetime LLM cost). Public by design for the About
        story — not an ops dump.
      </p>
    </div>
  );
}
