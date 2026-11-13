# TalentFlow AI — Vercel + Supabase Deployment

## Architecture

| Layer | Service |
|---|---|
| App runtime | Vercel **Container Runtime** (`Dockerfile.vercel`) |
| Database | Existing Supabase project `ovqmhbnrkdwuumpyxntf` (`ap-south-1`) |
| Shared tables | `talentflow` schema (not `public`) |
| Tenant tables | `tf_neepco` schema |
| Uploaded files | Supabase Storage bucket `talentflow-media` (public-read URLs; writes gated by RLS) |
| Background tasks | Celery eager mode inside the request (no worker) |
| Static files | WhiteNoise, collected at image build time |

The existing `public` schema and the other application on that Supabase project
are not modified.

## Why a container?

Vercel's native Python runtime cannot install Tesseract. The container image
installs `tesseract-ocr`, `tesseract-ocr-eng`, `tesseract-ocr-hin`,
`fonts-dejavu-core`, PyMuPDF and fpdf2, so OCR works for scanned PDFs and
images, and generated advertisement/offer PDFs work too.

## Supabase setup (one-time)

Run as the Supabase `postgres` role:

```sql
CREATE ROLE talentflow_app LOGIN PASSWORD '<password>' NOSUPERUSER NOCREATEDB NOCREATEROLE;
GRANT talentflow_app TO postgres; -- needed to create an owned schema
GRANT CONNECT, CREATE ON DATABASE postgres TO talentflow_app;
GRANT USAGE ON SCHEMA public TO talentflow_app;
CREATE SCHEMA talentflow AUTHORIZATION talentflow_app;
GRANT ALL ON SCHEMA talentflow TO talentflow_app;
ALTER ROLE talentflow_app SET search_path = talentflow, public;
```

Create the bucket (public-read for demo file URLs):

```sql
INSERT INTO storage.buckets (id, name, public)
VALUES ('talentflow-media', 'talentflow-media', true)
ON CONFLICT (id) DO NOTHING;
```

Uploads and deletes use the publishable/anon key plus a private
`x-talentflow-storage-key` header. The header value is enforced by RLS policies
on `storage.objects`, so the public anon key alone cannot write:

```sql
-- replace <token> with a long random value stored in Vercel
CREATE POLICY "talentflow_media_insert" ON storage.objects
  FOR INSERT TO anon
  WITH CHECK (bucket_id = 'talentflow-media'
    AND coalesce(current_setting('request.headers', true), '{}')::json->>'x-talentflow-storage-key' = '<token>');

CREATE POLICY "talentflow_media_select" ON storage.objects
  FOR SELECT TO anon USING (bucket_id = 'talentflow-media');

CREATE POLICY "talentflow_media_update" ON storage.objects
  FOR UPDATE TO anon
  USING (bucket_id = 'talentflow-media'
    AND coalesce(current_setting('request.headers', true), '{}')::json->>'x-talentflow-storage-key' = '<token>')
  WITH CHECK (bucket_id = 'talentflow-media'
    AND coalesce(current_setting('request.headers', true), '{}')::json->>'x-talentflow-storage-key' = '<token>');

CREATE POLICY "talentflow_media_delete" ON storage.objects
  FOR DELETE TO anon
  USING (bucket_id = 'talentflow-media'
    AND coalesce(current_setting('request.headers', true), '{}')::json->>'x-talentflow-storage-key' = '<token>');
```

No S3 keys are needed. The Django backend is
`config.supabase_storage.SupabaseStorage`. It uploads/deletes through the
Storage REST API and returns public object URLs. Keep the token private; the
bucket is public-read for the demo.

If you prefer S3 credentials later, generate Storage → S3 keys and set
`SUPABASE_S3_ACCESS_KEY_ID` / `SUPABASE_S3_SECRET_ACCESS_KEY`; the settings
fall back to the S3 backend only when the REST variables are unset.

## Environment variables (Vercel)

See `.env.production` for the full list. The important ones:

```
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=talentflow-ai.vercel.app,.vercel.app
CSRF_TRUSTED_ORIGINS=https://talentflow-ai.vercel.app,https://*.vercel.app
PUBLIC_SCHEMA_NAME=talentflow
DEMO_TENANT_SCHEMA=tf_neepco
PRIMARY_DOMAIN=talentflow-ai.vercel.app
DB_NAME=postgres
DB_USER=talentflow_app.ovqmhbnrkdwuumpyxntf
DB_HOST=aws-1-ap-south-1.pooler.supabase.com
DB_PORT=5432
DB_SSLMODE=require
DB_CONN_MAX_AGE=0
SUPABASE_URL=https://ovqmhbnrkdwuumpyxntf.supabase.co
SUPABASE_ANON_KEY=<legacy-anon-key>
SUPABASE_STORAGE_ACCESS_TOKEN=<private-header-token>
SUPABASE_STORAGE_BUCKET=talentflow-media
PORT=8000
```

Vercel functions are IPv4-only, so the app uses Supabase's **session-mode
pooler** (`aws-1-…pooler.supabase.com:5432`). Direct `db.…supabase.co` is IPv6
only. Session mode is required by django-tenants because it issues
`SET search_path`; transaction mode would not preserve it.

## Local migrations and seeding

Use a Python 3.12+ environment (Django 6 cannot run on Python 3.9). Example
using a standalone build:

```bash
export DJANGO_SETTINGS_MODULE=config.settings
# Load .env values (PUBLIC_SCHEMA_NAME=talentflow, DEMO_TENANT_SCHEMA=tf_neepco,
# direct DB host or the pooler, DB_SSLMODE=require)
python manage.py migrate_schemas --shared --noinput
python manage.py setup_tenant
python manage.py migrate_schemas --noinput
python manage.py seed_staff_users
python manage.py seed_cloud_data
python manage.py seed_portal_demo
for cmd in simulate_roster_panel simulate_duplicates_consents \
           simulate_internal_posting simulate_workforce_planning simulate_talent_data; do
  python manage.py tenant_command "$cmd" --schema=tf_neepco
done
```

Note: `setup_tenant` creates the `tf_neepco` schema and runs its migrations the
first time. Re-running is idempotent.

## Deploying

1. Push the repository to GitHub.
2. Create a Vercel project linked to the repository with framework **container**
   and region **bom1**.
3. Add the environment variables above.
4. Deploy. Vercel builds `Dockerfile.vercel`, runs `collectstatic`, and starts
   gunicorn on `$PORT`.
5. Confirm `https://<project>.vercel.app/health/` returns `{"status":"ok","ocr":true}`.

## Demo data

| Data | Count |
|---|---|
| Advertisement | 1 (`NEEPCO/02/2026`, closes 31 Mar 2027) |
| Posts | 12 |
| Candidates | 70 |
| Applications | 126 |
| Portal users | 5 |
| Consents | 10 |
| Roster matrix rows | 60 |
| Panel entries | 43 |

Candidate portal accounts (OTP is displayed in the page message):

```
rahul.sharma@example.com
sneha.reddy@example.com
arjun.patel@example.com
priya.sharma@example.com
vikram.singh@example.com
```

Staff: `admin` / `admin123` (superuser), `a.sharma` / `employee123`, etc.

## Verification checklist

- `/health/` → `ocr: true`
- `/landing/` lists NEEPCO and 12 posts
- `/login/` staff login, dashboard loads (roster/panel data present)
- `/portal/login/` OTP login, dashboard shows 3 applications
- `/admin/` loads static assets
- Upload a scanned/image resume → `Resume.parse_status == "parsed"` and the
  signed Supabase Storage URL opens

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No tenant for hostname` | Add the Vercel hostname to `talentflow.tenants_domain` via `setup_tenant` with `PRIMARY_DOMAIN`. |
| `ENOTFOUND tenant/user` on the pooler | Use the `aws-1-ap-south-1` host and the `talentflow_app.<project-ref>` username. |
| `must be able to SET ROLE` when creating the schema | `GRANT talentflow_app TO postgres;` first. |
| OCR returns `failed` | Check `/health/` for `ocr: true`; confirm the deploy used `Dockerfile.vercel`, not the native Python runtime. |
| Media uploads fail with 403 | Confirm `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_STORAGE_ACCESS_TOKEN` and the RLS policies; the token must match. |
| Media URL 404 | The bucket is public-read; verify `storage.buckets.public = true` and the object path. |
| Large upload rejected | Vercel caps function request bodies at 4.5 MB. |
