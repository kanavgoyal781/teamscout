/**
 * Compose deep-link builders (mailto / Gmail / Outlook).
 * TeamScout never sends mail — these only open the user's client.
 */

export const MAILTO_MAX_LENGTH = 1800;

export type ComposeClient = "mailto" | "gmail" | "outlook";

export type ComposeDraft = {
  to: string;
  subject: string;
  body: string;
};

export type MailtoBuildResult = {
  href: string;
  truncated: boolean;
  /** Full subject+body for clipboard when URL was truncated. */
  fullText: string;
};

function encodeQuery(params: Record<string, string>): string {
  // URLSearchParams encodes spaces as +; mail clients prefer %20 for body/subject.
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) sp.set(k, v);
  }
  return sp.toString().replace(/\+/g, "%20");
}

/** Build a mailto: URL; truncate body with ellipsis if over MAILTO_MAX_LENGTH. */
export function buildMailtoUrl(draft: ComposeDraft): MailtoBuildResult {
  const to = (draft.to || "").trim();
  const subject = draft.subject ?? "";
  const body = draft.body ?? "";
  const fullText = `Subject: ${subject}\n\n${body}`;

  const tryBuild = (subj: string, bod: string) => {
    const q = encodeQuery({ subject: subj, body: bod });
    return `mailto:${encodeURIComponent(to).replace(/%40/g, "@")}?${q}`;
  };

  let href = tryBuild(subject, body);
  if (href.length <= MAILTO_MAX_LENGTH) {
    return { href, truncated: false, fullText };
  }

  // Binary-search body length that fits under the cap.
  let lo = 0;
  let hi = body.length;
  let best = tryBuild(subject, "");
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    let slice = body.slice(0, mid);
    if (mid < body.length) {
      slice = slice.replace(/\s+\S*$/, "").trimEnd() + "…";
    }
    const candidate = tryBuild(subject, slice);
    if (candidate.length <= MAILTO_MAX_LENGTH) {
      best = candidate;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }

  // If even empty body + subject is too long, drop subject content too.
  if (best.length > MAILTO_MAX_LENGTH) {
    let sLo = 0;
    let sHi = subject.length;
    best = tryBuild("", "");
    while (sLo <= sHi) {
      const mid = Math.floor((sLo + sHi) / 2);
      let slice = subject.slice(0, mid);
      if (mid < subject.length) slice = slice.trimEnd() + "…";
      const candidate = tryBuild(slice, "");
      if (candidate.length <= MAILTO_MAX_LENGTH) {
        best = candidate;
        sLo = mid + 1;
      } else {
        sHi = mid - 1;
      }
    }
  }

  return { href: best, truncated: true, fullText };
}

/** Gmail web compose deep-link. */
export function buildGmailUrl(draft: ComposeDraft): string {
  const to = (draft.to || "").trim();
  const q = encodeQuery({
    view: "cm",
    fs: "1",
    to,
    su: draft.subject ?? "",
    body: draft.body ?? "",
  });
  return `https://mail.google.com/mail/?${q}`;
}

/** Outlook web compose deep-link. */
export function buildOutlookUrl(draft: ComposeDraft): string {
  const to = (draft.to || "").trim();
  const q = encodeQuery({
    to,
    subject: draft.subject ?? "",
    body: draft.body ?? "",
  });
  return `https://outlook.office.com/mail/deeplink/compose?${q}`;
}

export function buildComposeUrl(
  client: ComposeClient,
  draft: ComposeDraft,
): { href: string; truncated: boolean; fullText: string } {
  if (client === "gmail") {
    return {
      href: buildGmailUrl(draft),
      truncated: false,
      fullText: `Subject: ${draft.subject}\n\n${draft.body}`,
    };
  }
  if (client === "outlook") {
    return {
      href: buildOutlookUrl(draft),
      truncated: false,
      fullText: `Subject: ${draft.subject}\n\n${draft.body}`,
    };
  }
  return buildMailtoUrl(draft);
}
