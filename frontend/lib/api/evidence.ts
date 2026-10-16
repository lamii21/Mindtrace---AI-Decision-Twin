import { apiClient } from "./client";
import type { BeliefType, EvidenceChainOut } from "./types";

export function getEvidenceChain(beliefType: BeliefType, beliefId: string) {
  return apiClient.get<EvidenceChainOut>(`/v1/evidence/${beliefType}/${beliefId}`);
}
