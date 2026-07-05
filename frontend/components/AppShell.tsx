"use client";

import HealthBanner from "./HealthBanner";
import Sidebar from "./Sidebar";

type AppShellProps = {
  title: string;
  lede: string;
  children: React.ReactNode;
  toast?: { kind: "error" | "info"; message: string } | null;
};

export default function AppShell({ title, lede, children, toast }: AppShellProps) {
  return (
    <div className="app-shell">
      <Sidebar />
      <main className="page">
        <HealthBanner />
        <header className="page-header">
          <h1>{title}</h1>
          <p className="lede">{lede}</p>
        </header>

        {toast ? (
          <div className={`toast toast-${toast.kind}`} role="status">
            {toast.message}
          </div>
        ) : null}

        {children}
      </main>
    </div>
  );
}