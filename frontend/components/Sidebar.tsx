"use client";

import { BookOpen, Briefcase, Files, Library, Send } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import ThemeToggle from "./ui/ThemeToggle";

const NAV_ITEMS = [
  { href: "/", label: "Resume → Jobs → Team", icon: Briefcase },
  { href: "/library", label: "Resume Library", icon: Library },
  { href: "/about", label: "About", icon: BookOpen },
] as const;

const BETA_ITEMS = [
  { label: "Outreach (Beta)", icon: Send },
  { label: "Applications Tracker (Beta)", icon: Files },
] as const;

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div>
          <p className="eyebrow">TeamScout</p>
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
            >
              <Icon size={16} aria-hidden />
              {item.label}
            </Link>
          );
        })}
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
    </aside>
  );
}
