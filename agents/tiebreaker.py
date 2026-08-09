"""Deterministic Tie-Breaking Engine.

Pure functions for ranking candidates that share the same composite score.
No Django ORM imports — callers pass plain dicts so these functions stay
unit-testable without a database.

Default rule order (first match wins):
  1. age      — older candidate ranks higher  (descending)
  2. qual_pct — higher qualification % ranks higher (descending)
  3. name     — alphabetical ascending
"""

# ── Rule definitions ────────────────────────────────────────────────────────

# Each rule maps to a (key, reverse) pair suitable for sorted().
# "reverse=True" means descending (higher is better / older is better).
_RULES = {
    "age":      ("age",      True),
    "qual_pct": ("qual_pct", True),
    "name":     ("name",     False),
}


# ── Public API ──────────────────────────────────────────────────────────────


def break_tie(candidates, rules=None):
    """Return *candidates* sorted deterministically by the given tie-break rules.

    Parameters
    ----------
    candidates : list[dict]
        Each dict must contain the keys used by the chosen *rules*.
        Extra keys are preserved untouched.
    rules : list[str] | None
        Ordered list of rule names to apply.  First rule that produces a
        difference decides the order.  Defaults to ``["age", "qual_pct", "name"]``.

    Returns
    -------
    list[dict]
        A **new** list (the originals are not mutated) sorted by the
        composite key described by *rules*.

    Raises
    ------
    ValueError
        If *candidates* contains a non-dict entry or *rules* contains an
        unknown rule name.
    """
    if rules is None:
        rules = ["age", "qual_pct", "name"]

    # Validate rules up-front so callers get a clear error.
    unknown = [r for r in rules if r not in _RULES]
    if unknown:
        raise ValueError(f"Unknown tie-break rule(s): {unknown}")

    # Validate candidates.
    for i, c in enumerate(candidates):
        if not isinstance(c, dict):
            raise ValueError(
                f"Expected dict at index {i}, got {type(c).__name__}"
            )

    # Build a composite sort key: tuple of values in rule order, respecting
    # each rule's natural direction via negation (for numeric) or casefold.
    def _sort_key(cand):
        parts = []
        for rule in rules:
            key, reverse = _RULES[rule]
            val = cand.get(key)
            if val is None:
                # Missing values sort last regardless of direction.
                val = _sentinel(reverse)
            elif isinstance(val, str):
                # For string keys, reverse-alphabetical uses a wrapper.
                val = _ReversedStr(val) if reverse else val
            elif reverse:
                val = _Negated(val)
            parts.append(val)
        return tuple(parts)

    return sorted(candidates, key=_sort_key)


# ── Helpers ─────────────────────────────────────────────────────────────────


class _Negated:
    """Wrapper that reverses numeric sort order via ``__lt__`` swap."""

    __slots__ = ("val",)

    def __init__(self, val):
        self.val = val

    def __lt__(self, other):
        if isinstance(other, _Negated):
            return self.val > other.val
        return NotImplemented  # pragma: no cover

    def __eq__(self, other):
        if isinstance(other, _Negated):
            return self.val == other.val
        return NotImplemented  # pragma: no cover

    def __repr__(self):  # pragma: no cover
        return f"_Negated({self.val!r})"


class _ReversedStr:
    """Wrapper that reverses string sort order."""

    __slots__ = ("val",)

    def __init__(self, val):
        self.val = val.casefold()

    def __lt__(self, other):
        if isinstance(other, _ReversedStr):
            return self.val > other.val
        return NotImplemented  # pragma: no cover

    def __eq__(self, other):
        if isinstance(other, _ReversedStr):
            return self.val == other.val
        return NotImplemented  # pragma: no cover

    def __repr__(self):  # pragma: no cover
        return f"_ReversedStr({self.val!r})"


_SENTINEL_DESCENDING = object()
_SENTINEL_ASCENDING = object()


def _sentinel(reverse):
    """Return a sentinel that sorts last regardless of direction.

    For descending rules ``None`` should appear at the end (after all real
    values).  For ascending rules ``None`` also appears at the end.
    """
    # Using a fresh object that is neither < nor > any normal value
    # is tricky; instead we use the Negated/ReversedStr wrappers
    # with a max-like trick.  Simplest: return a value that always
    # compares as "greater" in the effective direction, i.e. last.
    # We handle this by returning a float('inf') for descending
    # (high value = appears last) and a string with max char for ascending.
    if reverse:
        return _Negated(float("-inf"))  # Negated flips: -inf becomes +inf → last
    return "\uffff" * 10  # sorts after any realistic string
