"use client";

import { useQuery } from "@tanstack/react-query";
import { getEvidenceChain } from "@/lib/api/evidence";
import { Card } from "@/components/ui/Card";
import { SkeletonText } from "@/components/ui/Skeleton";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import type { TraceGraphOut } from "@/lib/api/types";

const SOURCE_KIND_LABEL: Record<string, string> = {
  memory: "Memory",
  decision: "Decision",
  elicitation_answer: "Interview answer",
  outcome: "Outcome",
};

/** Reads the real `GET /v1/evidence/decision_factor/{simulationId}` endpoint - never
 * fabricated. `trace` (from the simulate response) supplies the factor list; this
 * fetches the actual provenance edges behind them. */
export function EvidenceTrace({
  simulationId,
  trace,
}: {
  simulationId: string;
  trace: TraceGraphOut;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["evidence", "decision_factor", simulationId],
    queryFn: () => getEvidenceChain("decision_factor", simulationId),
  });

  const knownFactors = trace.nodes.filter((n) => n.kind === "factor");

  return (
    <Card className="p-6">
      <p className="label-mono text-ivory-300/50">Evidence trace</p>

      {isLoading && (
        <div className="mt-4">
          <SkeletonText lines={3} />
        </div>
      )}
      {error && (
        <div className="mt-4">
          <ErrorMessage error={error} />
        </div>
      )}

      {data && (
        <div className="mt-4 space-y-3">
          {data.edges.length === 0 && (
            <p className="text-sm text-ivory-300/50">No evidence edges recorded yet.</p>
          )}
          {data.edges.map((edge, i) => (
            <div
              key={`${edge.source_kind}-${edge.source_id}-${i}`}
              className="flex items-start justify-between gap-4 rounded-xl border border-white/5 bg-white/[0.02] px-4 py-3"
            >
              <div>
                <p className="text-sm text-ivory-100">
                  {SOURCE_KIND_LABEL[edge.source_kind] ?? edge.source_kind}
                </p>
                <p className="mt-1 text-xs text-ivory-300/50">
                  {edge.polarity === "support" ? "Supports" : "Contradicts"} this decision ·
                  weight {edge.weight.toFixed(2)}
                </p>
              </div>
              <span className="label-mono shrink-0 text-ivory-300/30">
                engine v{edge.engine_version}
              </span>
            </div>
          ))}
        </div>
      )}

      {knownFactors.length > 0 && (
        <div className="mt-6">
          <p className="label-mono text-ivory-300/40">Known factors in this trace</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {knownFactors.map((f) => (
              <span
                key={f.id}
                className="rounded-full bg-white/[0.04] px-3 py-1 font-mono text-xs text-ivory-200/70"
              >
                {f.label}
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
