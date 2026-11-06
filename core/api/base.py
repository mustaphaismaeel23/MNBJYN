"""Shared plumbing for the results API: errors, JSON helpers, throttling, token auth."""
import functools
import hashlib
import json
import logging
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from core.models import ApiToken

from .validators import ValidationFailed

log = logging.getLogger("ssbyn.api")


class ApiError(Exception):
    def __init__(self, status, code, message, fields=None, headers=None, extra=None):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.fields, self.headers, self.extra = fields, headers or {}, extra or {}


# ------------------------------------------------------------------ responses
def json_response(data, status=200, cache_seconds=0):
    """JSON response. Private (never cached) unless ``cache_seconds`` > 0 (public data only)."""
    response = JsonResponse(data, status=status, json_dumps_params={"separators": (",", ":")})
    if cache_seconds:
        response["Cache-Control"] = (
            f"public, max-age={cache_seconds}, s-maxage={cache_seconds}, stale-while-revalidate={cache_seconds * 3}"
        )
    else:
        response["Cache-Control"] = "no-store"
    return response


def error_response(err):
    body = {"error": {"code": err.code, "message": err.message}}
    if err.fields:
        body["error"]["fields"] = err.fields
    body["error"].update(err.extra)
    response = json_response(body, status=err.status)
    for key, value in err.headers.items():
        response[key] = value
    return response


def get_json(request):
    """Parse the JSON body (size-limited). Returns a dict."""
    ctype = (request.META.get("CONTENT_TYPE") or "").split(";")[0].strip().lower()
    if ctype != "application/json":
        raise ApiError(415, "unsupported_media_type", "Send the body as application/json.")
    try:
        length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        length = 0
    if length > settings.API_MAX_JSON_BYTES:
        raise ApiError(413, "payload_too_large", "Request body is too large.")
    try:
        body = request.body
    except Exception:
        raise ApiError(413, "payload_too_large", "Request body is too large.")
    if len(body) > settings.API_MAX_JSON_BYTES:
        raise ApiError(413, "payload_too_large", "Request body is too large.")
    try:
        data = json.loads(body.decode("utf-8") or "null")
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "invalid_json", "The body is not valid JSON.")
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_json", "The JSON body must be an object.")
    return data


def client_ip(request):
    if settings.API_TRUST_PROXY:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:45]
    return (request.META.get("REMOTE_ADDR") or "")[:45]


def positive_int(value, default, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < 1:
        return default
    return min(number, maximum) if maximum else number


# ------------------------------------------------------------------ throttling
def throttle(scope, ident, limit, window):
    """Fixed-window counter. Uses Django's cache (per server instance with the default
    cache; configure a shared cache such as Redis for exact limits across servers)."""
    bucket = int(time.time() // window)
    digest = hashlib.sha1(str(ident).encode()).hexdigest()[:20]
    key = f"rl:{scope}:{digest}:{bucket}"
    if cache.add(key, 1, timeout=window + 5):
        count = 1
    else:
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window + 5)
            count = 1
    if count > limit:
        retry = max(1, window - int(time.time()) % window)
        raise ApiError(429, "rate_limited", "Too many requests. Slow down and retry shortly.",
                       headers={"Retry-After": str(retry)}, extra={"retry_after_seconds": retry})


# ------------------------------------------------------------------ audit
def audit(request, action, actor=None, target="", **detail):
    from core.models import AuditLog

    try:
        AuditLog.objects.create(
            actor=actor if actor is not None else getattr(request, "agent", None),
            action=action,
            target=str(target)[:120],
            ip_address=client_ip(request) or None,
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
            detail=detail,
        )
    except Exception:  # an audit failure must never break the request
        log.exception("audit log write failed")


# ------------------------------------------------------------------ tokens
def issue_token(agent, device_name=""):
    """Create a token. Returns (raw_token, ApiToken). The raw value is never stored."""
    raw = "mnbjyn_" + secrets.token_urlsafe(32)
    expires = timezone.now() + timedelta(hours=settings.API_TOKEN_TTL_HOURS)
    token = ApiToken.objects.create(
        agent=agent, key_hash=ApiToken.hash_key(raw), prefix=raw[:8],
        device_name=(device_name or "")[:100], expires_at=expires,
    )
    # keep at most 5 live sessions per agent: revoke the oldest extras
    live = list(agent.tokens.filter(revoked_at__isnull=True, expires_at__gt=timezone.now())
                .order_by("-created_at").values_list("id", flat=True))
    if len(live) > 5:
        agent.tokens.filter(id__in=live[5:]).update(revoked_at=timezone.now())
    return raw, token


def authenticate(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    scheme, _, raw = header.partition(" ")
    raw = raw.strip()
    unauthorized = {"WWW-Authenticate": 'Bearer realm="ssbyn-results"'}
    if scheme.lower() != "bearer" or not raw:
        raise ApiError(401, "not_authenticated", "Send the header 'Authorization: Bearer <token>'.",
                       headers=unauthorized)
    if len(raw) > 200:
        raise ApiError(401, "invalid_token", "The token is not valid.", headers=unauthorized)
    token = ApiToken.objects.select_related("agent").filter(key_hash=ApiToken.hash_key(raw)).first()
    if token is None or not token.is_valid or not token.agent.is_active:
        raise ApiError(401, "invalid_token", "The token is invalid, expired or revoked. Log in again.",
                       headers=unauthorized)
    now = timezone.now()
    if token.last_used_at is None or (now - token.last_used_at).total_seconds() > 60:
        ApiToken.objects.filter(pk=token.pk).update(last_used_at=now)
    request.agent = token.agent
    request.api_token = token
    return token.agent


# ------------------------------------------------------------------ decorators
def endpoint(roles=None, public=False, rate=None, allow_pin_pending=False, cache_seconds=0):
    """Wrap one handler.

    public=True      no token needed (read-only public data)
    roles=(...)      token required and the agent's role must be in this tuple
    rate=(n, secs)   per-IP limit; token endpoints also get a per-agent limit
    """
    ip_limit = rate or ((300, 60) if public else (120, 60))

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(request, *args, **kwargs):
            try:
                throttle("ip", client_ip(request), *ip_limit)
                if not public:
                    agent = authenticate(request)
                    throttle("agent", agent.pk, 240, 60)
                    if agent.must_change_pin and not allow_pin_pending:
                        raise ApiError(403, "pin_change_required",
                                       "You must change your temporary PIN first (POST /api/v1/auth/change-pin).")
                    if roles and agent.role not in roles:
                        raise ApiError(403, "forbidden", "Your role is not allowed to do this.")
                response = fn(request, *args, **kwargs)
                if public and cache_seconds and response.status_code == 200:
                    response["Cache-Control"] = (
                        f"public, max-age={cache_seconds}, s-maxage={cache_seconds}, "
                        f"stale-while-revalidate={cache_seconds * 3}"
                    )
                return response
            except ApiError as err:
                return error_response(err)
            except ValidationFailed as err:
                return error_response(ApiError(422, "validation_failed", err.message, fields=err.fields))
            except Exception:
                log.exception("unhandled error in %s", fn.__name__)
                return error_response(ApiError(500, "server_error", "Something went wrong on the server."))
        return wrapper
    return decorator


def route(**handlers):
    """Dispatch by HTTP method: ``route(GET=list_view, POST=create_view)``."""
    table = {k.upper(): v for k, v in handlers.items()}

    @csrf_exempt
    def view(request, *args, **kwargs):
        method = "GET" if request.method == "HEAD" else request.method
        handler = table.get(method)
        if handler is None:
            return error_response(ApiError(
                405, "method_not_allowed", f"Use one of: {', '.join(sorted(table))}.",
                headers={"Allow": ", ".join(sorted(table))}))
        return handler(request, *args, **kwargs)

    return view
