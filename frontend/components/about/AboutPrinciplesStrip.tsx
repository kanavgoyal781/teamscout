"use client";

import { ExternalLink } from "lucide-react";

import { PRINCIPLE_LINKS, githubFileUrl } from "./details";

export default function AboutPrinciplesStrip() {
  return (
    <ul className="about-principles-strip" data-testid="about-principles" aria-label="Engineering principles">
      {PRINCIPLE_LINKS.map((p) => {
        const href = githubFileUrl(p.path);
        const inner = (
          <>
            <span className="about-principle-link-label">{p.label}</span>
            <span className="about-principle-link-tip">{p.tip}</span>
            <span className="about-principle-link-path font-num">
              {p.path}
              {href ? (
                <>
                  {" "}
                  <ExternalLink size={12} aria-hidden />
                </>
              ) : null}
            </span>
          </>
        );
        return (
          <li key={p.path}>
            {href ? (
              <a
                className="about-principle-link pressable"
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                data-testid={`principle-link-${p.path.replace(/[/.]/g, "-")}`}
              >
                {inner}
              </a>
            ) : (
              <div
                className="about-principle-link"
                data-testid={`principle-path-${p.path.replace(/[/.]/g, "-")}`}
                title="Set NEXT_PUBLIC_GITHUB_BASE to enable repo links"
              >
                {inner}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
