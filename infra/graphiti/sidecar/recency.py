"""Query-time recency-decay scoring overlay.

Applies an exponential half-life weight to a list of edges returned by Graphiti
search, so that freshly-valid_at facts outrank stale ones.  This is a pure
function applied post-search — it does NOT re-query Graphiti, mutate edge
objects, or call any external service.

Half-life formula:
    weight = exp(-ln(2) * age_days / half_life_days)

Edge with no valid_at gets weight 1.0 (unknown recency → don't penalise).
Returns a NEW sorted list; the input list is never mutated.

Usage in search call sites:
    from sidecar.recency import apply_recency_decay

    edges = await g.search(query=query, num_results=num_results)
    if recency_decay:
        edges = apply_recency_decay(edges, reference_time=datetime.now())
"""

import math
from datetime import datetime, timezone
from typing import Any


_DEFAULT_HALF_LIFE_DAYS: float = 90.0


def apply_recency_decay(
    edges: list[Any],
    *,
    reference_time: datetime | None = None,
    half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
) -> list[Any]:
    """Return a new list of edges sorted by descending recency-decay weight.

    Parameters
    ----------
    edges:
        List of edge objects as returned by ``Graphiti.search()``.  Each edge
        is expected to have a ``valid_at`` attribute (``datetime | None``).
        Any other attributes are passed through unchanged.
    reference_time:
        The "now" anchor for age calculation.  Defaults to ``datetime.now()``
        in UTC if omitted.  Pass an explicit value in tests for determinism.
    half_life_days:
        Number of days after which an edge's weight decays to 0.5.  Default
        is 90 days — roughly one quarter.  Callers may override per use-case.

    Returns
    -------
    list
        A new list (same edge objects, no copies) sorted by weight descending.
        Ties preserve the original relative order (stable sort).
    """
    if not edges:
        return []

    if reference_time is None:
        reference_time = datetime.now(tz=timezone.utc)

    # Ensure reference_time is tz-aware for safe arithmetic.
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    ln2 = math.log(2)

    def _weight(edge: Any) -> float:
        valid_at = getattr(edge, "valid_at", None)
        if valid_at is None:
            return 1.0

        # Normalise valid_at to tz-aware so subtraction doesn't raise.
        if isinstance(valid_at, datetime):
            if valid_at.tzinfo is None:
                valid_at = valid_at.replace(tzinfo=timezone.utc)
        else:
            # Unexpected type (string, neo4j DateTime, etc.) — treat as unknown.
            return 1.0

        age_seconds = (reference_time - valid_at).total_seconds()
        if age_seconds < 0:
            # valid_at is in the future relative to reference_time — treat as
            # maximally fresh.
            return 1.0

        age_days = age_seconds / 86_400.0
        return math.exp(-ln2 * age_days / half_life_days)

    # Stable sort: items with equal weight preserve their input ordering.
    return sorted(edges, key=_weight, reverse=True)
