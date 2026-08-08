# OrgProfile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a single per-tenant `OrgProfile` row as the one source of truth for organisation identity (name, tagline, address, contact, fee text, logo, accent color), migrate the existing NEEPCO data once, and switch every consumer (advertisement text/PDF, offer letter, portal branding, admin) to it.

**Architecture:** Tenant-schema singleton model in `recruitment/models.py`; lazy `get_org_profile()` helper (get_or_create, never raises) as the only creation path — deliberately not a `Client` signal (would race schema creation). Two migrations: `0009` creates the table, `0010` seeds from the legacy Advertisement company columns and removes them. Portal branding via a context processor + one CSS variable; admin is change-only.

**Tech Stack:** Django 6.0, django-tenants (schema-per-tenant), PostgreSQL 16, pytest + pytest-django (44 existing tests), Pillow (already installed), existing `talentflow.css` design system.

## Global Constraints

- NEEPCO-first: the seeded profile must reproduce today's NEEPCO branding exactly; multi-tenant onboarding stays a documented skeleton only (no wizard).
- All new models go in `TENANT_APPS` (recruitment is already there). OrgProfile lives in the tenant schema.
- Run `python manage.py migrate_schemas` after any model change — never plain `migrate`.
- Every feature ships pytest coverage; the full suite (46 tests) must stay green.
- Never break the LLM → deterministic fallback pattern (no LLM involvement in this feature).
- Tests/scripts run with `.venv/Scripts/python.exe` on Windows; tenant host is `neepco.localhost`.
- Commit format: `Phase 2: OrgProfile — <brief description>`.

---

### Task 1: OrgProfile model + migration 0009

**Files:**
- Modify: `recruitment/models.py` (append `OrgProfile` at the bottom)
- Test: `recruitment/test_org_profile.py` (create — see Task 2 note)
- Generated: `recruitment/migrations/0009_orgprofile.py`

**Interfaces:**
- Produces: `recruitment.models.OrgProfile` with fields `name_en` (CharField 200, required), `name_hi`, `tagline_en`, `tagline_hi` (CharField 200, blank), `address` (TextField, blank), `footer_motto` (CharField 300, blank), `contact_email` (EmailField, blank), `website` (URLField, blank), `sbi_epay_text` (TextField, blank), `logo` (ImageField upload_to="org_logos/", blank, null), `accent_color` (CharField 9, default "#0b3d91"), `created_at`/`updated_at` (auto). `__str__` returns `name_en`. Consumed by Tasks 2–6.

- [ ] **Step 1: Write the failing test**

Create `recruitment/test_org_profile.py`:

```python
"""OrgProfile — per-tenant organisation identity tests."""


def test_org_profile_model_created(tenant):
    from recruitment.models import OrgProfile

    OrgProfile.objects.create(name_en="Test Org")
    assert OrgProfile.objects.filter(name_en="Test Org").exists()
    assert OrgProfile.objects.get(name_en="Test Org").accent_color == "#0b3d91"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'recruitment.models.OrgProfile'` (ImportError).

- [ ] **Step 3: Append the model**

At the bottom of `recruitment/models.py`:

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

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Generate migration 0009**

Run: `.venv/Scripts/python.exe manage.py makemigrations recruitment`
Expected: creates `recruitment/migrations/0009_orgprofile.py` with only a `CreateModel` for OrgProfile. Do NOT touch the Advertisement fields yet (Task 5).

- [ ] **Step 6: Commit**

```bash
git add recruitment/models.py recruitment/migrations/0009_orgprofile.py recruitment/test_org_profile.py
git commit -m "Phase 2: OrgProfile — model + migration 0009"
```

---

### Task 2: get_org_profile() access helper

**Files:**
- Create: `recruitment/org_profile.py`
- Test: `recruitment/test_org_profile.py` (append)

**Interfaces:**
- Consumes: `OrgProfile` from Task 1; `tenants.models.Client`.
- Produces: `recruitment.org_profile.get_org_profile() -> OrgProfile` — singleton get_or_create; `name_en` defaults to the current tenant's `Client.name`, falling back to `connection.schema_name`, then `"Organisation"`. Never raises. Consumed by Tasks 3, 4, 6.

- [ ] **Step 1: Write the failing tests** (append to `recruitment/test_org_profile.py`)

```python
def test_get_org_profile_creates_singleton(tenant):
    from recruitment.models import OrgProfile
    from recruitment.org_profile import get_org_profile

    # Migration 0010 seeds a row per test schema; drop it so this test
    # exercises the helper's own get_or_create defaults.
    OrgProfile.objects.all().delete()
    first = get_org_profile()
    second = get_org_profile()
    assert first.pk == second.pk
    assert first.name_en == "NEEPCO"  # fixture Client name


def test_get_org_profile_no_client_fallback(tenant, monkeypatch):
    from tenants.models import Client

    def raise_does_not_exist(*args, **kwargs):
        raise Client.DoesNotExist

    monkeypatch.setattr(Client.objects, "get", raise_does_not_exist)

    from recruitment.models import OrgProfile
    from recruitment.org_profile import get_org_profile

    OrgProfile.objects.all().delete()  # drop the migration-seeded row
    profile = get_org_profile()
    assert profile.name_en  # falls back to schema name, non-empty
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'recruitment.org_profile'`.

- [ ] **Step 3: Create the helper**

Create `recruitment/org_profile.py`:

```python
"""Access helpers for the per-tenant OrgProfile singleton."""

from django.db import connection

from tenants.models import Client


def get_org_profile():
    """Return the current tenant's OrgProfile, creating it on first access.

    Never raises: name_en defaults to the tenant's Client.name (readable from
    tenant context because 'public' is in the search_path), falling back to
    the schema name. This helper is the tenant-onboarding skeleton — a new
    schema gets its profile on first access.
    """
    from .models import OrgProfile

    try:
        name = Client.objects.get(schema_name=connection.schema_name).name
    except Client.DoesNotExist:
        name = connection.schema_name

    profile, _ = OrgProfile.objects.get_or_create(
        defaults={
            "name_en": name or connection.schema_name or "Organisation",
            "name_hi": "",
            "tagline_en": "",
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

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add recruitment/org_profile.py recruitment/test_org_profile.py
git commit -m "Phase 2: OrgProfile — get_org_profile() lazy singleton helper"
```

---

### Task 3: Generator cutover — advertisement text, offer text, advertisement PDF

**Files:**
- Modify: `recruitment/views.py` — `generate_advt_text(advt)` (header block, REGISTRATION FEES section, contact line) and `generate_offer_text(app)` (hardcoded org string)
- Modify: `recruitment/advt_pdf.py` — `AdvtPDF` header, REGISTRATION FEES section, contact line
- Test: `recruitment/test_org_profile.py` (append)

**Interfaces:**
- Consumes: `get_org_profile()` (Task 2).
- Produces: same signatures as today — `generate_advt_text(advt) -> str`, `generate_offer_text(app) -> str`, `AdvtPDF.generate() -> bytes`. No consumer changes.

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_generate_advt_text_uses_org_profile(tenant, advertisement):
    from recruitment.org_profile import get_org_profile
    from recruitment.views import generate_advt_text

    org = get_org_profile()
    org.name_en = "ACME Energy Ltd"
    org.tagline_en = "Power For All"
    org.address = "123 Test Street"
    org.contact_email = "careers@acme.example"
    org.sbi_epay_text = "Pay Rs 500 via SBI ePay"
    org.save()
    advertisement.description = "Test company profile description."
    advertisement.save()

    text = generate_advt_text(advertisement)
    assert "ACME Energy Ltd" in text
    assert "Power For All" in text
    assert "123 Test Street" in text
    assert "careers@acme.example" in text
    assert "SBI ePay" in text
    assert "North Eastern Electric Power Corporation Limited" not in text


def test_generate_offer_text_uses_org_profile(tenant, application):
    from recruitment.org_profile import get_org_profile
    from recruitment.views import generate_offer_text

    org = get_org_profile()
    org.name_en = "ACME Energy Ltd"
    org.address = "123 Test Street"
    org.save()

    text = generate_offer_text(application)
    assert "ACME Energy Ltd" in text
    assert "123 Test Street" in text
    assert "North Eastern Electric Power Corporation Limited" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: FAIL — the two new tests fail because `generate_advt_text`/`generate_offer_text` still use the legacy fields / literal.

- [ ] **Step 3: Update `generate_advt_text` in `recruitment/views.py`**

Inside the function (first lines), add:

```python
    from .org_profile import get_org_profile

    org = get_org_profile()
```

Then replace the header block (currently `lines.append(f"{advt.company_name or 'North Eastern Electric Power Corporation Limited'}")` through the address line):

```python
    lines.append(org.name_en or "North Eastern Electric Power Corporation Limited")
    lines.append(org.tagline_en or "(A Government of India Enterprise)")
    lines.append(org.address or "")
```

Replace the REGISTRATION FEES section (currently gated on `advt.registration_fee_text`):

```python
    if org.sbi_epay_text:
        lines.append("REGISTRATION FEES")
        lines.append(org.sbi_epay_text)
        lines.append("")
```

Replace the contact line (currently gated on `advt.contact_email`):

```python
    if org.contact_email:
        lines.append(f"Contact e-mail ID of Recruitment Cell: {org.contact_email}")
```

Leave `advt.description or DEFAULT_COMPANY_PROFILE` untouched (per-ad content, not identity).

- [ ] **Step 4: Update `generate_offer_text` in `recruitment/views.py`**

Replace the hardcoded lines:

```python
    org = "North Eastern Electric Power Corporation Limited"
    lines = [
        org,
        "Brookland Compound, Lower New Colony, Shillong – 793003, Meghalaya",
```

with:

```python
    from .org_profile import get_org_profile

    _org = get_org_profile()
    lines = [
        _org.name_en or "North Eastern Electric Power Corporation Limited",
        _org.address or "Brookland Compound, Lower New Colony, Shillong – 793003, Meghalaya",
```

Leave the rest of the function (post/advt/candidate interpolation, `"For " + org` later in the body) — update that trailing `"For " + org` reference to `"For " + _org.name_en`.

- [ ] **Step 5: Update `recruitment/advt_pdf.py`**

At the top of the `generate` method (before the header block), add:

```python
        from .org_profile import get_org_profile

        org = get_org_profile()
```

Replace the header lines (currently `advt.company_name or "..."` / `advt.company_tagline or "..."` / `if advt.company_address:`):

```python
    pdf._mc(org.name_en or "North Eastern Electric Power Corporation Limited", align="C")
    ...
    pdf._mc(org.tagline_en or "(A Government of India Enterprise)", align="C")
    ...
    if org.address:
        pdf._mc(org.address, align="C")
```

Replace the REGISTRATION FEES block (currently `if advt.registration_fee_text:`):

```python
    if org.sbi_epay_text:
        pdf._section("REGISTRATION FEES")
        pdf._para(org.sbi_epay_text)
```

Replace the contact line (currently `if advt.contact_email:`):

```python
    if org.contact_email:
        pdf.ln(2)
        pdf._set_f("", 9.5)
        pdf.set_text_color(*COLOR_TEXT)
        pdf._mc(f"Contact e-mail ID of Recruitment Cell: {org.contact_email}")
```

Leave `advt.description or DEFAULT_COMPANY_PROFILE` untouched. Do NOT change any layout/colors (restyle is a later phase).

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: PASS (5 passed).

- [ ] **Step 7: Commit**

```bash
git add recruitment/views.py recruitment/advt_pdf.py recruitment/test_org_profile.py
git commit -m "Phase 2: OrgProfile — generators read OrgProfile (advt text, offer text, advt PDF)"
```

---

### Task 4: Form / template / command cutover

**Files:**
- Modify: `recruitment/forms.py` — `AdvertisementForm.Meta.fields`, `widgets`, `__init__` prefill
- Modify: `templates/recruitment/advertisement_create.html` — remove company field block + Registration Fees field
- Modify: `templates/recruitment/advertisement_report.html` + `recruitment/views.py` `advertisement_report` view — report title uses `org_profile.name_en`
- Modify: `recruitment/management/commands/populate_neepco_real.py` — remove company-field assignments
- Modify: `recruitment/boilerplate.py` — remove now-unused constants
- Test: `recruitment/test_org_profile.py` (append)

**Interfaces:**
- Consumes: `get_org_profile()` (Task 2).
- Produces: `advertisement_report` view context gains key `org_profile` (OrgProfile instance).

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_advt_form_has_no_company_fields():
    from recruitment.forms import AdvertisementForm

    legacy = ("company_name", "company_tagline", "company_address", "contact_email", "registration_fee_text")
    for field in legacy:
        assert field not in AdvertisementForm.Meta.fields


def test_advertisement_report_uses_org_profile(api_client, tenant, advertisement, viewer_user):
    from recruitment.org_profile import get_org_profile

    org = get_org_profile()
    org.name_en = "ACME Energy Ltd"
    org.save()

    api_client.force_login(viewer_user)  # report route is viewer-role
    resp = api_client.get(f"/advertisements/{advertisement.id}/report/")
    assert resp.status_code == 200
    assert "ACME Energy Ltd" in resp.content.decode()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: FAIL — both new tests fail (legacy fields still in the form; report still shows `advt.company_name`).

- [ ] **Step 3: Update `recruitment/forms.py`**

In `AdvertisementForm.Meta.fields`, remove `"company_name", "company_tagline", "company_address", "contact_email", "registration_fee_text"` (keep everything else). Remove the five matching entries from `widgets`. In `__init__`, delete the five prefill lines:

```python
            self.fields["company_name"].initial = "North Eastern Electric Power Corporation Limited"
            self.fields["company_tagline"].initial = "(A Government of India Enterprise)"
            self.fields["company_address"].initial = "Brookland Compound, Lower New Colony, Shillong – 793003, Meghalaya"
            self.fields["contact_email"].initial = DEFAULT_CONTACT_EMAIL
            self.fields["registration_fee_text"].initial = DEFAULT_FEE_TEXT
```

Remove `DEFAULT_CONTACT_EMAIL` and `DEFAULT_FEE_TEXT` from the `from .boilerplate import (...)` block if no longer referenced in this file (verify with a quick grep — they are only used in those prefill lines).

- [ ] **Step 4: Update `templates/recruitment/advertisement_create.html`**

Delete the Company Name / Tagline / Address / Contact Email field block (the `<div class="tf-field">` group containing `{{ form.company_name }}` through `{{ form.contact_email }}`) and the Registration Fees field block (`<label>Registration Fees</label>` + `{{ form.registration_fee_text }}`). Leave all other fields (advt number, title, description, dates, posts formset, health, general conditions, how to apply).

- [ ] **Step 5: Update the advertisement report view + template**

In `recruitment/views.py` `advertisement_report`, add to the final render context:

```python
        "org_profile": get_org_profile(),
```

(import: `from .org_profile import get_org_profile` at the top of the view function or module). In `templates/recruitment/advertisement_report.html`, change the report title from:

```django
<div class="report-title">{{ advt.company_name|default:"North Eastern Electric Power Corporation Limited" }}</div>
```

to:

```django
<div class="report-title">{{ org_profile.name_en|default:"Organisation" }}</div>
```

- [ ] **Step 6: Update `recruitment/management/commands/populate_neepco_real.py`**

Delete the five lines that set `advt.company_name`, `advt.company_tagline`, `advt.company_address`, `advt.contact_email`, `advt.registration_fee_text`. Remove `DEFAULT_CONTACT_EMAIL` and `DEFAULT_FEE_TEXT` from its boilerplate import if then unused (keep `DEFAULT_GENERAL_CONDITIONS`, `DEFAULT_HEALTH_TEXT`, `DEFAULT_HOW_TO_APPLY`). OrgProfile seeding is the migration's job (Task 5).

- [ ] **Step 7: Update `recruitment/boilerplate.py`**

Delete the now-unused constants `DEFAULT_COMPANY_NAME`, `DEFAULT_COMPANY_TAGLINE`, `DEFAULT_COMPANY_ADDRESS`, `DEFAULT_CONTACT_EMAIL`, `DEFAULT_FEE_TEXT`. Keep `DEFAULT_COMPANY_PROFILE`, `DEFAULT_LOCATION`, `DEFAULT_PERIOD`, `DEFAULT_GENERAL_CONDITIONS`, `DEFAULT_HEALTH_TEXT`, `DEFAULT_HOW_TO_APPLY` (still used). After deletion, grep the repo for each removed name to confirm zero references.

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: PASS (7 passed).

- [ ] **Step 9: Commit**

```bash
git add recruitment/forms.py templates/recruitment/advertisement_create.html templates/recruitment/advertisement_report.html recruitment/views.py recruitment/management/commands/populate_neepco_real.py recruitment/boilerplate.py recruitment/test_org_profile.py
git commit -m "Phase 2: OrgProfile — form/template/command cutover, report title from OrgProfile"
```

---

### Task 5: Remove legacy Advertisement company fields + migration 0010

**Files:**
- Modify: `recruitment/models.py` — delete the five Advertisement fields
- Generated: `recruitment/migrations/0010_remove_advertisement_company_fields.py` (then edited to add the seed RunPython)
- Test: `recruitment/test_org_profile.py` (append)

**Interfaces:**
- Consumes: `Advertisement` (historical model) — the seed reads the five legacy columns before they are dropped.
- Produces: migration `0010` with operations `[RunPython(seed_org_profile), RemoveField ×5]` in that exact order.

- [ ] **Step 1: Write the failing test** (append)

```python
def test_advertisement_has_no_company_fields():
    from recruitment.models import Advertisement

    legacy = ("company_name", "company_tagline", "company_address", "contact_email", "registration_fee_text")
    for field in legacy:
        assert not hasattr(Advertisement, field)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: FAIL — `hasattr(Advertisement, "company_name")` is still True.

- [ ] **Step 3: Remove the fields from the model**

In `recruitment/models.py`, delete the `# Organisation header` block:

```python
    company_name = models.CharField(max_length=200, blank=True, default="North Eastern Electric Power Corporation Limited")
    company_tagline = models.CharField(max_length=200, blank=True, default="(A Government of India Enterprise)")
    company_address = models.CharField(max_length=300, blank=True, default="Brookland Compound, Lower New Colony, Shillong – 793003, Meghalaya")
    contact_email = models.CharField(max_length=120, blank=True, default="recruitment@neepco.co.in")
    registration_fee_text = models.TextField(blank=True)
```

- [ ] **Step 4: Generate migration 0010**

Run: `.venv/Scripts/python.exe manage.py makemigrations recruitment`
Expected: creates `recruitment/migrations/0010_remove_advertisement_company_fields.py` with five `RemoveField` operations (order may vary — the seed must run first, so edit the operations list as follows).

- [ ] **Step 5: Add the seed RunPython BEFORE the RemoveField operations**

Edit the generated migration — insert at the top of `operations`:

```python
def seed_org_profile(apps, schema_editor):
    """Copy the first Advertisement's company block into OrgProfile once.

    Self-contained (no app imports): migrations must not depend on code that
    evolves. Runs before the legacy columns are dropped.
    """
    OrgProfile = apps.get_model("recruitment", "OrgProfile")
    if OrgProfile.objects.exists():
        return
    Advertisement = apps.get_model("recruitment", "Advertisement")
    advt = Advertisement.objects.order_by("id").first()
    if advt is not None:
        OrgProfile.objects.create(
            name_en=advt.company_name or "",
            name_hi="",
            tagline_en=advt.company_tagline or "",
            tagline_hi="",
            address=advt.company_address or "",
            contact_email=advt.contact_email or "",
            sbi_epay_text=advt.registration_fee_text or "",
        )
    else:
        OrgProfile.objects.create(name_en=schema_editor.connection.schema_name)
```

and add `migrations.RunPython(seed_org_profile, migrations.RunPython.noop),` as the FIRST element of `operations`, before all `RemoveField` entries. Note: with the test DB (no advertisements), the else-branch creates a profile named after the schema — acceptable.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: PASS (8 passed). The test DB migration must apply cleanly (it does during pytest setup — if it fails, the suite errors before tests run; that is the verification).

- [ ] **Step 7: Commit**

```bash
git add recruitment/models.py recruitment/migrations/0010_remove_advertisement_company_fields.py recruitment/test_org_profile.py
git commit -m "Phase 2: OrgProfile — drop legacy Advertisement company fields, seed data migration 0010"
```

---

### Task 6: Portal branding + admin

**Files:**
- Create: `portal/context_processors.py`
- Modify: `config/settings.py` — TEMPLATES `context_processors`
- Modify: `templates/portal/base_portal.html` — `<head>` accent var, header, footer
- Modify: `recruitment/admin.py` — `OrgProfileAdmin` + `OrgProfileForm`
- Test: `recruitment/test_org_profile.py` (append)

**Interfaces:**
- Consumes: `get_org_profile()` (Task 2), `OrgProfile` fields (Task 1).
- Produces: template context key `org_profile` for all templates; admin registration of `OrgProfile` (change-only).

- [ ] **Step 1: Write the failing tests** (append)

```python
def test_portal_page_renders_org_branding(api_client, tenant):
    from recruitment.org_profile import get_org_profile

    org = get_org_profile()
    org.name_en = "ACME Energy Ltd"
    org.accent_color = "#123456"
    org.save()

    resp = api_client.get("/portal/login/")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "ACME Energy Ltd" in body
    assert "#123456" in body


def test_org_profile_admin_singleton():
    from django.contrib import admin as dj_admin

    from recruitment.models import OrgProfile

    model_admin = dj_admin.site._registry[OrgProfile]
    assert model_admin.has_add_permission(None) is False
    assert model_admin.has_delete_permission(None) is False


def test_accent_color_validation():
    from recruitment.admin import OrgProfileForm

    bad = OrgProfileForm(data={"name_en": "X", "accent_color": "red"})
    assert bad.is_valid() is False
    assert "accent_color" in bad.errors

    good = OrgProfileForm(data={"name_en": "X", "accent_color": "#0b3d91"})
    assert good.is_valid() is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: FAIL — portal page has no org name/accent (context processor not wired), admin not registered, `OrgProfileForm` import fails.

- [ ] **Step 3: Create the context processor**

Create `portal/context_processors.py`:

```python
"""Template context processors for the candidate portal."""


def org_profile(request):
    from recruitment.org_profile import get_org_profile

    return {"org_profile": get_org_profile()}
```

- [ ] **Step 4: Register it in `config/settings.py`**

In `TEMPLATES` → `OPTIONS` → `context_processors`, append:

```python
                "portal.context_processors.org_profile",
```

- [ ] **Step 5: Update `templates/portal/base_portal.html`**

In `<head>`, add before the stylesheet link:

```django
    <style>:root{--tf-accent:{{ org_profile.accent_color|default:'#0b3d91' }}}</style>
```

In the header block, render logo + name + tagline (guarded):

```django
    {% if org_profile.logo %}<img src="{{ org_profile.logo.url }}" alt="{{ org_profile.name_en }}" style="max-height:48px;margin-right:10px">{% endif %}
    <span class="portal-brand">{{ org_profile.name_en }}{% if org_profile.name_hi %} <span lang="hi">{{ org_profile.name_hi }}</span>{% endif %}</span>
    {% if org_profile.tagline_en %}<span class="portal-tagline">{{ org_profile.tagline_en }}</span>{% endif %}
```

In the footer block (guarded):

```django
    {% if org_profile.footer_motto %}<p>{{ org_profile.footer_motto }}</p>{% endif %}
    {% if org_profile.contact_email %}<p>{{ org_profile.contact_email }}</p>{% endif %}
    {% if org_profile.website %}<p><a href="{{ org_profile.website }}">{{ org_profile.website }}</a></p>{% endif %}
```

Fit these into the existing header/footer markup (the file is small — read it first and place the snippets in the header and footer containers, reusing existing classes where sensible; do not restructure the layout).

- [ ] **Step 6: Add the admin**

In `recruitment/admin.py`, add:

```python
import re

from django import forms
from django.utils.html import mark_safe

from .models import OrgProfile


class OrgProfileForm(forms.ModelForm):
    class Meta:
        model = OrgProfile
        fields = "__all__"

    def clean_accent_color(self):
        value = (self.cleaned_data.get("accent_color") or "").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise forms.ValidationError("Enter a hex color like #0b3d91.")
        return value


@admin.register(OrgProfile)
class OrgProfileAdmin(admin.ModelAdmin):
    form = OrgProfileForm
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

    @admin.display(description="Logo preview")
    def logo_preview(self, obj):
        if obj.logo:
            return mark_safe(f'<img src="{obj.logo.url}" height="48">')
        return "—"
```

(If `re`/`forms`/`mark_safe` are already imported in `recruitment/admin.py`, reuse the existing imports instead of adding duplicates.)

- [ ] **Step 7: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest recruitment/test_org_profile.py -q`
Expected: PASS (11 passed).

- [ ] **Step 8: Commit**

```bash
git add portal/context_processors.py config/settings.py templates/portal/base_portal.html recruitment/admin.py recruitment/test_org_profile.py
git commit -m "Phase 2: OrgProfile — portal branding (name, logo, accent) + change-only admin"
```

---

### Task 7: Final verification

**Files:** none new — verification only.

- [ ] **Step 1: Apply migrations to every schema**

Run: `.venv/Scripts/python.exe manage.py migrate_schemas`
Expected: applies 0009 + 0010 to `public` and `neepco`; no errors.

- [ ] **Step 2: Verify the NEEPCO seed**

Run:

```bash
.venv/Scripts/python.exe -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from django_tenants.utils import schema_context
from django.db import connection
with schema_context('neepco'):
    cur = connection.cursor()
    cur.execute('SELECT name_en, tagline_en, address, contact_email, sbi_epay_text FROM recruitment_orgprofile')
    row = cur.fetchone()
    print(row)
"
```

Expected: `name_en` = "North Eastern Electric Power Corporation Limited", `tagline_en` = "(A Government of India Enterprise)", address = the Shillong address, `contact_email` = "recruitment@neepco.co.in", `sbi_epay_text` non-empty — i.e. the legacy NEEPCO branding reproduced.

- [ ] **Step 3: Full test suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 57 passed (46 existing + 11 org_profile).

- [ ] **Step 4: Migration drift check**

Run: `.venv/Scripts/python.exe manage.py makemigrations --check --dry-run`
Expected: "No changes detected".

- [ ] **Step 5: Live E2E smoke**

Start server, run E2E:

```bash
.venv/Scripts/python.exe manage.py runserver 8123 --noreload   # in one terminal
.venv/Scripts/python.exe e2e_smoke.py                          # in another
```

Expected: 153 passed, 0 failed. The `advt_form_data()` payload in `e2e_smoke.py` already omits company fields, so no script change is required — but if the advt-create POST now fails form validation, update `advt_form_data()` accordingly.

- [ ] **Step 6: Visual spot-check (manual)**

1. `http://neepco.localhost:8000/admin/recruitment/orgprofile/` → change page shows NEEPCO data, no Add/Delete buttons.
2. `http://neepco.localhost:8000/portal/login/` → header shows NEEPCO name (EN), tagline; footer shows motto/contact; accent unchanged (#0b3d91 default).
3. `http://neepco.localhost:8000/advertisements/create/` → no company fields in the form.
4. `http://neepco.localhost:8000/advertisements/<id>/report/` → title shows "North Eastern Electric Power Corporation Limited" (from OrgProfile).
5. `http://neepco.localhost:8000/advertisements/<id>/pdf/` → header still shows the NEEPCO name.

- [ ] **Step 7: Commit any verification fixes** (only if Steps 1–5 surfaced bugs)

```bash
git add -A
git commit -m "Phase 2: OrgProfile — verification fixes"
```

---

## Self-Review Notes

- Spec §4 (model) → Task 1. Spec §5 (helper) → Task 2. Spec §8 (consumer cutover, all 8 rows) → Tasks 3–5. Spec §9 (portal) → Task 6. Spec §10 (admin) → Task 6. Spec §11 (error handling) → embedded in Tasks 2/6 (helper never raises, template guards, hex validation). Spec §12 (tests) → all 8 test cases mapped: singleton/no-client (Task 2), advt text/offer text (Task 3), form fields/report (Task 4), admin singleton/accent validation (Task 6), portal branding (Task 6). Spec §7 (onboarding skeleton) → documented, not built (Task 2's helper is the skeleton).
- Split migration rationale: 0009 (create) lands before any consumer stops using the legacy columns; 0010 (seed + drop) lands after no code references them — the app never has a broken intermediate state.
