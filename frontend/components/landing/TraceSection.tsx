"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./SectionHeading";
import { fadeUp, viewportOnce } from "@/lib/motion";

const STEPS = [
  { label: "Decision created", detail: "Your context and options, recorded." },
  { label: "Factors extracted", detail: "An LLM extracts structured factors — it never decides." },
  { label: "Four perspectives simulated", detail: "The same deterministic engine, four weightings." },
  { label: "Synthesis & confidence computed", detail: "A weight-of-evidence vote; confidence scored independently." },
  { label: "Evidence chain recorded", detail: "Every contributing factor stays inspectable after the fact." },
];

export function TraceSection() {
  return (
    <section className="relative py-28">
      <div className="mx-auto max-w-4xl px-6 lg:px-10">
        <SectionHeading
          eyebrow="Section 05 — Trace every decision"
          title="Nothing happens off the record"
          description="Every simulation you run is persisted and inspectable: the factors behind it, the per-twin results, the synthesis vote, and the confidence inputs that produced it."
        />

        <div className="mt-16 space-y-0">
          {STEPS.map((step, i) => (
            <motion.div
              key={step.label}
              variants={fadeUp}
              initial="hidden"
              whileInView="visible"
              viewport={viewportOnce}
              transition={{ delay: i * 0.05 }}
              className="relative flex gap-6 pb-10 last:pb-0"
            >
              <div className="flex flex-col items-center">
                <span className="label-mono flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-lavender-400/40 text-lavender-300">
                  {i + 1}
                </span>
                {i < STEPS.length - 1 && (
                  <span className="mt-2 w-px flex-1 bg-gradient-to-b from-lavender-400/30 to-transparent" />
                )}
              </div>
              <div className="pb-2">
                <p className="font-display text-lg text-ivory-100">{step.label}</p>
                <p className="mt-1 text-sm leading-relaxed text-ivory-300/70">{step.detail}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
