"use client";

import { motion } from "framer-motion";
import { fadeUp, viewportOnce } from "@/lib/motion";

export function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: React.ReactNode;
  description?: string;
}) {
  return (
    <motion.div
      variants={fadeUp}
      initial="hidden"
      whileInView="visible"
      viewport={viewportOnce}
      className="mx-auto max-w-2xl text-center"
    >
      <span className="label-mono text-lavender-400">{eyebrow}</span>
      <h2 className="mt-4 font-display text-4xl leading-[1.1] text-ivory-100 sm:text-5xl">
        {title}
      </h2>
      {description && (
        <p className="mt-5 text-balance text-lg leading-relaxed text-ivory-300/75">
          {description}
        </p>
      )}
    </motion.div>
  );
}
