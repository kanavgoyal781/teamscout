"use client";

import { Mail, X } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import type { Contact } from "../lib/types";

export type EmailTemplate = {
  subject: string;
  body: string;
};

const DEFAULT_TEMPLATE: EmailTemplate = {
  subject: "Exploring opportunities on your team",
  body: `Hi {{name}},

I came across the {{role}} opening{{company_clause}} and was impressed by the work your team is doing.

I'd welcome a brief conversation about how my background could help. Happy to share a resume or jump on a quick call.

Best regards`,
};

function applyTemplate(template: string, contact: Contact, roleHint: string): string {
  const company = contact.company?.trim() || "";
  const companyClause = company ? ` at ${company}` : "";
  return template
    .replaceAll("{{name}}", contact.full_name.split(" ")[0] || contact.full_name)
    .replaceAll("{{full_name}}", contact.full_name)
    .replaceAll("{{title}}", contact.title?.trim() || "your team")
    .replaceAll("{{company}}", company || "your company")
    .replaceAll("{{company_clause}}", companyClause)
    .replaceAll("{{role}}", roleHint || contact.title?.trim() || "open role");
}

type BulkEmailComposerProps = {
  contacts: Contact[];
  /** Optional job title for template tokens */
  roleHint?: string;
};

/**
 * Client-side compose helper: confirm subject/body, then open the system mail
 * client with BCC to all revealed emails. Does not send mail from TeamScout servers
 * (no outreach SMTP — stays inside Feature 1 contact UX).
 */
export default function BulkEmailComposer({ contacts, roleHint = "" }: BulkEmailComposerProps) {
  const revealed = useMemo(
    () => contacts.filter((c) => c.email_revealed && c.email && c.email.includes("@")),
    [contacts],
  );

  const [open, setOpen] = useState(false);
  const [subject, setSubject] = useState(DEFAULT_TEMPLATE.subject);
  const [body, setBody] = useState(DEFAULT_TEMPLATE.body);
  const [confirmed, setConfirmed] = useState(false);

  if (revealed.length === 0) {
    return (
      <p className="meta bulk-email-hint" data-testid="bulk-email-hint">
        Reveal at least one email to use <strong>Email all</strong> (opens your mail app with BCC —
        TeamScout does not send mail itself).
      </p>
    );
  }

  function resetAndClose() {
    setOpen(false);
    setConfirmed(false);
  }

  function handleOpenMail() {
    if (!confirmed) {
      toast.error("Confirm the template first.");
      return;
    }
    const emails = revealed.map((c) => c.email!).filter(Boolean);
    // Personalize with first recipient tokens for a single shared body (BCC blast).
    const sample = revealed[0];
    const finalSubject = applyTemplate(subject, sample, roleHint);
    const finalBody = applyTemplate(body, sample, roleHint);

    const params = new URLSearchParams();
    params.set("bcc", emails.join(","));
    params.set("subject", finalSubject);
    params.set("body", finalBody);
    const href = `mailto:?${params.toString()}`;

    // Length safety for long lists
    if (href.length > 1800) {
      toast.error(
        `Too many recipients for one mailto link (${emails.length}). Copy emails or email fewer people.`,
      );
      return;
    }

    window.location.href = href;
    toast.success(`Opening mail app for ${emails.length} recipient(s)…`);
    resetAndClose();
  }

  function copyAllEmails() {
    const list = revealed.map((c) => c.email!).join(", ");
    void navigator.clipboard.writeText(list).then(
      () => toast.success("All revealed emails copied"),
      () => toast.error("Could not copy emails"),
    );
  }

  return (
    <div className="bulk-email" data-testid="bulk-email">
      <div className="actions bulk-email-actions">
        <button
          type="button"
          className="primary"
          data-testid="bulk-email-open"
          onClick={() => {
            setOpen(true);
            setConfirmed(false);
          }}
        >
          <Mail size={14} aria-hidden /> Email all ({revealed.length})
        </button>
        <button type="button" onClick={copyAllEmails} data-testid="bulk-email-copy">
          Copy all emails
        </button>
      </div>

      {open ? (
        <div
          className="bulk-email-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="bulk-email-title"
          data-testid="bulk-email-dialog"
        >
          <div className="bulk-email-modal-head">
            <h4 id="bulk-email-title">Confirm email template</h4>
            <button type="button" className="ghost" onClick={resetAndClose} aria-label="Close">
              <X size={16} />
            </button>
          </div>
          <p className="meta">
            Edit the template, then confirm. Tokens:{" "}
            <code>{"{{name}}"}</code> <code>{"{{full_name}}"}</code> <code>{"{{title}}"}</code>{" "}
            <code>{"{{company}}"}</code> <code>{"{{role}}"}</code>. One shared body is used for the
            BCC blast (mail app personalization is limited).
          </p>

          <label className="bulk-email-field">
            <span>Subject</span>
            <input
              value={subject}
              onChange={(e) => {
                setSubject(e.target.value);
                setConfirmed(false);
              }}
              data-testid="bulk-email-subject"
            />
          </label>
          <label className="bulk-email-field">
            <span>Body</span>
            <textarea
              rows={10}
              value={body}
              onChange={(e) => {
                setBody(e.target.value);
                setConfirmed(false);
              }}
              data-testid="bulk-email-body"
            />
          </label>

          <div className="bulk-email-recipients" data-testid="bulk-email-recipients">
            <strong>Recipients ({revealed.length})</strong>
            <ul>
              {revealed.map((c) => (
                <li key={c.id}>
                  {c.full_name} · <span className="font-num">{c.email}</span>
                </li>
              ))}
            </ul>
          </div>

          <label className="bulk-email-confirm">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => setConfirmed(e.target.checked)}
              data-testid="bulk-email-confirm"
            />
            <span>I reviewed the subject and body and want to open my mail app with these BCC recipients.</span>
          </label>

          <div className="actions">
            <button type="button" onClick={resetAndClose}>
              Cancel
            </button>
            <button
              type="button"
              className="primary"
              disabled={!confirmed || !subject.trim() || !body.trim()}
              onClick={handleOpenMail}
              data-testid="bulk-email-send"
            >
              Open mail app for all
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
