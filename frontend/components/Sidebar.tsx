"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Resume → Jobs → Team" },
  { href: "/library", label: "Resume Library" },
] as const;

const BETA_ITEMS = [
  { label: "Outreach (Beta)" },
  { label: "Applications Tracker (Beta)" },
] as const;

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sidebar">
      <p className="eyebrow">TeamScout</p>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={pathname === item.href ? "sidebar-link active" : "sidebar-link"}
          >
            {item.label}
          </Link>
        ))}
        {BETA_ITEMS.map((item) => (
          <span key={item.label} className="sidebar-link disabled" title="Coming soon">
            {item.label}
          </span>
        ))}
      </nav>
    </aside>
  );
}