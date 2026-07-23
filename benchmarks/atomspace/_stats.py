"""Shared statistics for the atomspace T1/T2 gates.

Reuses the FreeCiv batch machinery (benchmark-docs/atomspace.md §Methodology:
"Statistics re-use the FreeCiv batch machinery") rather than re-deriving it:
exact two-sided sign test and paired-t live in
``benchmarks/freeciv/batch/aggregate.py``. Exact McNemar over discordant pairs
reduces to the sign test on b+c trials, so it is a thin wrapper here.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BATCH = os.path.normpath(os.path.join(_HERE, "..", "freeciv", "batch"))
if _BATCH not in sys.path:
    sys.path.insert(0, _BATCH)

from aggregate import _binom_two_sided, _paired_t  # noqa: E402

sign_test = _binom_two_sided   # exact two-sided sign-test p for k of n
paired_t = _paired_t


def mcnemar_exact(b, c):
    """Exact two-sided McNemar over discordant pairs.

    ``b`` = candidate-correct & baseline-wrong; ``c`` = the reverse. With no
    continuity correction this is exactly the two-sided sign test on the b+c
    discordant trials.
    """
    n = b + c
    return {"b": b, "c": c, "n_discordant": n,
            "p": _binom_two_sided(b, n) if n else 1.0}


__all__ = ["sign_test", "paired_t", "mcnemar_exact"]
