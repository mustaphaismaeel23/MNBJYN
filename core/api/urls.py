from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from . import views_admin as adm, views_agent as ag, views_public as pub
from .base import ApiError, endpoint, error_response, json_response, route
from .openapi import build_spec


@endpoint(public=True, cache_seconds=300)
def openapi_json(request):
    return json_response(build_spec())


@csrf_exempt
def api_not_found(request, rest=""):
    return error_response(ApiError(404, "not_found", "No such API endpoint."))


def p(pattern, view, name):
    """Register ``pattern`` with and without the trailing slash so clients cannot trip on it."""
    return [path(pattern, view, name=name), path(pattern.rstrip("/"), view)]


urlpatterns = [
    *p("health/", route(GET=pub.health), "health"),
    *p("openapi.json", route(GET=openapi_json), "openapi"),

    # ---- public (no login)
    *p("public/config/", route(GET=pub.config), "public_config"),
    *p("public/structure/", route(GET=pub.structure), "public_structure"),
    *p("public/results/", route(GET=pub.results), "public_results"),
    *p("public/summary/", route(GET=pub.summary), "public_summary"),
    *p("public/lgas/", route(GET=pub.lgas), "public_lgas"),
    *p("public/lgas/<slug:lga>/wards/", route(GET=pub.wards), "public_wards"),
    *p("public/lgas/<slug:lga>/wards/<int:ward_index>/polling-units/", route(GET=pub.polling_units), "public_pus"),

    # ---- authentication
    *p("auth/login/", route(POST=ag.login), "auth_login"),
    *p("auth/logout/", route(POST=ag.logout), "auth_logout"),
    *p("auth/me/", route(GET=ag.me), "auth_me"),
    *p("auth/change-pin/", route(POST=ag.change_pin), "auth_change_pin"),

    # ---- app: reference data and results
    *p("election/current/", route(GET=ag.election_current), "election_current"),
    *p("agent/assignments/", route(GET=ag.assignments), "agent_assignments"),
    *p("results/", route(GET=ag.results_list, POST=ag.results_create), "results"),
    *p("results/batch/", route(POST=ag.results_batch), "results_batch"),
    *p("results/mine/", route(GET=ag.results_mine), "results_mine"),
    *p("results/summary/", route(GET=ag.results_summary), "results_summary"),
    *p("results/<int:pk>/", route(GET=ag.results_detail), "results_detail"),
    *p("results/<int:pk>/review/", route(POST=ag.results_review), "results_review"),
    *p("results/<int:pk>/sheet/", route(GET=ag.sheet_get, POST=ag.sheet_upload, PUT=ag.sheet_upload), "results_sheet"),

    # ---- administrators
    *p("admin/agents/", route(GET=adm.agents_list, POST=adm.agents_create), "admin_agents"),
    *p("admin/agents/<int:pk>/", route(GET=adm.agent_detail, PATCH=adm.agent_update), "admin_agent"),
    *p("admin/agents/<int:pk>/reset-pin/", route(POST=adm.agent_reset_pin), "admin_agent_reset_pin"),
    *p("admin/agents/<int:pk>/revoke-tokens/", route(POST=adm.agent_revoke_tokens), "admin_agent_revoke"),
    *p("admin/agents/<int:pk>/assignments/", route(POST=adm.agent_assign), "admin_agent_assign"),
    *p("admin/polling-units/", route(GET=adm.pu_list), "admin_pus"),
    *p("admin/polling-units/import/", route(POST=adm.pu_import_view), "admin_pu_import"),
    *p("admin/polling-units/<str:code>/", route(PATCH=adm.pu_update), "admin_pu"),
    *p("admin/elections/", route(GET=adm.elections_list, POST=adm.elections_create), "admin_elections"),
    *p("admin/elections/<int:pk>/", route(PATCH=adm.elections_update), "admin_election"),
    *p("admin/situation-room/", route(GET=adm.situation_get, PATCH=adm.situation_update), "admin_situation"),
    *p("admin/audit/", route(GET=adm.audit_list), "admin_audit"),

    path("<path:rest>", api_not_found),
]
