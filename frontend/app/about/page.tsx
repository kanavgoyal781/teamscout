"use client";

import AboutArchitecture from "../../components/AboutArchitecture";
import AppShell from "../../components/AppShell";

export default function AboutPage() {
  return (
    <AppShell
      title="About TeamScout"
      lede="What this product is, how ranking and team discovery work, and the architecture decisions behind a two-feature recruiting tool."
    >
      <AboutArchitecture />
    </AppShell>
  );
}
