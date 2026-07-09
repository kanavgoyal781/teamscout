"use client";

import AboutArchitecture from "../../components/AboutArchitecture";
import AppShell from "../../components/AppShell";

export default function AboutPage() {
  return (
    <AppShell
      title="About TeamScout"
      lede="An engineering essay on a two-feature recruiting tool: how multi-signal ranking works, why the honesty layer fails loud, and the constraints we kept."
    >
      <AboutArchitecture />
    </AppShell>
  );
}
