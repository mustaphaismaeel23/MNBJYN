import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from .models import Executive, GalleryImage, Registration, SiteSettings, TeamMember


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = (
        "reference_col", "full_name", "gender", "age_range", "phone",
        "lga", "ward", "pvc_status", "status_badge", "created_at",
    )
    list_display_links = ("reference_col", "full_name")
    list_filter = (
        "status", "lga", "gender", "age_range", "occupation_status",
        "pvc_status", "has_disability", "created_at",
    )
    search_fields = ("full_name", "phone", "email", "ward", "community", "institution_or_workplace")
    date_hierarchy = "created_at"
    list_per_page = 50
    save_on_top = True
    actions = ["mark_reviewed", "mark_approved", "mark_rejected", "export_csv"]
    readonly_fields = ("created_at", "updated_at", "consent", "interests_display")

    fieldsets = (
        ("Personal details", {"fields": ("full_name", "gender", "age_range", "phone", "email")}),
        ("Location", {"fields": ("lga", "ward", "community")}),
        ("Background", {"fields": ("occupation_status", "institution_or_workplace", "has_disability")}),
        ("Participation", {"fields": ("pvc_status", "interests", "interests_display", "message")}),
        ("Review", {"fields": ("status", "admin_notes")}),
        ("Record", {"fields": ("consent", "created_at", "updated_at")}),
    )

    @admin.display(description="Ref", ordering="id")
    def reference_col(self, obj):
        return obj.reference

    @admin.display(description="Interests")
    def interests_display(self, obj):
        items = obj.interest_list
        return ", ".join(items) if items else "—"

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colors = {
            "new": "#b45309", "reviewed": "#1d4ed8",
            "approved": "#047857", "rejected": "#b91c1c",
        }
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 9px;border-radius:99px;'
            'font-size:11px;font-weight:600">{}</span>',
            colors.get(obj.status, "#555"), obj.get_status_display(),
        )

    def _set_status(self, request, queryset, status, label):
        updated = queryset.update(status=status, updated_at=timezone.now())
        self.message_user(request, f"{updated} registration(s) marked as {label}.", messages.SUCCESS)

    @admin.action(description="Mark selected as Reviewed")
    def mark_reviewed(self, request, queryset):
        self._set_status(request, queryset, Registration.Status.REVIEWED, "reviewed")

    @admin.action(description="Mark selected as Approved")
    def mark_approved(self, request, queryset):
        self._set_status(request, queryset, Registration.Status.APPROVED, "approved")

    @admin.action(description="Mark selected as Rejected")
    def mark_rejected(self, request, queryset):
        self._set_status(request, queryset, Registration.Status.REJECTED, "rejected")

    @admin.action(description="Export selected to CSV")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        response["Content-Disposition"] = f'attachment; filename="ssbyn-registrations-{stamp}.csv"'
        response.write("﻿")  # BOM so Excel reads UTF-8 correctly
        writer = csv.writer(response)
        writer.writerow([
            "Reference", "Full name", "Gender", "Age range", "Phone", "Email",
            "LGA", "Ward", "Community", "Status", "Institution/Workplace",
            "Person with disability", "PVC status", "Interests", "Message",
            "Review status", "Internal notes", "Registered at",
        ])
        for r in queryset.iterator():
            writer.writerow([
                r.reference, r.full_name, r.get_gender_display(), r.age_range, r.phone, r.email,
                r.get_lga_display(), r.ward, r.community, r.get_occupation_status_display(),
                r.institution_or_workplace, "Yes" if r.has_disability else "No",
                r.get_pvc_status_display(), "; ".join(r.interest_list), r.message,
                r.get_status_display(), r.admin_notes,
                timezone.localtime(r.created_at).strftime("%Y-%m-%d %H:%M"),
            ])
        return response


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
    AuditLog, Candidate, Election, PollingUnit, ResultAgent, ResultSubmission, SituationRoomConfig,
)


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
    """The simulation / live switch. Open it from the admin home page."""

    fields = ("mode", "publish_unverified", "refresh_seconds", "go_live_checks")
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
    list_display = ("code", "name", "lga", "ward_name", "registered_voters", "is_active")
    list_filter = ("lga", "is_active")
    search_fields = ("code", "name", "ward_name")
    list_per_page = 100


@admin.register(ResultAgent)
class ResultAgentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "role", "lga_scope", "is_active", "units", "last_login_at")
    list_filter = ("role", "is_active")
    search_fields = ("full_name", "phone")
    autocomplete_fields = ("polling_units",)
    exclude = ("pin_hash",)
    readonly_fields = ("failed_logins", "locked_until", "last_login_at", "created_at", "updated_at")
    actions = ["reset_pin", "unlock"]

    @admin.display(description="Polling units")
    def units(self, obj):
        return obj.polling_units.count()

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
