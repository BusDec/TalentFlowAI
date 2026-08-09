"""Candidate-facing portal views.

Phase I uses an email OTP simulation (printed to console via mail backend).
Real OTP (SMS/email gateway) drops in later behind the same views.
"""

import json
import secrets
from decimal import Decimal
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import logout as auth_logout
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods, require_POST
from django_ratelimit.decorators import ratelimit

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
    Grievance,
    JoiningReport,
    Resume,
)
from recruitment.tasks import parse_document_task
from .forms import (
    CandidateLoginForm,
    CandidateRegistrationForm,
    OTPVerifyForm,
)
from .models import CandidatePortalUser


def _client_ip(request):
    return request.META.get("REMOTE_ADDR")


def _clean_optional(value):
    """POST value → None for blank / literal 'None'.

    The profile template renders ``None`` model values as ``value="None"``,
    so the browser submits the string "None"; treat it like an empty field.
    """
    if value is None:
        return None
    value = str(value).strip()
    return None if value in ("", "None") else value


@ratelimit(key="ip", rate="5/m", block=True)
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
            # Send OTP via notification provider (console in dev).
            from notifications import notify

            notify("sms", user.phone, "OTP", f"Your OTP is {otp}")
            messages.info(
                request,
                _("Simulated OTP sent to email (console): %(otp)s") % {"otp": otp},
            )
            return redirect("portal_verify")
    else:
        form = CandidateRegistrationForm()
    return render(request, "portal/register.html", {"form": form})


@ratelimit(key="ip", rate="5/m", block=True)
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


@ratelimit(key="ip", rate="5/m", block=True)
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


_SESSION_PREFILL = "apply_prefill_{advt_id}"
_PREFILL_FIELDS = ("name", "email", "phone", "dob", "pan", "aadhaar", "education")
_DOC_SOURCE_LABELS = {
    "resume": "resume",
    "pan": "PAN card",
    "aadhaar": "Aadhaar card",
    "marksheet": "marksheet",
    "experience_letter": "experience letter",
    "caste_certificate": "caste certificate",
}


def _upload_to_temp(uploaded):
    """Persist an uploaded file to a temp path (extension preserved)."""
    import os
    import tempfile

    suffix = os.path.splitext(uploaded.name or "")[1] or ".txt"
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)  # release the handle so extract_text can open it on Windows
    with open(path, "wb") as handle:
        handle.write(uploaded.read())
    return path


def _build_prefill(files, user):
    """Parse uploaded documents into a candidate prefill (Autofill phase 1).

    Returns a dict with one key per field in ``_PREFILL_FIELDS`` plus two
    extras: ``sources`` (field -> human label of the document it came from)
    and ``warnings`` (cross-document consistency issues as strings).
    """
    import os

    from agents import doc_intel

    prefill = {field: None for field in _PREFILL_FIELDS}
    sources = {}
    docs = []  # (extracted doc dict, temp path)
    temp_paths = []

    def fill(field, value, source):
        if value and prefill[field] is None:
            prefill[field] = value
            sources[field] = source

    try:
        resume_file = files.get("resume")
        if resume_file:
            path = _upload_to_temp(resume_file)
            temp_paths.append(path)
            docs.append((doc_intel.extract_document(path), path))
        # Certificate-style uploads: real forms use cert_<post>_<n>, tests use cert_<n>.
        for key, uploaded in files.items():
            if key.startswith("cert_"):
                path = _upload_to_temp(uploaded)
                temp_paths.append(path)
                docs.append((doc_intel.extract_document(path), path))

        for doc, path in docs:
            doc_type = doc.get("doc_type")
            fields = doc.get("fields") or {}
            label = _DOC_SOURCE_LABELS.get(doc_type, doc_type or "document")
            if doc_type == "resume":
                name = fields.get("full_name")
                if not name:
                    # resume_parser's label regex can swallow the line after
                    # "Name:" (then hit its blocklist); doc_intel's per-line
                    # extractor handles that shape, so fall back to it.
                    name = doc_intel._extract_name(doc_intel.extract_text(path))
                    if name:
                        fields["full_name"] = name
                fill("name", name, label)
                fill("email", fields.get("email"), label)
                fill("phone", fields.get("phone"), label)
                fill("dob", fields.get("date_of_birth"), label)
                fill("education", fields.get("degree"), label)
            elif doc_type == "pan":
                fill("pan", fields.get("pan"), label)
                fill("name", fields.get("name"), label)
            elif doc_type == "aadhaar":
                fill("aadhaar", fields.get("aadhaar"), label)
                fill("dob", fields.get("dob"), label)
                fill("name", fields.get("name"), label)
            elif doc_type == "marksheet":
                education = ", ".join(
                    part
                    for part in (
                        fields.get("percentage"),
                        fields.get("university"),
                        fields.get("year"),
                    )
                    if part
                )
                fill("education", education or None, label)

        # Registered-profile fallbacks for fields no document carried. These
        # carry no ``sources`` entry so the UI never badges them as auto-filled.
        if prefill["name"] is None:
            prefill["name"] = user.full_name
        if prefill["email"] is None:
            prefill["email"] = user.email
        if prefill["phone"] is None:
            prefill["phone"] = user.phone

        # Cross-document consistency (the resume exposes its name as full_name).
        normalized = []
        for doc, _path in docs:
            fields = dict(doc.get("fields") or {})
            if (
                doc.get("doc_type") == "resume"
                and fields.get("full_name")
                and not fields.get("name")
            ):
                fields["name"] = fields["full_name"]
            normalized.append({"doc_type": doc.get("doc_type"), "fields": fields})
        prefill["warnings"] = [
            issue.get("detail")
            for issue in doc_intel.check_consistency(normalized)
            if issue.get("detail")
        ]
        # Display-only masked Aadhaar (never render the raw number).
        prefill["aadhaar_masked"] = (
            "XXXX-XXXX-" + prefill["aadhaar"][-4:] if prefill["aadhaar"] else None
        )
        prefill["sources"] = sources
        return prefill
    finally:
        for path in temp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass


@ratelimit(key="user", rate="10/h", block=True)
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

    session_key = _SESSION_PREFILL.format(advt_id=advt.id)

    if request.method == "POST":
        post_id = request.POST.get("post")
        post = advt.posts.filter(id=post_id).first()
        resume_file = request.FILES.get("resume")
        declared = request.POST.get("declare") in ("on", "1", "true")
        confirmed = request.POST.get("confirm") in ("on", "1", "true")
        prefill = request.session.get(session_key)

        # Phase 1: parse the uploaded documents into a session prefill.
        if post and resume_file and not declared and not confirmed and prefill is None:
            prefill = _build_prefill(request.FILES, request.user)
            request.session[session_key] = prefill
            return render(
                request,
                "portal/apply.html",
                {
                    "advt": advt,
                    "candidate": candidate,
                    "prefill": prefill,
                    "sources": prefill["sources"],
                    "warnings": prefill["warnings"],
                },
            )

        # Phase 2 gate: a pending prefill must be explicitly confirmed.
        if post and resume_file and prefill is not None and not confirmed:
            return render(
                request,
                "portal/apply.html",
                {
                    "advt": advt,
                    "candidate": candidate,
                    "prefill": prefill,
                    "sources": prefill["sources"],
                    "warnings": prefill["warnings"],
                    "confirm_error": _("Confirm the auto-filled information."),
                },
            )

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
                            document = Document.objects.create(
                                application=application,
                                doc_type=f"certificate:{cert}",
                                file=cert_file,
                            )
                            parse_document_task.delay(document.id)
                    # The prefill is consumed by a successful submission only.
                    request.session.pop(session_key, None)
                    messages.success(request, _("Application submitted successfully."))
                    return redirect("portal_application_detail", application_id=application.application_id)
        messages.error(request, _("Post not found or already applied."))

    context = {"advt": advt, "candidate": candidate}
    prefill = request.session.get(session_key)
    if prefill is not None:
        context.update(
            {
                "prefill": prefill,
                "sources": prefill["sources"],
                "warnings": prefill["warnings"],
            }
        )
    return render(request, "portal/apply.html", context)


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


def _application_detail_context(application):
    """Shared template context for the application detail page.

    Used by ``application_detail`` and reused by ``accept_offer`` when it
    re-renders the page (e.g. consent checkbox missing) so the stepper,
    withdraw button and employee-number badge stay intact.
    """
    from agents import doc_intel

    background_report = getattr(application, "background_report", None)
    stage_names = [s[0] for s in STAGES]
    stage_index = stage_names.index(application.status) if application.status in stage_names else len(stage_names)
    is_terminal = application.status in ("rejected", "withdrawn")
    terminal_index = None
    if is_terminal:
        rejected_stage = application.rejected_at_stage or "offered"
        terminal_index = stage_names.index(rejected_stage) if rejected_stage in stage_names else stage_names.index("offered")

    # Cross-document consistency warnings from stored extracted_data.
    docs_qs = application.documents.filter(extracted_data__isnull=False)
    normalized = []
    for d in docs_qs:
        data = d.extracted_data or {}
        fields = dict(data.get("fields") or {})
        # Resume parser stores the candidate name as ``full_name``;
        # check_consistency compares ``name``.
        if d.doc_type == "resume" and fields.get("full_name"):
            fields["name"] = fields.pop("full_name")
        normalized.append({"doc_type": d.doc_type, "fields": fields})
    consistency_warnings = [
        issue["detail"]
        for issue in doc_intel.check_consistency(normalized)
        if issue.get("detail")
    ]

    return {
        "application": application,
        "background_report": background_report,
        "resumes": application.candidate.resumes.all(),
        "stage_labels": STAGES,
        "stage_index": stage_index,
        "is_terminal": is_terminal,
        "terminal_index": terminal_index,
        "can_withdraw": application.status
        in ("received", "document_verification", "shortlisted", "interview"),
        "consistency_warnings": consistency_warnings,
    }


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

    return render(
        request,
        "portal/application_detail.html",
        _application_detail_context(application),
    )


@require_portal_user
def accept_offer(request, application_id):
    """Candidate accepts an offered appointment.

    GET renders the offer text (via ``generate_offer_text``) with the consent
    form. POST requires the ``consent`` checkbox; on acceptance the application
    moves to ``joined``, an employee number is assigned and the change is
    audited. Re-renders the detail page with ``accept_error`` when consent is
    missing so no state change occurs.
    """
    application = get_object_or_404(
        Application,
        application_id=application_id,
        candidate__portal_user=request.user,
    )
    from recruitment.audit import log_audit
    from recruitment.views import generate_offer_text

    context = _application_detail_context(application)
    context["offer_text"] = generate_offer_text(application)

    if request.method == "POST":
        if request.POST.get("consent") != "on":
            context["accept_error"] = "You must accept the offer to proceed."
            return render(request, "portal/application_detail.html", context)
        application.employee_number = (
            f"{application.post.advertisement.advt_number[:6]}-"
            f"{application.post.post_code}-"
            f"{Application.objects.filter(post=application.post, status='joined').count() + 1:04d}"
        )
        application.status = "joined"
        application.save()  # model save audits the status change
        log_audit(None, application, "status", "offered", "joined", reason="candidate accepted offer")
        messages.success(request, _("Offer accepted. Welcome aboard!"))
        return redirect("portal_application_detail", application_id=application.application_id)

    return render(request, "portal/application_detail.html", context)


@require_portal_user
@require_http_methods(["GET"])
def application_slip(request, application_id):
    """Serve the downloadable PDF application slip for the candidate's own application."""
    application = get_object_or_404(Application, application_id=application_id)
    if application.candidate.portal_user != request.user:
        messages.error(request, _("You can only download the slip for your own application."))
        return redirect("portal_application_detail", application_id=application_id)

    from recruitment.slip_pdf import ApplicationSlipPDF

    payload = ApplicationSlipPDF(application).generate()
    response = HttpResponse(payload, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="slip-{application.application_id}.pdf"'
    return response


@require_portal_user
@require_POST
def pay_fee(request, application_id):
    """Candidate pays the application fee.

    Creates a Payment record if one does not exist, determines exemption via
    ``fee_exempt``, and processes payment through the configured gateway.
    Mock gateway always succeeds; Razorpay stub shows a friendly error.
    Audits the transaction via ``log_audit`` with field_name="payment".
    """
    from django.contrib import messages as msg

    from recruitment.audit import log_audit
    from recruitment.fees import fee_amount, fee_exempt
    from recruitment.models import Payment
    from recruitment.payments import NotConfigured, get_gateway

    application = get_object_or_404(
        Application,
        application_id=application_id,
        candidate__portal_user=request.user,
    )

    # Get or create Payment record.
    is_exempt, reason = fee_exempt(application.candidate, application.post)
    amount = Decimal("0.00") if is_exempt else fee_amount(application.post)

    payment, created = Payment.objects.get_or_create(
        application=application,
        defaults={
            "amount": amount,
            "gateway": "mock",
            "gateway_ref": "",
            "status": "pending",
            "exempt": is_exempt,
            "exempt_reason": reason,
        },
    )

    # Exempt candidates are marked paid immediately.
    if is_exempt and payment.status == "pending":
        payment.status = "completed"
        payment.paid_at = timezone.now()
        payment.save()
        log_audit(
            None, application, "payment", "pending", "completed",
            reason=f"fee exempt: {reason}",
        )
        msg.success(request, _("Fee exempted — no payment required."))
        return redirect("portal_application_detail", application_id=application_id)

    # Already paid.
    if payment.status == "completed":
        msg.info(request, _("Fee already paid."))
        return redirect("portal_application_detail", application_id=application_id)

    # Process through gateway.
    try:
        gateway = get_gateway()
        result = gateway.create_payment(amount, application.application_id)
        payment.gateway_ref = result.get("id", "")

        if gateway.verify(result):
            payment.status = "completed"
            payment.paid_at = timezone.now()
            payment.save()
            log_audit(
                None, application, "payment", "pending", "completed",
                reason=f"gateway: {payment.gateway}, ref: {payment.gateway_ref}",
            )
            msg.success(request, _("Payment successful!"))
        else:
            payment.status = "failed"
            payment.save()
            msg.error(request, _("Payment verification failed. Please try again."))
    except NotConfigured:
        msg.error(
            request,
            _("Payment gateway not configured. Please contact support."),
        )
    except Exception:
        msg.error(
            request,
            _("Payment could not be processed. Please try again later."),
        )

    return redirect("portal_application_detail", application_id=application_id)


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
                    year_passed=_clean_optional(request.POST.get(f"academic_year_{idx}")),
                    marking_type=request.POST.get(f"academic_marking_{idx}", "percentage"),
                    score=request.POST.get(f"academic_score_{idx}", ""),
                    is_ugc_recognized=request.POST.get(f"academic_ugc_{idx}") in ("on", "1", "true"),
                )

        # Work experience (replace).
        candidate.work_experiences.all().delete()
        for key, value in request.POST.items():
            if key.startswith("work_org_") and value:
                idx = key.rsplit("_", 1)[1]
                start = _clean_optional(request.POST.get(f"work_start_{idx}"))
                end = _clean_optional(request.POST.get(f"work_end_{idx}"))
                WorkExperience.objects.create(
                    candidate=candidate,
                    org_name=value,
                    org_type=request.POST.get(f"work_orgtype_{idx}", ""),
                    designation=request.POST.get(f"work_designation_{idx}", ""),
                    start_date=start,
                    end_date=end,
                    annual_ctc_lakhs=_clean_optional(request.POST.get(f"work_ctc_{idx}")),
                    turnover_cr=_clean_optional(request.POST.get(f"work_turnover_{idx}")),
                )

        # Exam disclosure.
        exam.exam_type = request.POST.get("exam_type", "")
        exam.gate_year = _clean_optional(request.POST.get("gate_year"))
        exam.paper_code = request.POST.get("paper_code", "")
        exam.marks_out_100 = _clean_optional(request.POST.get("marks_out_100"))
        exam.gate_score = _clean_optional(request.POST.get("gate_score"))
        exam.air = _clean_optional(request.POST.get("air"))
        exam.ese_total_score = _clean_optional(request.POST.get("ese_total_score"))
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


# ── Grievance / Appeal ──────────────────────────────────────────────────────


@require_portal_user
def my_grievances(request):
    """List grievances filed by the authenticated candidate."""
    candidate = Candidate.objects.filter(portal_user=request.user).first()
    if not candidate:
        messages.error(request, _("No candidate profile found."))
        return redirect("portal_dashboard")
    grievances = Grievance.objects.filter(candidate=candidate)
    return render(request, "portal/my_grievances.html", {"grievances": grievances})


@require_portal_user
def file_grievance(request):
    """File a new grievance/appeal. GET shows form, POST creates."""
    candidate = Candidate.objects.filter(portal_user=request.user).first()
    if not candidate:
        messages.error(request, _("No candidate profile found."))
        return redirect("portal_dashboard")

    applications = Application.objects.filter(candidate=candidate)

    if request.method == "POST":
        subject = (request.POST.get("subject") or "").strip()
        description = (request.POST.get("description") or "").strip()
        application_id = _clean_optional(request.POST.get("application_id"))

        if not subject or not description:
            messages.error(request, _("Subject and description are required."))
        else:
            application = None
            if application_id:
                application = applications.filter(application_id=application_id).first()

            Grievance.objects.create(
                candidate=candidate,
                application=application,
                subject=subject,
                description=description,
            )
            messages.success(request, _("Grievance filed successfully. Our team will review it shortly."))
            return redirect("portal_my_grievances")

    return render(request, "portal/file_grievance.html", {"applications": applications})


@require_portal_user
@require_http_methods(["GET", "POST"])
def submit_joining_report(request, application_id):
    """Candidate submits a joining report for an application in 'joined' status.

    GET renders the form; POST validates and creates the JoiningReport.
    Redirects to the application detail page on success.
    """
    application = get_object_or_404(
        Application,
        application_id=application_id,
        candidate__portal_user=request.user,
    )

    if application.status != "joined":
        messages.error(request, _("You can only submit a joining report for applications in 'Joined' status."))
        return redirect("portal_application_detail", application_id=application_id)

    if hasattr(application, "joining_report"):
        messages.info(request, _("You have already submitted a joining report for this application."))
        return redirect("portal_application_detail", application_id=application_id)

    if request.method == "POST":
        joining_date = request.POST.get("joining_date")
        designation = (request.POST.get("designation") or "").strip()
        pay_fixation = (request.POST.get("pay_fixation") or "").strip()
        reported_to = (request.POST.get("reported_to") or "").strip()
        documents_submitted = request.POST.get("documents_submitted") == "on"

        errors = []
        if not joining_date:
            errors.append(_("Joining date is required."))
        if not designation:
            errors.append(_("Designation is required."))
        if not reported_to:
            errors.append(_("Reported-to officer is required."))

        if errors:
            for err in errors:
                messages.error(request, err)
        else:
            JoiningReport.objects.create(
                application=application,
                joining_date=joining_date,
                designation=designation,
                pay_fixation=pay_fixation,
                reported_to=reported_to,
                documents_submitted=documents_submitted,
            )
            messages.success(request, _("Joining report submitted successfully."))
            return redirect("portal_application_detail", application_id=application_id)

    return render(
        request,
        "portal/joining_report.html",
        {"application": application},
    )
