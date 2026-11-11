from django.contrib import admin
from django.db.models import Count, Q


class SSBYNAdminSite(admin.AdminSite):
    site_header = "MNBJYN Administration"
    site_title = "MNBJYN Admin"
    index_title = "Kano election operations dashboard"

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
            Election,
            PollingUnit,
            ResultAgent,
            ResultSubmission,
            Ward,
        )

        current_election = Election.current()
        active_pus = PollingUnit.objects.filter(is_active=True)
        agents = ResultAgent.objects.filter(role=ResultAgent.Role.AGENT)
        assignments = active_pus.filter(agents__role=ResultAgent.Role.AGENT).distinct()
        submissions = ResultSubmission.objects.filter(
            election=current_election, is_current=True
        ) if current_election else ResultSubmission.objects.none()
        active_submissions = submissions.filter(polling_unit__is_active=True)
        by_lga_results = dict(
            active_submissions.values("polling_unit__lga").annotate(total=Count("id"))
            .values_list("polling_unit__lga", "total")
        )
        by_lga_units = {
            row["lga"]: row
            for row in active_pus.values("lga").annotate(
                total=Count("id"),
                assigned=Count(
                    "id",
                    filter=Q(agents__role=ResultAgent.Role.AGENT),
                    distinct=True,
                ),
            )
        }
        reported_polling_units = active_pus.filter(
            submissions__election=current_election,
            submissions__is_current=True,
        ).distinct().count() if current_election else 0

        from .lga_data import KANO_LGAS

        by_lga = []
        for key, name, _ in KANO_LGAS:
            row = by_lga_units.get(key, {})
            total = row.get("total", 0)
            reported = by_lga_results.get(key, 0)
            by_lga.append({
                "key": key,
                "name": name,
                "total": total,
                "assigned": row.get("assigned", 0),
                "reported": reported,
                "pct": round(reported / total * 100) if total else 0,
            })

        stats = {
            "agents": agents.count(),
            "active_agents": agents.filter(is_active=True).count(),
            "polling_units": active_pus.count(),
            "assigned_polling_units": assignments.count(),
            "unassigned_polling_units": active_pus.count() - assignments.count(),
            "polling_units_yet_to_submit": active_pus.count() - reported_polling_units,
            "wards": Ward.objects.count(),
            "results_submitted": submissions.count(),
            "results_to_review": submissions.filter(status__in=(
                ResultSubmission.Status.SUBMITTED,
                ResultSubmission.Status.FLAGGED,
                ResultSubmission.Status.DISPUTED,
            )).count(),
            "verified_results": submissions.filter(status=ResultSubmission.Status.VERIFIED).count(),
            "rejected_results": submissions.filter(status=ResultSubmission.Status.REJECTED).count(),
        }
        extra_context = {
            **(extra_context or {}),
            "stats": stats,
            "current_election": current_election,
            "by_lga": by_lga,
        }
        return super().index(request, extra_context=extra_context)
