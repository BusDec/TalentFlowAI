"""Forms for the candidate-facing portal."""

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import CandidatePortalUser


class CandidateRegistrationForm(forms.ModelForm):
    class Meta:
        model = CandidatePortalUser
        fields = ["email", "phone", "full_name"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "tf-input", "placeholder": "you@example.com"}),
            "phone": forms.TextInput(attrs={"class": "tf-input", "placeholder": "10-digit mobile"}),
            "full_name": forms.TextInput(attrs={"class": "tf-input", "placeholder": "Full name as per certificates"}),
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if CandidatePortalUser.objects.filter(email=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email


class OTPVerifyForm(forms.Form):
    otp = forms.CharField(
        max_length=6,
        widget=forms.PasswordInput(attrs={"class": "tf-input", "inputmode": "numeric"}),
    )


class CandidateLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "tf-input", "placeholder": "you@example.com"})
    )
