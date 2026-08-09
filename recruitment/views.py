"""Internal HR views — recruitment workflow, roster, panels, duplicates."""

import csv
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import check_role, require_role
from agents import eligibility_verifier, interview_copilot, roster_compliance
from agents.fairness import compute_adverse_impact, compute_statistical_parity
from agents.shortlist import build_shortlist
from consent.models import Consent, ConsentEvent
from notifications import notify as send_notification
from .audit import log_audit
from .digilocker.client import DigiLockerError, fetch_documents, verify_signature
from .models import (
    Advertisement,
    Application,
    BackgroundReport,
    CategoryAllocation,
    CommunicationLog,
    Corrigendum,
    DuplicateFlag,
    EligibilityOverride,
    FetchedDocument,
    InternalApplication,
    InternalJobPosting,
    PanelList,
    Payment,
    Post,
    PostBasedRoster,
    RequisitionApproval,
    RosterMatrix,
    VacancyRequisition,
)
from .roster import build_roster


@login_required
@require_role("viewer", "recruiter", "hr_manager", "org_admin", "reviewer", "auditor")
def dashboard(request):
    total = Application.objects.count()
    by_status = {
        s: Application.objects.filter(status=s).count()
        for s, _ in Application.STATUS_CHOICES
    }
    roster_alerts = [
        row.breach_warning for row in RosterMatrix.objects.all() if row.breach_warning
    ]
    pending_duplicates = DuplicateFlag.objects.filter(resolution="pending").count()
    panel_promotable = PanelList.objects.filter(is_active=True, promoted_on__isnull=True).count()

    import json
    scored = Application.objects.exclude(resume_score=0)
    avg_score = round(sum(a.resume_score for a in scored) / len(scored), 1) if scored.exists() else 0
    top_applications = Application.objects.order_by("-resume_score")[:6]

    context = {
        "total": total,
        "by_status": by_status,
        "roster_alerts": roster_alerts,
        "pending_duplicates": pending_duplicates,
        "panel_promotable": panel_promotable,
        "advertisements": Advertisement.objects.filter(is_active=True).order_by("-published_date"),
        "avg_score": avg_score,
        "top_applications": top_applications,
        "funnel_data": json.dumps(by_status),
    }
    return render(request, "recruitment/dashboard.html", context)


@login_required
@require_role("viewer")
def advertisement_list(request):
    return render(
        request,
        "recruitment/advertisement_list.html",
        {"advertisements": Advertisement.objects.all()},
    )


@login_required
@require_role("hr_manager")
def advertisement_create(request):
    from .forms import AdvertisementForm, PostFormSet

    if request.method == "POST":
        form = AdvertisementForm(request.POST)
        if form.is_valid():
            advt = form.save(commit=False)
            formset = PostFormSet(request.POST, instance=advt)
            if formset.is_valid():
                advt.save()
                instances = formset.save(commit=False)
                for post_form in formset.forms:
                    if post_form.cleaned_data and not post_form.cleaned_data.get("DELETE"):
                        post = post_form.save(commit=False)
                        post.category_breakup = post_form.cleaned_data.get("category_breakup") or {}
                        post.required_certificates = post_form.cleaned_data.get("required_certificates") or []
                        post.save()
                formset.save_m2m()
                messages.success(request, f"Advertisement {advt.advt_number} created successfully.")
                return redirect("advertisement_detail", advt_id=advt.id)
        else:
            formset = PostFormSet()
    else:
        form = AdvertisementForm(initial={"is_active": True})
        formset = PostFormSet()

    return render(
        request,
        "recruitment/advertisement_create.html",
        {"form": form, "formset": formset},
    )


@login_required
@require_role("hr_manager")
def advertisement_generate(request, advt_id):
    """Render a NEEPCO/THDC-format advertisement text for copy/print."""
    advt = get_object_or_404(Advertisement, id=advt_id)
    text = generate_advt_text(advt)
    return render(
        request,
        "recruitment/advertisement_generated.html",
        {"advt": advt, "advt_text": text},
    )


@login_required
@require_role("hr_manager")
def advertisement_pdf(request, advt_id):
    """Download a formatted PDF advertisement matching the NEEPCO layout."""
    from .advt_pdf import generate_advertisement_pdf

    advt = get_object_or_404(Advertisement, id=advt_id)
    data = generate_advertisement_pdf(advt)
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{advt.advt_number}.pdf"'
    return response


def generate_advt_text(advt):
    """Build the full advertisement text in the exact NEEPCO/THDC format."""
    from .org_profile import get_org_profile

    org = get_org_profile()

    from .boilerplate import (
        DEFAULT_COMPANY_PROFILE,
        DEFAULT_HOW_TO_APPLY,
    )

    def _d(value):
        if isinstance(value, str):
            try:
                value = datetime.date.fromisoformat(value)
            except ValueError:
                return value
        return value.strftime("%d-%m-%Y") if value else ""

    def _num_words(n):
        words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
                 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}
        return words.get(n, str(n))

    lines = []
    # Header
    lines.append(org.name_en or "North Eastern Electric Power Corporation Limited")
    lines.append(org.tagline_en or "(A Government of India Enterprise)")
    lines.append(org.address or "")
    lines.append("")
    lines.append(f"Date {_d(advt.published_date)}    Advertisement .No.{advt.advt_number}")
    lines.append("")
    lines.append("COMPANY PROFILE")
    lines.append(advt.description or DEFAULT_COMPANY_PROFILE)
    lines.append("")
    lines.append(advt.title.upper())
    lines.append("")
    lines.append("NEEPCO is looking for experienced professionals on Fixed Term Basis, as per details given below:")
    lines.append("")

    # Posts
    for idx, post in enumerate(advt.posts.all(), start=1):
        lines.append(f"{idx}. Name of the Post: {post.name}")
        lines.append(f"Post Code No: {post.post_code}")
        breakups = post.category_breakup_display or f"UR-{post.vacancies}"
        lines.append(f"No. of Posts: {_num_words(post.vacancies)} ({breakups})")
        if post.max_age:
            lines.append(f"Maximum Age: {post.max_age} years as on {_d(advt.closing_date)}")
        if post.period_of_engagement:
            lines.append(f"Period of Engagement: {post.period_of_engagement}")
        lines.append(f"Required Qualification: {post.qualification}")
        if post.experience_required:
            lines.append(f"Experience profile of the candidate: {post.experience_required}")
        if post.pay_scale:
            lines.append(f"Remuneration: Consolidated minimum monthly compensation will be {post.pay_scale}")
            lines.append("Additionally, HRA or Company Accommodation and Medical facility for self, spouse, 2 children and dependent parents.")
        if post.location:
            lines.append(f"Location: {post.location}")
        lines.append("")

    # Registration schedule
    lines.append(f"Schedule of online registration etc against Advt. No- {advt.advt_number}")
    lines.append(f"Commencement of Online registration of Application: {_d(advt.published_date)}")
    lines.append(f"Closing of Online registration of Application: {_d(advt.closing_date)}")
    lines.append("")

    # Boilerplate sections
    lines.append("HEALTH")
    lines.append(advt.health_text or "The candidate should have sound health. Before joining, candidates will have to undergo medical examination and obtain a Medical certificate stating medical fitness.")
    lines.append("")

    lines.append("GENERAL CONDITIONS")
    lines.append(advt.general_conditions or "As per company recruitment rules.")
    lines.append("")

    lines.append("HOW TO APPLY")
    lines.append(advt.how_to_apply or DEFAULT_HOW_TO_APPLY)
    lines.append("")

    if org.sbi_epay_text:
        lines.append("REGISTRATION FEES")
        lines.append(org.sbi_epay_text)
        lines.append("")

    if org.contact_email:
        lines.append(f"Contact e-mail ID of Recruitment Cell: {org.contact_email}")

    return "\n".join(lines)


@login_required
@require_role("viewer")
def advertisement_detail(request, advt_id):
    advt = get_object_or_404(Advertisement, id=advt_id)
    corrigenda = advt.corrigenda.filter(is_active=True)
    is_hr = False
    try:
        check_role(request, "hr_manager")
        is_hr = True
    except Exception:
        pass
    return render(
        request,
        "recruitment/advertisement_detail.html",
        {"advt": advt, "corrigenda": corrigenda, "is_hr_manager": is_hr},
    )


@login_required
@require_role("hr_manager")
@require_POST
def corrigendum_create(request, advt_id):
    """Create a corrigendum for an advertisement; auto-bumps version and notifies applicants."""
    advt = get_object_or_404(Advertisement, id=advt_id)
    changes_text = request.POST.get("changes_text", "").strip()
    if not changes_text:
        messages.error(request, "Changes text is required.")
        return redirect("advertisement_detail", advt_id=advt_id)

    next_version = (
        Corrigendum.objects.filter(advertisement=advt).count() + 1
    )
    corrigendum = Corrigendum.objects.create(
        advertisement=advt,
        version=next_version,
        changes_text=changes_text,
        published_date=timezone.now().date(),
    )

    # Notify all applicants for posts under this advertisement.
    applicants = (
        Application.objects.filter(post__advertisement=advt)
        .select_related("candidate")
        .distinct()
    )
    notified = 0
    for app in applicants:
        to = app.candidate.email or app.candidate.mobile or ""
        if not to:
            continue
        channel = "email" if "@" in to else "sms"
        ok, _ = send_notification(
            channel=channel,
            to=to,
            subject=f"Corrigendum v{corrigendum.version} — {advt.advt_number}",
            body=(
                f"Dear {app.candidate.first_name},\n\n"
                f"A corrigendum (v{corrigendum.version}) has been published for "
                f"advertisement {advt.advt_number} ({advt.title}).\n\n"
                f"Changes:\n{changes_text}\n\n"
                f"Please review the updated advertisement."
            ),
        )
        if ok:
            notified += 1

    messages.success(
        request,
        f"Corrigendum v{corrigendum.version} published. {notified} applicant(s) notified.",
    )
    return redirect("advertisement_detail", advt_id=advt_id)


_QUAL_STOPWORDS = {
    "and", "or", "the", "for", "with", "from", "into", "as", "to", "of", "in",
    "on", "at", "a", "an", "by", "is", "are", "has", "have", "be", "shall",
    "will", "must", "should", "full", "time", "basis", "years", "minimum",
    "experience", "candidate", "required", "engineering", "degree", "equivalent",
}


def _qual_keywords(text):
    import re
    return {w.lower() for w in re.findall(r"[A-Za-z]{4,}", text or "") if w.lower() not in _QUAL_STOPWORDS}


def _qualification_verdict(post, application):
    """Return (met, matched, total) — None met when it can't be judged."""
    resume = application.candidate.resumes.filter(parse_status="parsed").first()
    resume_text = ""
    if resume and resume.parsed_json:
        resume_text = " ".join(str(v) for v in resume.parsed_json.values()).lower()
    keywords = _qual_keywords(post.qualification)
    if not keywords:
        return None, 0, 0
    if not resume_text:
        # No parsed resume to check against — mark for human review rather
        # than reporting a misleading "Not Met".
        return None, 0, len(keywords)
    matched = [k for k in keywords if k in resume_text]
    met = len(matched) / len(keywords) >= 0.4
    return met, len(matched), len(keywords)


@login_required
@require_role("viewer")
def advertisement_report(request, advt_id):
    from .org_profile import get_org_profile

    advt = get_object_or_404(Advertisement, id=advt_id)

    if request.method == "POST":
        application_id = request.POST.get("application_id")
        remarks = request.POST.get("remarks", "").strip()
        app = Application.objects.filter(application_id=application_id).first()
        if app:
            app.evaluation_notes = remarks
            app.save(update_fields=["evaluation_notes"])
            messages.success(request, "Remarks saved.")
        return redirect("advertisement_report", advt_id=advt_id)

    posts = []
    for post in advt.posts.all().prefetch_related("applications__candidate__resumes"):
        apps = []
        for application in post.applications.select_related("candidate").all():
            met, matched, total = _qualification_verdict(post, application)
            resume = application.candidate.resumes.filter(parse_status="parsed").first()
            apps.append({
                "application": application,
                "met": met,
                "matched": matched,
                "total": total,
                "resume": resume,
                "evaluation": application.resume_evaluation or {},
            })
        posts.append({"post": post, "applications": apps})

    return render(
        request,
        "recruitment/advertisement_report.html",
        {"advt": advt, "posts": posts, "today": datetime.date.today(), "org_profile": get_org_profile()},
    )


@login_required
@require_role("viewer")
def application_list(request):
    applications = Application.objects.select_related("candidate", "post", "post__advertisement").all()

    status_filter = request.GET.get("status")
    if status_filter:
        applications = applications.filter(status=status_filter)

    advt_filter = request.GET.get("advt")
    if advt_filter:
        applications = applications.filter(post__advertisement_id=advt_filter)

    min_score = request.GET.get("min_score")
    if min_score:
        applications = applications.filter(resume_score__gte=min_score)

    q = request.GET.get("q", "").strip()
    if q:
        applications = applications.filter(
            models.Q(candidate__first_name__icontains=q)
            | models.Q(candidate__last_name__icontains=q)
            | models.Q(candidate__email__icontains=q)
            | models.Q(application_id__icontains=q)
        )

    return render(
        request,
        "recruitment/application_list.html",
        {
            "applications": applications,
            "all_statuses": Application.STATUS_CHOICES,
            "advertisements": Advertisement.objects.all(),
        },
    )


@login_required
@require_role("viewer")
def applications_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="applications.csv"'
    writer = csv.writer(response)
    writer.writerow(["Application ID", "Candidate", "Email", "Post", "Advertisement", "Score", "Status", "Applied At", "Employee Number"])
    for app in Application.objects.select_related("candidate", "post", "post__advertisement").all():
        writer.writerow([
            app.application_id,
            str(app.candidate),
            app.candidate.email,
            app.post.name,
            app.post.advertisement.advt_number,
            app.resume_score,
            app.status,
            app.applied_at.strftime("%Y-%m-%d") if app.applied_at else "",
            app.employee_number or "",
        ])
    return response


# Stages where an application can be rejected/withdrawn (excludes joined,
# rejected and withdrawn themselves).
REJECTION_STAGE_CHOICES = [
    s for s in Application.STATUS_CHOICES if s[0] not in ("joined", "rejected", "withdrawn")
]


@login_required
@require_role("recruiter", "hr_manager")
def application_detail(request, application_id):
    if request.method == "POST":
        check_role(request, "hr_manager")
    application = get_object_or_404(Application, application_id=application_id)
    background_report = getattr(application, "background_report", None)
    category_allocations = application.category_allocations.all()

    if request.method == "POST":
        if background_report:
            explanation = request.POST.get("candidate_explanation")
            reviewer_notes = request.POST.get("reviewer_notes")
            if explanation is not None and explanation.strip():
                background_report.candidate_explanation = explanation.strip()
                background_report.status = "explained"
            if reviewer_notes is not None and reviewer_notes.strip():
                background_report.reviewer_notes = reviewer_notes.strip()
                background_report.status = "reviewed"
                background_report.reviewed_by = request.user
            background_report.save()
            messages.success(request, "Background report updated.")

        category = request.POST.get("category")
        if category:
            obj, _ = CategoryAllocation.objects.get_or_create(
                application=application,
                category=category,
                defaults={"certificate_file": request.FILES.get("certificate_file")},
            )
            obj.is_verified = request.POST.get("is_verified") == "on"
            obj.save()
            verdict = roster_compliance.validate_offer(application, category, allocate_slot=True)
            if verdict.get("warning"):
                messages.warning(request, verdict["warning"])
            else:
                messages.success(request, "Category allocation validated.")

        new_status = request.POST.get("status")
        if new_status in dict(Application.STATUS_CHOICES):
            previous_status = application.status
            application.status = new_status
            if new_status == "withdrawn":
                # No stage chosen for withdrawals — mark the cross at the last
                # stage the application actually reached.
                if previous_status in dict(REJECTION_STAGE_CHOICES):
                    application.rejected_at_stage = previous_status
                elif not application.rejected_at_stage:
                    application.rejected_at_stage = "offered"
            elif new_status == "rejected":
                rejected_stage = request.POST.get("rejected_at_stage")
                if rejected_stage in dict(REJECTION_STAGE_CHOICES):
                    application.rejected_at_stage = rejected_stage
                elif not application.rejected_at_stage:
                    application.rejected_at_stage = "offered"
            if new_status == "joined" and not application.employee_number:
                application.employee_number = (
                    f"{request.tenant.code}/{application.application_id}"
                )
            application.save()
            messages.success(request, f"Status updated to {application.get_status_display()}.")

        return redirect("application_detail", application_id=application_id)

    context = {
        "application": application,
        "background_report": background_report,
        "category_allocations": category_allocations,
        "suggested_questions": interview_copilot.generate_questions(application.post),
        "category_choices": CategoryAllocation.CATEGORY_CHOICES,
        "resume": application.candidate.resumes.filter(parse_status="parsed").first(),
        "rejection_stage_choices": REJECTION_STAGE_CHOICES,
        "digilocker_consent": None,
        "fetched_documents": application.fetched_documents.all(),
    }
    portal_user = application.candidate.portal_user
    if portal_user:
        consent = Consent.objects.filter(
            candidate_portal_user=portal_user,
            purpose="digilocker",
        ).first()
        context["digilocker_consent"] = consent if consent and consent.is_active else None
    return render(request, "recruitment/application_detail.html", context)


@login_required
@require_role("recruiter")
@require_POST
def digilocker_fetch(request, application_id):
    """Fetch documents from DigiLocker / NAD — only with active candidate consent."""
    application = get_object_or_404(Application, application_id=application_id)
    portal_user = application.candidate.portal_user
    if not portal_user:
        messages.error(request, "Candidate has no portal account; cannot fetch documents.")
        return redirect("application_detail", application_id=application_id)

    consent = Consent.objects.filter(
        candidate_portal_user=portal_user, purpose="digilocker"
    ).first()
    if not consent or not consent.is_active:
        messages.error(request, "The candidate has not given active DigiLocker/NAD consent.")
        return redirect("application_detail", application_id=application_id)

    try:
        docs = fetch_documents(
            str(consent.id),
            candidate_email=application.candidate.email,
            dob=application.candidate.date_of_birth,
        )
    except DigiLockerError as exc:
        messages.error(request, f"DigiLocker fetch failed: {exc}")
        return redirect("application_detail", application_id=application_id)

    created = 0
    for doc in docs:
        _, was_created = FetchedDocument.objects.get_or_create(
            application=application,
            source=doc.source,
            doc_type=doc.doc_type,
            defaults={
                "issuer": doc.issuer,
                "issue_date": doc.issue_date,
                "data": doc.data,
                "signature_valid": verify_signature(doc),
            },
        )
        created += 1 if was_created else 0

    messages.success(
        request,
        f"Fetched {len(docs)} document(s) from DigiLocker/NAD ({created} new).",
    )
    return redirect("application_detail", application_id=application_id)


@login_required
@require_role("recruiter")
def run_eligibility(request, application_id):
    application = get_object_or_404(Application, application_id=application_id)
    override = getattr(application, "eligibility_override", None)

    if request.method == "POST":
        override_verdict = request.POST.get("override_verdict", "")
        override_reason = request.POST.get("override_reason", "").strip()

        if not override_reason:
            verdict = eligibility_verifier.verify_application(
                application,
                dob=application.candidate.date_of_birth,
                digilocker_consent="mock-consent-ref",
            )
            return render(
                request,
                "recruitment/eligibility_result.html",
                {
                    "verdict": verdict,
                    "override": override,
                    "override_error": "Reason is required.",
                },
            )

        verdict = override_verdict.lower() in ("on", "1", "true")
        previous = override.verdict if override is not None else None
        EligibilityOverride.objects.update_or_create(
            application=application,
            defaults={
                "verdict": verdict,
                "reason": override_reason,
                "overridden_by": request.user,
            },
        )
        log_audit(
            request.user,
            application,
            "eligibility_override",
            previous,
            verdict,
            reason=override_reason,
        )
        messages.success(request, "Eligibility override recorded.")
        return redirect("run_eligibility", application_id=application.application_id)

    verdict = eligibility_verifier.verify_application(
        application,
        dob=application.candidate.date_of_birth,
        digilocker_consent="mock-consent-ref",
    )
    return render(
        request,
        "recruitment/eligibility_result.html",
        {"verdict": verdict, "override": override},
    )


@login_required
@require_role("recruiter", "hr_manager")
def roster_view(request, post_id):
    if request.method == "POST":
        check_role(request, "hr_manager")
    post = get_object_or_404(Post, id=post_id)
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "generate":
            # Create one row per category in the post's category breakup.
            created = 0
            for category, count in (post.category_breakup or {}).items():
                if not count:
                    continue
                _, was_created = RosterMatrix.objects.get_or_create(
                    post=post,
                    category=category,
                    defaults={"vertical_vacancies": count},
                )
                created += 1 if was_created else 0
            messages.success(request, f"Roster rows synced from category breakup ({created} added).")

        elif action == "dopt_generate":
            dopt, created = PostBasedRoster.objects.get_or_create(
                post=post,
                defaults={
                    "cycle_start_year": timezone.now().year,
                    "roster_points": build_roster(post, timezone.now().year),
                },
            )
            if created:
                messages.success(request, "DoPT 100-point roster generated.")
            else:
                messages.info(request, "DoPT roster already exists for this post.")

        else:
            category = request.POST.get("category")
            if category in dict(RosterMatrix.CATEGORY_CHOICES):
                row, _ = RosterMatrix.objects.update_or_create(
                    post=post,
                    category=category,
                    defaults={
                        "vertical_vacancies": int(request.POST.get("vertical_vacancies") or 0),
                        "pwbd_horizontal_vacancies": int(request.POST.get("pwbd_horizontal_vacancies") or 0),
                        "carry_forward": request.POST.get("carry_forward") == "on",
                    },
                )
                messages.success(request, f"Roster updated for {row.get_category_display()}.")
        return redirect("roster_view", post_id=post_id)

    rows = RosterMatrix.objects.filter(post=post).select_related("post")
    try:
        dopt = post.roster
    except PostBasedRoster.DoesNotExist:
        dopt = None

    # Build 10×10 grid for template rendering.
    dopt_grid = []
    if dopt and dopt.roster_points:
        for row_idx in range(10):
            start = row_idx * 10
            dopt_grid.append(dopt.roster_points[start : start + 10])

    return render(
        request,
        "recruitment/roster.html",
        {
            "rows": rows,
            "post": post,
            "category_choices": RosterMatrix.CATEGORY_CHOICES,
            "dopt": dopt,
            "dopt_grid": dopt_grid,
        },
    )


@login_required
@require_role("recruiter")
def panel_view(request, post_id):
    entries = PanelList.objects.filter(post_id=post_id, is_active=True)
    return render(request, "recruitment/panel.html", {"entries": entries, "post_id": post_id})


@login_required
@require_role("hr_manager")
@require_POST
def panel_promote(request, post_id, panel_id):
    entry = get_object_or_404(PanelList, id=panel_id, post_id=post_id)
    application = entry.application
    if application.status in ("rejected", "withdrawn"):
        messages.error(request, "Application no longer promotable.")
    else:
        application.status = "offered"
        application.save(audit_actor=request.user)
        entry.promoted_on = timezone.now()
        entry.is_active = False
        entry.save()
        messages.success(request, f"Promoted {application} from panel.")
    return redirect("panel_view", post_id=post_id)


@login_required
@require_role("viewer")
def internal_posting_list(request):
    postings = InternalJobPosting.objects.all()
    return render(request, "recruitment/internal_posting_list.html", {"postings": postings})


@login_required
@require_role("recruiter")
def duplicates_queue(request):
    flags = DuplicateFlag.objects.select_related(
        "candidate", "application_a", "application_b"
    ).all()
    return render(request, "recruitment/duplicates.html", {"flags": flags})


@login_required
@require_role("hr_manager")
@require_POST
def duplicates_resolve(request, flag_id):
    flag = get_object_or_404(DuplicateFlag, id=flag_id)
    resolution = request.POST.get("resolution")
    if resolution in dict(DuplicateFlag.RESOLUTION_CHOICES):
        flag.resolution = resolution
        flag.resolved_by = request.user
        flag.resolved_at = timezone.now()
        flag.save()
        messages.success(request, "Duplicate flag resolved.")
    return redirect("duplicates_queue")


@login_required
@require_role("recruiter")
def shortlist_view(request, post_id):
    """Smart shortlist for a post — ranks candidates by composite score."""
    post = get_object_or_404(Post, id=post_id)
    keyword_input = request.GET.get("keywords", "")
    keywords = [k.strip() for k in keyword_input.split(",") if k.strip()]

    apps = post.applications.exclude(status__in=["rejected", "withdrawn"])
    if not keywords:
        # Default keywords pulled from the post qualification.
        import re
        words = re.findall(r"[A-Za-z]{4,}", post.qualification + " " + post.experience_required)
        keywords = list(dict.fromkeys(w.lower() for w in words))[:8]

    ranked = build_shortlist(apps, required_keywords=keywords)
    return render(
        request,
        "recruitment/shortlist.html",
        {"post": post, "ranked": ranked, "keywords": keywords},
    )


@login_required
@require_role("viewer")
def analytics_view(request):
    """Recruitment analytics: funnel conversion, category mix, score distribution."""
    import json
    from django.db.models import Count

    apps = Application.objects.all()
    total = apps.count()

    # Funnel conversion
    status_counts = {s: apps.filter(status=s).count() for s, _ in Application.STATUS_CHOICES}
    conversion = {}
    if total:
        order = ["received", "document_verification", "shortlisted", "interview", "offered", "joined"]
        for i, s in enumerate(order[:-1]):
            if status_counts.get(order[0], 0):
                conversion[s] = round(100 * status_counts.get(s, 0) / max(1, status_counts.get(order[0], 1)), 1)

    # Category mix
    from .models import CategoryAllocation
    category_counts = (
        CategoryAllocation.objects.values("category").annotate(c=Count("id")).order_by("-c")
    )

    # Score distribution buckets
    buckets = {
        "0-49": apps.filter(resume_score__lt=50).count(),
        "50-79": apps.filter(resume_score__gte=50, resume_score__lt=80).count(),
        "80-100": apps.filter(resume_score__gte=80).count(),
    }

    # Per-post volume
    post_counts = apps.values("post__name").annotate(c=Count("id")).order_by("-c")[:8]

    context = {
        "total": total,
        "status_counts": status_counts,
        "conversion": conversion,
        "category_counts": category_counts,
        "buckets": buckets,
        "post_counts": post_counts,
        "stage_cards": [
            ("shortlisted", "Shortlisted"),
            ("interview", "Interview"),
            ("offered", "Offered"),
            ("joined", "Joined"),
        ],
        "status_chart_data": json.dumps(status_counts),
        "bucket_chart_data": json.dumps(buckets),
        "post_chart_data": {p["post__name"]: p["c"] for p in post_counts},
    }
    return render(request, "recruitment/analytics.html", context)


@login_required
@require_role("recruiter", "org_admin")
def offer_letter(request, application_id):
    """Stream the offer letter as a PDF download (text via generate_offer_text stays for email)."""
    if request.method == "POST":
        check_role(request, "org_admin")
    application = get_object_or_404(Application, application_id=application_id)
    if application.status not in ("offered", "joined"):
        messages.warning(request, "Set the application status to 'Offered' first.")
    from .offer_pdf import OfferPDF

    response = HttpResponse(OfferPDF(application).generate(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="offer-{application.application_id}.pdf"'
    return response


def generate_offer_text(app):
    """Build a formal PSU-style offer letter in plain text."""
    cand = app.candidate
    post = app.post
    from .org_profile import get_org_profile

    _org = get_org_profile()
    lines = [
        _org.name_en or "North Eastern Electric Power Corporation Limited",
        _org.address or "Brookland Compound, Lower New Colony, Shillong – 793003, Meghalaya",
        "",
        "OFFER OF APPOINTMENT",
        f"Advertisement No: {post.advertisement.advt_number}",
        f"Application ID: {app.application_id}",
        f"Post Code: {post.post_code}",
        "",
        f"Dear {cand.first_name} {cand.last_name},",
        "",
        f"With reference to your application for the post of {post.name} against "
        f"Advertisement No. {post.advertisement.advt_number}, we are pleased to offer you "
        "appointment on Fixed Term Basis on the following terms:",
        "",
        f"1. Post: {post.name}",
        f"2. Post Code: {post.post_code}",
        f"3. Remuneration: {post.pay_scale or 'As per company policy'} (consolidated) plus "
        "HRA or Company Accommodation and medical facility as per policy.",
        f"4. Place of Posting: Shillong or any Office/Project site of NEEPCO as per management discretion.",
        "5. Probation: As per company rules.",
        "6. You will be required to furnish satisfactory proof of identity, age, qualifications "
        "and medical fitness before joining.",
        "",
        "Please communicate your acceptance within 15 days of receipt of this letter.",
        "",
        "Yours faithfully,",
        "For " + _org.name_en,
        "",
        "(Authorised Signatory)",
        "Date: " + str(datetime.date.today()),
    ]
    return "\n".join(lines)


@login_required
@require_role("recruiter", "hr_manager")
def communications(request, application_id):
    """Communication hub — send and view candidate messages."""
    if request.method == "POST":
        check_role(request, "hr_manager")
    from .models import CommunicationLog

    application = get_object_or_404(Application, application_id=application_id)
    if request.method == "POST":
        comm_type = request.POST.get("comm_type")
        channel = request.POST.get("channel", "portal")
        subject = request.POST.get("subject", "")
        body = request.POST.get("body", "")
        if comm_type:
            CommunicationLog.objects.create(
                application=application,
                channel=channel,
                comm_type=comm_type,
                subject=subject,
                body=body,
            )
            messages.success(request, "Communication recorded.")
        return redirect("communications", application_id=application_id)

    logs = application.communications.all()
    return render(
        request,
        "recruitment/communications.html",
        {"application": application, "logs": logs},
    )


@login_required
@require_role("hr_manager")
def consent_ledger(request):
    consents = Consent.objects.select_related("candidate_portal_user").all()
    return render(request, "consent/ledger.html", {"consents": consents})


@login_required
@require_role("hr_manager")
def consent_ledger_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="consent_ledger.csv"'
    writer = csv.writer(response)
    writer.writerow(["Consent ID", "Candidate", "Purpose", "Granted At", "Expires At", "Revoked At", "Active"])
    for c in Consent.objects.select_related("candidate_portal_user").all():
        writer.writerow(
            [
                c.id,
                str(c.candidate_portal_user),
                c.purpose,
                c.granted_at,
                c.expires_at,
                c.revoked_at,
                c.is_active,
            ]
        )
    return response


@login_required
@require_role("viewer")
def fee_reconciliation(request):
    """Fee reconciliation dashboard — counts by status and exemption, with CSV export."""
    from django.db.models import Count, Sum

    payments = Payment.objects.select_related(
        "application", "application__candidate", "application__post"
    )

    # Aggregate counts by status.
    status_counts = dict(
        payments.values_list("status").annotate(count=Count("id")).values_list("status", "count")
    )

    # Aggregate counts by exemption.
    exempt_count = payments.filter(exempt=True).count()
    non_exempt_count = payments.filter(exempt=False).count()

    # Total collected from paid (non-exempt) payments.
    total_collected = (
        payments.filter(status="completed", exempt=False).aggregate(total=Sum("amount"))["total"]
        or 0
    )

    # CSV export.
    if request.GET.get("format") == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="fee_reconciliation.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Application ID", "Candidate", "Post", "Amount", "Status",
            "Exempt", "Exempt Reason", "Gateway", "Gateway Ref", "Paid At", "Created At",
        ])
        for p in payments:
            writer.writerow([
                p.application.application_id,
                str(p.application.candidate),
                str(p.application.post),
                p.amount,
                p.status,
                p.exempt,
                p.exempt_reason,
                p.gateway,
                p.gateway_ref,
                p.paid_at,
                p.created_at,
            ])
        return response

    context = {
        "payments": payments[:200],
        "status_counts": status_counts,
        "exempt_count": exempt_count,
        "non_exempt_count": non_exempt_count,
        "total_collected": total_collected,
    }
    return render(request, "recruitment/fee_reconciliation.html", context)


# ── Document Verification ────────────────────────────────────────────────────


@login_required
@require_role("recruiter", "hr_manager")
def verify_documents(request):
    """List pending documents and handle verify/reject actions."""
    from .models import DocumentVerification

    # Handle POST action (verify or reject)
    if request.method == "POST":
        dv_id = request.POST.get("verification_id")
        action = request.POST.get("action")
        comments = request.POST.get("comments", "").strip()

        dv = get_object_or_404(DocumentVerification, id=dv_id)

        if action in ("verified", "rejected"):
            old_status = dv.status
            dv.status = action
            dv.verifier = request.user
            dv.comments = comments
            dv.verified_at = timezone.now()
            dv.save()

            # Also update the legacy is_verified flag on the Document.
            doc = dv.document
            doc.is_verified = action == "verified"
            doc.verified_at = dv.verified_at if action == "verified" else None
            doc.save(update_fields=["is_verified", "verified_at"])

            # Write audit event.
            log_audit(
                request.user,
                dv.document.application,
                "document_verification",
                old_status,
                action,
                reason=comments or f"Document {action} by {request.user.username}",
            )

            messages.success(request, f"Document {action} successfully.")
            return redirect("verify_documents")

    # Filter by status
    status_filter = request.GET.get("status", "pending")
    verifications = DocumentVerification.objects.select_related(
        "document", "document__application", "document__application__candidate",
        "document__application__post", "verifier",
    ).all()

    if status_filter and status_filter != "all":
        verifications = verifications.filter(status=status_filter)

    # Counts for the summary bar
    from django.db.models import Count
    counts = dict(
        DocumentVerification.objects.values_list("status").annotate(c=Count("id")).values_list("status", "c")
    )

    context = {
        "verifications": verifications[:200],
        "status_filter": status_filter,
        "pending_count": counts.get("pending", 0),
        "verified_count": counts.get("verified", 0),
        "rejected_count": counts.get("rejected", 0),
        "total_count": sum(counts.values()),
    }
    return render(request, "recruitment/verify_documents.html", context)


@login_required
@require_role("viewer", "recruiter", "hr_manager")
def document_verification_dashboard(request):
    """Dashboard summary for document verification progress."""
    from django.db.models import Count, Q
    from .models import DocumentVerification

    total = DocumentVerification.objects.count()
    by_status = dict(
        DocumentVerification.objects.values_list("status").annotate(c=Count("id")).values_list("status", "c")
    )

    # Per-post breakdown
    per_post = (
        DocumentVerification.objects
        .values("document__application__post__name")
        .annotate(
            total=Count("id"),
            pending=Count("id", filter=Q(status="pending")),
            verified=Count("id", filter=Q(status="verified")),
            rejected=Count("id", filter=Q(status="rejected")),
        )
        .order_by("-total")
    )

    # Recent activity
    recent = DocumentVerification.objects.select_related(
        "document__application__candidate", "verifier",
    ).exclude(status="pending")[:20]

    context = {
        "total": total,
        "pending_count": by_status.get("pending", 0),
        "verified_count": by_status.get("verified", 0),
        "rejected_count": by_status.get("rejected", 0),
        "per_post": per_post,
        "recent": recent,
    }
    return render(request, "recruitment/document_verification_dashboard.html", context)


# ── Vacancy Requisition & Approval Workflow ─────────────────────────────────

# Role map: which role is required to act at each requisition approval stage.
_REQ_ROLE_MAP = {
    "finance": "recruiter",
    "hr": "hr_manager",
    "final": "org_admin",
}

# Status transition when a stage is approved.
_STAGE_STATUS_MAP = {
    "finance": "finance_approved",
    "hr": "reservation_certified",
    "final": "ca_approved",
}

# Next stage after each approval (None = workflow complete).
_NEXT_STAGE_MAP = {
    "finance": "hr",
    "hr": "final",
    "final": None,
}


def _log_requisition_audit(actor, requisition, old_status, new_status, reason=""):
    """Audit a requisition status change using the existing AuditEvent model."""
    log_audit(
        actor=actor,
        application=None,
        field_name="requisition_status",
        old_value=old_status,
        new_value=new_status,
        reason=reason,
    )


@login_required
@require_role("hr_manager")
def requisition_list(request):
    """List all vacancy requisitions."""
    requisitions = VacancyRequisition.objects.select_related("created_by").all()
    return render(request, "recruitment/requisition_list.html", {"requisitions": requisitions})


@login_required
@require_role("hr_manager")
def requisition_create(request):
    """Create a new vacancy requisition (initial status: draft)."""
    if request.method == "POST":
        post_name = request.POST.get("post_name", "").strip()
        count = request.POST.get("count", "0").strip()
        grade = request.POST.get("grade", "").strip()
        justification = request.POST.get("justification", "").strip()

        if not post_name or not count or not grade or not justification:
            messages.error(request, "All fields are required.")
            return render(request, "recruitment/requisition_create.html", {
                "post_name": post_name,
                "count": count,
                "grade": grade,
                "justification": justification,
            })

        req = VacancyRequisition.objects.create(
            post_name=post_name,
            count=int(count),
            grade=grade,
            justification=justification,
            status="draft",
            created_by=request.user,
        )
        messages.success(request, f"Requisition for {req.post_name} created as draft.")
        return redirect("requisition_detail", req_id=req.pk)

    return render(request, "recruitment/requisition_create.html")


@login_required
@require_role("hr_manager")
def requisition_detail(request, req_id):
    """View requisition details and approval history. POST submits from draft."""
    req = get_object_or_404(VacancyRequisition.objects.select_related("created_by"), pk=req_id)
    approvals = req.approvals.select_related("approver").all()

    if request.method == "POST":
        action = request.POST.get("action", "")

        if action == "submit" and req.status == "draft":
            old_status = req.status
            req.status = "submitted"
            req.save(update_fields=["status"])
            # Create the first approval step (finance stage).
            RequisitionApproval.objects.create(
                requisition=req,
                stage="finance",
                decision="pending",
            )
            _log_requisition_audit(request.user, req, old_status, "submitted", "Requisition submitted for approval")
            messages.success(request, "Requisition submitted for finance approval.")
            return redirect("requisition_detail", req_id=req.pk)

    return render(request, "recruitment/requisition_detail.html", {
        "req": req,
        "approvals": approvals,
    })


@login_required
@require_role("recruiter", "hr_manager", "org_admin")
def requisition_approve(request, req_id):
    """Approve or reject a requisition at the current stage. POST only."""
    if request.method != "POST":
        return redirect("requisition_detail", req_id=req_id)

    req = get_object_or_404(VacancyRequisition, pk=req_id)
    action = request.POST.get("action", "")
    comments = request.POST.get("comments", "").strip()

    # Find the current pending approval step.
    approval = req.approvals.filter(decision="pending").order_by("timestamp").first()
    if not approval:
        messages.error(request, "No pending approval step for this requisition.")
        return redirect("requisition_detail", req_id=req.pk)

    stage = approval.stage

    # Role gate: verify the user has permission for this stage.
    required_role = _REQ_ROLE_MAP.get(stage)
    if required_role:
        try:
            check_role(request, required_role)
        except PermissionDenied:
            messages.error(request, f"Only users with the '{required_role}' role can approve at the {stage} stage.")
            return redirect("requisition_detail", req_id=req.pk)

    if action == "reject":
        if not comments:
            messages.error(request, "Comments are required when rejecting a requisition.")
            return redirect("requisition_detail", req_id=req.pk)
        old_status = req.status
        approval.decision = "rejected"
        approval.approver = request.user
        approval.comments = comments
        approval.save(update_fields=["decision", "approver", "comments"])
        req.status = "rejected"
        req.save(update_fields=["status"])
        _log_requisition_audit(request.user, req, old_status, "rejected", f"Rejected at {stage}: {comments}")
        messages.success(request, f"Requisition rejected at {approval.get_stage_display()}.")

    elif action == "approve":
        approval.decision = "approved"
        approval.approver = request.user
        approval.comments = comments
        approval.save(update_fields=["decision", "approver", "comments"])

        new_status = _STAGE_STATUS_MAP.get(stage, req.status)
        old_status = req.status
        req.status = new_status
        req.save(update_fields=["status"])
        _log_requisition_audit(request.user, req, old_status, new_status, f"Approved at {stage}: {comments}")

        # Create next stage if workflow continues.
        next_stage = _NEXT_STAGE_MAP.get(stage)
        if next_stage:
            RequisitionApproval.objects.create(
                requisition=req,
                stage=next_stage,
                decision="pending",
            )

        messages.success(request, f"Requisition approved at {approval.get_stage_display()}.")

    return redirect("requisition_detail", req_id=req.pk)


# ── Fairness Dashboard ──────────────────────────────────────────────────────


@login_required
@require_role("viewer", "hr_manager", "org_admin", "auditor")
def fairness_dashboard(request):
    """Fairness analysis dashboard — adverse impact and statistical parity by category.

    Aggregates selection rates from CategoryAllocation + Application status to
    feed the EEOC 4/5ths rule and statistical-parity engine.
    """
    from collections import defaultdict
    from .models import CategoryAllocation, Application

    # Aggregate per-category: total applicants vs selected (offered/joined).
    totals = defaultdict(int)
    selected = defaultdict(int)

    allocations = (
        CategoryAllocation.objects
        .select_related("application")
        .values_list("category", "application__status")
    )
    for cat, status in allocations:
        totals[cat] += 1
        if status in ("offered", "joined"):
            selected[cat] += 1

    selection_rates = {}
    for cat in sorted(totals):
        selection_rates[cat] = selected[cat] / totals[cat] if totals[cat] else 0.0

    adverse = compute_adverse_impact(selection_rates) if selection_rates else {}
    parity = compute_statistical_parity(selection_rates) if selection_rates else {}

    # Category display names from the model.
    cat_labels = dict(CategoryAllocation.CATEGORY_CHOICES)

    categories = []
    for cat in sorted(totals):
        categories.append({
            "code": cat,
            "label": cat_labels.get(cat, cat.upper()),
            "total": totals[cat],
            "selected": selected[cat],
            "rate": selection_rates[cat],
        })

    context = {
        "categories": categories,
        "adverse_impact": adverse,
        "statistical_parity": parity,
        "has_data": bool(selection_rates),
    }
    return render(request, "recruitment/fairness_dashboard.html", context)
