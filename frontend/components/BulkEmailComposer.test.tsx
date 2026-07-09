import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import BulkEmailComposer from "./BulkEmailComposer";
import type { Contact } from "../lib/types";

const base: Contact = {
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

describe("BulkEmailComposer", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows hint when no revealed emails", () => {
    render(
      <BulkEmailComposer
        contacts={[{ ...base, email_revealed: false, email: null }]}
      />,
    );
    expect(screen.getByTestId("bulk-email-hint")).toBeInTheDocument();
  });

  it("requires template confirm before opening mail", () => {
    const assign = vi.fn();
    // jsdom location is not fully writable; stub via defineProperty
    const original = window.location;
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { ...original, href: "", assign },
    });

    render(<BulkEmailComposer contacts={[base]} roleHint="Data Scientist" />);
    fireEvent.click(screen.getByTestId("bulk-email-open"));
    expect(screen.getByTestId("bulk-email-dialog")).toBeInTheDocument();

    const send = screen.getByTestId("bulk-email-send");
    expect(send).toBeDisabled();

    fireEvent.click(screen.getByTestId("bulk-email-confirm"));
    expect(send).not.toBeDisabled();

    fireEvent.click(send);
    expect(window.location.href).toMatch(/^mailto:\?/);
    expect(window.location.href).toContain("bcc=ada%40example.com");
    expect(decodeURIComponent(window.location.href)).toContain("Ada");

    Object.defineProperty(window, "location", { configurable: true, value: original });
  });
});
