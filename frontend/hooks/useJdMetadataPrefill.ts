"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { extractJobMetadata } from "../lib/api";
import type { FieldConfidence, JobMetadata } from "../lib/types";

export type AutoFieldKey = "title" | "company" | "location";
export type DirtyFields = Partial<Record<AutoFieldKey, boolean>>;

const DEBOUNCE_MS = 800;
const MIN_CHARS = 200;
const TIMEOUT_MS = 6000;

type Setters = {
  setTitle: (v: string) => void;
  setCompany: (v: string) => void;
  setLocation: (v: string) => void;
};

/**
 * Auto-extract job metadata for paste flows.
 * - Debounce 800ms after description stops changing, only if >200 chars
 * - On paste with >200 chars, fire immediately (still seq-guarded)
 * - Never overwrites fields the user has edited (dirty set)
 * - Re-paste: non-dirty fields take latest extract (including null → clear)
 * - Short text (<200): bump seq + abort in-flight so late responses never apply
 * - Failure / 6s timeout: silent, form stays manual
 */
export function useJdMetadataPrefill(description: string, setters: Setters) {
  const [detecting, setDetecting] = useState(false);
  const [meta, setMeta] = useState<JobMetadata | null>(null);
  const [autoFields, setAutoFields] = useState<DirtyFields>({});
  const dirtyRef = useRef<DirtyFields>({});
  const seqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const settersRef = useRef(setters);
  const descriptionRef = useRef(description);
  settersRef.current = setters;
  descriptionRef.current = description;

  const markDirty = useCallback((key: AutoFieldKey) => {
    dirtyRef.current = { ...dirtyRef.current, [key]: true };
    setAutoFields((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  }, []);

  const setTitle = useCallback(
    (v: string) => {
      markDirty("title");
      settersRef.current.setTitle(v);
    },
    [markDirty],
  );
  const setCompany = useCallback(
    (v: string) => {
      markDirty("company");
      settersRef.current.setCompany(v);
    },
    [markDirty],
  );
  const setLocation = useCallback(
    (v: string) => {
      markDirty("location");
      settersRef.current.setLocation(v);
    },
    [markDirty],
  );

  const runExtract = useCallback((text: string) => {
    const trimmed = text.trim();
    if (trimmed.length < MIN_CHARS) return;
    const seq = ++seqRef.current;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setDetecting(true);
    const timeout = window.setTimeout(() => ac.abort(), TIMEOUT_MS);
    void (async () => {
      try {
        const res = await extractJobMetadata(trimmed, ac.signal);
        if (seq !== seqRef.current) return;
        setMeta(res.metadata);
        const m = res.metadata;
        const dirty = dirtyRef.current;
        const auto: DirtyFields = {};
        // Non-dirty keys take latest value (null clears stale auto-fill)
        if (!dirty.title) {
          settersRef.current.setTitle(m.title ?? "");
          if (m.title) auto.title = true;
        }
        if (!dirty.company) {
          settersRef.current.setCompany(m.company ?? "");
          if (m.company) auto.company = true;
        }
        if (!dirty.location) {
          settersRef.current.setLocation(m.location ?? "");
          if (m.location) auto.location = true;
        }
        setAutoFields((prev) => {
          // Preserve auto flags for dirty keys that still had chips? No — dirty clears chip.
          const next: DirtyFields = { ...auto };
          // Keep non-dirty auto only from this extract
          return next;
        });
      } catch {
        /* assist-only: no toast, form stays fully manual */
      } finally {
        window.clearTimeout(timeout);
        if (seq === seqRef.current) setDetecting(false);
      }
    })();
  }, []);

  /** Call from textarea onPaste after state will update — fires extract ASAP for long pastes. */
  const onDescriptionPaste = useCallback(
    (pastedText: string) => {
      const combined = pastedText.trim();
      if (combined.length < MIN_CHARS) return;
      // Immediate extract on paste (debounce effect will also schedule; seq invalidates the slower one)
      runExtract(combined);
    },
    [runExtract],
  );

  useEffect(() => {
    const text = description.trim();
    if (text.length < MIN_CHARS) {
      // Invalidate any in-flight extract from a prior long paste so late
      // responses cannot re-apply title/company/location after clear/short re-paste.
      seqRef.current += 1;
      abortRef.current?.abort();
      abortRef.current = null;
      setDetecting(false);
      return;
    }
    const seq = ++seqRef.current;
    const timer = window.setTimeout(() => {
      // Only run if this debounce still owns the latest seq (paste may have advanced it)
      if (seq !== seqRef.current) return;
      // Re-check length in case description changed mid-debounce
      const latest = descriptionRef.current.trim();
      if (latest.length < MIN_CHARS) return;
      // Align seq for this extract without double-increment: runExtract increments again.
      // So we call the body via runExtract which bumps seq — that would invalidate
      // concurrent paste. Instead inline the same path with current seq ownership:
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      setDetecting(true);
      const timeout = window.setTimeout(() => ac.abort(), TIMEOUT_MS);
      const extractSeq = seqRef.current;
      void (async () => {
        try {
          const res = await extractJobMetadata(latest, ac.signal);
          if (extractSeq !== seqRef.current) return;
          setMeta(res.metadata);
          const m = res.metadata;
          const dirty = dirtyRef.current;
          const auto: DirtyFields = {};
          if (!dirty.title) {
            settersRef.current.setTitle(m.title ?? "");
            if (m.title) auto.title = true;
          }
          if (!dirty.company) {
            settersRef.current.setCompany(m.company ?? "");
            if (m.company) auto.company = true;
          }
          if (!dirty.location) {
            settersRef.current.setLocation(m.location ?? "");
            if (m.location) auto.location = true;
          }
          setAutoFields(auto);
        } catch {
          /* assist-only */
        } finally {
          window.clearTimeout(timeout);
          if (extractSeq === seqRef.current) setDetecting(false);
        }
      })();
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [description]);

  function confidence(key: string): FieldConfidence | undefined {
    return meta?.confidence?.[key];
  }

  return {
    detecting,
    meta,
    autoFields,
    setTitle,
    setCompany,
    setLocation,
    confidence,
    onDescriptionPaste,
  };
}

/** Exported for unit tests — pure race helper mirroring short-text invalidation. */
export function shouldDiscardExtract(seqAtStart: number, seqNow: number): boolean {
  return seqAtStart !== seqNow;
}
