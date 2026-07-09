"use client";

import HealthBanner from "./HealthBanner";
import Sidebar from "./Sidebar";

type AppShellProps = {
  title: string;
  lede: string;
  children: React.ReactNode;
};

export default function AppShell({ title, lede, children }: AppShellProps) {
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
      </main>
    </div>
  );
}
