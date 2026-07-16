"use client";

import AboutArchitecture from "../../components/about/AboutArchitecture";
import AppShell from "../../components/layout/AppShell";

export default function AboutPage() {
  return (
    <AppShell
      title="About TeamScout"
      lede="A scroll-through story of two recruiting journeys: multi-signal ranking, hiring-team discovery, MaxSim resume pick, and the constraints that keep the product honest."
    >
      <AboutArchitecture />
    </AppShell>
  );
}
