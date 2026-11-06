from django import forms

from .models import INTEREST_CHOICES, Registration


class RegistrationForm(forms.ModelForm):
    interests = forms.MultipleChoiceField(
        label="Where would you like to help?",
        choices=INTEREST_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )
    consent = forms.BooleanField(
        required=True,
        label=(
            "I confirm the information above is correct and I agree to be contacted "
            "by MNBJYN about its activities."
        ),
        error_messages={"required": "Please tick the box to confirm and continue."},
    )
    # Honeypot: real users never see or fill this in; bots usually do.
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={
        "tabindex": "-1", "autocomplete": "off"}))

    class Meta:
        model = Registration
        fields = [
            "full_name", "gender", "age_range", "phone", "email",
            "lga", "ward", "community",
            "occupation_status", "institution_or_workplace", "has_disability",
            "pvc_status", "interests", "message", "consent",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs={"placeholder": "e.g. Aminu Musa Ibrahim", "autocomplete": "name"}),
            "phone": forms.TextInput(attrs={"placeholder": "08012345678", "inputmode": "tel", "autocomplete": "tel"}),
            "email": forms.EmailInput(attrs={"placeholder": "you@example.com (optional)", "autocomplete": "email"}),
            "ward": forms.TextInput(attrs={"placeholder": "Select LGA first, then pick or type your ward", "list": "ward-options", "autocomplete": "off"}),
            "community": forms.TextInput(attrs={"placeholder": "Town or community"}),
            "institution_or_workplace": forms.TextInput(
                attrs={"placeholder": "School, employer or business (optional)"}
            ),
            "message": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Anything you would like us to know (optional)"}
            ),
        }
        labels = {"has_disability": "I am a person living with a disability"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("gender", "age_range", "lga", "occupation_status", "pvc_status"):
            field = self.fields[name]
            field.choices = [("", "Select…")] + [c for c in field.choices if c[0] != ""]

    def clean_phone(self):
        phone = "".join(ch for ch in self.cleaned_data["phone"] if ch.isdigit() or ch == "+")
        if Registration.objects.filter(phone=phone).exists():
            raise forms.ValidationError(
                "This phone number has already been registered. Thank you!"
            )
        return phone

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("Spam detected.")
        return ""

    def clean_interests(self):
        return ",".join(self.cleaned_data.get("interests", []))

    def clean_full_name(self):
        return " ".join(self.cleaned_data["full_name"].split())
