import { describe, expect, it } from "vitest";

import {
  MAILTO_MAX_LENGTH,
  buildComposeUrl,
  buildGmailUrl,
  buildMailtoUrl,
  buildOutlookUrl,
} from "./composeLinks";

const base = {
  to: "ada@example.com",
  subject: "Hello Ada",
  body: "Quick note about the role.",
};

describe("composeLinks", () => {
  it("builds mailto with encoded subject and body", () => {
    const { href, truncated } = buildMailtoUrl(base);
    expect(truncated).toBe(false);
    expect(href.startsWith("mailto:ada@example.com?")).toBe(true);
    expect(href).toContain("subject=Hello%20Ada");
    expect(href).toContain("body=Quick%20note");
    expect(href).not.toContain(" ");
  });

  it("encodes special characters", () => {
    const { href } = buildMailtoUrl({
      to: "a+b@example.com",
      subject: "Q&A: 50% off?",
      body: "Line1\nLine2 & more",
    });
    expect(href).toContain("subject=");
    expect(decodeURIComponent(href)).toContain("Q&A");
    expect(href.toLowerCase()).toContain("%26"); // &
  });

  it("caps mailto length with ellipsis truncation", () => {
    const longBody = "word ".repeat(2000);
    const { href, truncated, fullText } = buildMailtoUrl({
      to: "ada@example.com",
      subject: "Long draft",
      body: longBody,
    });
    expect(truncated).toBe(true);
    expect(href.length).toBeLessThanOrEqual(MAILTO_MAX_LENGTH);
    expect(decodeURIComponent(href)).toContain("…");
    expect(fullText).toContain(longBody.slice(0, 20));
  });

  it("builds Gmail deep-link with to/su/body", () => {
    const href = buildGmailUrl(base);
    expect(href.startsWith("https://mail.google.com/mail/?")).toBe(true);
    expect(href).toContain("view=cm");
    expect(href).toContain("fs=1");
    expect(href).toContain("to=ada%40example.com");
    expect(href).toContain("su=Hello%20Ada");
    expect(href).toContain("body=Quick%20note");
  });

  it("builds Outlook deep-link with to/subject/body", () => {
    const href = buildOutlookUrl(base);
    expect(href.startsWith("https://outlook.office.com/mail/deeplink/compose?")).toBe(true);
    expect(href).toContain("to=ada%40example.com");
    expect(href).toContain("subject=Hello%20Ada");
    expect(href).toContain("body=Quick%20note");
  });

  it("buildComposeUrl dispatches clients", () => {
    expect(buildComposeUrl("gmail", base).href).toContain("mail.google.com");
    expect(buildComposeUrl("outlook", base).href).toContain("outlook.office.com");
    expect(buildComposeUrl("mailto", base).href.startsWith("mailto:")).toBe(true);
  });
});
