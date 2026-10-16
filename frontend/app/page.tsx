import { LandingNav } from "@/components/landing/LandingNav";
import { Hero } from "@/components/landing/Hero";
import { HiddenStructureSection } from "@/components/landing/HiddenStructureSection";
import { PerspectivesSection } from "@/components/landing/PerspectivesSection";
import { EvidenceSection } from "@/components/landing/EvidenceSection";
import { UncertaintySection } from "@/components/landing/UncertaintySection";
import { TraceSection } from "@/components/landing/TraceSection";
import { FinalCta } from "@/components/landing/FinalCta";

export default function LandingPage() {
  return (
    <main className="relative">
      <LandingNav />
      <Hero />
      <HiddenStructureSection />
      <PerspectivesSection />
      <EvidenceSection />
      <UncertaintySection />
      <TraceSection />
      <FinalCta />
      <footer className="border-t border-white/5 py-10 text-center">
        <p className="label-mono text-ivory-300/30">MINDTRACE — an auditable AI decision twin</p>
      </footer>
    </main>
  );
}
