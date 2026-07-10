"use client";

import { Copy, Check } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import type { Contact } from "../lib/types";
import type { JobTeamState } from "../hooks/useJobTeam";
import BulkEmailComposer from "./BulkEmailComposer";
import ContactEmailCompose from "./ContactEmailCompose";
import EmptyState from "./ui/EmptyState";
import { ContactSkeleton } from "./ui/Skeleton";

type TeamDiscoveryPanelProps = {
  teamState: JobTeamState;
  onExtract: () => void;
  onFindTeam: () => void;
  onRevealEmail: (contact: Contact, confirm: boolean) => void;
  /** Optional role title for bulk email {{role}} token */
  roleHint?: string;
};

export default function TeamDiscoveryPanel({
  teamState,
  onExtract,
  onFindTeam,
  onRevealEmail,
  roleHint = "",
}: TeamDiscoveryPanelProps) {
  const pendingCost = teamState.pendingReveal;
  const [copiedId, setCopiedId] = useState<string | null>(null);

  async function copyEmail(contact: Contact) {
    if (!contact.email) return;
    try {
      await navigator.clipboard.writeText(contact.email);
      setCopiedId(contact.id);
      toast.success("Email copied");
      window.setTimeout(() => setCopiedId(null), 1500);
    } catch {
      toast.error("Could not copy email");
    }
  }

  return (
    <div className="team-panel" data-testid="team-panel">
      <div className="actions">
        <button
          type="button"
          onClick={onExtract}
          disabled={teamState.extracting || teamState.finding || teamState.hydrating}
        >
          {teamState.extracting
            ? "Extracting team…"
            : teamState.hydrating
              ? "Loading team…"
              : "Extract team from description"}
        </button>
      </div>

      {teamState.extracting || teamState.hydrating ? (
        <div style={{ marginTop: 12 }}>
          <ContactSkeleton />
        </div>
      ) : null}

      {teamState.extraction ? (
        <div className="team-extraction" data-testid="extraction-card">
          <p className="meta">Hiring-team signals from the job description — confirm before we look up people.</p>
          <ul className="breakdown-list" style={{ margin: "8px 0", paddingLeft: "1.1rem", color: "var(--text-secondary)" }}>
            <li>
              <strong>Team:</strong> {teamState.extraction.team_name || "—"}
            </li>
            <li>
              <strong>Department:</strong> {teamState.extraction.department || "—"}
            </li>
            <li>
              <strong>Likely hiring titles:</strong>{" "}
              {teamState.extraction.likely_hiring_titles.length > 0
                ? teamState.extraction.likely_hiring_titles.join(", ")
                : "—"}
            </li>
          </ul>
          <p className="meta font-num">
            Est. max for role match: ~30 credits · fallback people search: ~20 credits before
            lookup spend.
          </p>
          <div className="actions">
            <button
              type="button"
              className="primary"
              onClick={onFindTeam}
              disabled={teamState.finding || !teamState.extractionId}
              data-testid="confirm-find-team" data-tour="confirm-find-team" data-tour-credit-gate="true"
            >
              {teamState.finding ? "Finding hiring team…" : "Confirm & find hiring team"}
            </button>
          </div>
        </div>
      ) : null}

      {teamState.finding ? (
        <div style={{ marginTop: 12 }}>
          <ContactSkeleton />
          <ContactSkeleton />
        </div>
      ) : null}

      {teamState.contacts.length > 0 ? (
        <div className="contact-list" data-testid="contact-list">
          <div className="contact-list-head">
            <h4>People</h4>
            {teamState.searchPath ? (
              <span className="path-badge" data-testid="search-path">
                {teamState.searchPath}
              </span>
            ) : null}
          </div>
          <BulkEmailComposer contacts={teamState.contacts} roleHint={roleHint} />
          {teamState.contacts.map((contact) => {
            const awaitingConfirm = pendingCost[contact.id] != null;
            const revealing = teamState.revealLoading[contact.id];
            return (
              <div key={contact.id} className="contact-card">
                <div>
                  <strong>{contact.full_name}</strong>
                  {contact.seniority ? (
                    <span className="seniority-badge">{contact.seniority}</span>
                  ) : null}
                  <p className="meta" style={{ margin: "4px 0 0" }}>
                    {contact.title ?? "Title unknown"}
                    {contact.team ? ` · ${contact.team}` : ""}
                  </p>
                  {contact.email_revealed && contact.email ? (
                    <p className="contact-email">
                      <span className="font-num">{contact.email}</span>
                      <button
                        type="button"
                        className="copy-btn"
                        onClick={() => copyEmail(contact)}
                        aria-label={`Copy email for ${contact.full_name}`}
                      >
                        {copiedId === contact.id ? <Check size={12} /> : <Copy size={12} />}
                        {copiedId === contact.id ? "Copied" : "Copy"}
                      </button>
                    </p>
                  ) : null}
                </div>
                {!contact.email_revealed ? (
                  <div className="actions">
                    {!awaitingConfirm ? (
                      <button
                        type="button"
                        onClick={() => onRevealEmail(contact, false)}
                        disabled={revealing}
                      >
                        {revealing ? "Checking…" : "Reveal email — preview cost"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="primary"
                        onClick={() => onRevealEmail(contact, true)}
                        disabled={revealing}
                      >
                        {revealing ? (
                          "Revealing…"
                        ) : (
                          <>
                            Confirm reveal —{" "}
                            <span className="font-num">{pendingCost[contact.id]}</span> credits
                          </>
                        )}
                      </button>
                    )}
                  </div>
                ) : (
                  <ContactEmailCompose contact={contact} />
                )}
              </div>
            );
          })}
        </div>
      ) : teamState.teamSearched && !teamState.finding ? (
        <div style={{ marginTop: 12 }}>
          <EmptyState instruction="No people matched — try broadening team or title filters, then search again." />
        </div>
      ) : teamState.extraction && !teamState.finding ? (
        <p className="meta empty-hint" style={{ marginTop: 12 }}>
          No contacts yet. Confirm the extraction above to find hiring managers for this role.
        </p>
      ) : null}
    </div>
  );
}
