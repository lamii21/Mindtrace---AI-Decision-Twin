/**
 * The four parallel twins, read directly from the repository's own source of
 * truth: `schema/twins.yaml` (ADR-007). These are NOT fictional personalities
 * or independent LLM agents - each is a fixed, deterministic shift applied to
 * the user's own base weight vector: `w_t = renorm(w* . (1 + lambda . shift_t))`,
 * lambda = 0.35. Everything below (up/down factor lists, lambda) is copied
 * verbatim from that file, not invented for the UI.
 */

export const TWIN_LAMBDA = 0.35;

export interface TwinDefinition {
  id: "base" | "career" | "safe" | "dream" | "future";
  label: string;
  tagline: string;
  up: string[];
  down: string[];
  accent: string;
  accentSoft: string;
}

export const TWINS: TwinDefinition[] = [
  {
    id: "career",
    label: "Career You",
    tagline: "Up-weights growth and optionality; down-weights convenience and routine.",
    up: ["skill_growth", "option_value"],
    down: ["time_demand", "stability"],
    accent: "#6ab8ff",
    accentSoft: "rgba(106,184,255,0.18)",
  },
  {
    id: "safe",
    label: "Safe You",
    tagline: "Up-weights security, stability, and reversibility; down-weights novelty.",
    up: ["financial_security", "stability", "downside_risk", "reversibility"],
    down: ["novelty"],
    accent: "#ab9aea",
    accentSoft: "rgba(171,154,234,0.18)",
  },
  {
    id: "dream",
    label: "Dream You",
    tagline: "Up-weights intrinsic interest and meaning; down-weights financial security.",
    up: ["intrinsic_interest", "creative_expression", "values_alignment"],
    down: ["financial_security"],
    accent: "#ffb968",
    accentSoft: "rgba(255,185,104,0.18)",
  },
  {
    id: "future",
    label: "Future You",
    tagline: "Up-weights long-term value and optionality. No down-weights.",
    up: ["long_term_value", "option_value"],
    down: [],
    accent: "#ff9d85",
    accentSoft: "rgba(255,157,133,0.18)",
  },
];

export const BASE_TWIN: TwinDefinition = {
  id: "base",
  label: "You (base)",
  tagline: "Your own current weighting - untransformed.",
  up: [],
  down: [],
  accent: "#faf8f3",
  accentSoft: "rgba(250,248,243,0.12)",
};

export const ALL_TWINS: TwinDefinition[] = [BASE_TWIN, ...TWINS];

export function twinById(id: string): TwinDefinition | undefined {
  return ALL_TWINS.find((t) => t.id === id);
}
