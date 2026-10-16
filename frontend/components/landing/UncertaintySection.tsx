"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./SectionHeading";
import { Card } from "@/components/ui/Card";
import { fadeUp, staggerContainer, viewportOnce } from "@/lib/motion";

const REASONS = [
  {
    code: "score_in_band",
    description: "The score itself sits too close to the decision boundary to call.",
  },
  {
    code: "insufficient_coverage",
    description: "Too few factors were extracted from the scenario to form a judgment.",
  },
  {
    code: "low_model_confidence",
    description: "The score is decisive, but the evidence behind it is too thin to trust.",
  },
  {
    code: "ensemble_disagreement",
    description: "The four perspectives disagree enough that no single recommendation holds.",
  },
];

export function UncertaintySection() {
  return (
    <section className="relative py-28">
      <div className="mx-auto max-w-6xl px-6 lg:px-10">
        <SectionHeading
          eyebrow="Section 04 — Uncertainty is information"
          title={
            <>
              Confidence is <span className="text-gradient-lavender">not</span> the decision
              score
            </>
          }
          description="A decision's score (S) and the model's confidence (C) are computed independently and never conflated. Low confidence is a real, named finding — never a cosmetic percentage."
        />

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={viewportOnce}
          className="mt-16 grid grid-cols-1 gap-5 lg:grid-cols-2"
        >
          {REASONS.map((r) => (
            <motion.div key={r.code} variants={fadeUp}>
              <Card className="flex items-start gap-4 p-6">
                <span className="label-mono mt-0.5 shrink-0 rounded-full bg-amber-500/15 px-3 py-1 text-amber-400 ring-1 ring-amber-500/30">
                  UNCERTAIN
                </span>
                <div>
                  <p className="font-mono text-sm text-ivory-100">{r.code}</p>
                  <p className="mt-1 text-sm leading-relaxed text-ivory-300/70">
                    {r.description}
                  </p>
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
