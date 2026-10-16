"use client";

import { motion } from "framer-motion";
import { SectionHeading } from "./SectionHeading";
import { Card } from "@/components/ui/Card";
import { TWINS, TWIN_LAMBDA } from "@/lib/twins";
import { fadeUp, staggerContainer, viewportOnce } from "@/lib/motion";

export function PerspectivesSection() {
  return (
    <section className="relative py-28">
      <div className="mx-auto max-w-6xl px-6 lg:px-10">
        <SectionHeading
          eyebrow="Section 02 — Four perspectives, one decision"
          title="Four weightings of the same you"
          description={`Each twin is a fixed, deterministic re-weighting of your own preferences — never a separate prompt, personality, or LLM agent. w_t = renorm(w* · (1 + λ · shift_t)), with λ = ${TWIN_LAMBDA}.`}
        />

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={viewportOnce}
          className="mt-16 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4"
        >
          {TWINS.map((twin) => (
            <motion.div key={twin.id} variants={fadeUp}>
              <Card
                className="h-full p-6"
                style={{ boxShadow: `0 0 0 1px ${twin.accentSoft} inset` }}
              >
                <div
                  className="mb-4 h-10 w-10 rounded-full"
                  style={{ background: twin.accentSoft, boxShadow: `0 0 24px ${twin.accentSoft}` }}
                />
                <h3 className="font-display text-xl text-ivory-100">{twin.label}</h3>
                <p className="mt-2 text-sm leading-relaxed text-ivory-300/70">{twin.tagline}</p>

                <div className="mt-5 space-y-2 text-xs">
                  <div>
                    <span className="label-mono text-ivory-300/40">Up-weights</span>
                    <p className="mt-1 font-mono text-ivory-200/80">
                      {twin.up.length ? twin.up.join(", ") : "—"}
                    </p>
                  </div>
                  <div>
                    <span className="label-mono text-ivory-300/40">Down-weights</span>
                    <p className="mt-1 font-mono text-ivory-200/80">
                      {twin.down.length ? twin.down.join(", ") : "—"}
                    </p>
                  </div>
                </div>
              </Card>
            </motion.div>
          ))}
        </motion.div>

        <p className="mt-10 text-center text-sm text-ivory-300/40">
          Source of truth: <code className="font-mono">schema/twins.yaml</code> (ADR-007). A fifth
          result — your own, untransformed weighting — is always included alongside these four.
        </p>
      </div>
    </section>
  );
}
