"""Business logic for the results API (kept out of the views so it is easy to reason about)."""
import os
from collections import defaultdict
from datetime import timedelta, timezone as dt_timezone

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.lga_data import KANO_LGAS, STATE_CODE, STATE_NAME, lga_code, ward_code
from core.models import Election, PollingUnit, ResultAgent, ResultSubmission, SituationRoomConfig

from . import validators as v
from .base import ApiError, audit, issue_token

ROLE_AGENT, ROLE_SUPERVISOR, ROLE_ADMIN = "agent", "supervisor", "admin"
S = ResultSubmission.Status
EDITABLE_STATUSES = (S.SUBMITTED, S.FLAGGED, S.DISPUTED, S.REJECTED)

_DUMMY_HASH = None


def _dummy_hash():
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = make_password("not-a-real-pin")
    return _DUMMY_HASH


def iso(dt):
    return dt.isoformat() if dt else None


def cursor_str(dt):
    """UTC 'Z' timestamp with no '+', so it survives being put in a query string."""
    return dt.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ============================================================ serializers
def election_payload(election):
    if election is None:
        return None
    return {
        "id": election.pk,
        "name": election.name,
        "slug": election.slug,
        "election_date": election.election_date.isoformat() if election.election_date else None,
        "is_current": election.is_current,
        "candidates": [
            {"id": c.pk, "name": c.name, "short_name": c.short_name, "color": c.color, "order": c.order}
            for c in election.candidates.all()
        ],
    }


def agent_payload(agent, with_counts=False):
    data = {
        "id": agent.pk,
        "full_name": agent.full_name,
        "phone": agent.phone,
        "role": agent.role,
        "lga_scope": agent.lga_scope,
        "is_active": agent.is_active,
        "must_change_pin": agent.must_change_pin,
        "is_locked": agent.is_locked,
        "last_login_at": iso(agent.last_login_at),
        "created_at": iso(agent.created_at),
    }
    if with_counts:
        data["assigned_polling_units"] = agent.polling_units.count()
    return data


def pu_payload(pu):
    return {
        "code": pu.code,
        "number": pu.number,
        "name": pu.display_name,
        "lga": pu.lga,
        "lga_name": pu.lga_name,
        "ward_index": pu.ward_index,
        "ward_name": pu.ward_name,
        "registered_voters": pu.registered_voters,
        "latitude": pu.latitude,
        "longitude": pu.longitude,
        "is_active": pu.is_active,
    }


def submission_payload(sub, include_agent=True):
    pu = sub.polling_unit
    data = {
        "id": sub.pk,
        "submission_id": str(sub.submission_id),
        "election_id": sub.election_id,
        "polling_unit": {
            "code": pu.code, "name": pu.display_name, "lga": pu.lga,
            "ward_index": pu.ward_index, "ward_name": pu.ward_name,
        },
        "registered_voters": sub.registered_voters,
        "accredited_voters": sub.accredited_voters,
        "rejected_votes": sub.rejected_votes,
        "valid_votes": sub.valid_votes,
        "votes": sub.votes,
        "status": sub.status,
        "is_current": sub.is_current,
        "flags": sub.flags,
        "review_note": sub.review_note,
        "has_sheet": bool(sub.sheet_name),
        "created_at": iso(sub.created_at),
        "updated_at": iso(sub.updated_at),
        "reviewed_at": iso(sub.reviewed_at),
    }
    if include_agent:
        data["agent"] = {"id": sub.agent_id, "full_name": sub.agent.full_name}
    return data


# ============================================================ authentication
def login(request, phone, pin, device_name=""):
    phone = v.normalise_phone(phone)
    invalid = ApiError(401, "invalid_credentials", "Phone number or PIN is incorrect.")
    if not v.phone_is_valid(phone) or not isinstance(pin, str) or not pin:
        check_password("x", _dummy_hash())
        raise invalid
    agent = ResultAgent.objects.filter(phone=phone).first()
    if agent is None:
        check_password(pin, _dummy_hash())          # same timing as a real check
        audit(request, "login_failed", target=phone, reason="unknown_phone")
        raise invalid
    if agent.is_locked:
        wait = max(1, int((agent.locked_until - timezone.now()).total_seconds()))
        audit(request, "login_blocked", actor=agent, target=phone)
        raise ApiError(429, "account_locked",
                       "Too many wrong PINs. Try again later or ask your administrator to reset your PIN.",
                       headers={"Retry-After": str(wait)}, extra={"retry_after_seconds": wait})
    if not agent.is_active or not agent.check_pin(pin):
        if agent.is_active:
            agent.failed_logins += 1
            update = ["failed_logins"]
            if agent.failed_logins >= settings.API_LOGIN_MAX_FAILS:
                agent.locked_until = timezone.now() + timedelta(minutes=settings.API_LOGIN_LOCK_MINUTES)
                agent.failed_logins = 0
                update += ["locked_until"]
            agent.save(update_fields=update)
        audit(request, "login_failed", actor=agent, target=phone, reason="bad_pin_or_inactive")
        raise invalid
    agent.failed_logins, agent.locked_until, agent.last_login_at = 0, None, timezone.now()
    agent.save(update_fields=["failed_logins", "locked_until", "last_login_at"])
    raw, token = issue_token(agent, device_name)
    audit(request, "login", actor=agent, target=phone, device=device_name[:100])
    return {
        "token": raw,
        "token_type": "Bearer",
        "expires_at": iso(token.expires_at),
        "agent": agent_payload(agent, with_counts=True),
    }


def change_pin(request, agent, current_pin, new_pin):
    if not agent.check_pin(current_pin or ""):
        audit(request, "change_pin_failed", actor=agent)
        raise ApiError(403, "invalid_credentials", "The current PIN is incorrect.")
    problem = v.pin_problem(new_pin)
    if problem:
        raise v.ValidationFailed({"new_pin": problem})
    if new_pin == current_pin:
        raise v.ValidationFailed({"new_pin": "Choose a different PIN."})
    agent.set_pin(new_pin)
    agent.must_change_pin = False
    agent.save(update_fields=["pin_hash", "must_change_pin", "updated_at"])
    # sign out every other device
    agent.tokens.filter(revoked_at__isnull=True).exclude(pk=request.api_token.pk).update(revoked_at=timezone.now())
    audit(request, "change_pin", actor=agent)


# ============================================================ authorisation helpers
def can_access_pu(agent, pu):
    if agent.role == ROLE_ADMIN:
        return True
    if agent.role == ROLE_SUPERVISOR:
        return not agent.lga_scope or agent.lga_scope == pu.lga
    return agent.polling_units.filter(pk=pu.pk).exists()


def scoped_submissions(agent):
    qs = ResultSubmission.objects.select_related("polling_unit", "agent")
    if agent.role == ROLE_SUPERVISOR and agent.lga_scope:
        qs = qs.filter(polling_unit__lga=agent.lga_scope)
    elif agent.role == ROLE_AGENT:
        qs = qs.filter(agent=agent)
    return qs


# ============================================================ submissions
def submit_result(request, agent, payload):
    """Validate and store one result sheet. Returns (submission, created)."""
    election = Election.current()
    if election is None:
        raise ApiError(409, "no_active_election", "No election is open for results right now.")
    candidate_ids = list(election.candidates.values_list("id", flat=True))

    code = payload.get("polling_unit_code") if isinstance(payload, dict) else None
    pu = None
    if isinstance(code, str) and v.PU_CODE_RE.fullmatch(code.strip()):
        pu = PollingUnit.objects.filter(code=code.strip().replace("-", "/"), is_active=True).first()
        if pu is None:
            raise ApiError(404, "polling_unit_not_found", "No active polling unit has that code.")
        if not can_access_pu(agent, pu):
            audit(request, "submit_denied", target=pu.code)
            raise ApiError(403, "not_assigned", "You are not assigned to this polling unit.")

    clean = v.validate_result_payload(
        payload, candidate_ids,
        pu_registered=pu.registered_voters if pu else 0,
        pu_lat=pu.latitude if pu else None, pu_lng=pu.longitude if pu else None,
    )
    digest = v.payload_hash(clean)

    # Idempotent replay (the app retried after a dropped connection)?
    existing = (ResultSubmission.objects.select_related("polling_unit", "agent")
                .filter(submission_id=clean["submission_id"]).first())
    if existing is not None:
        if existing.agent_id != agent.pk or existing.payload_hash != digest:
            raise ApiError(409, "submission_id_reused", "This submission_id was already used for different figures.")
        return existing, False

    if clean["anomalies"] and not clean["acknowledge_anomalies"]:
        raise ApiError(
            422, "anomalies_detected",
            "These figures look unusual. Re-check the result sheet; if they are correct, "
            "send again with acknowledge_anomalies=true.",
            extra={"anomalies": [{"code": a, "message": v.ANOMALY_TEXT[a]} for a in clean["anomalies"]]},
        )

    try:
        with transaction.atomic():
            PollingUnit.objects.select_for_update().get(pk=pu.pk)   # one writer per polling unit
            current = (ResultSubmission.objects.select_for_update()
                       .filter(election=election, polling_unit=pu, is_current=True).first())
            if current is not None:
                if current.status == S.VERIFIED:
                    raise ApiError(409, "already_verified",
                                   "This polling unit's result is already verified. Ask your supervisor to reject it first.")
                if current.payload_hash == digest and current.status != S.REJECTED:
                    current = ResultSubmission.objects.select_related("polling_unit", "agent").get(pk=current.pk)
                    return current, False
                current.is_current = False
                current.status = S.SUPERSEDED
                current.save(update_fields=["is_current", "status", "updated_at"])
            sub = ResultSubmission.objects.create(
                submission_id=clean["submission_id"], election=election, polling_unit=pu, agent=agent,
                registered_voters=clean["registered_voters"], accredited_voters=clean["accredited_voters"],
                rejected_votes=clean["rejected_votes"], valid_votes=clean["valid_votes"],
                votes=clean["votes"], status=S.FLAGGED if clean["anomalies"] else S.SUBMITTED,
                flags=clean["anomalies"], latitude=clean["latitude"], longitude=clean["longitude"],
                client_time=clean["client_time"], payload_hash=digest,
            )
    except IntegrityError:
        raise ApiError(409, "conflict", "Another submission for this polling unit arrived at the same time. Retry.")
    audit(request, "submit_result", actor=agent, target=pu.code, submission=sub.pk, status=sub.status,
          superseded=bool(current))
    sub = ResultSubmission.objects.select_related("polling_unit", "agent").get(pk=sub.pk)
    return sub, True


def review_submission(request, reviewer, sub, action, note):
    if not can_access_pu(reviewer, sub.polling_unit):
        raise ApiError(403, "forbidden", "This polling unit is outside your area.")
    if not sub.is_current:
        raise ApiError(409, "not_current", "Only the current submission of a polling unit can be reviewed.")
    note = (note or "").strip()
    if action in ("dispute", "reject") and len(note) < 5:
        raise v.ValidationFailed({"note": "Explain the reason (at least 5 characters)."})
    if action == "verify":
        if sub.status not in (S.SUBMITTED, S.FLAGGED, S.DISPUTED):
            raise ApiError(409, "invalid_state", f"A {sub.status} result cannot be verified.")
        sub.status = S.VERIFIED
    elif action == "dispute":
        if sub.status not in (S.SUBMITTED, S.FLAGGED, S.VERIFIED):
            raise ApiError(409, "invalid_state", f"A {sub.status} result cannot be disputed.")
        sub.status = S.DISPUTED
    elif action == "reject":
        sub.status = S.REJECTED
    else:
        raise v.ValidationFailed({"action": "Use verify, dispute or reject."})
    sub.review_note = note[:1000]
    sub.reviewed_by, sub.reviewed_at = reviewer, timezone.now()
    sub.save(update_fields=["status", "review_note", "reviewed_by", "reviewed_at", "updated_at"])
    audit(request, f"review_{action}", actor=reviewer, target=sub.polling_unit.code, submission=sub.pk)
    return sub


# ============================================================ public data
def public_statuses(config=None):
    config = config or SituationRoomConfig.load()
    return (S.VERIFIED, S.SUBMITTED) if config.publish_unverified else (S.VERIFIED,)


def structure_payload():
    by_ward = defaultdict(list)
    total = 0
    rows = (PollingUnit.objects.filter(is_active=True).order_by("lga", "ward_index", "number")
            .values_list("lga", "ward_index", "number", "code", "name", "registered_voters"))
    for lga, ward_index, number, code, name, registered in rows:
        by_ward[(lga, ward_index)].append([number, code, name or f"Polling Unit {number:03d}", registered])
        total += 1
    lgas = []
    for key, name, wards in KANO_LGAS:
        lgas.append({
            "key": key, "code": lga_code(key), "name": name,
            "wards": [
                {"index": wi, "code": ward_code(key, wi), "name": wn, "pus": by_ward.get((key, wi), [])}
                for wi, wn in enumerate(wards)
            ],
        })
    return {
        "state": {"name": STATE_NAME, "code": STATE_CODE},
        "pu_fields": ["number", "code", "name", "registered_voters"],
        "total_polling_units": total,
        "lgas": lgas,
    }


def config_payload():
    config = SituationRoomConfig.load()
    election = Election.current()
    return {
        "mode": config.mode,
        "refresh_seconds": config.refresh_seconds,
        "publish_unverified": config.publish_unverified,
        "state": {"name": STATE_NAME, "code": STATE_CODE},
        "election": election_payload(election),
        "server_time": iso(timezone.now()),
    }


def public_results_payload(since=None):
    """Public results. With ``since`` only polling units changed after it are returned."""
    config = SituationRoomConfig.load()
    election = Election.current()
    now = timezone.now()
    cursor = cursor_str(now - timedelta(seconds=5))     # small overlap so nothing is missed
    if election is None:
        return {"mode": config.mode, "election_id": None, "cursor": cursor, "full": since is None,
                "public_count": 0, "results": [], "withdrawn": []}
    order = list(election.candidates.values_list("id", flat=True))
    allowed = public_statuses(config)
    current = (ResultSubmission.objects.filter(election=election, is_current=True)
               .select_related("polling_unit", "agent"))
    public_count = current.filter(status__in=allowed).count()
    if since is not None:
        changed = (ResultSubmission.objects.filter(election=election, updated_at__gt=since)
                   .values_list("polling_unit_id", flat=True))
        current = current.filter(polling_unit_id__in=changed)
    results, withdrawn = [], []
    for sub in current:
        if sub.status in allowed:
            results.append({
                "pu": sub.polling_unit.code,
                "registered": sub.registered_voters,
                "accredited": sub.accredited_voters,
                "rejected": sub.rejected_votes,
                "valid": sub.valid_votes,
                "votes": [sub.votes.get(str(cid), 0) for cid in order],
                "by": sub.agent.public_name,
                "at": iso(sub.created_at),
                "status": sub.status,
            })
        else:
            withdrawn.append(sub.polling_unit.code)
    return {
        "mode": config.mode, "election_id": election.pk, "cursor": cursor, "full": since is None,
        "public_count": public_count, "results": results,
        "withdrawn": withdrawn if since is not None else [],
    }


def summary_payload(lga=None, ward_index=None, allowed_statuses=None, lga_scope=None):
    """Totals for the whole state, an LGA or a ward."""
    election = Election.current()
    if election is None:
        return {"election": None}
    allowed = allowed_statuses or public_statuses()
    candidates = list(election.candidates.all())
    pu_qs = PollingUnit.objects.filter(is_active=True)
    sub_qs = ResultSubmission.objects.filter(election=election, is_current=True, status__in=allowed)
    if lga_scope:
        lga = lga_scope
    if lga:
        pu_qs, sub_qs = pu_qs.filter(lga=lga), sub_qs.filter(polling_unit__lga=lga)
    if ward_index is not None:
        pu_qs, sub_qs = pu_qs.filter(ward_index=ward_index), sub_qs.filter(polling_unit__ward_index=ward_index)
    totals = {c.pk: 0 for c in candidates}
    registered = accredited = rejected = valid = reported = 0
    for sub in sub_qs.only("registered_voters", "accredited_voters", "rejected_votes", "valid_votes", "votes"):
        reported += 1
        registered += sub.registered_voters
        accredited += sub.accredited_voters
        rejected += sub.rejected_votes
        valid += sub.valid_votes
        for c in candidates:
            totals[c.pk] += int(sub.votes.get(str(c.pk), 0))
    total_pus = pu_qs.count()
    return {
        "election": {"id": election.pk, "name": election.name},
        "scope": {"lga": lga or None, "ward_index": ward_index},
        "polling_units_total": total_pus,
        "polling_units_reported": reported,
        "percent_reported": round(reported / total_pus * 100, 1) if total_pus else 0.0,
        "registered_voters": registered,
        "accredited_voters": accredited,
        "rejected_votes": rejected,
        "valid_votes": valid,
        "turnout_percent": round(accredited / registered * 100, 1) if registered else 0.0,
        "candidates": [
            {"id": c.pk, "name": c.name, "short_name": c.short_name, "color": c.color, "votes": totals[c.pk],
             "percent": round(totals[c.pk] / valid * 100, 1) if valid else 0.0}
            for c in candidates
        ],
    }


# ============================================================ go-live readiness
def security_warnings():
    """Things to fix before real election data is collected. Non-blocking."""
    from django.contrib.auth import get_user_model
    from core.accounts import DEFAULT_USERNAME

    out = []

    def add(level, text):
        out.append({"level": level, "message": text})

    if settings.DEBUG:
        add("critical", "DJANGO_DEBUG is on. Set DJANGO_DEBUG=0 in production.")
    if getattr(settings, "SECRET_KEY_IS_FALLBACK", False):
        add("critical", "DJANGO_SECRET_KEY is not set (a predictable fallback key is in use). Set a long random value.")
    user = get_user_model().objects.filter(
        username=os.environ.get("DJANGO_SUPERUSER_USERNAME", DEFAULT_USERNAME), is_superuser=True).first()
    password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
    if user is not None and password and user.check_password(password):
        add("critical", "The configured super-user password is still active. Change it after initial setup.")
    if settings.ON_VERCEL and settings.USING_SQLITE:
        add("critical", "No DATABASE_URL: results would be stored in temporary storage and lost. Use Postgres.")
    if "*" in settings.API_CORS_ORIGINS:
        add("warning", "API_CORS_ORIGINS contains '*'. List only the origins you trust.")
    if Election.current() is None:
        add("critical", "There is no current election. Create one (Admin > Elections) so agents can report.")
    total = PollingUnit.objects.filter(is_active=True).count()
    if total == 0:
        add("critical", "No polling units are loaded. Run seed_polling_units or import the official INEC list.")
    else:
        unnamed = PollingUnit.objects.filter(is_active=True, name="").count()
        zero = PollingUnit.objects.filter(is_active=True, registered_voters=0).count()
        if unnamed:
            add("warning", f"{unnamed} of {total} polling units still have placeholder names "
                           "(import the official list with import_polling_units).")
        if zero:
            add("warning", f"{zero} of {total} polling units have no registered-voter count.")
    if not ResultAgent.objects.filter(role=ROLE_ADMIN, is_active=True).exists():
        add("warning", "No results administrator exists yet (python manage.py create_agent --role admin).")
    return out
