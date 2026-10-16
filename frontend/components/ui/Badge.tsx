import clsx from "clsx";
import type { DecisionLabel } from "@/lib/api/types";

const LABEL_STYLES: Record<DecisionLabel, string> = {
  ACCEPT: "bg-electric-500/15 text-electric-300 ring-1 ring-electric-500/30",
  REJECT: "bg-coral-500/15 text-coral-400 ring-1 ring-coral-500/30",
  UNCERTAIN: "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30",
};

export function DecisionLabelBadge({ label }: { label: DecisionLabel }) {
  return (
    <span
      className={clsx(
        "label-mono inline-flex items-center rounded-full px-3 py-1 font-semibold",
        LABEL_STYLES[label],
      )}
    >
      {label}
    </span>
  );
}

export function Badge({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={clsx(
        "label-mono inline-flex items-center rounded-full bg-white/[0.06] px-3 py-1 text-ivory-300 ring-1 ring-white/10",
        className,
      )}
    >
      {children}
    </span>
  );
}
