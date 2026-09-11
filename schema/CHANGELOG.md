# Schema changelog

Canonical, language-agnostic specs. See `docs/spec/03-factor-model.md` §5 for the versioning
policy. A structural change (add/remove a factor, change `direction`/`anchors`, move a factor
between core and extended, add/remove a trait) is a **major** change and requires a migration +
a scheduled twin re-derivation once those exist (M4+).

## factors.yaml

### v1 — 2026-09-09
- Initial taxonomy: 16 core factors, 3 extended factors.
- Shared 5-level ordinal scale (`very_low`…`very_high`) with linear default anchors.
- `financial_return` and `downside_risk` carry non-linear anchor overrides.

## traits.yaml

### v1 — 2026-09-09
- Initial trait model: one importance weight per core + extended factor (Normal logit posterior),
  4 dispositions (`risk_tolerance`, `time_discount`, `ambiguity_aversion`, `effort_tolerance`;
  Beta posteriors).
- `factor_schema_version: 1`.

## interview.yaml

### v1 — 2026-09-09
- Initial Twin Interview item bank: 14 pairwise trade-off items (2 with `consistency_check`
  repeats) + 8 disposition items (2 per disposition).
- `factor_schema_version: 1`.
