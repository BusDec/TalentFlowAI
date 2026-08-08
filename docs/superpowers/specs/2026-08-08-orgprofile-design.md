# OrgProfile — Per-Tenant Organisation Identity (Phase 2.1)

**Date**: 2026-08-08
**Status**: Approved design — awaiting implementation plan
**Source**: `docs/specs/2026-08-08-production-grade-roadmap.md` §2.1
**Priority**: NEEPCO-focused. Multi-tenant onboarding is a documented skeleton only.

---

## 1. Problem

`Advertisement` carries the organisation's identity as five hardcoded columns
(`company_name`, `company_tagline`, `company_address`, `contact_email`,
`registration_fee_text`) with NEEPCO literals as model defaults. Consequences:

- Every tenant's advertisements say "NEEPCO, Shillong" (multi-tenancy is fake).
- The identity is duplicated per advertisement and can drift between ads.
- The advertisement **create form** still asks staff to type the company block
  on every single ad — wasted keystrokes, guaranteed drift.
- The offer letter generator hardcodes the org name as a Python string literal.

## 2. Goal

A single per-tenant `OrgProfile` row that is the **one source of truth** for
organisation identity. All generators (advertisement text, advertisement PDF,
offer letter) and the candidate portal (header/footer/accent color/logo) read
from it. Existing NEEPCO data is migrated once; the advertisement create form
stops asking for company fields.

Non-goals (explicitly out of scope for 2.1):
- Full tenant-onboarding wizard UI (documented skeleton only — §7).
- Government-format advertisement PDF restyle (that is 2.2; 2.1 only switches
  the PDF's data source, the layout stays as-is).
- Portal theming beyond one accent color + logo + text (no multi-color themes).

## 3. Decisions (approved)

1. **Model location**: tenant-schema `OrgProfile` in `recruitment/models.py`.
   One row per schema — the schema IS the tenant. No public-schema fields.
2. **Singleton creation**: lazy `get_org_profile()` — `get_or_create` on first
   access. Explicitly NOT a `Client` post_save signal: django-tenants runs
   tenant migrations during `Client.save()` (auto_create_schema), so a signal
   would query a table that does not exist yet and crash tenant creation.
3. **Legacy fields**: one-time data migration copies the values into OrgProfile,
   then the five Advertisement columns are **removed** (clean cutover, no
   second source of truth, no drift). All consumers switch to OrgProfile.
4. **Portal branding**: text (name EN/HI, tagline, contact, footer motto,
   website) + ONE accent color injected as a CSS variable + optional logo.
5. **Admin surface**: Django admin, change-only (no add/delete on the
   singleton). No new staff pages.

## 4. Model

New model in `recruitment/models.py` (tenant schema):

```python
class OrgProfile(models.Model):
    """Single per-tenant organisation identity row (schema == tenant)."""

    name_en = models.CharField(max_length=200)
    name_hi = models.CharField(max_length=200, blank=True)
    tagline_en = models.CharField(max_length=200, blank=True)
    tagline_hi = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    footer_motto = models.CharField(max_length=300, blank=True)
    contact_email = models.EmailField(blank=True)
    website = models.URLField(blank=True)
    sbi_epay_text = models.TextField(
        blank=True,
        help_text="Registration fee / SBI ePay payment instructions (moved from Advertisement.registration_fee_text).",
    )
    logo = models.ImageField(upload_to="org_logos/", blank=True, null=True)
    accent_color = models.CharField(
        max_length=9,
        default="#0b3d91",
        help_text="CSS hex color (e.g. #0b3d91) used for portal accent theming.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organisation Profile"

    def __str__(self):
        return self.name_en
```

Notes:
- `accent_color` default `#0b3d91` is a deep government blue, matching the
  current `--tf-accent` used across the design system; portal branding keeps
  the rest of the existing CSS untouched.
- No DB-level single-row constraint — schema scoping + the `get_or_create`
  helper + admin `has_add_permission=False` enforce the singleton.

## 5. Access helper

New file `recruitment/org_profile.py`:

```python
"""Access helpers for the per-tenant OrgProfile singleton."""

from django.db import connection

from tenants.models import Client


def get_org_profile():
    """Return the current tenant's OrgProfile, creating it on first access.

    Never raises: name_en defaults to the tenant's Client.name (readable from
    tenant context because 'public' is in the search_path), falling back to
    the schema name, then to a literal default. Used by generators, the portal
    context processor, and the admin.
    """
    from .models import OrgProfile

    try:
        name = Client.objects.get(schema_name=connection.schema_name).name
    except Client.DoesNotExist:
        name = connection.schema_name

    profile, _ = OrgProfile.objects.get_or_create(
        defaults={
            "name_en": name or connection.schema_name or "Organisation",
            "tagline_en": "",
            "name_hi": "",
            "tagline_hi": "",
            "address": "",
            "footer_motto": "",
            "contact_email": "",
            "website": "",
            "sbi_epay_text": "",
        }
    )
    return profile
```

This helper IS the tenant-onboarding skeleton (§7): a brand-new schema has no
OrgProfile row, and the first access (any generator, portal page, or admin)
creates it with the tenant's name. Nothing else is required to onboard.

## 6. Migration `recruitment/0009_orgprofile_and_remove_company_fields`

Operations, in order:

1. **`CreateModel OrgProfile`** — fields per §4.
2. **`RunPython(seed_org_profile, RunPython.noop)`** — self-contained (no
   `boilerplate` import — migrations must not depend on app code that evolves):
   - If an OrgProfile row already exists → return (idempotent).
   - Read the first `Advertisement` (order_by id) via the historical model.
   - Seed: `name_en` ← `advt.company_name`, else `""`; `name_hi` ← `""`;
     `tagline_en` ← `advt.company_tagline`; `tagline_hi` ← `""`;
     `address` ← `advt.company_address`; `contact_email` ← `advt.contact_email`;
     `sbi_epay_text` ← `advt.registration_fee_text`; all other fields blank,
     `accent_color` default.
   - If no Advertisement exists, seed a row with `name_en` set to the literal
     fallback (schema `neepco` → "NEEPCO" is NOT assumed; the migration runs
     per schema, so use the schema name via `connection.schema_name` as the
     name_en fallback) and everything else blank.
   - No `footer_motto` seed — left for admin to fill (do not invent an
     official-sounding motto).
3. **`RemoveField` × 5** on Advertisement: `company_name`, `company_tagline`,
   `company_address`, `contact_email`, `registration_fee_text`.

The seed runs before the removals so the source values are still readable.

## 7. Future: onboarding new tenants (skeleton — NOT built now)

Documented pattern for later:

1. Create the tenant (`tenants.Client` with `auto_create_schema=True` + a
   `Domain`) — existing path, no new UI.
2. First access to any OrgProfile consumer creates the row with
   `name_en = Client.name` (§5).
3. Branding is completed in Django admin (name_hi, tagline, logo, accent,
   motto, payment text).

If a wizard is ever wanted, it is a thin wrapper over these three steps; the
data layer needs no changes. Out of scope until a second tenant is real.

## 8. Consumer cutover (exact list)

All of these switch from Advertisement company fields / literals to
`get_org_profile()`:

| # | File | Change |
|---|---|---|
| 1 | `recruitment/views.py` `generate_advt_text(advt)` | Header block (L155-157): `advt.company_name/tagline/address` → `org.name_en`, `org.tagline_en`, `org.address`. REGISTRATION FEES section (L208-210): `advt.registration_fee_text` → `org.sbi_epay_text`. Contact line (L213-214): `advt.contact_email` → `org.contact_email`. `DEFAULT_COMPANY_PROFILE` stays as the `advt.description` fallback (per-ad content, not identity). |
| 2 | `recruitment/views.py` `generate_offer_text(app)` | Replace the hardcoded `org = "North Eastern Electric Power Corporation Limited"` string and the hardcoded address line with `get_org_profile()` `name_en` + `address` (fall back to current literals if blank). |
| 3 | `recruitment/advt_pdf.py` `AdvtPDF` | Header (L176-183): company name/tagline/address → OrgProfile. REGISTRATION FEES section (L228-230) → `org.sbi_epay_text`. Contact line (L232-236) → `org.contact_email`. Data source only — layout/restyle is 2.2. |
| 4 | `recruitment/forms.py` `AdvertisementForm` | Remove the 5 fields from `Meta.fields`, their `widgets` entries, and the prefill assignments (L50-54). Keep `DEFAULT_*` boilerplate imports only if still used. |
| 5 | `recruitment/models.py` `Advertisement` | Remove the 5 fields (L18-23) — handled by migration. |
| 6 | `recruitment/management/commands/populate_neepco_real.py` | Remove the 5 company-field assignment lines (L171-176); OrgProfile is seeded by the migration. Keep `description`/boilerplate-section assignments. |
| 7 | `templates/recruitment/advertisement_create.html` | Remove the Company Name/Tagline/Address/Contact Email field block (L47-61) and the Registration Fees field (L77-78). |
| 8 | `templates/recruitment/advertisement_report.html` | Report title (L15): `advt.company_name|default:"NEEPCO..."` → `org_profile.name_en`. The `advertisement_report` view adds `org_profile=get_org_profile()` to its render context (explicit context, matching how the view already builds its context dict). |

## 9. Portal branding

- New `portal/context_processors.py`:
  ```python
  def org_profile(request):
      from recruitment.org_profile import get_org_profile
      return {"org_profile": get_org_profile()}
  ```
  Registered in `config/settings.py` TEMPLATES `context_processors` (applies
  to all templates; staff pages simply don't use the keys).
- `templates/portal/base_portal.html`:
  - `<head>`: `<style>:root{--tf-accent:{{ org_profile.accent_color|default:'#0b3d91' }}}</style>`.
  - Header: logo image when `org_profile.logo` exists; `name_en`; `name_hi`
    in a `<span lang="hi">` when present; `tagline_en`.
  - Footer: `footer_motto`, `contact_email`, `website` link — each guarded
    (`{% if %}`) so blank fields render nothing.
- Logo is optional; missing logo/file errors must never break a page.

## 10. Admin

`recruitment/admin.py`:

```python
@admin.register(OrgProfile)
class OrgProfileAdmin(admin.ModelAdmin):
    list_display = ["name_en", "tagline_en", "contact_email", "updated_at"]
    fieldsets = (
        ("Branding", {"fields": ("name_en", "name_hi", "tagline_en", "tagline_hi", "logo", "accent_color")}),
        ("Contact", {"fields": ("address", "contact_email", "website", "footer_motto")}),
        ("Payments", {"fields": ("sbi_epay_text",)}),
    )
    readonly_fields = ["logo_preview"]

    def has_add_permission(self, request):
        return False  # singleton — created by get_org_profile()

    def has_delete_permission(self, request, obj=None):
        return False

    def logo_preview(self, obj):
        if obj.logo:
            return mark_safe(f'<img src="{obj.logo.url}" height="48">')
        return "—"
```

`accent_color` hex validation: `clean()` on the admin form
(`OrgProfileAdmin.get_form` → override `form` with a ModelForm whose
`clean_accent_color` regex-validates `^#[0-9a-fA-F]{6}$`; invalid → ValidationError).

## 11. Error handling

- `get_org_profile()` never raises: `Client.DoesNotExist` → schema-name
  fallback; `get_or_create` handles the race on first access.
- Templates guard every optional OrgProfile value with `{% if %}` — blank
  fields and a missing logo render nothing.
- `accent_color` is admin-validated; an invalid value can only enter via raw
  DB writes, and the CSS var with an invalid color is ignored by browsers
  (falls back to inherited `--tf-accent`) — no crash path.
- Logo uploads use Django `ImageField` validation (Pillow, already installed).

## 12. Testing (`recruitment/test_org_profile.py`, new)

| Test | Asserts |
|---|---|
| `test_get_org_profile_creates_singleton` | First call creates a row; second call returns the same id; `name_en` == tenant Client name. |
| `test_get_org_profile_no_client_fallback` | With no matching `Client`, returns a profile (never raises) with a non-empty name. |
| `test_generate_advt_text_uses_org_profile` | Set OrgProfile to a distinct name/tagline/fee text; `generate_advt_text(advt)` contains them and not the hardcoded NEEPCO literal. |
| `test_generate_offer_text_uses_org_profile` | Offer text contains OrgProfile `name_en`/`address`. |
| `test_advt_form_has_no_company_fields` | `AdvertisementForm` Meta fields exclude all five legacy company fields. |
| `test_portal_page_renders_org_branding` | GET portal login/register page: contains `name_en` and the accent color var. |
| `test_org_profile_admin_singleton` | Admin registry entry has `has_add_permission` and `has_delete_permission` returning False. |
| `test_accent_color_validation` | Admin form rejects `"red"`, accepts `#0b3d91`. |

Migration correctness is verified operationally: after implementation, run
`manage.py migrate_schemas` and assert the `neepco` OrgProfile row contains the
copied NEEPCO values (`SELECT * FROM neepco.recruitment_orgprofile`).

## 13. Commands to run after implementation

1. `manage.py makemigrations recruitment` (generate 0009)
2. `manage.py migrate_schemas` (both schemas)
3. `pytest -q` (full suite)
4. Live E2E: `manage.py runserver 8123 --noreload` + `python e2e_smoke.py`
   (151+ checks must stay green — the advt create POST no longer sends
   company fields; update `e2e_smoke.py` `advt_form_data()` if the form
   changes make the payload invalid)

## 14. Commit format

`Phase 2: OrgProfile — <brief>` (e.g. `Phase 2: OrgProfile — model, data
migration, generator cutover, portal branding`).
