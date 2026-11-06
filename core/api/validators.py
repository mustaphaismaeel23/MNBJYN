"""Pure-Python validation for the results API (no Django imports, easy to test).

Hard errors  -> ValidationFailed (HTTP 422). The figures cannot be stored as sent.
Anomalies    -> returned in ``result["anomalies"]``. The figures are possible but odd
                (e.g. more accredited voters than registered). The agent must confirm
                them (``acknowledge_anomalies: true``); such a result is stored as FLAGGED.
"""
import hashlib
import json
import math
import re
import secrets
import uuid
from datetime import datetime, timezone

MAX_COUNT = 20000          # no polling unit has more voters than this
MAX_DISTANCE_KM = 1.5      # submit-from-far-away check, only if the PU has coordinates
PIN_RE = re.compile(r"^[0-9]{6}$")
PU_CODE_RE = re.compile(r"^[0-9]{2}[/-][0-9]{2}[/-][0-9]{2}[/-][0-9]{3,4}$")


class ValidationFailed(Exception):
    """Carries ``{field: message}`` for the API's 422 response."""

    def __init__(self, fields, message="Some fields are invalid."):
        super().__init__(message)
        self.fields = fields
        self.message = message


# ---------------------------------------------------------------- basic parsers
def parse_count(value, field, errors, required=True, maximum=MAX_COUNT):
    """A whole number >= 0. Booleans, floats, and numeric strings with junk are refused."""
    if value is None or value == "":
        if required:
            errors[field] = "This field is required."
        return None
    if isinstance(value, bool):
        errors[field] = "Must be a whole number."
        return None
    if isinstance(value, float):
        if not value.is_integer():
            errors[field] = "Must be a whole number."
            return None
        value = int(value)
    if isinstance(value, str):
        if not re.fullmatch(r"[0-9]{1,6}", value.strip()):
            errors[field] = "Must be a whole number."
            return None
        value = int(value.strip())
    if not isinstance(value, int):
        errors[field] = "Must be a whole number."
        return None
    if value < 0:
        errors[field] = "Cannot be negative."
        return None
    if value > maximum:
        errors[field] = f"Cannot be more than {maximum}."
        return None
    return value


def parse_uuid(value, field, errors):
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        errors[field] = "Must be a valid UUID."
        return None


def parse_iso_datetime(value, field, errors):
    """ISO-8601 -> aware datetime (naive input is treated as UTC). None when absent."""
    if value in (None, ""):
        return None
    try:
        text = str(value).strip()
        text = re.sub(r" ([0-9]{2}:[0-9]{2})$", r"+\1", text)   # '+' turned into ' ' by a query string
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        errors[field] = "Must be an ISO-8601 date-time, e.g. 2027-02-25T10:30:00+01:00."
        return None


def parse_coordinate(value, field, errors, low, high):
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        errors[field] = "Must be a number."
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors[field] = "Must be a number."
        return None
    if not (low <= number <= high) or math.isnan(number):
        errors[field] = f"Must be between {low} and {high}."
        return None
    return number


def haversine_km(lat1, lng1, lat2, lng2):
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------- phone / PIN
def normalise_phone(raw):
    """'+234 801 234 5678' -> '08012345678'. Other numbers keep digits (and a leading +)."""
    text = re.sub(r"[\s\-().]", "", str(raw or ""))
    if text.startswith("+234") and len(text) == 14:
        return "0" + text[4:]
    if text.startswith("234") and len(text) == 13:
        return "0" + text[3:]
    return text


def phone_is_valid(phone):
    return bool(re.fullmatch(r"\+?[0-9]{10,15}", phone or ""))


def pin_problem(pin):
    """Return a message when the PIN is not acceptable, else None."""
    if not isinstance(pin, str) or not PIN_RE.fullmatch(pin):
        return "PIN must be exactly 6 digits."
    if len(set(pin)) == 1:
        return "PIN cannot be the same digit repeated."
    if pin in ("012345", "123456", "234567", "345678", "456789", "987654", "876543", "765432", "654321", "543210"):
        return "PIN cannot be a simple sequence."
    return None


def generate_pin():
    """Random 6-digit PIN that passes ``pin_problem``."""
    while True:
        pin = "".join(secrets.choice("0123456789") for _ in range(6))
        if pin_problem(pin) is None:
            return pin


# ---------------------------------------------------------------- result sheet
def validate_result_payload(payload, candidate_ids, pu_registered=0, pu_lat=None, pu_lng=None):
    """Validate one submission.

    ``candidate_ids``: iterable of the election's candidate ids.
    Returns a dict with cleaned figures + ``anomalies`` (list of codes).
    Raises ValidationFailed for hard errors.
    """
    if not isinstance(payload, dict):
        raise ValidationFailed({"_": "Body must be a JSON object."})
    errors = {}
    ids = [str(c) for c in candidate_ids]

    submission_id = parse_uuid(payload.get("submission_id"), "submission_id", errors)

    code = payload.get("polling_unit_code")
    if not isinstance(code, str) or not PU_CODE_RE.fullmatch(code.strip()):
        errors["polling_unit_code"] = "Use the polling unit code, e.g. 20/21/03/007."
        code = None
    else:
        code = code.strip().replace("-", "/")

    registered = parse_count(payload.get("registered_voters"), "registered_voters", errors,
                             required=not pu_registered)
    if registered is None and "registered_voters" not in errors:
        registered = pu_registered
    accredited = parse_count(payload.get("accredited_voters"), "accredited_voters", errors)
    rejected = parse_count(payload.get("rejected_votes"), "rejected_votes", errors)
    claimed_valid = parse_count(payload.get("valid_votes"), "valid_votes", errors, required=False)

    # votes: {"<candidate id>": n}
    votes_in = payload.get("votes")
    votes = {}
    if not isinstance(votes_in, dict):
        errors["votes"] = 'Send an object like {"<candidate id>": 120, ...} with every candidate.'
    else:
        keys = {str(k) for k in votes_in}
        missing = [i for i in ids if i not in keys]
        unknown = sorted(keys - set(ids))
        if unknown:
            errors["votes"] = f"Unknown candidate id(s): {', '.join(unknown)}."
        elif missing:
            errors["votes"] = f"Missing candidate id(s): {', '.join(missing)}. Send 0 for no votes."
        else:
            for k, v in votes_in.items():
                n = parse_count(v, f"votes.{k}", errors)
                if n is not None:
                    votes[str(k)] = n

    lat = parse_coordinate(payload.get("latitude"), "latitude", errors, -90, 90)
    lng = parse_coordinate(payload.get("longitude"), "longitude", errors, -180, 180)
    if (lat is None) != (lng is None) and "latitude" not in errors and "longitude" not in errors:
        errors["latitude"] = "Send latitude and longitude together."
    client_time = parse_iso_datetime(payload.get("client_time"), "client_time", errors)
    acknowledged = payload.get("acknowledge_anomalies", False)
    if not isinstance(acknowledged, bool):
        errors["acknowledge_anomalies"] = "Must be true or false."
        acknowledged = False

    valid = sum(votes.values()) if len(votes) == len(ids) and "votes" not in errors else None
    if valid is not None and claimed_valid is not None and claimed_valid != valid:
        errors["valid_votes"] = f"Does not match the sum of the candidate votes ({valid})."

    if errors:
        raise ValidationFailed(errors)

    anomalies = []
    if accredited > registered:
        anomalies.append("accredited_exceeds_registered")
    if valid + rejected > accredited:
        anomalies.append("votes_exceed_accredited")
    if pu_registered and registered != pu_registered:
        anomalies.append("registered_differs_from_register")
    if valid + rejected >= 50 and rejected > 0.10 * (valid + rejected):
        anomalies.append("high_rejected_votes")
    if (lat is not None and pu_lat is not None and pu_lng is not None
            and haversine_km(lat, lng, pu_lat, pu_lng) > MAX_DISTANCE_KM):
        anomalies.append("location_far_from_polling_unit")

    return {
        "submission_id": submission_id,
        "polling_unit_code": code,
        "registered_voters": registered,
        "accredited_voters": accredited,
        "rejected_votes": rejected,
        "valid_votes": valid,
        "votes": votes,
        "latitude": lat,
        "longitude": lng,
        "client_time": client_time,
        "acknowledge_anomalies": acknowledged,
        "anomalies": anomalies,
    }


def payload_hash(clean):
    """Stable fingerprint of the figures (not of ids/times) for duplicate detection."""
    body = {
        "pu": clean["polling_unit_code"],
        "registered": clean["registered_voters"],
        "accredited": clean["accredited_voters"],
        "rejected": clean["rejected_votes"],
        "votes": {k: clean["votes"][k] for k in sorted(clean["votes"], key=lambda s: int(s) if s.isdigit() else 0)},
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


ANOMALY_TEXT = {
    "accredited_exceeds_registered": "More voters were accredited than are registered at this polling unit.",
    "votes_exceed_accredited": "Valid + rejected votes are more than the number of accredited voters.",
    "registered_differs_from_register": "Registered voters differ from INEC's register for this polling unit.",
    "high_rejected_votes": "More than 10% of the votes cast were rejected.",
    "location_far_from_polling_unit": "The phone is more than 1.5 km from this polling unit.",
}
