from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html, format_html_join

from .lga_data import KANO_LGAS, pu_code
from .models import Executive, GalleryImage, SiteSettings, TeamMember


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    """Edit the hero photo shown on the home page."""

    fields = ("hero_image", "hero_caption")

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # Jump straight to the single settings record.
        from django.shortcuts import redirect
        from django.urls import reverse

        obj = SiteSettings.load()
        return redirect(reverse("admin:core_sitesettings_change", args=[obj.pk]))


@admin.register(GalleryImage)
class GalleryImageAdmin(admin.ModelAdmin):
    list_display = ("thumb", "caption", "event_date", "order", "is_published")
    list_editable = ("order", "is_published")
    list_filter = ("is_published",)
    search_fields = ("caption",)

    @admin.display(description="Photo")
    def thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:48px;width:72px;object-fit:cover;border-radius:6px">',
                obj.image.url,
            )
        return "—"


class PersonAdmin(admin.ModelAdmin):
    list_display = ("thumb", "name", "subname", "order", "is_published")
    list_display_links = ("thumb", "name")
    list_editable = ("order", "is_published")
    search_fields = ("name", "subname")
    fields = ("name", "subname", "image", "photo_preview", "order", "is_published")
    readonly_fields = ("photo_preview",)

    @admin.display(description="Photo")
    def thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="height:48px;width:48px;object-fit:cover;border-radius:50%">',
                obj.image.url,
            )
        return "—"

    @admin.display(description="Current photo")
    def photo_preview(self, obj):
        if obj and obj.image:
            return format_html(
                '<img src="{}" style="max-height:180px;border-radius:10px">', obj.image.url
            )
        return "No photo uploaded yet."


@admin.register(Executive)
class ExecutiveAdmin(PersonAdmin):
    pass


@admin.register(TeamMember)
class TeamMemberAdmin(PersonAdmin):
    """The website's Team section shows every published team member (no limit)."""


# ===========================================================================
# Election-day results: elections, polling units, agents, submissions, switch
# ===========================================================================
from django.shortcuts import redirect as _redirect
from django.urls import reverse as _reverse

from .models import (
    AuditLog, Candidate, Election, PollingUnit, ResultAgent, ResultSubmission, SituationRoomConfig, Ward,
)


class ResultAgentCreationForm(forms.ModelForm):
    assignment_lga = forms.ChoiceField(
        label="Local government",
        required=False,
        choices=[("", "Select local government")] + [(key, name) for key, name, _ in KANO_LGAS],
    )
    assignment_ward = forms.ChoiceField(
        label="Ward",
        required=False,
        choices=[("", "Select ward")],
    )
    assignment_polling_unit = forms.ModelChoiceField(
        label="Polling unit",
        required=False,
        queryset=PollingUnit.objects.none(),
        to_field_name="code",
        empty_label="Select polling unit",
    )

    class Meta:
        model = ResultAgent
        fields = ("full_name", "phone", "role", "lga_scope")

    class Media:
        js = ("core/js/result_agent_location.js",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        lga = self.data.get(self.add_prefix("assignment_lga")) if self.is_bound else ""
        ward_index = self.data.get(self.add_prefix("assignment_ward")) if self.is_bound else ""

        if lga:
            wards = Ward.objects.filter(lga=lga).order_by("sort_order", "ward_index")
            self.fields["assignment_ward"].choices = [("", "Select ward")] + [
                (str(ward.ward_index), ward.name) for ward in wards
            ]
            if ward_index and ward_index.isdigit():
                self.fields["assignment_polling_unit"].queryset = PollingUnit.objects.filter(
                    is_active=True, lga=lga, ward_index=int(ward_index),
                ).order_by("number")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("role") == ResultAgent.Role.AGENT:
            for field in ("assignment_lga", "assignment_ward", "assignment_polling_unit"):
                if not cleaned.get(field):
                    self.add_error(field, "Select the agent's local government, ward and polling unit.")
        return cleaned

    def save_related_assignment(self, agent):
        polling_unit = self.cleaned_data.get("assignment_polling_unit")
        agent.polling_units.set([polling_unit] if polling_unit else [])


class ResultAgentUpdateForm(forms.ModelForm):
    class Meta:
        model = ResultAgent
        exclude = ("pin_hash",)

    def clean_polling_units(self):
        polling_units = self.cleaned_data["polling_units"]
        role = self.cleaned_data.get("role", self.instance.role)
        if role == ResultAgent.Role.AGENT and polling_units.count() != 1:
            raise forms.ValidationError("Assign each polling-unit agent to exactly one polling unit.")
        if role != ResultAgent.Role.AGENT and polling_units.exists():
            raise forms.ValidationError("Only polling-unit agents can have polling-unit assignments.")
        return polling_units


class CandidateInline(admin.TabularInline):
    model = Candidate
    extra = 0
    fields = ("order", "name", "short_name", "color")


@admin.register(Election)
class ElectionAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "election_date", "is_current")
    inlines = [CandidateInline]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(SituationRoomConfig)
class SituationRoomConfigAdmin(admin.ModelAdmin):
    """Configure live Situation Room visibility."""

    fields = ("publish_unverified", "refresh_seconds", "go_live_checks")
    readonly_fields = ("go_live_checks",)

    @admin.display(description="Go-live checks")
    def go_live_checks(self, obj):
        from .api.services import security_warnings

        items = security_warnings()
        if not items:
            return "All checks passed."
        return format_html(
            "<ul>{}</ul>",
            format_html_join("", "<li><b>{}</b>: {}</li>", ((w["level"].upper(), w["message"]) for w in items)),
        )

    def has_add_permission(self, request):
        return not SituationRoomConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        obj = SituationRoomConfig.load()
        return _redirect(_reverse("admin:core_situationroomconfig_change", args=[obj.pk]))


@admin.register(PollingUnit)
class PollingUnitAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "lga_display", "ward_display", "registered_voters", "is_active")
    list_filter = ("lga", "is_active")
    search_fields = ("code", "name", "ward_name", "ward_record__name")
    autocomplete_fields = ("ward_record",)
    list_per_page = 100

    class Form(forms.ModelForm):
        class Meta:
            model = PollingUnit
            fields = "__all__"

        def clean(self):
            cleaned = super().clean()
            ward = cleaned.get("ward_record")
            number = cleaned.get("number")
            if ward is not None and number is not None:
                location_changed = (
                    not self.instance.pk
                    or ward.pk != self.instance.ward_record_id
                    or number != self.instance.number
                )
                if location_changed:
                    code = pu_code(ward.lga, ward.ward_index, number)
                    existing = PollingUnit.objects.filter(code=code)
                    if self.instance.pk:
                        existing = existing.exclude(pk=self.instance.pk)
                    if existing.exists():
                        self.add_error(
                            "number",
                            "A polling unit with this number already exists in the selected ward.",
                        )
            return cleaned

    form = Form

    def get_fields(self, request, obj=None):
        return (
            "ward_record", "number", "code", "name", "registered_voters",
            "latitude", "longitude", "is_active",
        )

    def get_readonly_fields(self, request, obj=None):
        return ("code",)

    def save_model(self, request, obj, form, change):
        if obj.ward_record_id is None:
            raise ValueError("Select a ward before saving a polling unit.")
        previous = None
        if change:
            previous = PollingUnit.objects.get(pk=obj.pk)
        obj.lga = obj.ward_record.lga
        obj.ward_index = obj.ward_record.ward_index
        obj.ward_name = obj.ward_record.name
        if previous is None or (
            previous.ward_record_id != obj.ward_record_id or previous.number != obj.number
        ):
            obj.code = pu_code(obj.lga, obj.ward_index, obj.number)
        super().save_model(request, obj, form, change)

    @admin.display(description="LGA", ordering="lga")
    def lga_display(self, obj):
        return obj.lga_name

    @admin.display(description="Ward", ordering="ward_record__sort_order")
    def ward_display(self, obj):
        return obj.ward_record.name if obj.ward_record_id else obj.ward_name


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ("name", "get_lga_display", "ward_index", "sort_order", "polling_unit_count")
    list_display_links = ("name",)
    list_editable = ("sort_order",)
    list_filter = ("lga",)
    search_fields = ("name", "lga")
    ordering = ("lga", "sort_order", "ward_index")

    def get_fields(self, request, obj=None):
        return ("lga", "name", "sort_order") if obj else ("lga", "name")

    def get_readonly_fields(self, request, obj=None):
        return ("lga",) if obj else ()

    def save_model(self, request, obj, form, change):
        if not change:
            from django.db.models import Max

            existing = Ward.objects.filter(lga=obj.lga)
            last = existing.aggregate(index=Max("ward_index"), order=Max("sort_order"))
            obj.ward_index = (last["index"] if last["index"] is not None else -1) + 1
            obj.sort_order = (last["order"] if last["order"] is not None else -1) + 1
        super().save_model(request, obj, form, change)

    @admin.display(description="Polling units")
    def polling_unit_count(self, obj):
        return obj.polling_units.count()

    def has_delete_permission(self, request, obj=None):
        if obj and obj.polling_units.exists():
            return False
        return super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        if queryset.filter(polling_units__isnull=False).exists():
            self.message_user(
                request,
                "Wards with polling units cannot be deleted. Remove or move those units first.",
                messages.ERROR,
            )
            return
        super().delete_queryset(request, queryset)


@admin.register(ResultAgent)
class ResultAgentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "role", "lga_scope", "is_active", "units", "last_login_at")
    list_filter = ("role", "is_active")
    search_fields = ("full_name", "phone")
    autocomplete_fields = ("polling_units",)
    exclude = ("pin_hash",)
    form = ResultAgentUpdateForm
    readonly_fields = ("failed_logins", "locked_until", "last_login_at", "created_at", "updated_at")
    actions = ["reset_pin", "unlock"]

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = ResultAgentCreationForm
        return super().get_form(request, obj, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return (
                "full_name", "phone", "role", "assignment_lga", "assignment_ward",
                "assignment_polling_unit", "lga_scope",
            )
        return super().get_fields(request, obj)

    @admin.display(description="Polling units")
    def units(self, obj):
        return obj.polling_units.count()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if isinstance(form, ResultAgentCreationForm):
            form.save_related_assignment(form.instance)

    def save_model(self, request, obj, form, change):
        from .api.validators import generate_pin, normalise_phone

        # The app/API always look users up by the normalised number (08012345678),
        # so store it that way even if +234... was typed here.
        obj.phone = normalise_phone(obj.phone)
        pin = None
        if not change:
            pin = generate_pin()
            obj.set_pin(pin)
            obj.must_change_pin = True
        super().save_model(request, obj, form, change)
        if change and obj.role != ResultAgent.Role.AGENT:
            obj.polling_units.clear()
        if pin:
            messages.warning(request, f"Temporary PIN for {obj.full_name}: {pin}  (shown once - give it to the agent securely).")

    @admin.action(description="Reset PIN (shows a new temporary PIN) and sign out")
    def reset_pin(self, request, queryset):
        from django.utils import timezone as tz
        from .api.validators import generate_pin

        for agent in queryset:
            pin = generate_pin()
            agent.set_pin(pin)
            agent.must_change_pin, agent.failed_logins, agent.locked_until = True, 0, None
            agent.save()
            agent.tokens.filter(revoked_at__isnull=True).update(revoked_at=tz.now())
            messages.warning(request, f"New temporary PIN for {agent.full_name}: {pin}")

    @admin.action(description="Unlock login")
    def unlock(self, request, queryset):
        queryset.update(failed_logins=0, locked_until=None)


@admin.register(ResultSubmission)
class ResultSubmissionAdmin(admin.ModelAdmin):
    list_display = ("polling_unit", "status", "is_current", "valid_votes", "accredited_voters", "agent", "created_at")
    list_filter = ("status", "is_current", "polling_unit__lga")
    search_fields = ("polling_unit__code", "agent__full_name")
    date_hierarchy = "created_at"
    actions = ["verify", "dispute", "reject"]
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields if f.name not in ("status", "review_note")]

    def _review(self, request, queryset, status):
        from django.utils import timezone as tz

        n = queryset.filter(is_current=True).update(status=status, reviewed_at=tz.now(), updated_at=tz.now())
        self.message_user(request, f"{n} result(s) marked {status}.", messages.SUCCESS)

    @admin.action(description="Mark selected as Verified")
    def verify(self, request, queryset):
        self._review(request, queryset, ResultSubmission.Status.VERIFIED)

    @admin.action(description="Mark selected as Disputed")
    def dispute(self, request, queryset):
        self._review(request, queryset, ResultSubmission.Status.DISPUTED)

    @admin.action(description="Mark selected as Rejected")
    def reject(self, request, queryset):
        self._review(request, queryset, ResultSubmission.Status.REJECTED)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "action", "actor", "target", "ip_address")
    list_filter = ("action",)
    search_fields = ("target", "actor__full_name")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
