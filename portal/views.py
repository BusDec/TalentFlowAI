"""Candidate-facing portal views.

Phase I uses an email OTP simulation (printed to console via mail backend).
Real OTP (SMS/email gateway) drops in later behind the same views.
"""

import json
import secrets
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST

from agents.eligibility_verifier import verify_application
from agents.resume_evaluator import evaluate_resume
from agents.resume_parser import names_match
from consent.models import Consent, ConsentEvent
from profiles.models import (
    AcademicRecord,
    CandidateProfile,
    ExamDisclosure,
    ProfileDocument,
    WorkExperience,
)
from recruitment.models import (
    Advertisement,
    Application,
    BackgroundReport,
    Candidate,
    CategoryAllocation,
    Document,
    Resume,
)
from .forms import (
    CandidateLoginForm,
    CandidateRegistrationForm,
    OTPVerifyForm,
)
from .models import CandidatePortalUser


def _client_ip(request):
    return request.META.get("REMOTE_ADDR")


def register(request):
    if request.method == "POST":
        form = CandidateRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_unusable_password()
            user.save()
            # Store pending OTP in session (simulated).
            otp = f"{secrets.randbelow(900000) + 100000}"
            request.session["pending_otp"] = otp
            request.session["pending_user_id"] = user.id
            messages.info(
                request,
                _("Simulated OTP sent to email (console): %(otp)s") % {"otp": otp},
            )
            return redirect("portal_verify")
    else:
        form = CandidateRegistrationForm()
    return render(request, "portal/register.html", {"form": form})


def verify_otp(request):
    if request.method == "POST":
        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            entered = form.cleaned_data["otp"]
            if entered == request.session.get("pending_otp"):
                user_id = request.session.get("pending_user_id")
                user = CandidatePortalUser.objects.filter(id=user_id).first()
                if user:
                    user.otp_verified = True
                    user.save()
                    login(request, user, backend="portal.backends.CandidatePortalBackend")
                    request.session.pop("pending_otp", None)
                    request.session.pop("pending_user_id", None)
                    messages.success(request, _("OTP verified. Welcome!"))
                    # First login: build the profile (template-driven onboarding).
                    if not Candidate.objects.filter(portal_user=user).exists():
                        return redirect("portal_profile")
                    return redirect("portal_dashboard")
                messages.error(request, _("Verification session expired."))
            else:
                messages.error(request, _("Invalid OTP."))
    else:
        form = OTPVerifyForm()
    return render(request, "portal/verify_otp.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated and isinstance(request.user, CandidatePortalUser):
        return redirect("portal_dashboard")
    if request.method == "POST":
        form = CandidateLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            user = CandidatePortalUser.objects.filter(email__iexact=email).first()
            if user:
                # Phase I: no password; email-link style login simulated by OTP.
                otp = f"{secrets.randbelow(900000) + 100000}"
                request.session["pending_otp"] = otp
                request.session["pending_user_id"] = user.id
                messages.info(
                    request,
                    _("Simulated OTP sent to email (console): %(otp)s") % {"otp": otp},
                )
                return redirect("portal_verify")
            messages.error(request, _("No account found with this email."))
    else:
        form = CandidateLoginForm()
    return render(request, "portal/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def logout_view(request):
    try:
        auth_logout(request)
    except Exception:
        request.session.flush()
    messages.success(request, _("You have been logged out."))
    return redirect("portal_login")


def require_portal_user(view_func):
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not isinstance(
            request.user, CandidatePortalUser
        ):
            return redirect("portal_login")
        return view_func(request, *args, **kwargs)

    return wrapped


@require_portal_user
def portal_dashboard(request):
    applications = Application.objects.filter(candidate__portal_user=request.user)
    applied_advt_ids = set(
        Application.objects.filter(candidate__portal_user=request.user)
        .values_list("post__advertisement_id", flat=True)
    )
    has_profile = CandidateProfile.objects.filter(candidate__portal_user=request.user).exists()
    return render(
        request,
        "portal/dashboard.html",
        {
            "applications": applications,
            "advertisements": Advertisement.objects.filter(is_active=True).order_by("-published_date"),
            "applied_advt_ids": applied_advt_ids,
            "today": timezone.localdate(),
            "has_profile": has_profile,
        },
    )


@require_portal_user
def apply(request, advt_id):
    advt = get_object_or_404(Advertisement, id=advt_id)
    if advt.closing_date and advt.closing_date <= timezone.localdate():
        messages.error(request, _("This advertisement has closed."))
        return redirect("portal_dashboard")
    candidate = Candidate.objects.filter(portal_user=request.user).first()
    if not candidate:
        candidate = Candidate.objects.create(
            portal_user=request.user,
            first_name=request.user.full_name.split()[0] if request.user.full_name else "Candidate",
            last_name=" ".join(request.user.full_name.split()[1:]) if request.user.full_name else "",
            email=request.user.email,
            mobile=request.user.phone,
        )

    # A candidate may apply to an advertisement only once (any post).
    existing_application = (
        Application.objects.filter(
            candidate__portal_user=request.user,
            post__advertisement=advt,
        ).first()
    )
    if existing_application:
        messages.info(
            request,
            _("You have already applied to this advertisement."),
        )
        return redirect("portal_application_detail", application_id=existing_application.application_id)

    if request.method == "POST":
        post_id = request.POST.get("post")
        post = advt.posts.filter(id=post_id).first()
        resume_file = request.FILES.get("resume")
        declared = request.POST.get("declare") in ("on", "1", "true")

        if post and not resume_file:
            messages.error(request, _("Please upload your resume before submitting."))
        elif post and not declared:
            messages.error(
                request,
                _("You must confirm that the information you provided is true and correct."),
            )
        elif post and Application.objects.filter(
            candidate__portal_user=request.user, post=post
        ).exists():
            messages.error(request, _("Post not found or already applied."))
        elif post:
            resume = Resume.objects.create(candidate=candidate, file=resume_file)
            parsed_name = (resume.parsed_json or {}).get("full_name")
            name_match = names_match(parsed_name, request.user.full_name)
            if name_match is False:
                resume.delete()
                messages.error(
                    request,
                    _(
                        "The name on your resume (%(parsed)s) does not match the name you "
                        "registered with (%(registered)s). Please upload a resume in your own name."
                    )
                    % {"parsed": parsed_name, "registered": request.user.full_name},
                )
            else:
                application, created = Application.objects.get_or_create(
                    post=post,
                    candidate=candidate,
                    defaults={"application_id": f"APP-{secrets.token_hex(4).upper()}"},
                )
                if not created:
                    resume.delete()
                    messages.error(request, _("You have already applied to this post."))
                else:
                    if resume.parsed_json:
                        evaluation = evaluate_resume(resume.parsed_json, post)
                        application.resume_score = evaluation.get("overall_score", 0)
                        application.resume_evaluation = evaluation
                        application.save(update_fields=["resume_score", "resume_evaluation"])
                    Consent.objects.create(
                        candidate_portal_user=request.user,
                        application=application,
                        purpose="application",
                        scope_text=(
                            "Consent to process my application and documents, and to verify the "
                            "information provided. I declare that the information given is true and "
                            "correct to the best of my knowledge; in case any information is found "
                            "false or incorrect, my application is liable to be rejected and I may be "
                            "barred from applying to this organisation in future."
                        ),
                        ip_address=_client_ip(request),
                    )
                    for idx, cert in enumerate(post.required_certificates or []):
                        cert_file = request.FILES.get(f"cert_{post.id}_{idx}")
                        if cert_file:
                            Document.objects.create(
                                application=application,
                                doc_type=f"certificate:{cert}",
                                file=cert_file,
                            )
                    messages.success(request, _("Application submitted successfully."))
                    return redirect("portal_application_detail", application_id=application.application_id)
        messages.error(request, _("Post not found or already applied."))
    return render(
        request,
        "portal/apply.html",
        {"advt": advt, "candidate": candidate},
    )


@require_portal_user
def my_applications(request):
    applications = Application.objects.filter(candidate__portal_user=request.user)
    return render(request, "portal/my_applications.html", {"applications": applications})


STAGES = [
    ("received", "Received"),
    ("document_verification", "Document Verification"),
    ("shortlisted", "Shortlisted"),
    ("interview", "Interview"),
    ("offered", "Offered"),
    ("joined", "Joined"),
]


@require_portal_user
def application_detail(request, application_id):
    application = get_object_or_404(
        Application,
        application_id=application_id,
        candidate__portal_user=request.user,
    )
    background_report = getattr(application, "background_report", None)

    if request.method == "POST":
        # BGV explanation
        explanation = request.POST.get("candidate_explanation")
        if background_report and explanation:
            background_report.candidate_explanation = explanation
            background_report.status = "explained"
            background_report.save()
            messages.success(request, _("Explanation submitted."))
        return redirect("portal_application_detail", application_id=application_id)

    stage_names = [s[0] for s in STAGES]
    stage_index = stage_names.index(application.status) if application.status in stage_names else len(stage_names)
    is_terminal = application.status in ("rejected", "withdrawn")
    terminal_index = None
    if is_terminal:
        rejected_stage = application.rejected_at_stage or "offered"
        terminal_index = stage_names.index(rejected_stage) if rejected_stage in stage_names else stage_names.index("offered")

    return render(
        request,
        "portal/application_detail.html",
        {
            "application": application,
            "background_report": background_report,
            "resumes": application.candidate.resumes.all(),
            "stage_labels": STAGES,
            "stage_index": stage_index,
            "is_terminal": is_terminal,
            "terminal_index": terminal_index,
            "can_withdraw": application.status
            in ("received", "document_verification", "shortlisted", "interview"),
        },
    )


@require_portal_user
@require_POST
def withdraw_application(request, application_id):
    application = get_object_or_404(
        Application,
        application_id=application_id,
        candidate__portal_user=request.user,
    )
    withdrawable = ("received", "document_verification", "shortlisted", "interview")
    if application.status in withdrawable:
        application.rejected_at_stage = application.status
        application.status = "withdrawn"
        application.save()
        messages.success(request, _("Your application has been withdrawn."))
    else:
        messages.error(
            request,
            _("This application can no longer be withdrawn at its current stage."),
        )
    return redirect("portal_application_detail", application_id=application_id)


@require_portal_user
def profile_view(request):
    """Candidate profile: bio, addresses, academics, work, exam, proof docs."""
    ugc_universities = []
    try:
        ugc_path = Path(__file__).resolve().parent.parent / "profiles" / "ugc_universities.json"
        ugc_universities = json.loads(ugc_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass

    candidate = Candidate.objects.filter(portal_user=request.user).first()
    if not candidate:
        candidate = Candidate.objects.create(
            portal_user=request.user,
            first_name=request.user.full_name.split()[0] if request.user.full_name else "Candidate",
            last_name=" ".join(request.user.full_name.split()[1:]) if request.user.full_name else "",
            email=request.user.email,
            mobile=request.user.phone,
        )

    profile, _profile_created = CandidateProfile.objects.get_or_create(candidate=candidate)
    exam, _exam_created = ExamDisclosure.objects.get_or_create(candidate=candidate)

    if request.method == "POST":
        same = request.POST.get("current_same_as_permanent") in ("on", "1", "true")
        profile.gender = request.POST.get("gender", "")
        profile.category = request.POST.get("category", "")
        profile.is_pwbd = request.POST.get("is_pwbd") in ("on", "1", "true")
        profile.aadhar_no = request.POST.get("aadhar_no", "").strip()
        profile.permanent_address = request.POST.get("permanent_address", "").strip()
        profile.current_address = "" if same else request.POST.get("current_address", "").strip()
        profile.current_same_as_permanent = same
        profile.save()

        # Academic records (replace).
        candidate.academic_records.all().delete()
        for key, value in request.POST.items():
            if key.startswith("academic_level_") and value:
                idx = key.rsplit("_", 1)[1]
                AcademicRecord.objects.create(
                    candidate=candidate,
                    level=value,
                    discipline=request.POST.get(f"academic_discipline_{idx}", ""),
                    university_board=request.POST.get(f"academic_board_{idx}", ""),
                    year_passed=request.POST.get(f"academic_year_{idx}") or None,
                    marking_type=request.POST.get(f"academic_marking_{idx}", "percentage"),
                    score=request.POST.get(f"academic_score_{idx}", ""),
                    is_ugc_recognized=request.POST.get(f"academic_ugc_{idx}") in ("on", "1", "true"),
                )

        # Work experience (replace).
        candidate.work_experiences.all().delete()
        for key, value in request.POST.items():
            if key.startswith("work_org_") and value:
                idx = key.rsplit("_", 1)[1]
                start = request.POST.get(f"work_start_{idx}") or None
                end = request.POST.get(f"work_end_{idx}") or None
                WorkExperience.objects.create(
                    candidate=candidate,
                    org_name=value,
                    org_type=request.POST.get(f"work_orgtype_{idx}", ""),
                    designation=request.POST.get(f"work_designation_{idx}", ""),
                    start_date=start,
                    end_date=end,
                    annual_ctc_lakhs=request.POST.get(f"work_ctc_{idx}") or None,
                    turnover_cr=request.POST.get(f"work_turnover_{idx}") or None,
                )

        # Exam disclosure.
        exam.exam_type = request.POST.get("exam_type", "")
        exam.gate_year = request.POST.get("gate_year") or None
        exam.paper_code = request.POST.get("paper_code", "")
        exam.marks_out_100 = request.POST.get("marks_out_100") or None
        exam.gate_score = request.POST.get("gate_score") or None
        exam.air = request.POST.get("air") or None
        exam.ese_total_score = request.POST.get("ese_total_score") or None
        exam.public_disclosure_consent = request.POST.get("public_disclosure_consent") in ("on", "1", "true")
        exam.save()

        # Proof documents.
        for doc_type, field in (
            ("dob", "doc_dob"),
            ("aadhar", "doc_aadhar"),
            ("academic", "doc_academic"),
            ("work_ex", "doc_work_ex"),
            ("public_exam", "doc_public_exam"),
        ):
            f = request.FILES.get(field)
            if f:
                ProfileDocument.objects.create(candidate=candidate, doc_type=doc_type, file=f)

        messages.success(request, _("Profile saved successfully."))
        return redirect("portal_profile")

    return render(
        request,
        "portal/profile.html",
        {
            "candidate": candidate,
            "profile": profile,
            "exam": exam,
            "academic_records": candidate.academic_records.all(),
            "work_experiences": candidate.work_experiences.all(),
            "documents": candidate.profile_documents.all(),
            "current_same_as_permanent": profile.current_same_as_permanent,
            "ugc_universities": ugc_universities,
        },
    )


@require_portal_user
def consent_list(request):
    consents = Consent.objects.filter(candidate_portal_user=request.user)
    return render(request, "portal/consents.html", {"consents": consents})


@require_portal_user
@require_POST
def consent_revoke(request, consent_id):
    consent = Consent.objects.filter(id=consent_id, candidate_portal_user=request.user).first()
    if consent and consent.is_active:
        consent.revoked_at = timezone.now()
        consent.save()
        ConsentEvent.objects.create(
            consent=consent,
            action="revoked",
            ip_address=_client_ip(request),
            details="Candidate revoked consent from the portal.",
        )
        messages.success(request, _("Consent revoked. We will stop processing your data for this purpose."))
    return redirect("portal_consents")
