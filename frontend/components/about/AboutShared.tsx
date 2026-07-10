"use client";

import type { ComponentType, RefObject } from "react";
import { useLayoutEffect, useRef } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ChevronDown } from "lucide-react";

import { DETAIL_PANEL_ID, DETAILS, type DetailKey } from "./details";

export function DetailPanel({
  detailKey,
  onClose,
  closeRef,
}: {
  detailKey: Exclude<DetailKey, null>;
  onClose: () => void;
  closeRef: RefObject<HTMLButtonElement | null>;
}) {
  const d = DETAILS[detailKey];
  const reduced = useReducedMotion();
  const panelRef = useRef<HTMLElement | null>(null);

  useLayoutEffect(() => {
    const closeBtn = closeRef.current;
    const panel = panelRef.current;
    closeBtn?.focus({ preventScroll: true });
    panel?.scrollIntoView({
      block: "nearest",
      behavior: reduced ? "auto" : "smooth",
    });
  }, [detailKey, closeRef, reduced]);

  return (
    <motion.aside
      ref={panelRef}
      className="about-detail"
      style={{ borderColor: d.color }}
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={reduced ? undefined : { opacity: 0, y: 6 }}
      transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
      role="region"
      aria-label={`Details: ${d.title}`}
      data-testid="about-detail"
      id={DETAIL_PANEL_ID}
      tabIndex={-1}
    >
      <div className="about-detail-head">
        <span className="about-detail-swatch" style={{ background: d.color }} aria-hidden />
        <h3>{d.title}</h3>
        <button
          ref={closeRef}
          type="button"
          className="about-detail-close"
          onClick={onClose}
          aria-label="Close details"
        >
          ×
        </button>
      </div>
      <div className="about-detail-body">
        <div>
          <h4>Why</h4>
          <p>{d.why}</p>
        </div>
        <div>
          <h4>How it works in TeamScout</h4>
          <p>{d.how}</p>
        </div>
        <div>
          <h4>Tradeoff we accepted</h4>
          <p>{d.tradeoff}</p>
        </div>
      </div>
    </motion.aside>
  );
}

export function SelectableCard({
  id,
  active,
  color,
  icon: Icon,
  title,
  blurb,
  onSelect,
}: {
  id: Exclude<DetailKey, null>;
  active: boolean;
  color: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  title: string;
  blurb: string;
  onSelect: (k: Exclude<DetailKey, null>, el: HTMLElement | null) => void;
}) {
  return (
    <button
      type="button"
      className={`about-card${active ? " is-active" : ""}`}
      style={{ ["--card-accent" as string]: color }}
      onClick={(e) => onSelect(id, e.currentTarget)}
      aria-expanded={active}
      aria-controls={active ? DETAIL_PANEL_ID : undefined}
      data-testid={`about-card-${id}`}
    >
      <span className="about-card-icon" style={{ color }} aria-hidden>
        <Icon size={18} strokeWidth={1.75} />
      </span>
      <span className="about-card-title">{title}</span>
      <span className="about-card-blurb">{blurb}</span>
      <span className="about-card-cta">
        Why this design <ChevronDown size={14} aria-hidden />
      </span>
    </button>
  );
}

export function SectionHead({
  kicker,
  title,
  lede,
  icon: Icon,
}: {
  kicker: string;
  title: string;
  lede: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number; "aria-hidden"?: boolean }>;
}) {
  return (
    <div className="about-section-head">
      <span className="about-section-icon" aria-hidden>
        <Icon size={16} strokeWidth={1.75} />
      </span>
      <div>
        <p className="about-section-kicker">{kicker}</p>
        <h2 className="about-section-title">{title}</h2>
        <p className="about-section-lede">{lede}</p>
      </div>
    </div>
  );
}
