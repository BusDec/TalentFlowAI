"""Live-server E2E smoke: walks every URL route x role over real HTTP.

Run against `manage.py runserver 8123` (tenant host neepco.localhost).
Creates scratch rows (E2E-* ids), exercises every route as each role,
asserts role gating + side effects, then cleans up. Exits non-zero on failure.
"""

import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

BASE = "http://neepco.localhost:8123"
PORT = 8123

USERS = {
    "viewer": ("k.nath", "employee123"),
    "recruiter": ("r.mehta", "employee123"),
    "hr_manager": ("a.sharma", "employee123"),
    "org_admin": ("admin", "admin123"),  # superuser — bypasses all gates
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # surface 3xx as HTTPError so statuses are exact


class Session:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            NoRedirect, urllib.request.HTTPCookieProcessor(self.jar)
        )

    def _cookie(self, name):
        for c in self.jar:
            if c.name == name:
                return c.value
        return None

    def req(self, method, path, data=None):
        url = BASE + path
        headers = {
            "User-Agent": "e2e-smoke/1.0",
            "Referer": url,  # CSRF referer check
        }
        body = None
        if data:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            resp = self.opener.open(request, timeout=30)
            return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")

    def login(self, username, password):
        code, html = self.req("GET", "/login/")
        assert code == 200, f"login page {code}"
        m = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)
        token = m.group(1) if m else self._cookie("csrftoken") or ""
        code, _ = self.req(
            "POST",
            "/login/",
            {"username": username, "password": password, "csrfmiddlewaretoken": token},
        )
        assert code == 302, f"login POST {code} for {username}"
        code, _ = self.req("GET", "/")
        assert code in (200, 302), f"dashboard after login {code} for {username}"

    def csrf_token(self):
        return self._cookie("csrftoken") or ""


def main():
    from django_tenants.utils import schema_context

    with schema_context("neepco"):
        from recruitment.models import (
            Advertisement,
            Application,
            AuditEvent,
            Candidate,
            CommunicationLog,
            DuplicateFlag,
            PanelList,
            Post,
            RosterMatrix,
        )

        advt = Advertisement.objects.order_by("id").first()
        post = advt.posts.first()
        real_app = Application.objects.order_by("id").first()
        panel = PanelList.objects.order_by("id").first()

        # ---- idempotent: purge leftovers from a previous crashed run ----
        AuditEvent.objects.filter(application__application_id__startswith="E2E-").delete()
        Application.objects.filter(application_id__startswith="E2E-").delete()
        Advertisement.objects.filter(advt_number__startswith="E2E-").delete()
        Candidate.objects.filter(email__startswith="e2e").delete()

        # ---- scratch data (E2E-* ids, cleaned up at the end) ----
        cand = Candidate.objects.create(
            first_name="E2E", last_name="Scratch", email="e2e@example.com", mobile="1111111111"
        )
        s_app = Application.objects.create(
            post=post, candidate=cand, application_id="E2E-TEST-001", status="received"
        )
        s_panel = PanelList.objects.create(
            post=post, application=s_app, panel_rank=999, is_active=True
        )
        cand2 = Candidate.objects.create(
            first_name="E2E2", last_name="Scratch", email="e2e2@example.com"
        )
        s_flag = DuplicateFlag.objects.create(
            candidate=cand2,
            application_a=real_app,
            application_b=s_app,
            confidence=50,
            match_fields=["email"],
        )
        s_advt = Advertisement.objects.create(
            advt_number="E2E-ADVT-001",
            title="E2E Scratch",
            published_date="2026-01-01",
            closing_date="2026-12-31",
        )
        s_post = Post.objects.create(
            advertisement=s_advt,
            name="E2E Post",
            post_code="E2E-01",
            vacancies=1,
            qualification="Any",
            category_breakup={"ur": 1},
        )

        from profiles.models import CandidateProfile

        s_profile = CandidateProfile.objects.create(
            candidate=cand, aadhar_no="123456789012"
        )

        ids = dict(
            advt=advt.id,
            post=post.id,
            app=real_app.application_id,
            panel_post=panel.post_id,
            panel=panel.id,
            s_app=s_app.application_id,
            s_post=s_post.id,
            s_panel=s_panel.id,
            s_flag=s_flag.id,
            s_profile=s_profile.id,
        )
        with open("e2e_ids.json", "w") as fh:
            json.dump(ids, fh)

        A = ids["advt"]
        P = ids["post"]
        APP = ids["app"]
        SP = ids["s_post"]
        SAPP = ids["s_app"]
        SPANEL = ids["s_panel"]
        SFLAG = ids["s_flag"]
        SPROF = ids["s_profile"]

        def advt_form_data(number):
            return {
                "advt_number": number,
                "title": "E2E Created",
                "description": "",
                "published_date": "2026-09-01",
                "closing_date": "2026-12-31",
                "is_active": "on",
                "posts-TOTAL_FORMS": "1",
                "posts-INITIAL_FORMS": "0",
                "posts-MIN_NUM_FORMS": "1",
                "posts-MAX_NUM_FORMS": "1000",
                "posts-0-name": "E2E Engineer",
                "posts-0-post_code": "E2E-ENG",
                "posts-0-qualification": "Any",
                "posts-0-vacancies": "1",
                "posts-0-cat_ur": "1",
                "posts-0-cat_ews": "0",
                "posts-0-cat_obc": "0",
                "posts-0-cat_sc": "0",
                "posts-0-cat_st": "0",
            }

        # (label, method, path, data, allow)
        GETS = [
            ("dashboard", "GET", "/", None, ["viewer", "recruiter", "hr_manager", "org_admin"]),
            ("advt_list", "GET", "/advertisements/", None, ["viewer"]),
            ("advt_detail", "GET", f"/advertisements/{A}/", None, ["viewer"]),
            ("advt_report", "GET", f"/advertisements/{A}/report/", None, ["viewer"]),
            ("advt_create", "GET", "/advertisements/create/", None, ["hr_manager"]),
            ("advt_generate", "GET", f"/advertisements/{A}/generate/", None, ["hr_manager"]),
            ("advt_pdf", "GET", f"/advertisements/{A}/pdf/", None, ["hr_manager"]),
            ("app_list", "GET", "/applications/", None, ["viewer"]),
            ("app_export", "GET", "/applications/export/", None, ["viewer"]),
            ("app_detail", "GET", f"/applications/{APP}/", None, ["recruiter", "hr_manager"]),
            ("eligibility", "GET", f"/applications/{APP}/eligibility/", None, ["recruiter"]),
            ("offer_get", "GET", f"/applications/{APP}/offer/", None, ["recruiter", "org_admin"]),
            ("comms_get", "GET", f"/applications/{APP}/communications/", None, ["recruiter", "hr_manager"]),
            ("roster_get", "GET", f"/roster/{P}/", None, ["recruiter", "hr_manager"]),
            ("shortlist", "GET", f"/shortlist/{P}/", None, ["recruiter"]),
            ("panel", "GET", f"/panel/{P}/", None, ["recruiter"]),
            ("int_posting", "GET", "/internal-postings/", None, ["viewer"]),
            ("dup_queue", "GET", "/duplicates/", None, ["recruiter"]),
            ("analytics", "GET", "/analytics/", None, ["viewer"]),
            ("consent_ledger", "GET", "/audit/consents/", None, ["hr_manager"]),
            ("consent_export", "GET", "/audit/consents/export/", None, ["hr_manager"]),
            ("profile_import", "GET", "/profile-import/", None, ["hr_manager"]),
        ]
        POSTS = [
            ("advt_create_post", "POST", "/advertisements/create/", advt_form_data("E2E-ADVT-002"), ["hr_manager"]),
            ("advt_report_post", "POST", f"/advertisements/{A}/report/", {"application_id": SAPP, "remarks": "e2e"}, ["viewer"]),
            ("app_detail_post", "POST", f"/applications/{SAPP}/", {"candidate_explanation": "e2e explanation"}, ["hr_manager"]),
            ("elig_post", "POST", f"/applications/{SAPP}/eligibility/", {}, ["recruiter"]),
            ("offer_post", "POST", f"/applications/{SAPP}/offer/", {}, ["org_admin"]),
            ("comms_post", "POST", f"/applications/{SAPP}/communications/", {"comm_type": "acknowledgement", "channel": "portal", "subject": "e2e", "body": "e2e body"}, ["hr_manager"]),
            ("digilocker_post", "POST", f"/applications/{SAPP}/digilocker-fetch/", {}, ["recruiter"]),
            ("roster_post", "POST", f"/roster/{SP}/", {"action": "generate"}, ["hr_manager"]),
            ("promote_post", "POST", f"/panel/{P}/promote/{SPANEL}/", {}, ["hr_manager"]),
            ("dup_resolve_post", "POST", f"/duplicates/{SFLAG}/resolve/", {"resolution": "false_positive"}, ["hr_manager"]),
        ]
        ADMIN_GETS = [
            ("admin_home", "GET", "/admin/", None),
            ("admin_audit", "GET", "/admin/recruitment/auditevent/", None),
            ("admin_profiles", "GET", "/admin/profiles/candidateprofile/", None),
            ("admin_apps", "GET", "/admin/recruitment/application/", None),
            ("admin_resumes", "GET", "/admin/recruitment/resume/", None),
        ]
        PORTAL_PUBLIC = [
            ("portal_register", "GET", "/portal/register/", 200),
            ("portal_login", "GET", "/portal/login/", 200),
            ("portal_dash", "GET", "/portal/", 302),
            ("portal_apps", "GET", "/portal/applications/", 302),
            ("portal_apply", "GET", f"/portal/apply/{A}/", 302),
            ("portal_app_detail", "GET", f"/portal/applications/{APP}/", 302),
        ]

    failures = []
    passed = 0

    def check(label, role, method, path, code, expected):
        nonlocal passed
        ok = code in expected
        if ok:
            passed += 1
        else:
            failures.append(f"{label} [{role}] {method} {path}: got {code}, expected {expected}")

    # ---- anonymous portal checks ----
    anon = Session()
    for label, method, path, want in PORTAL_PUBLIC:
        code, _ = anon.req(method, path)
        check(label, "anonymous", method, path, code, (want,))
    code, _ = anon.req("GET", "/login/")
    check("anon_login_page", "anonymous", "GET", "/login/", code, (200,))

    # ---- per-role checks ----
    for role, (username, password) in USERS.items():
        sess = Session()
        sess.login(username, password)
        token = sess.csrf_token()
        # admin is a superuser — by design it bypasses every role gate.
        bypass = role == "org_admin"
        for label, method, path, data, allow in GETS:
            code, _ = sess.req(method, path)
            if role in allow or bypass:
                check(label, role, method, path, code, (200, 302))
            else:
                check(label, role, method, path, code, (403,))
        for label, method, path, data, allow in POSTS:
            payload = dict(data or {})
            payload["csrfmiddlewaretoken"] = token
            code, _ = sess.req(method, path, payload)
            if role in allow or bypass:
                check(label, role, method, path, code, (200, 302))
            else:
                check(label, role, method, path, code, (403,))
        if role == "org_admin":
            for label, method, path, _ in ADMIN_GETS:
                code, _ = sess.req(method, path)
                check(label, role, method, path, code, (200,))
            # Admin change form must show a masked Aadhaar, never plaintext.
            code, body = sess.req("GET", f"/admin/profiles/candidateprofile/{SPROF}/change/")
            check("admin_profile_change", role, "GET", f"/admin/profiles/candidateprofile/{SPROF}/change/", code, (200,))
            if "XXXX-XXXX-9012" not in body or "123456789012" in body:
                failures.append("effect aadhar mask: change form does not mask Aadhaar")
            else:
                passed += 1
        code, _ = sess.req("POST", "/logout/", {"csrfmiddlewaretoken": token})
        check("logout", role, "POST", "/logout/", code, (302,))

    # ---- side-effect verification (ORM) ----
    with schema_context("neepco"):
        from recruitment.models import Application as AppM, AuditEvent, CommunicationLog, DuplicateFlag as FlagM, RosterMatrix

        promoted = AppM.objects.get(application_id=SAPP)
        if promoted.status != "offered":
            failures.append(f"effect promote: status={promoted.status}, expected offered")
        else:
            passed += 1
        if not AuditEvent.objects.filter(application_id=promoted.id, field_name="status").exists():
            failures.append("effect audit: no AuditEvent for promoted status change")
        else:
            passed += 1
        if not RosterMatrix.objects.filter(post_id=SP).exists():
            failures.append("effect roster: no RosterMatrix rows generated")
        else:
            passed += 1
        if not CommunicationLog.objects.filter(application=promoted).exists():
            failures.append("effect comms: no CommunicationLog created")
        else:
            passed += 1
        if FlagM.objects.get(id=SFLAG).resolution != "false_positive":
            failures.append("effect flag: resolution not updated")
        else:
            passed += 1
        if not Advertisement.objects.filter(advt_number="E2E-ADVT-002").exists():
            failures.append("effect advt: advertisement not created by POST")
        else:
            passed += 1
        bg = promoted.background_report
        if bg.status != "explained":
            failures.append(f"effect bg: status={bg.status}, expected explained")
        else:
            passed += 1

        # ---- cleanup ----
        AuditEvent.objects.filter(application=promoted).delete()
        Advertisement.objects.filter(advt_number="E2E-ADVT-002").delete()
        s_advt.delete()  # cascades s_post + roster rows
        s_flag.delete()
        s_panel.delete()
        promoted.delete()  # cascades bg report, comm logs
        cand.delete()
        cand2.delete()

    print(f"\nE2E RESULT: {passed} passed, {len(failures)} failed")
    for f in failures:
        print("  FAIL:", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
