# Task 11: Data Archival (Phase 4.10) — COMPLETE

## Files Created
- `recruitment/archival.py` — eligibility detection + hash-chain helpers
- `recruitment/test_archival.py` — 14 tests covering both features

## Implementation

### `archive_eligible()` → QuerySet
Returns applications where:
- `status` in `("joined", "rejected", "withdrawn")` **and**
- parent advertisement's `closing_date` < 1 year ago (via `post__advertisement__closing_date__lt=cutoff`)

### Hash-chain
- `_event_canonical(event)` — deterministic string representation of an AuditEvent row
- `hash_row(event, prev_hash="")` — `sha256(prev_hash + canonical(event))`
- `verify_chain(events, hashes)` — walks both lists in order, recomputes each hash, returns `True` iff every hash matches

### Test Coverage (14 tests)
| Test | Category |
|------|----------|
| `test_eligible_old_closing_terminal_status` | Eligibility — positive (all 3 terminal statuses) |
| `test_not_eligible_recent_closing` | Eligibility — recent closing_date excluded |
| `test_not_eligible_nonterminal_status` | Eligibility — non-terminal statuses excluded |
| `test_eligible_ignores_nonterminal_among_old` | Eligibility — mixed statuses in same old ad |
| `test_empty_queryset_when_no_applications` | Eligibility — empty DB |
| `test_hash_row_deterministic` | Hash-chain — same input → same output |
| `test_hash_row_changes_with_prev_hash` | Hash-chain — prev_hash matters |
| `test_hash_row_changes_with_event_data` | Hash-chain — event data matters |
| `test_verify_chain_valid` | Chain verification — correct chain passes |
| `test_verify_chain_tampered` | Chain verification — tampered hash fails |
| `test_verify_chain_length_mismatch` | Chain verification — length mismatch fails |
| `test_verify_chain_empty` | Chain verification — empty chain passes |
| `test_verify_chain_single_element` | Chain verification — single-element chain |
| `test_hash_chain_with_real_audit_events` | Integration — real ORM AuditEvent rows |

## Commit
`Phase 4: Archival — eligibility detection + hash-chain`
