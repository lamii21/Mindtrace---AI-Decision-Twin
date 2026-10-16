import { DecisionLabelBadge } from "@/components/ui/Badge";
import { ConfidencePanel } from "./ConfidencePanel";
import { TwinComparison } from "./TwinComparison";
import { EvidenceTrace } from "./EvidenceTrace";
import type { SimulationOut } from "@/lib/api/types";

export function SimulationResult({ simulation }: { simulation: SimulationOut }) {
  return (
    <div className="space-y-10">
      <div className="flex items-center justify-between">
        <div>
          <p className="label-mono text-ivory-300/50">Result</p>
          <div className="mt-2 flex items-center gap-3">
            <DecisionLabelBadge label={simulation.decision.label} />
            <span className="text-sm text-ivory-300/50">
              engine v{simulation.engine_version} · factor schema v
              {simulation.factor_schema_version}
            </span>
          </div>
        </div>
      </div>

      <ConfidencePanel decision={simulation.decision} confidence={simulation.confidence} />

      <div>
        <p className="label-mono mb-4 text-ivory-300/50">Four perspectives, one decision</p>
        <TwinComparison perTwin={simulation.per_twin} synthesis={simulation.synthesis} />
      </div>

      <EvidenceTrace simulationId={simulation.simulation_id} trace={simulation.trace} />
    </div>
  );
}
