"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/Skeleton";

/** Dynamically imported, client-only, no SSR - the 3D bundle (three/r3f/drei) never
 * ships to users who don't scroll to it, and never runs on the server. */
export const LazyObservatory = dynamic(
  () => import("./DecisionObservatory").then((m) => m.DecisionObservatory),
  {
    ssr: false,
    loading: () => <Skeleton className="h-full w-full rounded-3xl" />,
  },
);
