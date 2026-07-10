"use client";

import { useSyncExternalStore, useState, useEffect, useId, useRef } from "react";
import { BookOpen, Briefcase, Files, Library, Lock, Play, Send, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

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

type BetaKey = "outreach" | "tracker";

const BETA_ITEMS: {
  key: BetaKey;
  label: string;
  icon: typeof Send;
  title: string;
  bullets: string[];
  why: string;
}[] = [
  {
    key: "outreach",
    label: "Outreach (Beta)",
    icon: Send,
    title: "Outreach — planned",
    bullets: [
      "Sequenced follow-ups across hiring contacts",
      "Reply detection and status on each thread",
      "Per-contact history in one place",
      "Daily send caps and clear opt-out handling",
    ],
    why: "CONSTRAINTS.md keeps TeamScout to two live features. Outreach stays a roadmap stub until it earns a real surface.",
  },
  {
    key: "tracker",
    label: "Applications Tracker (Beta)",
    icon: Files,
    title: "Applications Tracker — planned",
    bullets: [
      "Kanban board fed from apply and compose actions",
      "Stage reminders so nothing stalls",
      "Resume version tied to each application",
      "Lightweight notes without becoming a full ATS",
    ],
    why: "CONSTRAINTS.md gates third product surfaces. The tracker is planned, not built, so the two core journeys stay focused.",
  },
];

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

function BetaRoadmapModal({
  item,
  onClose,
}: {
  item: (typeof BETA_ITEMS)[number];
  onClose: () => void;
}) {
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);
  const Icon = item.icon;

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="beta-modal-backdrop"
      role="presentation"
      onClick={onClose}
      data-testid={`beta-modal-${item.key}`}
    >
      <div
        className="beta-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="beta-modal-head">
          <Icon size={18} aria-hidden />
          <h2 id={titleId}>{item.title}</h2>
          <button
            ref={closeRef}
            type="button"
            className="about-detail-close"
            onClick={onClose}
            aria-label="Close roadmap dialog"
          >
            ×
          </button>
        </div>
        <ul className="beta-modal-list">
          {item.bullets.map((b) => (
            <li key={b}>{b}</li>
          ))}
        </ul>
        <p className="meta">Why gated: {item.why}</p>
        <div className="actions" style={{ marginTop: 12 }}>
          <button
            type="button"
            className="primary"
            data-testid={`beta-notify-${item.key}`}
            onClick={() => toast.message("Noted — this is a demo roadmap")}
          >
            Notify me
          </button>
          <button type="button" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Sidebar() {
  const pathname = usePathname();
  const opsToken = useOpsToken();
  const [tourOpen, setTourOpen] = useState(false);
  const [opsPrompt, setOpsPrompt] = useState(false);
  const [opsDraft, setOpsDraft] = useState("");
  const [betaOpen, setBetaOpen] = useState<BetaKey | null>(null);
  const opsFormId = useId();

  function openOps() {
    if (!opsToken) {
      setOpsPrompt(true);
      return;
    }
    void (async () => {
      try {
        const res = await fetch(`${API_BASE}/ops`, {
          credentials: "include",
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

  const openBeta = BETA_ITEMS.find((b) => b.key === betaOpen) ?? null;

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
            title="Ops access"
            aria-haspopup="dialog"
            aria-expanded={opsPrompt}
          >
            <Lock size={16} aria-hidden />
            Ops access
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
            <button
              key={item.key}
              type="button"
              className="sidebar-link sidebar-link-btn sidebar-link-muted"
              title="Open roadmap"
              data-testid={`beta-nav-${item.key}`}
              onClick={() => setBetaOpen(item.key)}
            >
              <Icon size={16} aria-hidden />
              {item.label}
            </button>
          );
        })}
      </nav>

      {opsPrompt ? (
        <form
          id={opsFormId}
          className="ops-token-form"
          onSubmit={submitOpsToken}
          data-testid="ops-token-form"
          role="dialog"
          aria-label="Ops access"
        >
          <label className="meta" htmlFor="ops-token-input">
            Ops access
          </label>
          <input
            id="ops-token-input"
            type="password"
            autoComplete="off"
            value={opsDraft}
            onChange={(e) => setOpsDraft(e.target.value)}
            placeholder="Paste access token"
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

      {openBeta ? <BetaRoadmapModal item={openBeta} onClose={() => setBetaOpen(null)} /> : null}

      <DemoTour open={tourOpen} onClose={() => setTourOpen(false)} />
    </aside>
  );
}
