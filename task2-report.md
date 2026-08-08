# Task 2 Report — get_org_profile() access helper

**Status:** DONE
**Commit:** `10a0e73` — "Phase 2: OrgProfile — get_org_profile() lazy singleton helper"
**Branch:** `phase2-orgprofile`

## What was done

1. **Step 1 (tests, red):** Appended the two brief-specified tests to `recruitment/test_org_profile.py`:
   - `test_get_org_profile_creates_singleton` — drops the migration-seeded row, asserts two calls return the same row (`first.pk == second.pk`) and `name_en == "NEEPCO"` (fixture Client name).
   - `test_get_org_profile_no_client_fallback` — monkeypatches `Client.objects.get` to raise `Client.DoesNotExist`, asserts the helper falls back to a non-empty schema name.
2. **Step 2 (verify red):** `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q` → `2 failed, 1 passed` with `ModuleNotFoundError: No module named 'recruitment.org_profile'` on both new tests (expected).
3. **Step 3 (implement):** Created `recruitment/org_profile.py` exactly per the brief — lazy `from .models import OrgProfile` inside the function; `Client.objects.get(schema_name=connection.schema_name).name` → `connection.schema_name` → `"Organisation"` fallback chain; `OrgProfile.objects.get_or_create(defaults={...})` singleton semantics. Never raises (only `Client.DoesNotExist` is caught; `get_or_create` handles the row-creation race atomically).
4. **Step 4 (verify green):** Same pytest command → `3 passed in 7.23s`.
5. **Step 5 (commit):** `git add recruitment/org_profile.py recruitment/test_org_profile.py && git commit -m "Phase 2: OrgProfile — get_org_profile() lazy singleton helper"` → `10a0e73`.

## Files modified

- `recruitment/org_profile.py` (new, 42 lines) — per brief verbatim.
- `recruitment/test_org_profile.py` (appended 2 tests, +28 lines).

## Constraints honored

- No `manage.py migrate`/`migrate_schemas` run (dev DB untouched).
- Only the targeted pytest command executed, not the full suite.
- Only the two allowed files touched.
- Interfaces verified against Task 1: `OrgProfile` model (`name_en`, `name_hi`, `tagline_en`, `tagline_hi`, `address`, `footer_motto`, `contact_email`, `website`, `sbi_epay_text`, `logo` nullable, `accent_color` default `#0b3d91`) and `tenants.models.Client` (`schema_name`, `name`) both confirmed present.

## Review-fix round (Main review findings F1 + F2)

**Fix commit:** `10a0e73` (below) — message "Phase 2: OrgProfile — enforce single-row OrgProfile (partial unique constraint) + race-safe helper"

- **F1 (MAJOR):** `get_or_create` is not race-safe without a uniqueness guarantee; two concurrent first-accesses would INSERT twice → `MultipleObjectsReturned`, breaking the never-raises contract. Fixed three ways:
  1. `recruitment/models.py` `OrgProfile.Meta` now carries `constraints = [models.UniqueConstraint(models.Value(1), condition=models.Q(pk__isnull=False), name="orgprofile_singleton_row")]` — a partial unique index on the constant `1` enforces at most one real row per schema. *Note: the review's original snippet (`UniqueConstraint(condition=..., name=...)` with no fields/expressions) is rejected by Django's own validation ("At least one field or expression is required"); the constant-expression form is the equivalent, standard singleton recipe and renders as `CREATE UNIQUE INDEX ... ON "recruitment_orgprofile" (1) WHERE "pk" IS NOT NULL` on Postgres (verified against Django 6.0.7 `ddl_references.Expressions` / PG `_create_unique_sql`).*
  2. `recruitment/migrations/0009_orgprofile.py` amended to carry the constraint in the `CreateModel` options (0009 was generated but never applied to any real DB, so amending is safe). `.venv/Scripts/python.exe manage.py makemigrations --check --dry-run` → **"No changes detected"** (model and migration in sync).
  3. `get_org_profile()` wraps the `get_or_create` in `try/except OrgProfile.MultipleObjectsReturned` → returns `OrgProfile.objects.first()` for legacy multi-row schemas; with the constraint this never triggers, but the never-raises contract now holds unconditionally.
- **F2 (MINOR):** both tests' comments claimed "Migration 0010 seeds a row per test schema" — no 0010 exists yet (Task 5 adds it). Reworded to "Defensive: drop any pre-existing row so this test exercises the helper's own defaults."
- **Verification re-run:** `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q` → **3 passed in 7.76s**.

## Concerns

none
