"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchWorkspace } from "../lib/api";
import HealthBanner from "./HealthBanner";
import Sidebar from "./Sidebar";

type AppShellProps = {
  title: string;
  lede: string;
  children: React.ReactNode;
};

export default function AppShell({ title, lede, children }: AppShellProps) {
  const { data: workspace } = useQuery({
    queryKey: ["workspace"],
    queryFn: fetchWorkspace,
    staleTime: 60_000,
    retry: false,
  });
  const ttl = workspace?.ttl_days ?? 7;

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="page">
        <HealthBanner />
        <header className="page-header">
          <p className="eyebrow">TeamScout</p>
          <h1>{title}</h1>
          <p className="lede">{lede}</p>
        </header>
        {children}
        <footer className="workspace-footer" data-testid="workspace-footer">
          Anonymous workspace: product data auto-deletes after {ttl} days. New browser = new
          workspace. Email reveal credits are shared process-wide to avoid double-billing.
        </footer>
      </main>
    </div>
  );
}
