"use client";

import { useMemo, useState } from "react";
import clsx from "clsx";
import { LazyObservatory } from "@/components/scene/LazyObservatory";
import { Card } from "@/components/ui/Card";
import { DecisionLabelBadge } from "@/components/ui/Badge";
import { twinById } from "@/lib/twins";
import type { SynthesisOut, TwinResultOut } from "@/lib/api/types";

export function TwinComparison({
  perTwin,
  synthesis,
}: {
  perTwin: TwinResultOut[];
  synthesis: SynthesisOut | null;
}) {
  const [activeTwinId, setActiveTwinId] = useState<string>(perTwin[0]?.twin ?? "base");

  const scores = useMemo(() => {
    const out: Record<string, number> = {};
    for (const t of perTwin) out[t.twin] = t.score;
    return out;
  }, [perTwin]);

  const active = perTwin.find((t) => t.twin === activeTwinId);
  const activeMeta = twinById(activeTwinId);

  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1.1fr_1fr]">
      <div className="relative aspect-square rounded-3xl bg-atmosphere lg:aspect-auto lg:h-full lg:min-h-[420px]">
        <LazyObservatory
          activeTwinId={activeTwinId}
          onSelectTwin={setActiveTwinId}
          scores={scores}
          interactive
        />
      </div>

      <div className="flex flex-col gap-4">
        {synthesis && (
          <Card className="p-5">
            <div className="flex items-center justify-between">
              <p className="label-mono text-ivory-300/50">Synthesis</p>
              <DecisionLabelBadge label={synthesis.recommendation} />
            </div>
            <p className="mt-3 text-sm text-ivory-300/70">
              Consensus: <span className="font-mono text-ivory-100">{synthesis.label_consensus}</span>
            </p>
            {synthesis.conflict_axis.length > 0 && (
              <p className="mt-1 text-sm text-ivory-300/70">
                Conflict axis:{" "}
                <span className="font-mono text-ivory-100">
                  {synthesis.conflict_axis.join(", ")}
                </span>
              </p>
            )}
          </Card>
        )}

        <div className="space-y-2">
          {perTwin.map((t) => {
            const meta = twinById(t.twin);
            const isActive = t.twin === activeTwinId;
            return (
              <button
                key={t.twin}
                onClick={() => setActiveTwinId(t.twin)}
                className={clsx(
                  "flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition-all duration-200",
                  isActive
                    ? "border-white/20 bg-white/[0.06]"
                    : "border-white/5 bg-white/[0.015] hover:bg-white/[0.04]",
                )}
              >
                <div className="flex items-center gap-3">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: meta?.accent ?? "#faf8f3" }}
                  />
                  <span className="text-sm text-ivory-100">{meta?.label ?? t.twin}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm text-ivory-300/70">
                    {t.score >= 0 ? "+" : ""}
                    {t.score.toFixed(3)}
                  </span>
                  <DecisionLabelBadge label={t.label} />
                </div>
              </button>
            );
          })}
        </div>

        {active && activeMeta && (
          <Card className="p-5">
            <p className="font-display text-lg text-ivory-100">{activeMeta.label}</p>
            <p className="mt-1 text-sm text-ivory-300/60">{activeMeta.tagline}</p>
            {active.top_contributions.length > 0 && (
              <div className="mt-4 space-y-2">
                <p className="label-mono text-ivory-300/40">Top contributions</p>
                {active.top_contributions.slice(0, 5).map((c) => (
                  <div key={c.factor_id} className="flex items-center justify-between text-sm">
                    <span className="font-mono text-ivory-200/80">{c.factor_id}</span>
                    <span
                      className={clsx(
                        "font-mono",
                        c.raw_contribution >= 0 ? "text-electric-300" : "text-coral-400",
                      )}
                    >
                      {c.contribution_pct >= 0 ? "+" : ""}
                      {c.contribution_pct.toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
