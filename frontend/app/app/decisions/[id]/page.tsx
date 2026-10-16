"use client";

import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getDecision } from "@/lib/api/decisions";
import { runSimulation } from "@/lib/api/simulate";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { SkeletonText } from "@/components/ui/Skeleton";
import { SimulationResult } from "@/components/decision/SimulationResult";
import type { SimulationOut } from "@/lib/api/types";
import { useState } from "react";

export default function DecisionDetailPage() {
  const params = useParams<{ id: string }>();
  const decisionId = params.id;
  const queryClient = useQueryClient();
  const [simulation, setSimulation] = useState<SimulationOut | null>(null);

  const decisionQuery = useQuery({
    queryKey: ["decision", decisionId],
    queryFn: () => getDecision(decisionId),
  });

  const simulateMutation = useMutation({
    mutationFn: () => runSimulation(decisionId),
    onSuccess: (result) => {
      setSimulation(result);
      void queryClient.invalidateQueries({ queryKey: ["decision", decisionId] });
    },
  });

  if (decisionQuery.isLoading) {
    return (
      <Card className="p-8">
        <SkeletonText lines={5} />
      </Card>
    );
  }

  if (decisionQuery.error) {
    return <ErrorMessage error={decisionQuery.error} />;
  }

  const decision = decisionQuery.data!;

  return (
    <div className="space-y-10">
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="font-display text-3xl text-ivory-100">{decision.title}</h1>
          <Badge>{decision.category}</Badge>
          <Badge>{decision.status}</Badge>
        </div>
        <p className="mt-4 max-w-2xl whitespace-pre-wrap text-sm leading-relaxed text-ivory-300/70">
          {decision.context}
        </p>
      </div>

      {!simulation && (
        <Card className="flex flex-col items-center gap-4 p-14 text-center">
          <p className="font-display text-xl text-ivory-100">Ready to simulate</p>
          <p className="max-w-md text-sm text-ivory-300/60">
            MINDTRACE will extract the factors behind this decision and run them through your
            four perspectives plus your own base weighting.
          </p>
          <Button
            size="lg"
            onClick={() => simulateMutation.mutate()}
            disabled={simulateMutation.isPending}
          >
            {simulateMutation.isPending ? "Simulating…" : "Run simulation"}
          </Button>
          <ErrorMessage error={simulateMutation.error} />
        </Card>
      )}

      {simulation && (
        <>
          <SimulationResult simulation={simulation} />
          <div className="flex justify-center">
            <Button
              variant="secondary"
              onClick={() => simulateMutation.mutate()}
              disabled={simulateMutation.isPending}
            >
              {simulateMutation.isPending ? "Simulating…" : "Run again"}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
