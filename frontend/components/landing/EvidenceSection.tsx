"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./SectionHeading";
import { Card } from "@/components/ui/Card";
import { fadeUp, staggerContainer, viewportOnce } from "@/lib/motion";

const PROVENANCE = [
  {
    id: "declared",
    label: "Declared",
    description: "You stated it directly — a preference, a note, an answer.",
    color: "#6ab8ff",
  },
  {
    id: "observed",
    label: "Observed",
    description: "Drawn from a decision you actually made, not a stated opinion.",
    color: "#ab9aea",
  },
  {
    id: "inferred",
    label: "Inferred",
    description: "The system derived it — always shown as inferred, never as fact.",
    color: "#ffb968",
  },
  {
    id: "uncertain",
    label: "Uncertain",
    description: "Insufficient or conflicting evidence. Named explicitly, not hidden.",
    color: "#ff9d85",
  },
];

export function EvidenceSection() {
  return (
    <section className="relative py-28">
      <div className="mx-auto max-w-6xl px-6 lg:px-10">
        <SectionHeading
          eyebrow="Section 03 — Evidence before conclusions"
          title="Provenance is never collapsed into a single number"
          description="Every belief MINDTRACE holds about your preferences traces back to real evidence — and that evidence is always labeled by what kind of claim it actually is."
        />

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={viewportOnce}
          className="mt-16 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4"
        >
          {PROVENANCE.map((p) => (
            <motion.div key={p.id} variants={fadeUp}>
              <Card className="h-full p-6">
                <span
                  className="label-mono inline-flex items-center gap-2 rounded-full px-3 py-1"
                  style={{ background: `${p.color}22`, color: p.color }}
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: p.color }} />
                  {p.label}
                </span>
                <p className="mt-4 text-sm leading-relaxed text-ivory-300/70">{p.description}</p>
              </Card>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
