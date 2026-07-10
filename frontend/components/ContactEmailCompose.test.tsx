import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Contact } from "../lib/types";
import ContactEmailCompose from "./ContactEmailCompose";

const generateOutreachDraft = vi.fn();
const postFeedback = vi.fn();

vi.mock("../lib/api", () => ({
  generateOutreachDraft: (...args: unknown[]) => generateOutreachDraft(...args),
  formatApiError: (e: unknown) => (e instanceof Error ? e.message : "err"),
  postFeedback: (...args: unknown[]) => postFeedback(...args),
}));

vi.mock("./FeedbackButtons", () => ({
  trackImplicitFeedback: (payload: unknown) => {
    // mirror real fire-and-forget shape for assertions via postFeedback mock if needed
    const p = payload as {
      kind: string;
      targetType: string;
      targetId: string;
      secondaryId?: string;
    };
    void postFeedback({
      kind: p.kind,
      target_type: p.targetType,
      target_id: p.targetId,
      secondary_id: p.secondaryId ?? null,
    });
  },
}));

const contact: Contact = {
  id: "c1",
  full_name: "Ada Lovelace",
  title: "Engineering Manager",
  company: "Analytical Engines",
  team: "Hiring",
  seniority: "senior",
  sumble_person_id: "s1",
  email_revealed: true,
  email: "ada@example.com",
};

describe("ContactEmailCompose", () => {
  beforeEach(() => {
    generateOutreachDraft.mockReset();
    postFeedback.mockReset();
    generateOutreachDraft.mockResolvedValue({
      contact_id: "c1",
      subject: "Draft subject",
      body: "Draft body about the role.",
      email: "ada@example.com",
    });
    postFeedback.mockResolvedValue({ id: "f1", kind: "compose_opened", target_type: "contact", target_id: "c1" });
    vi.stubGlobal("open", vi.fn());
  });

  it("renders nothing without revealed email", () => {
    const { container } = render(
      <ContactEmailCompose contact={{ ...contact, email_revealed: false, email: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("opens modal, keeps edits in Gmail href, logs compose_opened", async () => {
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, href: "" },
    });

    render(<ContactEmailCompose contact={contact} />);
    fireEvent.click(screen.getByTestId("email-btn-c1"));

    await waitFor(() => {
      expect(screen.getByTestId("compose-dialog-c1")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("compose-subject-c1")).toHaveValue("Draft subject");
    });

    fireEvent.change(screen.getByTestId("compose-subject-c1"), {
      target: { value: "Edited subject & more" },
    });
    fireEvent.change(screen.getByTestId("compose-body-c1"), {
      target: { value: "Edited body line" },
    });

    fireEvent.click(screen.getByTestId("compose-open-gmail-c1"));

    await waitFor(() => {
      expect(window.open).toHaveBeenCalled();
    });
    const href = (window.open as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(href).toContain("https://mail.google.com/mail/?");
    expect(href).toContain("to=ada%40example.com");
    expect(href).toContain("su=Edited%20subject");
    expect(href).toContain("%26"); // encoded &
    expect(href).toContain("body=Edited%20body%20line");

    await waitFor(() => {
      expect(postFeedback).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "compose_opened",
          target_type: "contact",
          target_id: "c1",
          secondary_id: "gmail",
        }),
      );
    });

    Object.defineProperty(window, "location", { configurable: true, value: original });
  });

  it("encodes Outlook deep-link from editor contents", async () => {
    render(<ContactEmailCompose contact={contact} />);
    fireEvent.click(screen.getByTestId("email-menu-c1"));
    fireEvent.click(screen.getByTestId("email-outlook-c1"));

    await waitFor(() => {
      expect(screen.getByTestId("compose-body-c1")).toHaveValue("Draft body about the role.");
    });

    fireEvent.change(screen.getByTestId("compose-subject-c1"), {
      target: { value: "Outlook subj" },
    });
    fireEvent.click(screen.getByTestId("compose-open-outlook-c1"));

    await waitFor(() => expect(window.open).toHaveBeenCalled());
    const href = (window.open as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(href).toContain("https://outlook.office.com/mail/deeplink/compose?");
    expect(href).toContain("to=ada%40example.com");
    expect(href).toContain("subject=Outlook%20subj");
    expect(href).toContain("body=Draft%20body");
  });

  it("skip blank clears editor before open", async () => {
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, href: "" },
    });

    render(<ContactEmailCompose contact={contact} />);
    fireEvent.click(screen.getByTestId("email-btn-c1"));
    await waitFor(() => {
      expect(screen.getByTestId("compose-subject-c1")).toHaveValue("Draft subject");
    });

    fireEvent.click(screen.getByTestId("compose-skip-blank-c1"));
    expect(screen.getByTestId("compose-subject-c1")).toHaveValue("");
    expect(screen.getByTestId("compose-body-c1")).toHaveValue("");

    fireEvent.click(screen.getByTestId("compose-open-mailto-c1"));
    expect(window.location.href.startsWith("mailto:ada@example.com?")).toBe(true);
    expect(window.location.href).toMatch(/subject=&|subject=$|subject=(?:&|$)/);

    Object.defineProperty(window, "location", { configurable: true, value: original });
  });
});
