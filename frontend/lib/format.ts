/** Display helpers — mono numbers should use font-mono / .font-num in UI. */

/** Relative “posted ago” for job cards. */
export function formatPostedAgo(value: string | null): string {
  if (!value) return "Date unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date unknown";
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 0) return "Just now";
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 60) return mins <= 1 ? "1m ago" : `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return hours === 1 ? "1h ago" : `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return days === 1 ? "1d ago" : `${days}d ago`;
  return date.toLocaleDateString();
}

export function formatScore(score: number): string {
  if (!Number.isFinite(score)) return "—";
  return Math.round(score).toString();
}

export function formatScoreDecimal(score: number, digits = 2): string {
  if (!Number.isFinite(score)) return "—";
  return score.toFixed(digits);
}

/** Normalize score fields that may be 0–1 or 0–100 into 0–100 for bars. */
export function toPercent(value: number, alreadyPercent = false): number {
  if (!Number.isFinite(value)) return 0;
  if (alreadyPercent || value > 1) return Math.min(100, Math.max(0, value));
  return Math.min(100, Math.max(0, value * 100));
}
