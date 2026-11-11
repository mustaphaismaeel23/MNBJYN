"""Public, read-only endpoints (no login). Used by the Situation Room and by anyone who
wants to display results or the polling-unit directory."""
from django.db.models import Count

from core.lga_data import KANO_LGAS, LGA_INDEX, lga_code, ward_code
from core.models import PollingUnit, Ward

from . import services, validators as v
from .base import ApiError, endpoint, json_response


@endpoint(public=True, cache_seconds=3)
def health(request):
    return json_response({"status": "ok", "service": "mnbjyn-results-api", "version": "1"})


@endpoint(public=True, cache_seconds=3)
def config(request):
    """Live Situation Room settings, the active election and candidates."""
    return json_response(services.config_payload())


@endpoint(public=True, cache_seconds=60)
def structure(request):
    """Every LGA > ward > polling unit in one compact response."""
    return json_response(services.structure_payload())


@endpoint(public=True, cache_seconds=3)
def results(request):
    """Public results. Poll with ``?since=<cursor from the previous response>`` for changes only."""
    since = None
    raw = request.GET.get("since", "").strip()
    if raw:
        errors = {}
        since = v.parse_iso_datetime(raw, "since", errors)
        if errors:
            raise v.ValidationFailed(errors)
    return json_response(services.public_results_payload(since))


@endpoint(public=True, cache_seconds=5)
def summary(request):
    """Totals for the state, an LGA (``?lga=kano_municipal``) or a ward."""
    lga = request.GET.get("lga", "").strip() or None
    ward = request.GET.get("ward", "").strip()
    if lga and lga not in LGA_INDEX:
        raise v.ValidationFailed({"lga": "Unknown LGA key. See /api/v1/public/lgas/."})
    ward_index = None
    if ward:
        if not lga:
            raise v.ValidationFailed({"ward": "Give the lga as well."})
        if not ward.isdigit() or not Ward.objects.filter(lga=lga, ward_index=int(ward)).exists():
            raise v.ValidationFailed({"ward": "Unknown ward index for that LGA."})
        ward_index = int(ward)
    return json_response(services.summary_payload(lga=lga, ward_index=ward_index))


@endpoint(public=True, cache_seconds=300)
def lgas(request):
    ward_counts = dict(
        Ward.objects.values("lga").annotate(total=Count("id")).values_list("lga", "total")
    )
    return json_response({"lgas": [
        {"key": key, "code": lga_code(key), "name": name, "wards": ward_counts.get(key, 0)}
        for key, name, _ in KANO_LGAS
    ]})


@endpoint(public=True, cache_seconds=300)
def wards(request, lga):
    lga_names = {key: name for key, name, _ in KANO_LGAS}
    if lga not in lga_names:
        raise ApiError(404, "lga_not_found", "Unknown LGA key.")
    counts = {}
    for idx in PollingUnit.objects.filter(lga=lga, is_active=True).values_list("ward_index", flat=True):
        counts[idx] = counts.get(idx, 0) + 1
    ward_rows = Ward.objects.filter(lga=lga).order_by("sort_order", "ward_index")
    return json_response({
        "lga": {"key": lga, "code": lga_code(lga), "name": lga_names[lga]},
        "wards": [
            {
                "index": ward.ward_index,
                "code": ward_code(lga, ward.ward_index),
                "name": ward.name,
                "polling_units": counts.get(ward.ward_index, 0),
            }
            for ward in ward_rows
        ],
    })


@endpoint(public=True, cache_seconds=60)
def polling_units(request, lga, ward_index):
    ward = Ward.objects.filter(lga=lga, ward_index=ward_index).first()
    if ward is None:
        raise ApiError(404, "ward_not_found", "Unknown LGA or ward.")
    qs = PollingUnit.objects.filter(lga=lga, ward_index=ward_index, is_active=True)
    return json_response({
        "lga": lga, "ward_index": ward_index, "ward_name": ward.name,
        "polling_units": [services.pu_payload(p) for p in qs],
    })
