"use client";

import type { Contact } from "../lib/api";
import type { JobTeamState } from "../hooks/useJobTeam";

type TeamDiscoveryPanelProps = {
  teamState: JobTeamState;
  onExtract: () => void;
  onFindTeam: () => void;
  onRevealEmail: (contact: Contact, confirm: boolean) => void;
};

export default function TeamDiscoveryPanel({
  teamState,
  onExtract,
  onFindTeam,
  onRevealEmail,
}: TeamDiscoveryPanelProps) {
  const pendingCost = teamState.pendingReveal;

  return (
    <div className="team-panel">
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

      {teamState.extraction ? (
        <div className="team-extraction">
          <p className="meta">LLM-extracted team signals — confirm before Sumble lookup.</p>
          <ul className="breakdown-list">
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
          <div className="actions">
            <button
              type="button"
              className="primary"
              onClick={onFindTeam}
              disabled={teamState.finding || !teamState.extractionId}
            >
              {teamState.finding ? "Searching Sumble…" : "Confirm & search Sumble"}
            </button>
          </div>
        </div>
      ) : null}

      {teamState.contacts.length > 0 ? (
        <div className="contact-list">
          <h4>People</h4>
          {teamState.contacts.map((contact) => {
            const awaitingConfirm = pendingCost[contact.id] != null;
            const revealing = teamState.revealLoading[contact.id];
            return (
              <div key={contact.id} className="contact-card">
                <div>
                  <strong>{contact.full_name}</strong>
                  <p className="meta">
                    {contact.title ?? "Title unknown"}
                    {contact.team ? ` · ${contact.team}` : ""}
                    {contact.seniority ? ` · ${contact.seniority}` : ""}
                  </p>
                  {contact.email_revealed && contact.email ? (
                    <p className="contact-email">{contact.email}</p>
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
                        {revealing
                          ? "Revealing…"
                          : `Confirm reveal — ${pendingCost[contact.id]} credits`}
                      </button>
                    )}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : teamState.teamSearched && !teamState.finding ? (
        <p className="meta empty-hint">
          No people matched — try broadening team or title filters, then search again.
        </p>
      ) : teamState.extraction && !teamState.finding ? (
        <p className="meta empty-hint">
          No contacts yet. Confirm the extraction above to search Sumble for hiring managers.
        </p>
      ) : null}

    </div>
  );
}