"""Authenticated endpoints for the results app: login, assignments, submitting and reviewing results."""
import io
import math
import uuid

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import HttpResponse
from django.utils import timezone

from core.lga_data import LGA_INDEX
from core.models import Election, ResultSubmission, StoredFile

from . import services, validators as v
from .base import ApiError, audit, endpoint, get_json, json_response, positive_int

AGENT, SUPERVISOR, ADMIN = services.ROLE_AGENT, services.ROLE_SUPERVISOR, services.ROLE_ADMIN
ANY = (AGENT, SUPERVISOR, ADMIN)
REVIEWERS = (SUPERVISOR, ADMIN)
S = ResultSubmission.Status


def paginate(qs, request, default=50, maximum=200):
    page = positive_int(request.GET.get("page"), 1)
    size = positive_int(request.GET.get("page_size"), default, maximum)
    total = qs.count()
    items = list(qs[(page - 1) * size: page * size])
    return items, {"count": total, "page": page, "page_size": size, "pages": math.ceil(total / size) if total else 0}


def _get_submission(request, pk):
    """Fetch a submission the caller may see; otherwise 404 (never reveal that it exists)."""
    sub = ResultSubmission.objects.select_related("polling_unit", "agent").filter(pk=pk).first()
    agent = request.agent
    if sub is None:
        raise ApiError(404, "not_found", "No such result.")
    if agent.role == AGENT and sub.agent_id != agent.pk:
        raise ApiError(404, "not_found", "No such result.")
    if agent.role != AGENT and not services.can_access_pu(agent, sub.polling_unit):
        raise ApiError(404, "not_found", "No such result.")
    return sub


# ---------------------------------------------------------------- authentication
@endpoint(public=True, rate=(10, 60))
def login(request):
    """Exchange phone + PIN for a bearer token."""
    data = get_json(request)
    result = services.login(request, data.get("phone"), data.get("pin"), str(data.get("device_name") or ""))
    return json_response(result)


@endpoint(roles=ANY, allow_pin_pending=True)
def logout(request):
    request.api_token.revoked_at = timezone.now()
    request.api_token.save(update_fields=["revoked_at"])
    audit(request, "logout")
    return json_response({"ok": True})


@endpoint(roles=ANY, allow_pin_pending=True)
def me(request):
    return json_response({"agent": services.agent_payload(request.agent, with_counts=True),
                          "token_expires_at": services.iso(request.api_token.expires_at)})


@endpoint(roles=ANY, allow_pin_pending=True, rate=(20, 60))
def change_pin(request):
    data = get_json(request)
    services.change_pin(request, request.agent, data.get("current_pin"), data.get("new_pin"))
    return json_response({"ok": True})


# ---------------------------------------------------------------- reference data for the app
@endpoint(roles=ANY)
def election_current(request):
    election = Election.current()
    if election is None:
        raise ApiError(409, "no_active_election", "No election is open for results right now.")
    return json_response({"election": services.election_payload(election)})


@endpoint(roles=(AGENT,))
def assignments(request):
    """The polling units this agent must report, with the state of each one's result."""
    election = Election.current()
    pus = list(request.agent.polling_units.filter(is_active=True).order_by("lga", "ward_index", "number"))
    mine = {}
    if election is not None:
        for sub in ResultSubmission.objects.filter(
                election=election, is_current=True, polling_unit__in=pus):
            mine[sub.polling_unit_id] = sub
    items = []
    for pu in pus:
        data = services.pu_payload(pu)
        sub = mine.get(pu.pk)
        data["result"] = None if sub is None else {
            "id": sub.pk, "status": sub.status, "submitted_at": services.iso(sub.created_at),
            "has_sheet": bool(sub.sheet_name),
        }
        items.append(data)
    return json_response({"election": services.election_payload(election), "polling_units": items})


# ---------------------------------------------------------------- submitting results
@endpoint(roles=(AGENT,))
def results_create(request):
    sub, created = services.submit_result(request, request.agent, get_json(request))
    return json_response({"duplicate": not created, "submission": services.submission_payload(sub)},
                         status=201 if created else 200)


@endpoint(roles=(AGENT,), rate=(30, 60))
def results_batch(request):
    """Up to 20 results in one call (for phones that were offline). Each item is judged separately."""
    data = get_json(request)
    items = data.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise v.ValidationFailed({"items": "Send a list of 1 to 20 result objects."})
    out = []
    for i, item in enumerate(items):
        try:
            sub, created = services.submit_result(request, request.agent, item)
            out.append({"index": i, "ok": True, "duplicate": not created,
                        "submission": services.submission_payload(sub)})
        except ApiError as err:
            entry = {"index": i, "ok": False, "error": {"code": err.code, "message": err.message}}
            entry["error"].update(err.extra)
            out.append(entry)
        except v.ValidationFailed as err:
            out.append({"index": i, "ok": False,
                        "error": {"code": "validation_failed", "message": err.message, "fields": err.fields}})
    return json_response({"results": out, "accepted": sum(1 for o in out if o["ok"])})


@endpoint(roles=(AGENT,))
def results_mine(request):
    qs = ResultSubmission.objects.select_related("polling_unit", "agent").filter(agent=request.agent)
    if request.GET.get("history") != "1":
        qs = qs.filter(is_current=True)
    items, page = paginate(qs, request, default=100, maximum=200)
    return json_response({**page, "results": [services.submission_payload(s, include_agent=False) for s in items]})


@endpoint(roles=ANY)
def results_detail(request, pk):
    return json_response({"submission": services.submission_payload(_get_submission(request, pk))})


# ---------------------------------------------------------------- result-sheet photo
ALLOWED_IMAGES = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}


@endpoint(roles=(AGENT, ADMIN), rate=(30, 60))
def sheet_upload(request, pk):
    """multipart/form-data with a ``sheet`` image (JPEG/PNG/WEBP) of the signed result sheet."""
    sub = _get_submission(request, pk)
    if not sub.is_current or sub.status == S.VERIFIED:
        raise ApiError(409, "not_editable", "Only the current, unverified result can take a new sheet photo.")
    upload = request.FILES.get("sheet")
    if upload is None:
        raise v.ValidationFailed({"sheet": "Send the photo as multipart form field 'sheet'."})
    if upload.size > settings.API_MAX_SHEET_BYTES:
        raise ApiError(413, "payload_too_large",
                       f"The photo is larger than {settings.API_MAX_SHEET_BYTES // 1_000_000} MB. Compress it first.")
    try:
        from PIL import Image

        img = Image.open(upload)
        fmt = img.format
        img.verify()
    except Exception:
        raise v.ValidationFailed({"sheet": "This file is not a readable image."})
    if fmt not in ALLOWED_IMAGES:
        raise v.ValidationFailed({"sheet": "Use a JPEG, PNG or WEBP image."})
    upload.seek(0)
    old = sub.sheet_name
    name = default_storage.save(f"sheets/{uuid.uuid4().hex}.{ALLOWED_IMAGES[fmt]}", upload)
    sub.sheet_name = name
    sub.save(update_fields=["sheet_name", "updated_at"])
    if old:
        default_storage.delete(old)
    audit(request, "upload_sheet", target=sub.polling_unit.code, submission=sub.pk)
    return json_response({"submission": services.submission_payload(sub)})


@endpoint(roles=ANY)
def sheet_get(request, pk):
    sub = _get_submission(request, pk)
    stored = StoredFile.objects.filter(name=sub.sheet_name).first() if sub.sheet_name else None
    if stored is None:
        raise ApiError(404, "no_sheet", "No sheet photo has been uploaded for this result.")
    data = bytes(stored.data)
    try:
        from PIL import Image

        mime = MIME.get(Image.open(io.BytesIO(data)).format, "application/octet-stream")
    except Exception:
        mime = "application/octet-stream"
    response = HttpResponse(data, content_type=mime)
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = 'inline; filename="result-sheet"'
    return response


# ---------------------------------------------------------------- supervisors / admins
@endpoint(roles=REVIEWERS)
def results_list(request):
    """Filter with ?lga=&ward=&status=&history=1&page=&page_size=."""
    qs = services.scoped_submissions(request.agent)
    election = Election.current()
    if election is not None:
        qs = qs.filter(election=election)
    if request.GET.get("history") != "1":
        qs = qs.filter(is_current=True)
    lga = request.GET.get("lga", "").strip()
    if lga:
        if lga not in LGA_INDEX:
            raise v.ValidationFailed({"lga": "Unknown LGA key."})
        qs = qs.filter(polling_unit__lga=lga)
    ward = request.GET.get("ward", "").strip()
    if ward:
        if not ward.isdigit():
            raise v.ValidationFailed({"ward": "Must be a ward index (0, 1, 2 ...)."})
        qs = qs.filter(polling_unit__ward_index=int(ward))
    status = request.GET.get("status", "").strip()
    if status:
        if status not in dict(S.choices):
            raise v.ValidationFailed({"status": "Unknown status."})
        qs = qs.filter(status=status)
    items, page = paginate(qs.order_by("-created_at"), request)
    return json_response({**page, "results": [services.submission_payload(s) for s in items]})


@endpoint(roles=REVIEWERS)
def results_review(request, pk):
    """Body: {"action": "verify" | "dispute" | "reject", "note": "..."}."""
    sub = _get_submission(request, pk)
    data = get_json(request)
    sub = services.review_submission(request, request.agent, sub, data.get("action"), data.get("note"))
    return json_response({"submission": services.submission_payload(sub)})


@endpoint(roles=REVIEWERS)
def results_summary(request):
    """Totals for supervisors, including results not yet verified, plus a count per status."""
    agent = request.agent
    lga = request.GET.get("lga", "").strip() or None
    if lga and lga not in LGA_INDEX:
        raise v.ValidationFailed({"lga": "Unknown LGA key."})
    ward = request.GET.get("ward", "").strip()
    ward_index = int(ward) if ward.isdigit() else None
    if ward and ward_index is None:
        raise v.ValidationFailed({"ward": "Must be a ward index."})
    data = services.summary_payload(
        lga=lga, ward_index=ward_index, lga_scope=agent.lga_scope if agent.role == SUPERVISOR else None,
        allowed_statuses=(S.SUBMITTED, S.VERIFIED, S.FLAGGED, S.DISPUTED))
    qs = services.scoped_submissions(agent).filter(is_current=True)
    election = Election.current()
    if election is not None:
        qs = qs.filter(election=election)
    data["by_status"] = {key: qs.filter(status=key).count() for key, _ in S.choices if key != S.SUPERSEDED}
    return json_response(data)
