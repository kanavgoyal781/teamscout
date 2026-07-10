"use client";

import { useSyncExternalStore, useState } from "react";
import { BookOpen, Briefcase, Files, Library, Play, Send, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { API_BASE, fetchHealth } from "../lib/api";
import { getOpsToken, setOpsToken, subscribeOpsToken } from "../lib/opsToken";
import { queryKeys } from "../lib/query";
import DemoTour from "./tour/DemoTour";
import ThemeToggle from "./ui/ThemeToggle";

const NAV_ITEMS = [
  { href: "/", label: "Feature 1", full: "Resume → Jobs → Team", icon: Briefcase, tour: "nav-feature-1" },
  { href: "/library", label: "Feature 2", full: "Resume Library", icon: Library, tour: "nav-feature-2" },
  { href: "/about", label: "About", full: "About", icon: BookOpen, tour: "nav-about" },
] as const;

const BETA_ITEMS = [
  { label: "Outreach (Beta)", icon: Send },
  { label: "Applications Tracker (Beta)", icon: Files },
] as const;

function useOpsToken() {
  return useSyncExternalStore(subscribeOpsToken, getOpsToken, () => null);
}

function HealthDot() {
  const { data, isError, isPending } = useQuery({
    queryKey: queryKeys.health,
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    retry: false,
  });

  let status: "ok" | "degraded" | "unknown" = "unknown";
  if (!isPending && !isError && data?.ok) status = "ok";
  else if (!isPending && (isError || data?.ok === false)) status = "degraded";

  const label =
    status === "ok" ? "All systems healthy" : status === "degraded" ? "Degraded" : "Health unknown";

  return (
    <span
      className={`health-dot health-dot-${status}`}
      title={label}
      aria-label={label}
      data-testid="health-dot"
      data-status={status}
    />
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const opsToken = useOpsToken();
  const [tourOpen, setTourOpen] = useState(false);
  const [opsPrompt, setOpsPrompt] = useState(false);
  const [opsDraft, setOpsDraft] = useState("");

  function openOps() {
    if (!opsToken) {
      setOpsPrompt(true);
      return;
    }
    // Open backend ops HTML with token header via query only in local operator use;
    // prefer Bearer via a small form-less window fetch is hard — use Authorization
    // by opening a same-origin proxy is out of scope. Open /ops with X-Ops-Token via
    // a temporary fetch download is overkill; document: operator pastes token once
    // and we open `${API_BASE}/ops` with header via window name workaround is fragile.
    // Practical: open ops URL; token sent as Authorization Bearer via a blob HTML
    // redirect is too heavy. Use fetch + open blob for HTML.
    void (async () => {
      try {
        const res = await fetch(`${API_BASE}/ops`, {
          headers: {
            Authorization: `Bearer ${opsToken}`,
            "X-Ops-Token": opsToken,
          },
        });
        const html = await res.text();
        const blob = new Blob([html], { type: "text/html" });
        const url = URL.createObjectURL(blob);
        window.open(url, "_blank", "noopener,noreferrer");
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      } catch {
        window.open(`${API_BASE}/ops`, "_blank", "noopener,noreferrer");
      }
    })();
  }

  function submitOpsToken(e: React.FormEvent) {
    e.preventDefault();
    setOpsToken(opsDraft);
    setOpsPrompt(false);
    setOpsDraft("");
  }

  return (
    <aside className="sidebar" data-testid="app-sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-row">
          <p className="eyebrow">TeamScout</p>
          <HealthDot />
        </div>
        <ThemeToggle />
      </div>
      <nav className="sidebar-nav" aria-label="Primary">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={active ? "sidebar-link active" : "sidebar-link"}
              aria-current={active ? "page" : undefined}
              title={item.full}
              data-tour={item.tour}
              data-testid={item.tour}
            >
              <Icon size={16} aria-hidden />
              {item.label}
            </Link>
          );
        })}

        {opsToken ? (
          <button
            type="button"
            className="sidebar-link sidebar-link-btn"
            onClick={openOps}
            data-testid="nav-ops"
          >
            <Settings size={16} aria-hidden />
            Ops
          </button>
        ) : (
          <button
            type="button"
            className="sidebar-link sidebar-link-btn sidebar-link-muted"
            onClick={() => setOpsPrompt(true)}
            data-testid="nav-ops-unlock"
            title="Enter OPS_TOKEN (memory only)"
          >
            <Settings size={16} aria-hidden />
            Ops
          </button>
        )}

        <button
          type="button"
          className="sidebar-link sidebar-link-btn"
          onClick={() => setTourOpen(true)}
          data-testid="demo-tour-start"
          data-tour="demo-tour-start"
        >
          <Play size={16} aria-hidden />
          Demo tour
        </button>

        <p className="sidebar-section-label">Coming soon</p>
        {BETA_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <span key={item.label} className="sidebar-link disabled" title="Coming soon">
              <Icon size={16} aria-hidden />
              {item.label}
            </span>
          );
        })}
      </nav>

      {opsPrompt ? (
        <form className="ops-token-form" onSubmit={submitOpsToken} data-testid="ops-token-form">
          <label className="meta" htmlFor="ops-token-input">
            OPS_TOKEN (memory only — never stored)
          </label>
          <input
            id="ops-token-input"
            type="password"
            autoComplete="off"
            value={opsDraft}
            onChange={(e) => setOpsDraft(e.target.value)}
            placeholder="Paste token"
            data-testid="ops-token-input"
          />
          <div className="actions" style={{ marginTop: 8 }}>
            <button type="submit" className="primary" data-testid="ops-token-submit">
              Unlock Ops
            </button>
            <button type="button" onClick={() => setOpsPrompt(false)}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}

      <DemoTour open={tourOpen} onClose={() => setTourOpen(false)} />
    </aside>
  );
}
