"""Load polling units: parse the official INEC list (CSV) or generate placeholders.

Parsing is pure Python. Database writes happen in ``apply_rows`` (lazy model import).

CSV columns (header names are case-insensitive; order does not matter):

  lga                 LGA name or key, e.g. "Kano Municipal" or "kano_municipal"
  ward                ward name in the admin-managed catalog (quotes/spaces ignored)
  pu_number           polling unit number inside the ward (1, 2, 3 ...)      [or: number]
  name                polling unit name, e.g. "Primary School, Majidadi"       (optional)
  registered_voters   registered voters on the INEC register                   (optional)
  latitude, longitude GPS of the polling unit                                  (optional)
  code                official code such as 20/21/03/007; derived if omitted   (optional)
"""
import csv
import hashlib
import io
import re

from core.lga_data import find_lga_key, normalise_name, pu_code

ALIASES = {
    "lga": ("lga", "lga_name", "local_government", "localgovernment"),
    "ward": ("ward", "ward_name", "registration_area", "ra"),
    "number": ("pu_number", "number", "pu_no", "pu", "polling_unit_number"),
    "name": ("name", "pu_name", "polling_unit", "polling_unit_name", "location"),
    "registered": ("registered_voters", "registered", "voters", "reg_voters", "rv"),
    "latitude": ("latitude", "lat"),
    "longitude": ("longitude", "lng", "lon", "long"),
    "code": ("code", "pu_code", "polling_unit_code"),
}
MAX_ERRORS = 50
CODE_RE = re.compile(r"^[0-9]{2}/[0-9]{2}/[0-9]{2}/[0-9]{3,4}$")


def _header_map(fieldnames):
    norm = {re.sub(r"[^a-z0-9]+", "_", (f or "").strip().lower()).strip("_"): f for f in fieldnames or []}
    mapping = {}
    for key, names in ALIASES.items():
        for n in names:
            if n in norm:
                mapping[key] = norm[n]
                break
    return mapping


def _to_int(text, lo, hi):
    text = str(text).strip().replace(",", "")
    if not re.fullmatch(r"[0-9]{1,7}", text):
        return None
    n = int(text)
    return n if lo <= n <= hi else None


def _to_float(text, lo, hi):
    try:
        n = float(str(text).strip())
    except ValueError:
        return None
    return n if lo <= n <= hi else None


def decode_bytes(raw):
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def parse_csv(text):
    """Return (rows, errors). A row: dict(lga, ward_index, ward_name, number, name,
    registered_voters, latitude, longitude, code)."""
    reader = csv.DictReader(io.StringIO(text))
    cols = _header_map(reader.fieldnames)
    errors = []
    missing = [k for k in ("lga", "ward", "number") if k not in cols]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}. Required: lga, ward, pu_number."]
    from core.models import Ward

    ward_lookup = {
        (lga, normalise_name(name)): (index, name)
        for lga, index, name in Ward.objects.values_list("lga", "ward_index", "name")
    }
    rows, seen = [], set()
    for line_no, rec in enumerate(reader, start=2):
        def err(msg):
            if len(errors) < MAX_ERRORS:
                errors.append(f"Line {line_no}: {msg}")

        if not any((v or "").strip() for v in rec.values() if isinstance(v, str)):
            continue
        lga = find_lga_key(rec.get(cols["lga"], ""))
        if lga is None:
            err(f"unknown LGA '{rec.get(cols['lga'], '')}'")
            continue
        ward = ward_lookup.get((lga, normalise_name(rec.get(cols["ward"], ""))))
        if ward is None:
            err(f"unknown ward '{rec.get(cols['ward'], '')}' in {lga}")
            continue
        ward_index, ward_name = ward
        number = _to_int(rec.get(cols["number"], ""), 1, 9999)
        if number is None:
            err("pu_number must be a whole number from 1 to 9999")
            continue
        key = (lga, ward_index, number)
        if key in seen:
            err(f"duplicate polling unit {lga} / ward {ward_index + 1} / {number}")
            continue
        seen.add(key)
        registered = 0
        if "registered" in cols and (rec.get(cols["registered"]) or "").strip():
            registered = _to_int(rec[cols["registered"]], 0, 20000)
            if registered is None:
                err("registered_voters must be a whole number up to 20000")
                continue
        lat = lng = None
        if "latitude" in cols and "longitude" in cols and (rec.get(cols["latitude"]) or "").strip():
            lat = _to_float(rec[cols["latitude"]], -90, 90)
            lng = _to_float(rec.get(cols["longitude"], ""), -180, 180)
            if lat is None or lng is None:
                err("latitude/longitude are not valid numbers")
                continue
        code = ""
        if "code" in cols and (rec.get(cols["code"]) or "").strip():
            code = rec[cols["code"]].strip().replace("-", "/")
            if not CODE_RE.fullmatch(code):
                err(f"code '{code}' must look like 20/21/03/007")
                continue
        rows.append({
            "lga": lga, "ward_index": ward_index, "ward_name": ward_name,
            "number": number,
            "name": (rec.get(cols["name"], "") if "name" in cols else "").strip()[:200],
            "registered_voters": registered, "latitude": lat, "longitude": lng,
            "code": code or pu_code(lga, ward_index, number),
        })
    return rows, errors


def placeholder_count(lga, ward_index):
    """8 to 15 polling units per ward, the same every run (so reseeding is idempotent)."""
    digest = hashlib.md5(f"{lga}:{ward_index}".encode()).digest()
    return 8 + digest[0] % 8


def placeholder_rows():
    """One generic polling unit per number for every ward. NOT official data."""
    from core.models import Ward

    rows = []
    for ward in Ward.objects.order_by("lga", "sort_order", "ward_index"):
        for n in range(1, placeholder_count(ward.lga, ward.ward_index) + 1):
            rows.append({
                "lga": ward.lga, "ward_index": ward.ward_index, "ward_name": ward.name,
                "number": n, "name": "", "registered_voters": 0, "latitude": None,
                "longitude": None, "code": pu_code(ward.lga, ward.ward_index, n),
            })
    return rows


def apply_rows(rows, replace=False):
    """Insert/update polling units. Returns a dict of counts."""
    from django.db import transaction

    from core.models import PollingUnit, Ward

    existing = {(p.lga, p.ward_index, p.number): p for p in PollingUnit.objects.all()}
    ward_records = {
        (ward.lga, ward.ward_index): ward
        for ward in Ward.objects.all()
    }
    to_create, to_update, file_keys = [], [], set()
    for r in rows:
        key = (r["lga"], r["ward_index"], r["number"])
        ward_record = ward_records.get((r["lga"], r["ward_index"]))
        if ward_record is None:
            raise ValueError(f"Unknown ward index {r['ward_index']} for {r['lga']}.")
        file_keys.add(key)
        pu = existing.get(key)
        if pu is None:
            to_create.append(PollingUnit(
                lga=r["lga"], ward_index=r["ward_index"], ward_name=r["ward_name"], number=r["number"],
                ward_record=ward_record,
                code=r["code"], name=r["name"], registered_voters=r["registered_voters"],
                latitude=r["latitude"], longitude=r["longitude"], is_active=True,
            ))
        else:
            pu.ward_name, pu.ward_record, pu.code, pu.is_active = r["ward_name"], ward_record, r["code"], True
            if r["name"] or r.get("overwrite_blank"):
                pu.name = r["name"]
            pu.registered_voters = r["registered_voters"] or pu.registered_voters
            if r["latitude"] is not None:
                pu.latitude, pu.longitude = r["latitude"], r["longitude"]
            to_update.append(pu)
    removed = deactivated = 0
    with transaction.atomic():
        if to_update:
            PollingUnit.objects.bulk_update(
                to_update, [
                    "ward_name", "ward_record", "code", "is_active", "name", "registered_voters",
                    "latitude", "longitude",
                ],
                batch_size=500)
        if to_create:
            PollingUnit.objects.bulk_create(to_create, batch_size=500)
        if replace:
            touched = {(r["lga"], r["ward_index"]) for r in rows}
            for lga, ward_index in touched:
                for pu in PollingUnit.objects.filter(lga=lga, ward_index=ward_index):
                    if (pu.lga, pu.ward_index, pu.number) in file_keys:
                        continue
                    if pu.submissions.exists():
                        if pu.is_active:
                            pu.is_active = False
                            pu.save(update_fields=["is_active"])
                            deactivated += 1
                    else:
                        pu.delete()
                        removed += 1
    return {"created": len(to_create), "updated": len(to_update), "removed": removed, "deactivated": deactivated}
