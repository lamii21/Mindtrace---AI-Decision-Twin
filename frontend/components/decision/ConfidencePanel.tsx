import { Card } from "@/components/ui/Card";
import type { ConfidenceOut, DecisionSummaryOut } from "@/lib/api/types";

const UNCERTAIN_EXPLANATIONS: Record<string, string> = {
  score_in_band: "The score sits too close to the decision boundary to call confidently.",
  insufficient_coverage: "Too few factors were extracted from the scenario.",
  low_model_confidence: "The score is decisive, but the evidence behind it is too thin.",
  ensemble_disagreement: "The four perspectives disagree enough that no recommendation holds.",
};

/** Score (S) and confidence (C) are rendered as two separate, independently-computed
 * numbers - never a single circular progress bar implying "this decision is correct". */
export function ConfidencePanel({
  decision,
  confidence,
}: {
  decision: DecisionSummaryOut;
  confidence: ConfidenceOut;
}) {
  return (
    <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
      <Card className="p-6">
        <p className="label-mono text-ivory-300/50">Decision score (S)</p>
        <p className="mt-3 font-mono text-4xl text-ivory-100">
          {decision.score >= 0 ? "+" : ""}
          {decision.score.toFixed(3)}
        </p>
        <p className="mt-2 text-xs text-ivory-300/50">
          Signed, [-1, 1] · margin {decision.margin.toFixed(3)} · coverage{" "}
          {(decision.coverage * 100).toFixed(0)}%
        </p>
      </Card>

      <Card className="p-6">
        <p className="label-mono text-ivory-300/50">Model confidence (C)</p>
        <p className="mt-3 font-mono text-4xl text-electric-300">
          {(confidence.value * 100).toFixed(1)}%
        </p>
        <p className="mt-2 text-xs text-ivory-300/50">
          Computed independently of S · never equal to |S|
        </p>
      </Card>

      {decision.uncertain_reason && (
        <Card className="sm:col-span-2 border border-amber-500/30 bg-amber-500/5 p-6">
          <p className="label-mono text-amber-400">Why this is uncertain</p>
          <p className="mt-2 font-mono text-sm text-ivory-100">{decision.uncertain_reason}</p>
          <p className="mt-2 text-sm text-ivory-300/70">
            {UNCERTAIN_EXPLANATIONS[decision.uncertain_reason] ?? "The model could not form a confident judgment."}
          </p>
        </Card>
      )}
    </div>
  );
}
