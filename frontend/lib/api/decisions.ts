import { apiClient } from "./client";
import type { DecisionCreate, DecisionOut } from "./types";

export function createDecision(body: DecisionCreate) {
  return apiClient.post<DecisionOut>("/v1/decisions", body);
}

export function getDecision(id: string) {
  return apiClient.get<DecisionOut>(`/v1/decisions/${id}`);
}

export function listDecisions() {
  return apiClient.get<{ items: DecisionOut[]; next_cursor: string | null }>("/v1/decisions");
}
