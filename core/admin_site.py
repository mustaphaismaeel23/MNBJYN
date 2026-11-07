from datetime import timedelta

from django.contrib import admin
from django.db.models import Count
from django.utils import timezone


class SSBYNAdminSite(admin.AdminSite):
    site_header = "MNBJYN Administration"
    site_title = "MNBJYN Admin"
    index_title = "Registrations dashboard"

    def each_context(self, request):
        from django.conf import settings

        context = super().each_context(request)
        # On Vercel without DATABASE_URL the database is a throw-away file that
        # differs from one server instance to the next, so nothing saved in
        # /admin can reliably show on the website.
        context["db_warning"] = bool(settings.ON_VERCEL and settings.USING_SQLITE)
        return context

    def index(self, request, extra_context=None):
        from .models import (
            LGA_CHOICES,
            Election,
            PollingUnit,
            Registration,
            ResultAgent,
            ResultSubmission,
        )

        qs = Registration.objects.all()
        now = timezone.now()
        lga_names = dict(LGA_CHOICES)
        by_lga = [
            {"name": lga_names.get(r["lga"], r["lga"]), "total": r["total"]}
            for r in qs.values("lga").annotate(total=Count("id")).order_by("-total")
        ]
        top = by_lga[0]["total"] if by_lga else 1
        for row in by_lga:
            row["pct"] = round(row["total"] / top * 100)

        stats = {
            "total": qs.count(),
            "new": qs.filter(status=Registration.Status.NEW).count(),
            "approved": qs.filter(status=Registration.Status.APPROVED).count(),
            "week": qs.filter(created_at__gte=now - timedelta(days=7)).count(),
            "female": qs.filter(gender="female").count(),
            "male": qs.filter(gender="male").count(),
            "pwd": qs.filter(has_disability=True).count(),
            "no_pvc": qs.filter(pvc_status="no").count(),
            "agents": ResultAgent.objects.count(),
            "active_agents": ResultAgent.objects.filter(is_active=True).count(),
            "polling_units": PollingUnit.objects.count(),
            "active_polling_units": PollingUnit.objects.filter(is_active=True).count(),
            "results_to_review": ResultSubmission.objects.filter(
                is_current=True,
                status__in=(
                    ResultSubmission.Status.SUBMITTED,
                    ResultSubmission.Status.FLAGGED,
                    ResultSubmission.Status.DISPUTED,
                ),
            ).count(),
            "verified_results": ResultSubmission.objects.filter(
                is_current=True, status=ResultSubmission.Status.VERIFIED
            ).count(),
        }
        current_election = Election.current()
        extra_context = {
            **(extra_context or {}),
            "stats": stats,
            "current_election": current_election,
            "by_lga": by_lga,
            "recent": qs[:6],
        }
        return super().index(request, extra_context=extra_context)
