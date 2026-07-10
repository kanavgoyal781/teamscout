"use client";

import { ChevronDown, Copy, Mail, X } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";

import { formatApiError, generateOutreachDraft } from "../lib/api";
import {
  buildComposeUrl,
  type ComposeClient,
} from "../lib/composeLinks";
import type { Contact } from "../lib/types";
import { trackImplicitFeedback } from "./FeedbackButtons";

const MAX_DRAFT_GENERATIONS = 3;

type ContactEmailComposeProps = {
  contact: Contact;
};

type ModalState = {
  open: boolean;
  pendingClient: ComposeClient;
};

export default function ContactEmailCompose({ contact }: ContactEmailComposeProps) {
  const email = contact.email_revealed && contact.email?.includes("@") ? contact.email : null;
  const menuId = useId();
  const [menuOpen, setMenuOpen] = useState(false);
  const [modal, setModal] = useState<ModalState>({ open: false, pendingClient: "mailto" });
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [loadingDraft, setLoadingDraft] = useState(false);
  const [genCount, setGenCount] = useState(0);
  const [mailtoTruncated, setMailtoTruncated] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    if (!menuOpen) return;
    function onDoc(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  if (!email) return null;

  async function loadDraft(resetCount: boolean) {
    setLoadingDraft(true);
    try {
      const draft = await generateOutreachDraft(contact.id);
      setSubject(draft.subject);
      setBody(draft.body);
      setGenCount((c) => (resetCount ? 1 : c + 1));
      setMailtoTruncated(false);
    } catch (err) {
      toast.error(formatApiError(err));
      // Still open modal so user can skip to blank compose.
      if (resetCount) {
        setSubject("");
        setBody("");
        setGenCount(0);
      }
    } finally {
      setLoadingDraft(false);
    }
  }

  function openModal(client: ComposeClient) {
    closeMenu();
    setModal({ open: true, pendingClient: client });
    setSubject("");
    setBody("");
    setGenCount(0);
    setMailtoTruncated(false);
    void loadDraft(true);
  }

  function closeModal() {
    setModal({ open: false, pendingClient: "mailto" });
    setMailtoTruncated(false);
  }

  async function handleRegenerate() {
    if (genCount >= MAX_DRAFT_GENERATIONS || loadingDraft) return;
    await loadDraft(false);
  }

  function skipBlank() {
    setSubject("");
    setBody("");
    setMailtoTruncated(false);
  }

  function openCompose(client: ComposeClient) {
    if (!email) return;
    const draft = { to: email, subject, body };
    const built = buildComposeUrl(client, draft);
    setMailtoTruncated(client === "mailto" && built.truncated);

    trackImplicitFeedback({
      kind: "compose_opened",
      targetType: "contact",
      targetId: contact.id,
      secondaryId: client,
    });

    if (client === "mailto") {
      if (built.truncated) {
        toast.message("Mailto link truncated — copy full draft if needed", {
          description: "Some mail clients cap URL length.",
        });
      }
      window.location.href = built.href;
      toast.success("Opening your mail app…");
    } else {
      window.open(built.href, "_blank", "noopener,noreferrer");
      toast.success(client === "gmail" ? "Opening Gmail…" : "Opening Outlook…");
    }
  }

  function copyEmail() {
    closeMenu();
    if (!email) {
      toast.error("No email revealed yet");
      return;
    }
    void navigator.clipboard.writeText(email).then(
      () => toast.success("Email address copied"),
      () => toast.error("Could not copy email"),
    );
  }

  function copyFullDraft() {
    const text = `Subject: ${subject}\n\n${body}`;
    void navigator.clipboard.writeText(text).then(
      () => toast.success("Full draft copied"),
      () => toast.error("Could not copy draft"),
    );
  }

  return (
    <div className="contact-email-compose" data-testid={`contact-email-compose-${contact.id}`}>
      <div className="email-split" ref={menuRef}>
        <button
          type="button"
          className="primary email-split-main"
          data-testid={`email-btn-${contact.id}`}
          onClick={() => openModal("mailto")}
        >
          <Mail size={14} aria-hidden /> Email
        </button>
        <button
          type="button"
          className="primary email-split-caret"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          aria-controls={menuId}
          data-testid={`email-menu-${contact.id}`}
          onClick={() => setMenuOpen((o) => !o)}
        >
          <ChevronDown size={14} aria-hidden />
          <span className="sr-only">More email options</span>
        </button>
        {menuOpen ? (
          <ul className="email-split-menu" role="menu" id={menuId} data-testid={`email-dropdown-${contact.id}`}>
            <li role="none">
              <button
                type="button"
                role="menuitem"
                data-testid={`email-gmail-${contact.id}`}
                onClick={() => openModal("gmail")}
              >
                Open in Gmail
              </button>
            </li>
            <li role="none">
              <button
                type="button"
                role="menuitem"
                data-testid={`email-outlook-${contact.id}`}
                onClick={() => openModal("outlook")}
              >
                Open in Outlook
              </button>
            </li>
            <li role="none">
              <button
                type="button"
                role="menuitem"
                data-testid={`email-copy-addr-${contact.id}`}
                onClick={copyEmail}
              >
                <Copy size={12} aria-hidden /> Copy email address
              </button>
            </li>
          </ul>
        ) : null}
      </div>

      {modal.open ? (
        <div
          className="bulk-email-modal contact-compose-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby={`compose-title-${contact.id}`}
          data-testid={`compose-dialog-${contact.id}`}
        >
          <div className="bulk-email-modal-head">
            <h4 id={`compose-title-${contact.id}`}>Email draft — {contact.full_name}</h4>
            <button type="button" className="ghost" onClick={closeModal} aria-label="Close">
              <X size={16} />
            </button>
          </div>
          <p className="meta">
            Review or edit before opening your mail client. TeamScout does not send mail.
            {email ? (
              <>
                {" "}
                To: <span className="font-num">{email}</span>
              </>
            ) : null}
          </p>

          {loadingDraft ? <p className="meta">Generating draft…</p> : null}

          <label className="bulk-email-field">
            <span>Subject</span>
            <input
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              data-testid={`compose-subject-${contact.id}`}
              disabled={loadingDraft}
            />
          </label>
          <label className="bulk-email-field">
            <span>Body</span>
            <textarea
              rows={10}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              data-testid={`compose-body-${contact.id}`}
              disabled={loadingDraft}
            />
          </label>

          <div className="actions compose-modal-actions">
            <button
              type="button"
              onClick={() => void handleRegenerate()}
              disabled={loadingDraft || genCount >= MAX_DRAFT_GENERATIONS}
              data-testid={`compose-regenerate-${contact.id}`}
            >
              Regenerate{genCount > 0 ? ` (${genCount}/${MAX_DRAFT_GENERATIONS})` : ""}
            </button>
            <button type="button" onClick={skipBlank} data-testid={`compose-skip-blank-${contact.id}`}>
              Skip to blank
            </button>
            <button type="button" onClick={copyFullDraft} data-testid={`compose-copy-draft-${contact.id}`}>
              Copy full draft
            </button>
          </div>

          {mailtoTruncated ? (
            <p className="meta compose-trunc-hint" data-testid={`compose-trunc-${contact.id}`}>
              Mailto URL was truncated to fit client limits. Use <strong>Copy full draft</strong> for
              the complete text.
            </p>
          ) : null}

          <div className="actions compose-open-actions">
            <button type="button" onClick={closeModal}>
              Cancel
            </button>
            <button
              type="button"
              className="primary"
              data-testid={`compose-open-mailto-${contact.id}`}
              onClick={() => openCompose("mailto")}
              disabled={loadingDraft}
            >
              Open mail app
            </button>
            <button
              type="button"
              data-testid={`compose-open-gmail-${contact.id}`}
              onClick={() => openCompose("gmail")}
              disabled={loadingDraft}
            >
              Open in Gmail
            </button>
            <button
              type="button"
              data-testid={`compose-open-outlook-${contact.id}`}
              onClick={() => openCompose("outlook")}
              disabled={loadingDraft}
            >
              Open in Outlook
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
