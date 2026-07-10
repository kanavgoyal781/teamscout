"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { usePathname, useRouter } from "next/navigation";
import { useReducedMotion } from "framer-motion";
import { X } from "lucide-react";

export type TourStep = {
  id: string;
  /** CSS selector or [data-tour="…"] — prefer always-mounted anchors */
  target: string;
  title: string;
  body: string;
  href?: string;
};

/**
 * Feature-1 guided tour using always-mounted anchors only.
 * Last step is the credit-gate policy note — never auto-clicks find-team or reveal.
 */
export const TOUR_STEPS: TourStep[] = [
  {
    id: "nav-f1",
    target: '[data-tour="nav-feature-1"]',
    title: "Feature 1",
    body: "Resume → ranked jobs → hiring team. Primary operator path in the sidebar.",
    href: "/",
  },
  {
    id: "wizard",
    target: '[data-tour="resume-wizard"], [data-testid="resume-wizard"]',
    title: "Upload a resume",
    body: "Drop a PDF/DOCX (or samples/sample_resume.pdf). Parsing uses the live LLM — no invented profiles.",
    href: "/",
  },
  {
    id: "stepper",
    target: '[data-tour="wizard-stepper"], [data-testid="wizard-stepper"]',
    title: "Guided steps",
    body: "Upload → Profile → Matches → Team. Confirm the profile before any search spends API budget.",
    href: "/",
  },
  {
    id: "nav-about",
    target: '[data-tour="nav-about"]',
    title: "About the ranking",
    body: "The About story documents hybrid rank, MMR, MaxSim, and eval floors — open it anytime without credits.",
    href: "/",
  },
  {
    id: "credit-gate",
    target: '[data-tour="credit-confirm"], [data-testid="credit-confirm"]',
    title: "Stop before credit spend",
    body: "Hiring-team lookup and email reveal are confirm-gated. This tour never auto-clicks those actions — real credits need an explicit operator gesture.",
    href: "/",
  },
];

type DemoTourProps = {
  open: boolean;
  onClose: () => void;
};

function resolveTarget(selector: string): Element | null {
  if (typeof document === "undefined") return null;
  for (const part of selector.split(",").map((s) => s.trim())) {
    const el = document.querySelector(part);
    if (el) return el;
  }
  return null;
}

function focusableWithin(root: HTMLElement): HTMLElement[] {
  const nodes = root.querySelectorAll<HTMLElement>(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
  );
  return Array.from(nodes).filter((el) => !el.hasAttribute("disabled"));
}

export default function DemoTour({ open, onClose }: DemoTourProps) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [mounted, setMounted] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const reduced = useReducedMotion();
  const cardRef = useRef<HTMLDivElement | null>(null);
  const nextRef = useRef<HTMLButtonElement | null>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const bodyId = useId();

  const step = TOUR_STEPS[index] ?? TOUR_STEPS[0];
  const isLast = index >= TOUR_STEPS.length - 1;

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!open) {
      setIndex(0);
      setRect(null);
    }
  }, [open]);

  // Capture return focus before moving into dialog; restore on close.
  useLayoutEffect(() => {
    if (!open) return;
    if (!returnFocusRef.current) {
      const start = document.querySelector(
        '[data-testid="demo-tour-start"]',
      ) as HTMLElement | null;
      const active = document.activeElement;
      returnFocusRef.current =
        active instanceof HTMLElement &&
        active !== document.body &&
        !active.closest?.('[data-testid="demo-tour"]')
          ? active
          : start;
    }
    const focusNext = () => nextRef.current?.focus({ preventScroll: true });
    focusNext();
    // Portal/paint: one rAF so focus sticks after mount (jsdom + real browsers).
    const id = window.requestAnimationFrame(focusNext);
    return () => window.cancelAnimationFrame(id);
  }, [open, index, mounted]);

  useEffect(() => {
    if (open) return;
    const el = returnFocusRef.current;
    returnFocusRef.current = null;
    if (el && document.contains(el)) {
      // Defer past unmount so focus is not lost when Next disappears
      window.setTimeout(() => el.focus?.(), 0);
    }
  }, [open]);

  const measure = useCallback(() => {
    if (!open) return;
    const el = resolveTarget(step.target);
    if (el) {
      if (typeof (el as HTMLElement).scrollIntoView === "function") {
        (el as HTMLElement).scrollIntoView({
          block: "center",
          behavior: reduced ? "auto" : "smooth",
        });
      }
      setRect(el.getBoundingClientRect());
    } else {
      setRect(null);
    }
  }, [open, step, reduced]);

  useEffect(() => {
    if (!open) return;
    if (step.href && pathname !== step.href) {
      router.push(step.href);
      return;
    }
    const t = window.setTimeout(measure, 120);
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.clearTimeout(t);
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [open, step, pathname, router, measure]);

  const next = useCallback(() => {
    if (isLast) {
      onClose();
      return;
    }
    setIndex((i) => Math.min(TOUR_STEPS.length - 1, i + 1));
  }, [isLast, onClose]);

  const prev = useCallback(() => {
    setIndex((i) => Math.max(0, i - 1));
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "ArrowRight" || e.key === "Enter") {
        // Don't steal Enter from buttons (they fire click); still support global →
        if (e.key === "ArrowRight") {
          e.preventDefault();
          next();
        }
        return;
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        prev();
        return;
      }
      if (e.key === "Tab" && cardRef.current) {
        const list = focusableWithin(cardRef.current);
        if (list.length === 0) return;
        const first = list[0];
        const last = list[list.length - 1];
        const active = document.activeElement as HTMLElement | null;
        if (e.shiftKey) {
          if (active === first || !cardRef.current.contains(active)) {
            e.preventDefault();
            last.focus();
          }
        } else if (active === last || !cardRef.current.contains(active)) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, next, prev, onClose]);

  const pad = 8;
  const hole = useMemo(() => {
    if (!rect) return null;
    return {
      top: Math.max(0, rect.top - pad),
      left: Math.max(0, rect.left - pad),
      width: rect.width + pad * 2,
      height: rect.height + pad * 2,
    };
  }, [rect]);

  if (!open || !mounted) return null;

  return createPortal(
    <div
      className="demo-tour"
      data-testid="demo-tour"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={bodyId}
    >
      <div className="demo-tour-backdrop" aria-hidden />
      {hole ? (
        <div
          className="demo-tour-spotlight"
          style={{
            top: hole.top,
            left: hole.left,
            width: hole.width,
            height: hole.height,
          }}
          aria-hidden
        />
      ) : null}
      <div className="demo-tour-card panel" data-testid="demo-tour-card" ref={cardRef}>
        <div className="demo-tour-card-head">
          <p className="eyebrow font-num" data-testid="demo-tour-step-label">
            Step {index + 1} / {TOUR_STEPS.length}
          </p>
          <button
            type="button"
            className="about-detail-close"
            onClick={onClose}
            aria-label="Close tour"
            data-testid="demo-tour-close"
          >
            <X size={16} />
          </button>
        </div>
        <h2 className="demo-tour-title" id={titleId}>
          {step.title}
        </h2>
        <p className="demo-tour-body" id={bodyId}>
          {step.body}
        </p>
        {!hole ? (
          <p className="meta" data-testid="demo-tour-missing">
            Highlight target is off this view — press Next to keep reading. The page stays locked
            while the tour is open (no mid-tour UI actions).
          </p>
        ) : null}
        <div className="demo-tour-actions">
          <button
            type="button"
            onClick={prev}
            disabled={index === 0}
            data-testid="demo-tour-prev"
          >
            Back
          </button>
          <button
            ref={nextRef}
            type="button"
            className="primary"
            onClick={next}
            data-testid="demo-tour-next"
          >
            {isLast ? "Finish (no credit spend)" : "Next"}
          </button>
        </div>
        <p className="meta demo-tour-keys">Keyboard: ← → · Esc · Tab trapped in card</p>
      </div>
    </div>,
    document.body,
  );
}
