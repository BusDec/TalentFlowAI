"""Internal HR views — recruitment workflow, roster, panels, duplicates."""

import csv
import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from agents import eligibility_verifier, interview_copilot, roster_compliance
from agents.shortlist import build_shortlist
from consent.models import Consent, ConsentEvent
from .digilocker.client import DigiLockerError, fetch_documents, verify_signature
from .models import (
    Advertisement,
    Application,
    BackgroundReport,
    CategoryAllocation,
    DuplicateFlag,
    FetchedDocument,
    InternalApplication,
    InternalJobPosting,
    PanelList,
    Post,
    RosterMatrix,
)


@login_required
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
def advertisement_list(request):
    return render(
        request,
        "recruitment/advertisement_list.html",
        {"advertisements": Advertisement.objects.all()},
    )


@login_required
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
    from .boilerplate import (
        DEFAULT_COMPANY_PROFILE,
        DEFAULT_HOW_TO_APPLY,
    )

    def _d(value):
        return value.strftime("%d-%m-%Y") if value else ""

    def _num_words(n):
        words = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
                 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten"}
        return words.get(n, str(n))

    lines = []
    # Header
    lines.append(f"{advt.company_name or 'North Eastern Electric Power Corporation Limited'}")
    lines.append(f"{advt.company_tagline or '(A Government of India Enterprise)'}")
    lines.append(f"{advt.company_address or ''}")
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

    if advt.registration_fee_text:
        lines.append("REGISTRATION FEES")
        lines.append(advt.registration_fee_text)
        lines.append("")

    if advt.contact_email:
        lines.append(f"Contact e-mail ID of Recruitment Cell: {advt.contact_email}")

    return "\n".join(lines)


@login_required
def advertisement_detail(request, advt_id):
    advt = get_object_or_404(Advertisement, id=advt_id)
    return render(request, "recruitment/advertisement_detail.html", {"advt": advt})


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
def advertisement_report(request, advt_id):
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
        {"advt": advt, "posts": posts, "today": datetime.date.today()},
    )


@login_required
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
def application_detail(request, application_id):
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
def run_eligibility(request, application_id):
    application = get_object_or_404(Application, application_id=application_id)
    verdict = eligibility_verifier.verify_application(
        application,
        dob=application.candidate.date_of_birth,
        digilocker_consent="mock-consent-ref",
    )
    return render(request, "recruitment/eligibility_result.html", {"verdict": verdict})


@login_required
def roster_view(request, post_id):
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
    return render(
        request,
        "recruitment/roster.html",
        {"rows": rows, "post": post, "category_choices": RosterMatrix.CATEGORY_CHOICES},
    )


@login_required
def panel_view(request, post_id):
    entries = PanelList.objects.filter(post_id=post_id, is_active=True)
    return render(request, "recruitment/panel.html", {"entries": entries, "post_id": post_id})


@login_required
@require_POST
def panel_promote(request, post_id, panel_id):
    entry = get_object_or_404(PanelList, id=panel_id, post_id=post_id)
    application = entry.application
    if application.status in ("rejected", "withdrawn"):
        messages.error(request, "Application no longer promotable.")
    else:
        application.status = "offered"
        application.save()
        entry.promoted_on = datetime.datetime.now()
        entry.is_active = False
        entry.save()
        messages.success(request, f"Promoted {application} from panel.")
    return redirect("panel_view", post_id=post_id)


@login_required
def internal_posting_list(request):
    postings = InternalJobPosting.objects.all()
    return render(request, "recruitment/internal_posting_list.html", {"postings": postings})


@login_required
def duplicates_queue(request):
    flags = DuplicateFlag.objects.select_related(
        "candidate", "application_a", "application_b"
    ).all()
    return render(request, "recruitment/duplicates.html", {"flags": flags})


@login_required
@require_POST
def duplicates_resolve(request, flag_id):
    flag = get_object_or_404(DuplicateFlag, id=flag_id)
    resolution = request.POST.get("resolution")
    if resolution in dict(DuplicateFlag.RESOLUTION_CHOICES):
        flag.resolution = resolution
        flag.resolved_by = request.user
        flag.resolved_at = datetime.datetime.now()
        flag.save()
        messages.success(request, "Duplicate flag resolved.")
    return redirect("duplicates_queue")


@login_required
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
def offer_letter(request, application_id):
    """Generate an offer letter for a candidate (text preview; PDF via print)."""
    application = get_object_or_404(Application, application_id=application_id)
    if application.status not in ("offered", "joined"):
        messages.warning(request, "Set the application status to 'Offered' first.")
    offer_text = generate_offer_text(application)
    return render(
        request,
        "recruitment/offer_letter.html",
        {"application": application, "offer_text": offer_text},
    )


def generate_offer_text(app):
    """Build a formal PSU-style offer letter in plain text."""
    cand = app.candidate
    post = app.post
    org = "North Eastern Electric Power Corporation Limited"
    lines = [
        org,
        "Brookland Compound, Lower New Colony, Shillong – 793003, Meghalaya",
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
        "For " + org,
        "",
        "(Authorised Signatory)",
        "Date: " + str(datetime.date.today()),
    ]
    return "\n".join(lines)


@login_required
def communications(request, application_id):
    """Communication hub — send and view candidate messages."""
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
def consent_ledger(request):
    consents = Consent.objects.select_related("candidate_portal_user").all()
    return render(request, "consent/ledger.html", {"consents": consents})


@login_required
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
