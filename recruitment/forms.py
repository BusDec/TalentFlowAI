"""Forms for creating advertisements in the NEEPCO/THDC format."""

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .boilerplate import (
    DEFAULT_GENERAL_CONDITIONS,
    DEFAULT_HEALTH_TEXT,
    DEFAULT_HOW_TO_APPLY,
    DEFAULT_LOCATION,
    DEFAULT_PERIOD,
)
from .models import Advertisement, Post


class AdvertisementForm(forms.ModelForm):
    error_css_class = "tf-input-error"

    class Meta:
        model = Advertisement
        fields = [
            "advt_number", "title", "description", "published_date", "closing_date", "is_active",
            "health_text", "general_conditions", "how_to_apply",
        ]
        widgets = {
            "advt_number": forms.TextInput(attrs={"class": "tf-input", "placeholder": "e.g. NEEPCO/03/2026"}),
            "title": forms.TextInput(attrs={"class": "tf-input", "placeholder": "e.g. Recruitment of Executives on Fixed Term Basis"}),
            "description": forms.Textarea(attrs={"class": "tf-textarea", "rows": 4}),
            "published_date": forms.DateInput(attrs={"class": "tf-input", "type": "date"}),
            "closing_date": forms.DateInput(attrs={"class": "tf-input", "type": "date"}),
            "is_active": forms.CheckboxInput(attrs={"style": "width:18px;height:18px;accent-color:var(--tf-accent);cursor:pointer"}),
            "health_text": forms.Textarea(attrs={"class": "tf-textarea", "rows": 4}),
            "general_conditions": forms.Textarea(attrs={"class": "tf-textarea", "rows": 6}),
            "how_to_apply": forms.Textarea(attrs={"class": "tf-textarea", "rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill boilerplate for a fresh (non-POST) form.
        if not kwargs.get("data"):
            self.fields["health_text"].initial = DEFAULT_HEALTH_TEXT
            self.fields["general_conditions"].initial = DEFAULT_GENERAL_CONDITIONS
            self.fields["how_to_apply"].initial = DEFAULT_HOW_TO_APPLY

    def clean(self):
        cleaned = super().clean()
        published = cleaned.get("published_date")
        closing = cleaned.get("closing_date")
        today = timezone.localdate()
        if published and published < today:
            self.add_error("published_date", "Opening date cannot be in the past.")
        if closing and closing < today:
            self.add_error("closing_date", "Closing date cannot be in the past.")
        if published and closing and closing <= published:
            self.add_error("closing_date", "Closing date must be after the opening date.")
        return cleaned


class PostForm(forms.ModelForm):
    error_css_class = "tf-input-error"

    # Category-wise vacancy inputs (stored as JSON on the model).
    cat_ur = forms.IntegerField(required=False, min_value=0, initial=0, label="UR", widget=forms.NumberInput(attrs={"class": "tf-input"}))
    cat_ews = forms.IntegerField(required=False, min_value=0, initial=0, label="EWS", widget=forms.NumberInput(attrs={"class": "tf-input"}))
    cat_obc = forms.IntegerField(required=False, min_value=0, initial=0, label="OBC (NCL)", widget=forms.NumberInput(attrs={"class": "tf-input"}))
    cat_sc = forms.IntegerField(required=False, min_value=0, initial=0, label="SC", widget=forms.NumberInput(attrs={"class": "tf-input"}))
    cat_st = forms.IntegerField(required=False, min_value=0, initial=0, label="ST", widget=forms.NumberInput(attrs={"class": "tf-input"}))
    required_certificates = forms.CharField(
        required=False,
        label="Required Certificates (comma-separated)",
        widget=forms.TextInput(attrs={"class": "tf-input", "placeholder": "e.g. SAP, Primavera, GATE scorecard"}),
        help_text="Leave blank to auto-detect certification keywords from the JD.",
    )

    # Certification keywords recognised in job descriptions.
    CERT_KEYWORDS = [
        "SAP", "Primavera", "AutoCAD", "MS Project", "FIDIC", "SCADA", "PMP",
        "GATE", "Six Sigma", "Tally", "Revit", "ETABS", "STAAD", "ArcGIS", "Python",
        "CFA", "CPA", "ISO 9001", "ISO 14001", "OHSAS", "NEBOSH", "First Aid",
    ]

    class Meta:
        model = Post
        fields = [
            "name", "post_code", "vacancies", "max_age", "qualification",
            "experience_required", "pay_scale", "location", "period_of_engagement",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "tf-input", "placeholder": "e.g. Executive (Civil)"}),
            "post_code": forms.TextInput(attrs={"class": "tf-input", "placeholder": "e.g. FTB/5/HR/12"}),
            "vacancies": forms.NumberInput(attrs={"class": "tf-input"}),
            "max_age": forms.NumberInput(attrs={"class": "tf-input"}),
            "qualification": forms.Textarea(attrs={"class": "tf-textarea", "rows": 2, "placeholder": "Full time B.E./B.Tech in Civil Engineering..."}),
            "experience_required": forms.Textarea(attrs={"class": "tf-textarea", "rows": 2, "placeholder": "Minimum 4 years post-qualification experience in..."}),
            "pay_scale": forms.NumberInput(attrs={"class": "tf-input", "placeholder": "e.g. 145000", "min": "0"}),
            "location": forms.TextInput(attrs={"class": "tf-input", "placeholder": DEFAULT_LOCATION}),
            "period_of_engagement": forms.TextInput(attrs={"class": "tf-input", "placeholder": DEFAULT_PERIOD}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not kwargs.get("data") and self.instance and self.instance.pk and self.instance.category_breakup:
            cb = self.instance.category_breakup
            for key in ("ur", "ews", "obc", "sc", "st"):
                self.fields[f"cat_{key}"].initial = cb.get(key, 0)
        # Set location/period defaults when editing.
        if not kwargs.get("data") and self.instance and not self.instance.location:
            self.fields["location"].initial = DEFAULT_LOCATION
        if not kwargs.get("data") and self.instance and not self.instance.period_of_engagement:
            self.fields["period_of_engagement"].initial = DEFAULT_PERIOD

    def clean(self):
        cleaned = super().clean()
        category_breakup = {}
        for key in ("ur", "ews", "obc", "sc", "st"):
            val = cleaned.get(f"cat_{key}") or 0
            if val:
                category_breakup[key] = int(val)
        cleaned["category_breakup"] = category_breakup

        # Certificates: use explicit list, or auto-detect from the JD text.
        certs = [c.strip() for c in (cleaned.get("required_certificates") or "").split(",") if c.strip()]
        if not certs:
            jd = " ".join([
                cleaned.get("qualification") or "",
                cleaned.get("experience_required") or "",
            ]).lower()
            certs = [kw for kw in self.CERT_KEYWORDS if kw.lower() in jd]
        cleaned["required_certificates"] = certs

        vacancies = cleaned.get("vacancies")
        if vacancies is not None and category_breakup:
            total = sum(category_breakup.values())
            if total != vacancies:
                self.add_error(
                    "vacancies",
                    f"Vacancies ({vacancies}) must equal the sum of category vacancies ({total}).",
                )
        return cleaned

    def clean_pay_scale(self):
        value = (self.cleaned_data.get("pay_scale") or "").strip()
        if not value:
            return value
        digits = value.replace(",", "").replace(" ", "")
        if not digits.isdigit():
            raise forms.ValidationError("Pay scale must be a number.")
        return f"Rs {digits}"


PostFormSet = forms.inlineformset_factory(
    Advertisement,
    Post,
    form=PostForm,
    extra=1,
    can_delete=True,
    min_num=1,
    validate_min=True,
)
