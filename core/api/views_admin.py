"""Administrator endpoints: agents, assignments, polling units, elections, Situation Room switch, audit log."""
import re

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from core.lga_data import LGA_INDEX
from core.models import (
    AuditLog, Candidate, Election, PollingUnit, ResultAgent, ResultSubmission, SituationRoomConfig,
)

from . import pu_import, services, validators as v
from .base import ApiError, audit, endpoint, get_json, json_response
from .views_agent import paginate

ADMIN = services.ROLE_ADMIN
ROLES = dict(ResultAgent.Role.choices)
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,58}$")


def _agent_or_404(pk):
    agent = ResultAgent.objects.filter(pk=pk).first()
    if agent is None:
        raise ApiError(404, "not_found", "No such agent.")
    return agent


# ================================================================= agents
@endpoint(roles=(ADMIN,))
def agents_list(request):
    qs = ResultAgent.objects.all()
    role = request.GET.get("role", "").strip()
    if role:
        qs = qs.filter(role=role)
    q = request.GET.get("q", "").strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(full_name__icontains=q) | Q(phone__icontains=q))
    items, page = paginate(qs, request)
    return json_response({**page, "agents": [services.agent_payload(a, with_counts=True) for a in items]})


def _resolve_pus(data):
    """polling_unit_codes / ward / lga selectors -> list of PollingUnit."""
    found = {}
    codes = data.get("polling_unit_codes")
    if codes is not None:
        if not isinstance(codes, list) or len(codes) > 2000:
            raise v.ValidationFailed({"polling_unit_codes": "Send a list of at most 2000 codes."})
        wanted = {str(c).strip().replace("-", "/") for c in codes}
        for pu in PollingUnit.objects.filter(code__in=wanted, is_active=True):
            found[pu.pk] = pu
        unknown = sorted(wanted - {p.code for p in found.values()})
        if unknown:
            raise v.ValidationFailed({"polling_unit_codes": "Unknown or inactive: " + ", ".join(unknown[:20])})
    ward = data.get("ward")
    if ward is not None:
        if (not isinstance(ward, dict) or ward.get("lga") not in LGA_INDEX
                or not isinstance(ward.get("ward_index"), int)):
            raise v.ValidationFailed({"ward": 'Use {"lga": "kano_municipal", "ward_index": 3}.'})
        for pu in PollingUnit.objects.filter(lga=ward["lga"], ward_index=ward["ward_index"], is_active=True):
            found[pu.pk] = pu
    lga = data.get("lga")
    if lga is not None:
        if lga not in LGA_INDEX:
            raise v.ValidationFailed({"lga": "Unknown LGA key."})
        for pu in PollingUnit.objects.filter(lga=lga, is_active=True):
            found[pu.pk] = pu
    return list(found.values())


def _apply_assignment(agent, mode, pus):
    if mode == "replace":
        agent.polling_units.set(pus)
    elif mode == "add":
        agent.polling_units.add(*pus)
    elif mode == "remove":
        agent.polling_units.remove(*pus)
    else:
        raise v.ValidationFailed({"mode": "Use add, remove or replace."})


@endpoint(roles=(ADMIN,))
def agents_create(request):
    """Create an agent. The response contains the temporary PIN ONCE; hand it over securely."""
    data = get_json(request)
    errors = {}
    name = str(data.get("full_name") or "").strip()
    if not 3 <= len(name) <= 150:
        errors["full_name"] = "Enter the full name (3 to 150 characters)."
    phone = v.normalise_phone(data.get("phone"))
    if not v.phone_is_valid(phone):
        errors["phone"] = "Enter a valid phone number, e.g. 08012345678."
    elif ResultAgent.objects.filter(phone=phone).exists():
        errors["phone"] = "An agent with this phone number already exists."
    role = data.get("role", "agent")
    if role not in ROLES:
        errors["role"] = f"Use one of: {', '.join(ROLES)}."
    scope = str(data.get("lga_scope") or "")
    if scope and scope not in LGA_INDEX:
        errors["lga_scope"] = "Unknown LGA key."
    if errors:
        raise v.ValidationFailed(errors)
    pus = _resolve_pus(data) if any(k in data for k in ("polling_unit_codes", "ward", "lga")) else []
    if pus and role != "agent":
        raise v.ValidationFailed({"role": "Only polling-unit agents have assigned polling units."})
    pin = v.generate_pin()
    agent = ResultAgent(full_name=name, phone=phone, role=role, lga_scope=scope, must_change_pin=True)
    agent.set_pin(pin)
    try:
        with transaction.atomic():
            agent.save()
            if pus:
                agent.polling_units.set(pus)
    except IntegrityError:
        raise v.ValidationFailed({"phone": "An agent with this phone number already exists."})
    audit(request, "agent_create", target=agent.pk, role=role, assigned=len(pus))
    return json_response({"agent": services.agent_payload(agent, with_counts=True), "temporary_pin": pin}, status=201)


@endpoint(roles=(ADMIN,))
def agent_detail(request, pk):
    agent = _agent_or_404(pk)
    pus = [services.pu_payload(p) for p in agent.polling_units.order_by("lga", "ward_index", "number")[:500]]
    return json_response({"agent": services.agent_payload(agent, with_counts=True), "polling_units": pus})


@endpoint(roles=(ADMIN,))
def agent_update(request, pk):
    agent = _agent_or_404(pk)
    data = get_json(request)
    errors, changed = {}, []
    if "full_name" in data:
        name = str(data["full_name"] or "").strip()
        if not 3 <= len(name) <= 150:
            errors["full_name"] = "Enter the full name (3 to 150 characters)."
        else:
            agent.full_name = name; changed.append("full_name")
    if "phone" in data:
        phone = v.normalise_phone(data["phone"])
        if not v.phone_is_valid(phone):
            errors["phone"] = "Enter a valid phone number."
        elif ResultAgent.objects.filter(phone=phone).exclude(pk=agent.pk).exists():
            errors["phone"] = "Another agent already uses this phone number."
        else:
            agent.phone = phone; changed.append("phone")
    if "role" in data:
        if data["role"] not in ROLES:
            errors["role"] = f"Use one of: {', '.join(ROLES)}."
        elif agent.pk == request.agent.pk and data["role"] != ADMIN:
            errors["role"] = "You cannot remove your own administrator role."
        else:
            agent.role = data["role"]; changed.append("role")
    if "lga_scope" in data:
        scope = str(data["lga_scope"] or "")
        if scope and scope not in LGA_INDEX:
            errors["lga_scope"] = "Unknown LGA key."
        else:
            agent.lga_scope = scope; changed.append("lga_scope")
    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            errors["is_active"] = "Must be true or false."
        elif agent.pk == request.agent.pk and not data["is_active"]:
            errors["is_active"] = "You cannot deactivate yourself."
        else:
            agent.is_active = data["is_active"]; changed.append("is_active")
    if errors:
        raise v.ValidationFailed(errors)
    if changed:
        agent.save(update_fields=changed + ["updated_at"])
        if "is_active" in changed and not agent.is_active:
            agent.tokens.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
        audit(request, "agent_update", target=agent.pk, fields=changed)
    return json_response({"agent": services.agent_payload(agent, with_counts=True)})


@endpoint(roles=(ADMIN,))
def agent_reset_pin(request, pk):
    agent = _agent_or_404(pk)
    pin = v.generate_pin()
    agent.set_pin(pin)
    agent.must_change_pin, agent.failed_logins, agent.locked_until = True, 0, None
    agent.save(update_fields=["pin_hash", "must_change_pin", "failed_logins", "locked_until", "updated_at"])
    agent.tokens.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
    audit(request, "agent_reset_pin", target=agent.pk)
    return json_response({"agent": services.agent_payload(agent), "temporary_pin": pin})


@endpoint(roles=(ADMIN,))
def agent_revoke_tokens(request, pk):
    agent = _agent_or_404(pk)
    n = agent.tokens.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())
    audit(request, "agent_revoke_tokens", target=agent.pk, revoked=n)
    return json_response({"revoked": n})


@endpoint(roles=(ADMIN,))
def agent_assign(request, pk):
    """Body: {"mode": "add"|"remove"|"replace", and any of "polling_unit_codes": [...],
    "ward": {"lga": "kano_municipal", "ward_index": 3}, "lga": "kano_municipal"}"""
    agent = _agent_or_404(pk)
    if agent.role != "agent":
        raise v.ValidationFailed({"role": "Only polling-unit agents have assigned polling units."})
    data = get_json(request)
    pus = _resolve_pus(data)
    if not pus and data.get("mode") != "replace":
        raise v.ValidationFailed({"polling_unit_codes": "Select at least one polling unit."})
    _apply_assignment(agent, data.get("mode", "add"), pus)
    audit(request, "agent_assign", target=agent.pk, mode=data.get("mode", "add"), count=len(pus))
    return json_response({"agent": services.agent_payload(agent, with_counts=True)})


# ================================================================= polling units
@endpoint(roles=(ADMIN,))
def pu_list(request):
    qs = PollingUnit.objects.all()
    lga = request.GET.get("lga", "").strip()
    if lga:
        qs = qs.filter(lga=lga)
    ward = request.GET.get("ward", "").strip()
    if ward.isdigit():
        qs = qs.filter(ward_index=int(ward))
    q = request.GET.get("q", "").strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
    items, page = paginate(qs, request, default=100, maximum=500)
    return json_response({**page, "polling_units": [services.pu_payload(p) for p in items]})


@endpoint(roles=(ADMIN,))
def pu_update(request, code):
    pu = PollingUnit.objects.filter(code=code.replace("-", "/")).first()
    if pu is None:
        raise ApiError(404, "not_found", "No such polling unit.")
    data = get_json(request)
    errors, changed = {}, []
    if "name" in data:
        pu.name = str(data["name"] or "").strip()[:200]; changed.append("name")
    if "registered_voters" in data:
        n = v.parse_count(data["registered_voters"], "registered_voters", errors)
        if n is not None:
            pu.registered_voters = n; changed.append("registered_voters")
    if "latitude" in data or "longitude" in data:
        lat = v.parse_coordinate(data.get("latitude"), "latitude", errors, -90, 90)
        lng = v.parse_coordinate(data.get("longitude"), "longitude", errors, -180, 180)
        if (lat is None) != (lng is None):
            errors["latitude"] = "Send latitude and longitude together (or both null)."
        elif not errors:
            pu.latitude, pu.longitude = lat, lng; changed += ["latitude", "longitude"]
    if "is_active" in data:
        if not isinstance(data["is_active"], bool):
            errors["is_active"] = "Must be true or false."
        else:
            pu.is_active = data["is_active"]; changed.append("is_active")
    if errors:
        raise v.ValidationFailed(errors)
    if changed:
        pu.save(update_fields=changed)
        audit(request, "pu_update", target=pu.code, fields=changed)
    return json_response({"polling_unit": services.pu_payload(pu)})


@endpoint(roles=(ADMIN,), rate=(10, 60))
def pu_import_view(request):
    """multipart/form-data: ``file`` (CSV, see docs) and optional ``replace=true``."""
    upload = request.FILES.get("file")
    if upload is None:
        raise v.ValidationFailed({"file": "Upload a CSV file in the 'file' field."})
    if upload.size > 4_000_000:
        raise ApiError(413, "payload_too_large", "CSV is larger than 4 MB. Split it by LGA or use the import_polling_units command.")
    rows, errors = pu_import.parse_csv(pu_import.decode_bytes(upload.read()))
    if errors:
        raise ApiError(422, "invalid_csv", "The CSV has problems. Nothing was imported.",
                       extra={"problems": errors})
    if not rows:
        raise v.ValidationFailed({"file": "The CSV has no data rows."})
    replace = str(request.POST.get("replace", "")).lower() in ("1", "true", "yes")
    result = pu_import.apply_rows(rows, replace=replace)
    audit(request, "pu_import", rows=len(rows), replace=replace, **result)
    return json_response({"rows": len(rows), **result})


# ================================================================= elections
def _clean_candidates(raw):
    if not isinstance(raw, list) or not 2 <= len(raw) <= 30:
        raise v.ValidationFailed({"candidates": "Send 2 to 30 candidates."})
    out, shorts = [], set()
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            raise v.ValidationFailed({"candidates": f"Item {i} must be an object."})
        name = str(c.get("name") or "").strip()
        short = str(c.get("short_name") or "").strip()
        color = str(c.get("color") or "#FFFFFF")
        if not name or not 1 <= len(short) <= 12 or not HEX.fullmatch(color) or short.lower() in shorts:
            raise v.ValidationFailed({"candidates": f"Item {i}: need name, a unique short_name (max 12) and a #RRGGBB colour."})
        shorts.add(short.lower())
        out.append({"name": name[:120], "short_name": short, "color": color, "order": i})
    return out


@endpoint(roles=(ADMIN,))
def elections_list(request):
    return json_response({"elections": [services.election_payload(e) for e in Election.objects.all()]})


@endpoint(roles=(ADMIN,))
def elections_create(request):
    data = get_json(request)
    errors = {}
    name = str(data.get("name") or "").strip()
    slug = str(data.get("slug") or "").strip()
    if not name:
        errors["name"] = "Required."
    if not SLUG.fullmatch(slug):
        errors["slug"] = "Use lowercase letters, digits and hyphens, e.g. kano-2027."
    elif Election.objects.filter(slug=slug).exists():
        errors["slug"] = "Already used."
    date = None
    if data.get("election_date"):
        date = parse_date(str(data["election_date"]))
        if date is None:
            errors["election_date"] = "Use YYYY-MM-DD."
    if errors:
        raise v.ValidationFailed(errors)
    candidates = _clean_candidates(data.get("candidates"))
    with transaction.atomic():
        election = Election.objects.create(name=name, slug=slug, election_date=date,
                                           is_current=bool(data.get("make_current")))
        Candidate.objects.bulk_create([Candidate(election=election, **c) for c in candidates])
    audit(request, "election_create", target=election.pk, current=election.is_current)
    return json_response({"election": services.election_payload(election)}, status=201)


@endpoint(roles=(ADMIN,))
def elections_update(request, pk):
    election = Election.objects.filter(pk=pk).first()
    if election is None:
        raise ApiError(404, "not_found", "No such election.")
    data = get_json(request)
    changed = []
    if "name" in data and str(data["name"]).strip():
        election.name = str(data["name"]).strip(); changed.append("name")
    if "election_date" in data:
        d = parse_date(str(data["election_date"])) if data["election_date"] else None
        if data["election_date"] and d is None:
            raise v.ValidationFailed({"election_date": "Use YYYY-MM-DD."})
        election.election_date = d; changed.append("election_date")
    if "is_current" in data:
        if not isinstance(data["is_current"], bool):
            raise v.ValidationFailed({"is_current": "Must be true or false."})
        election.is_current = data["is_current"]; changed.append("is_current")
    with transaction.atomic():
        if "candidates" in data:
            if ResultSubmission.objects.filter(election=election).exists():
                raise ApiError(409, "has_results",
                               "Candidates cannot change after results have been submitted.")
            candidates = _clean_candidates(data["candidates"])
            election.candidates.all().delete()
            Candidate.objects.bulk_create([Candidate(election=election, **c) for c in candidates])
            changed.append("candidates")
        if changed:
            election.save()
    audit(request, "election_update", target=election.pk, fields=changed)
    election = Election.objects.get(pk=election.pk)
    return json_response({"election": services.election_payload(election)})


# ================================================================= Situation Room switch
def _config_response():
    config = SituationRoomConfig.load()
    return {
        "config": {"mode": config.mode, "publish_unverified": config.publish_unverified,
                   "refresh_seconds": config.refresh_seconds, "updated_at": services.iso(config.updated_at)},
        "election": services.election_payload(Election.current()),
        "warnings": services.security_warnings(),
        "stats": {
            "polling_units": PollingUnit.objects.filter(is_active=True).count(),
            "agents": ResultAgent.objects.filter(role="agent", is_active=True).count(),
            "submissions_current": ResultSubmission.objects.filter(is_current=True).count(),
        },
    }


@endpoint(roles=(ADMIN,))
def situation_get(request):
    return json_response(_config_response())


@endpoint(roles=(ADMIN,))
def situation_update(request):
    """Body: {"mode": "simulation"|"live", "publish_unverified": bool, "refresh_seconds": 5-120}."""
    data = get_json(request)
    config = SituationRoomConfig.load()
    errors = {}
    if "mode" in data:
        if data["mode"] not in ("simulation", "live"):
            errors["mode"] = "Use simulation or live."
        elif data["mode"] == "live":
            if Election.current() is None:
                raise ApiError(409, "not_ready", "Create a current election before going live.")
            if not PollingUnit.objects.filter(is_active=True).exists():
                raise ApiError(409, "not_ready", "Load polling units before going live.")
            config.mode = "live"
        else:
            config.mode = "simulation"
    if "publish_unverified" in data:
        if not isinstance(data["publish_unverified"], bool):
            errors["publish_unverified"] = "Must be true or false."
        else:
            config.publish_unverified = data["publish_unverified"]
    if "refresh_seconds" in data:
        n = v.parse_count(data["refresh_seconds"], "refresh_seconds", errors, maximum=120)
        if n is not None and n < 5:
            errors["refresh_seconds"] = "Must be between 5 and 120."
        elif n is not None:
            config.refresh_seconds = n
    if errors:
        raise v.ValidationFailed(errors)
    config.save()
    audit(request, "situation_update", mode=config.mode, publish_unverified=config.publish_unverified)
    return json_response(_config_response())


# ================================================================= audit log
@endpoint(roles=(ADMIN,))
def audit_list(request):
    qs = AuditLog.objects.select_related("actor")
    action = request.GET.get("action", "").strip()
    if action:
        qs = qs.filter(action=action)
    actor = request.GET.get("actor", "").strip()
    if actor.isdigit():
        qs = qs.filter(actor_id=int(actor))
    items, page = paginate(qs, request, default=100, maximum=500)
    return json_response({**page, "entries": [{
        "id": a.pk, "at": services.iso(a.created_at), "action": a.action, "target": a.target,
        "actor": {"id": a.actor_id, "full_name": a.actor.full_name} if a.actor else None,
        "ip": a.ip_address, "detail": a.detail,
    } for a in items]})
