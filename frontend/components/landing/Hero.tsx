"use client";

import { motion } from "framer-motion";
import { ButtonLink } from "@/components/ui/Button";
import { LazyObservatory } from "@/components/scene/LazyObservatory";
import { EASE } from "@/lib/motion";

export function Hero() {
  return (
    <section className="relative flex min-h-[100vh] flex-col overflow-hidden bg-atmosphere">
      <div className="pointer-events-none absolute inset-0 bg-radial-fade from-lavender-600/10 via-transparent to-transparent" />

      <div className="relative z-10 mx-auto flex max-w-7xl flex-1 flex-col px-6 pt-28 lg:px-10">
        <div className="grid flex-1 grid-cols-1 items-center gap-12 lg:grid-cols-2">
          <div>
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, ease: EASE }}
              className="label-mono mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-lavender-300"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-lavender-400" />
              An auditable AI decision twin
            </motion.div>

            <motion.h1
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.1, ease: EASE }}
              className="font-display text-5xl italic leading-[1.05] text-ivory-100 sm:text-6xl lg:text-[4.2rem]"
            >
              Every decision has a{" "}
              <span className="text-gradient-lavender not-italic">hidden structure</span>.
            </motion.h1>

            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.25, ease: EASE }}
              className="mt-6 max-w-lg text-lg leading-relaxed text-ivory-300/80"
            >
              MINDTRACE simulates how you weigh trade-offs — across four mathematically
              distinct weightings of your own preferences, with computed confidence,
              visible uncertainty, and a full evidence trace. Not a chatbot. Not a
              personality quiz. A window into the architecture of a decision.
            </motion.p>

            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.4, ease: EASE }}
              className="mt-10 flex flex-wrap items-center gap-4"
            >
              <ButtonLink size="lg" href="/register">
                Explore a decision
              </ButtonLink>
              <ButtonLink variant="secondary" size="lg" href="#structure">
                Discover how it works
              </ButtonLink>
            </motion.div>
          </div>

          <motion.div
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1.1, delay: 0.3, ease: EASE }}
            className="relative aspect-square w-full lg:aspect-[4/5]"
            aria-hidden
          >
            <LazyObservatory />
          </motion.div>
        </div>
      </div>

      <div className="relative z-10 mx-auto w-full max-w-7xl px-6 pb-10 lg:px-10">
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 1, delay: 1 }}
          className="label-mono flex flex-wrap items-center gap-x-8 gap-y-2 text-ivory-300/40"
        >
          <span>Deterministic decision core</span>
          <span>·</span>
          <span>LLM as structured extractor only</span>
          <span>·</span>
          <span>Confidence ≠ decision score</span>
          <span>·</span>
          <span>Every result traceable</span>
        </motion.div>
      </div>
    </section>
  );
}
