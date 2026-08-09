"""DoPT 100-point roster generator.

Implements the standard Department of Personnel & Training (DoPT) 100-point
roster used for vacancy-based reservation in direct recruitment.

Cycle pattern
-------------
The roster is built by repeating a canonical 10-point cycle ten times to reach
100 serials.  The canonical first 10 points are::

    1 UR, 2 SC, 3 UR, 4 UR, 5 ST, 6 UR, 7 UR, 8 UR, 9 OBC, 10 UR

i.e. positions 1, 3, 4, 6, 7, 8, 10 are UR, with SC at 2, ST at 5 and OBC at 9
per DoPT's fixed reservation sequence.  EWS (introduced via DoPT OM
36017/1/2019-Estt.(Res.I) dated 31.01.2019) occupies the UR point that opens
every second cycle: serials 11, 31, 51, 71, 91.

Point types
-----------
Each entry carries a ``point_type``:
    "r"  reserved point (SC / ST / OBC / EWS)
    "l"  LR (local roster) backlog point — serial 1, the first UR point
    "u"  UR (unreserved) point
"""

CANONICAL_CYCLE = [
    "UR", "SC", "UR", "UR", "ST", "UR", "UR", "UR", "OBC", "UR",
]

# EWS replaces the (UR) first point of cycles 2, 4, 6, 8, 10 — serials 11, 31, 51, 71, 91.
EWS_SERIALS = frozenset({11, 31, 51, 71, 91})


def build_roster(post, start_year):
    """Return the deterministic DoPT 100-point roster for a post.

    ``post`` and ``start_year`` are accepted for interface stability with the
    rest of the roster pipeline; the pure generator is currently
    deterministic and ignores both (Task 3 consumes the same signature when
    advancing the roster on joining).
    """
    entries = []
    for cycle in range(10):
        for offset, category in enumerate(CANONICAL_CYCLE):
            serial = cycle * 10 + offset + 1
            if serial in EWS_SERIALS:
                category = "EWS"
            if category != "UR":
                point_type = "r"
            elif serial == 1:
                point_type = "l"
            else:
                point_type = "u"
            entries.append(
                {"serial": serial, "category": category, "point_type": point_type}
            )
    return entries
