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
  settersRef.current = setters;

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
      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;
      setDetecting(true);
      const timeout = window.setTimeout(() => ac.abort(), TIMEOUT_MS);
      void (async () => {
        try {
          const res = await extractJobMetadata(text, ac.signal);
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
          setAutoFields(auto);
        } catch {
          /* assist-only: no toast */
        } finally {
          window.clearTimeout(timeout);
          if (seq === seqRef.current) setDetecting(false);
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
  };
}

/** Exported for unit tests — pure race helper mirroring short-text invalidation. */
export function shouldDiscardExtract(seqAtStart: number, seqNow: number): boolean {
  return seqAtStart !== seqNow;
}
