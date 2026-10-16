"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { listDecisions } from "@/lib/api/decisions";
import { Card } from "@/components/ui/Card";
import { ButtonLink } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { ErrorMessage } from "@/components/ui/ErrorMessage";
import { SkeletonText } from "@/components/ui/Skeleton";

export default function DecisionsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["decisions"],
    queryFn: listDecisions,
  });

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl text-ivory-100">Your decisions</h1>
          <p className="mt-1 text-sm text-ivory-300/60">
            Create a decision, then run a simulation across your four perspectives.
          </p>
        </div>
        <ButtonLink href="/app/decisions/new">New decision</ButtonLink>
      </div>

      <div className="mt-10">
        {isLoading && (
          <Card className="p-6">
            <SkeletonText lines={4} />
          </Card>
        )}

        {error && <ErrorMessage error={error} />}

        {data && data.items.length === 0 && (
          <Card className="flex flex-col items-center gap-4 p-16 text-center">
            <p className="font-display text-xl text-ivory-100">No decisions yet</p>
            <p className="max-w-sm text-sm text-ivory-300/60">
              Describe a real decision you&apos;re weighing — MINDTRACE will simulate how your
              four perspectives see it.
            </p>
            <ButtonLink href="/app/decisions/new">Create your first decision</ButtonLink>
          </Card>
        )}

        {data && data.items.length > 0 && (
          <div className="space-y-3">
            {data.items.map((decision) => (
              <Link key={decision.id} href={`/app/decisions/${decision.id}`}>
                <Card className="flex items-center justify-between gap-4 p-5 transition-colors hover:bg-white/[0.05]">
                  <div>
                    <p className="font-display text-lg text-ivory-100">{decision.title}</p>
                    <p className="mt-1 text-sm text-ivory-300/50">{decision.category}</p>
                  </div>
                  <Badge>{decision.status}</Badge>
                </Card>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
