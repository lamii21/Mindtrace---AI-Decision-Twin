"use client";

import { motion } from "framer-motion";
import { ButtonLink } from "@/components/ui/Button";
import { fadeUp, viewportOnce } from "@/lib/motion";

export function FinalCta() {
  return (
    <section className="relative py-32">
      <div className="pointer-events-none absolute inset-0 bg-radial-fade from-electric-600/10 via-transparent to-transparent" />
      <motion.div
        variants={fadeUp}
        initial="hidden"
        whileInView="visible"
        viewport={viewportOnce}
        className="relative mx-auto max-w-3xl px-6 text-center lg:px-10"
      >
        <h2 className="font-display text-4xl italic text-ivory-100 sm:text-5xl">
          Bring your own decision.
        </h2>
        <p className="mt-5 text-lg text-ivory-300/75">
          Create a decision, run a simulation, and see your four perspectives — with real
          confidence, real uncertainty, and a real evidence trace.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <ButtonLink size="lg" href="/register">
            Start a simulation
          </ButtonLink>
          <ButtonLink variant="ghost" size="lg" href="/login">
            I already have an account
          </ButtonLink>
        </div>
      </motion.div>
    </section>
  );
}
