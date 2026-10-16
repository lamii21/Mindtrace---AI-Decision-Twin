"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { SectionHeading } from "./SectionHeading";
import { fadeIn, viewportOnce } from "@/lib/motion";

const FACTORS = [
  { id: "skill_growth", label: "Skill growth" },
  { id: "financial_security", label: "Financial security" },
  { id: "autonomy", label: "Autonomy" },
  { id: "stability", label: "Stability" },
];

const EVIDENCE = [
  { id: "e1", label: "Declared preference", links: ["skill_growth", "autonomy"] },
  { id: "e2", label: "Observed decision", links: ["financial_security", "stability"] },
  { id: "e3", label: "Elicitation answer", links: ["skill_growth", "financial_security"] },
];

const OUTCOME = { label: "Decision" };

/** Illustrative only - a simplified, representative version of the real
 * decision <- factor <- evidence trace the API actually returns (not live data). */
export function HiddenStructureSection() {
  const [hovered, setHovered] = useState<string | null>(null);

  const isFactorActive = (id: string) =>
    hovered === id || EVIDENCE.some((e) => e.id === hovered && e.links.includes(id));
  const isEvidenceActive = (id: string) => {
    const ev = EVIDENCE.find((e) => e.id === id);
    return hovered === id || (hovered !== null && ev?.links.includes(hovered));
  };

  return (
    <section id="structure" className="relative py-28">
      <div className="mx-auto max-w-6xl px-6 lg:px-10">
        <SectionHeading
          eyebrow="Section 01 — The hidden structure"
          title="A decision can be decomposed"
          description="Evidence supports factors. Factors combine into a score. The score — never the confidence — is the raw signal. Hover any node to trace its path."
        />

        <motion.div
          variants={fadeIn}
          initial="hidden"
          whileInView="visible"
          viewport={viewportOnce}
          className="mt-20 grid grid-cols-1 gap-10 lg:grid-cols-[1fr_1fr_auto] lg:items-center"
        >
          <div className="space-y-3">
            <p className="label-mono mb-4 text-ivory-300/50">Evidence</p>
            {EVIDENCE.map((e) => (
              <button
                key={e.id}
                onMouseEnter={() => setHovered(e.id)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(e.id)}
                onBlur={() => setHovered(null)}
                className={`w-full rounded-xl border px-4 py-3 text-left text-sm transition-all duration-200 ${
                  isEvidenceActive(e.id)
                    ? "border-lavender-400/50 bg-lavender-500/10 text-ivory-100"
                    : "border-white/10 bg-white/[0.02] text-ivory-300/70"
                }`}
              >
                {e.label}
              </button>
            ))}
          </div>

          <div className="space-y-3">
            <p className="label-mono mb-4 text-ivory-300/50">Factors</p>
            {FACTORS.map((f) => (
              <div
                key={f.id}
                className={`rounded-xl border px-4 py-3 text-sm transition-all duration-200 ${
                  isFactorActive(f.id)
                    ? "border-electric-400/50 bg-electric-500/10 text-ivory-100"
                    : "border-white/10 bg-white/[0.02] text-ivory-300/70"
                }`}
              >
                {f.label}
              </div>
            ))}
          </div>

          <div className="flex items-center justify-center lg:justify-start">
            <div className="flex h-28 w-28 flex-col items-center justify-center rounded-full border border-amber-400/40 bg-amber-500/10 text-center">
              <span className="label-mono text-amber-400">Outcome</span>
              <span className="mt-1 text-xs text-ivory-300/60">{OUTCOME.label}</span>
            </div>
          </div>
        </motion.div>

        <p className="mt-10 text-center text-sm text-ivory-300/40">
          Illustrative diagram. A real simulation&apos;s trace reflects your own decision&apos;s
          actual factors and evidence.
        </p>
      </div>
    </section>
  );
}
