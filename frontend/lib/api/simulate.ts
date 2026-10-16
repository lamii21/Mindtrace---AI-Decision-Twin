import { apiClient } from "./client";
import type { SimulationOut } from "./types";

export function runSimulation(decisionId: string) {
  return apiClient.post<SimulationOut>("/v1/simulate", { decision_id: decisionId });
}

export function getSimulation(id: string) {
  return apiClient.get<SimulationOut>(`/v1/simulations/${id}`);
}
