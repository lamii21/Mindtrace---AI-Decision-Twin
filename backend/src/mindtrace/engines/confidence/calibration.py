"""`historical_calibration` (spec §06 §4.3).

No `Prediction`/`Outcome` ledger exists yet (that persistence layer is a later
milestone), so every caller passes `calibration=None` for now - which lands
squarely on the spec's own explicitly-defined small-`n` branch: `n = 0 <
N_CAL_MIN` in both scopes, so the term is omitted and `calibrated = "false"`.
This is not a fallback invented for this milestone; it is the documented
behaviour the spec already prescribes for "not enough data yet".
"""

from __future__ import annotations

from collections.abc import Sequence

from mindtrace.domain.confidence import CalibrationLedger, CalibrationRecord
from mindtrace.engines.confidence.config import ConfidenceConfig

_N_BINS = 5


def _expected_calibration_error(records: Sequence[CalibrationRecord]) -> float:
    """`ECE = sum_b (n_b/n) * |accuracy_b - mean_confidence_b|` over 5 equal-width bins."""
    bins: list[list[CalibrationRecord]] = [[] for _ in range(_N_BINS)]
    for record in records:
        index = min(int(record.predicted_confidence * _N_BINS), _N_BINS - 1)
        bins[index].append(record)

    n = len(records)
    ece = 0.0
    for bin_records in bins:
        if not bin_records:
            continue
        n_b = len(bin_records)
        accuracy_b = sum(1.0 for r in bin_records if r.correct) / n_b
        mean_confidence_b = sum(r.predicted_confidence for r in bin_records) / n_b
        ece += (n_b / n) * abs(accuracy_b - mean_confidence_b)
    return ece


def historical_calibration(
    ledger: CalibrationLedger | None,
    config: ConfidenceConfig,
) -> tuple[float | None, str, int]:
    """`(historical_calibration, calibrated status, n used)` (spec §06 §4.3)."""
    domain_records = ledger.domain_records if ledger is not None else ()
    all_domain_records = ledger.all_domain_records if ledger is not None else ()

    if len(domain_records) < config.n_cal_min and len(all_domain_records) < config.n_cal_min:
        return None, "false", 0

    if len(domain_records) >= config.n_cal_min:
        records, status = domain_records, "true"
    else:
        records, status = all_domain_records, "cross_domain"

    n = len(records)
    raw = 1.0 - _expected_calibration_error(records)
    shrunk = (n * raw + config.n_cal_min * config.hc_prior) / (n + config.n_cal_min)
    return shrunk, status, n
