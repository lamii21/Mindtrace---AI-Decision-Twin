/**
 * Types mirroring the REAL backend contract, read directly from
 * `backend/src/mindtrace/api/schemas/*.py` (not the aspirational
 * `docs/api/08-api-contracts.md`, which documents the full post-M10 shape -
 * some fields there, e.g. `SimulateRequest.twins`, don't exist yet).
 *
 * Field names/shapes are exact matches of the Pydantic response models.
 */

// ---- Auth (api/schemas/auth.py) ----------------------------------------

export interface AuthUser {
  user_id: string;
  email: string;
  created_at: string;
}

export interface TokenPairResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface ConsentStateResponse {
  scope: "store_memories" | "run_inference" | "use_llm_provider" | "retain_outcomes";
  granted: boolean;
  policy_version: string;
  updated_at: string;
}

export interface MeResponse {
  user_id: string;
  email: string;
  created_at: string;
  consents: ConsentStateResponse[];
}

// ---- Decisions (api/schemas/decision.py) -------------------------------

export type DecisionCategory =
  | "career"
  | "education"
  | "project"
  | "purchase"
  | "relationship"
  | "other";

export type DecisionStatus = "draft" | "simulated" | "committed" | "archived";

export interface OptionIn {
  id: string;
  label: string;
  body: string;
}

export interface DecisionCreate {
  title: string;
  category: DecisionCategory;
  context: string;
  options: OptionIn[];
  high_stakes?: boolean;
  decided_at?: string | null;
  chosen_option?: string | null;
}

export interface DecisionOut {
  id: string;
  title: string;
  category: string;
  context: string;
  options: OptionIn[];
  status: DecisionStatus;
  extracted_factors: Record<string, Record<string, unknown>> | null;
  extraction_model_run_id: string | null;
  chosen_option: string | null;
  reasoning: string | null;
  decided_at: string | null;
  latest_prediction: Record<string, unknown> | null;
  outcome: Record<string, unknown> | null;
  created_at: string;
}

// ---- Simulate (api/schemas/simulation.py) ------------------------------

export type DecisionLabel = "ACCEPT" | "REJECT" | "UNCERTAIN";
export type UncertainReason =
  | "score_in_band"
  | "insufficient_coverage"
  | "low_model_confidence"
  | "ensemble_disagreement";
export type LabelConsensus = "unanimous" | "majority" | "split";

export interface SimulateRequest {
  decision_id: string;
}

export interface ContributionOut {
  factor_id: string;
  level_a: string;
  weight: number;
  normalized_value_a: number;
  normalized_value_b: number;
  raw_contribution: number;
  contribution_pct: number;
}

export interface ConfidenceInputsOut {
  evidence_sufficiency: number;
  n_bar: number;
  coverage: number;
  ensemble_disagreement: number | null;
  ensemble_term_capped: boolean;
  historical_calibration: number | null;
  calibrated: string;
  calibration_n: number;
  extraction_entropy: number | null;
  extraction_path: string;
  margin_adequacy: number;
  margin: number;
}

export interface ConfidenceOut {
  confidence_engine_version: string;
  confidence_config_version: string;
  value: number;
  raw: number;
  calibrated_output: boolean;
  credible_interval: null;
  inputs: ConfidenceInputsOut;
  weights_used: Record<string, number>;
}

export interface DecisionSummaryOut {
  label: DecisionLabel;
  uncertain_reason: UncertainReason | null;
  score: number;
  margin: number;
  coverage: number;
}

export interface TwinResultOut {
  twin: string;
  label: DecisionLabel;
  score: number;
  top_contributions: ContributionOut[];
}

export interface SynthesisOut {
  recommendation: DecisionLabel;
  label_consensus: LabelConsensus;
  conflict_axis: string[];
  vote: Record<string, string>;
}

export interface TraceNodeOut {
  id: string;
  kind: "decision" | "factor" | "evidence";
  label: string;
}

export interface TraceEdgeOut {
  source: string;
  target: string;
  kind: "cites" | "supports";
}

export interface TraceGraphOut {
  nodes: TraceNodeOut[];
  edges: TraceEdgeOut[];
}

export interface SimulationOut {
  simulation_id: string;
  decision_id: string;
  engine_version: string;
  factor_schema_version: number;
  twin_version_id: string | null;
  decision: DecisionSummaryOut;
  confidence: ConfidenceOut;
  contributions: ContributionOut[];
  trace: TraceGraphOut;
  per_twin: TwinResultOut[];
  synthesis: SynthesisOut | null;
  debate: null;
  elicitation_hint: null;
  created_at: string;
}

// ---- Evidence (api/schemas/evidence.py) --------------------------------

export type BeliefType = "preference" | "trait" | "value" | "decision_factor" | "contradiction";
export type SourceKind = "memory" | "decision" | "elicitation_answer" | "outcome";

export interface BeliefSummaryOut {
  type: BeliefType;
  id: string;
  label: string;
  value: number | null;
  confidence: number | null;
  source: "declared" | "inferred";
}

export interface EvidenceEdgeOut {
  source_kind: SourceKind;
  source_id: string;
  source_excerpt: string;
  weight: number;
  polarity: "support" | "contradict";
  engine_version: string;
  created_at: string;
}

export interface EvidenceChainOut {
  belief: BeliefSummaryOut;
  engine_version: string;
  edges: EvidenceEdgeOut[];
}

// ---- Errors (api/errors.py, RFC 9457 problem+json) ---------------------

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  errors?: unknown[];
}
