### Task 12: Staff i18n (4.14) — COMPLETE

**Status:** Done  
**Date:** 2026-08-09

#### Changes Made

1. **Base template (`templates/base.html`)**
   - Added `{% load i18n %}` before first `{% trans %}` usage
   - Wrapped all sidebar nav items: Dashboard, Advertisements, Applications, Analytics, Duplicates, Grievances, Internal Postings, Consents, Admin
   - Wrapped Logout button, Back link, Skip to main content, default page title

2. **31 recruitment templates (`templates/recruitment/*.html`)**
   - Added `{% load i18n %}` to every template
   - Wrapped all user-visible English strings with `{% trans %}` or `{% blocktrans %}`
   - Categories of strings wrapped:
     - Page titles, subtitles, section titles
     - Table headers (`<th>` content)
     - Button text (Submit, Save, Cancel, Create, etc.)
     - Form labels (`<label>` content)
     - Link text (View →, Report →, etc.)
     - Status badges (Active, Closed, Verified, etc.)
     - Empty state messages ("No records found", etc.)
     - Aria-label attributes with user-visible text
     - `<option>` text in `<select>` elements
     - `<summary>` text in `<details>` elements
   - Mixed static/variable strings use `{% blocktrans with var=... %}...{% endblocktrans %}`
   - Plural forms use `{% blocktrans count %}...{% plural %}...{% endblocktrans %}`
   - Dynamic model display fields (`get_status_display`, etc.) left unwrapped
   - JS `DataTable` language strings left as-is (JS i18n is separate)

3. **Hindi translations (`locale/hi/LC_MESSAGES/django.po` + `.mo`)**
   - 600 msgid entries total (up from ~100 portal-only entries)
   - All 600 entries have Hindi translations
   - 0 untranslated, 0 fuzzy
   - Compiled to `.mo` via `polib`

4. **`fee_reconciliation.html`** — already had full i18n from prior work; untouched

#### Verification

- All 44 templates (31 recruitment + base + 12 portal) compile without errors via `get_template()`
- `.po` file validated: 600/600 entries translated
- `.mo` file compiled successfully

#### Commit
```
Phase 4: i18n — Hindi translations for staff templates
```
