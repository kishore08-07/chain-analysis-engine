"""
Heuristic configuration.

Thresholds can be tuned via environment variables without code changes.
"""

import os


def _get_int(name, default, minimum=0):
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _get_float(name, default, minimum=0.0):
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


COINJOIN_MIN_INPUTS = _get_int('SHERLOCK_COINJOIN_MIN_INPUTS', 2, minimum=2)
COINJOIN_MIN_EQUAL_OUTPUTS = _get_int('SHERLOCK_COINJOIN_MIN_EQUAL_OUTPUTS', 2, minimum=2)
CONSOLIDATION_MIN_INPUTS = _get_int('SHERLOCK_CONSOLIDATION_MIN_INPUTS', 3, minimum=2)
PEELING_MIN_RATIO = _get_float('SHERLOCK_PEELING_MIN_RATIO', 5.0, minimum=1.0)
PEELING_MAX_INPUTS = _get_int('SHERLOCK_PEELING_MAX_INPUTS', 3, minimum=1)
