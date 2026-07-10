/**
 * In-memory OPS_TOKEN only — never persisted to browser storage APIs.
 * Survives SPA navigations within the tab; clears on full reload.
 */

let opsToken: string | null = null;
const listeners = new Set<() => void>();

export function getOpsToken(): string | null {
  return opsToken;
}

export function setOpsToken(token: string | null): void {
  const next = token && token.trim() ? token.trim() : null;
  opsToken = next;
  listeners.forEach((l) => l());
}

export function subscribeOpsToken(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}
