"""Machine-readable description of the API (OpenAPI 3.0). Served at /api/v1/openapi.json.

Import it into Postman, Insomnia or Swagger UI to explore the API and generate client code.
"""

UUID_EX = "3f2b8c1e-6a4d-4f55-9d36-2b1f0c7a9e10"
CAND_EX = {"id": 1, "name": "Malam Nasiru Bala Ja'oji", "short_name": "MNBJ", "color": "#14B8A6", "order": 0}
ERR = {"error": {"code": "validation_failed", "message": "Some fields are invalid.", "fields": {"votes": "Missing candidate id(s): 4."}}}
SUBMISSION_EX = {
    "id": 118, "submission_id": UUID_EX, "election_id": 1,
    "polling_unit": {"code": "20/21/03/007", "name": "Polling Unit 007", "lga": "kano_municipal", "ward_index": 2, "ward_name": "Gandun Albasa"},
    "registered_voters": 612, "accredited_voters": 301, "rejected_votes": 4, "valid_votes": 297,
    "votes": {"1": 120, "2": 98, "3": 51, "4": 28}, "status": "submitted", "is_current": True,
    "flags": [], "review_note": "", "has_sheet": False,
    "created_at": "2027-02-25T14:02:11+00:00", "updated_at": "2027-02-25T14:02:11+00:00", "reviewed_at": None,
    "agent": {"id": 7, "full_name": "Aminu Musa"},
}
AGENT_EX = {"id": 7, "full_name": "Aminu Musa", "phone": "08012345678", "role": "agent", "lga_scope": "",
            "is_active": True, "must_change_pin": False, "is_locked": False,
            "last_login_at": "2027-02-25T06:55:00+00:00", "created_at": "2027-02-10T09:00:00+00:00",
            "assigned_polling_units": 2}

PUBLIC, AGENT, REVIEW, ADMIN = "public", "agent", "supervisor|admin", "admin"

# (method, path, tag, summary, who, request example, response example, [query params])
ENDPOINTS = [
    ("get", "/health/", "System", "Health check", PUBLIC, None, {"status": "ok", "service": "mnbjyn-results-api", "version": "1"}, []),

    ("get", "/public/config/", "Public", "Situation Room mode, election and candidates", PUBLIC, None,
     {"mode": "live", "refresh_seconds": 10, "publish_unverified": True, "state": {"name": "Kano", "code": "20"},
      "election": {"id": 1, "name": "2027 Governorship – Kano State", "slug": "kano-gov-2027", "election_date": None, "is_current": True, "candidates": [CAND_EX]},
      "server_time": "2027-02-25T14:00:00+00:00"}, []),
    ("get", "/public/structure/", "Public", "All LGAs, wards and polling units (compact)", PUBLIC, None,
     {"state": {"name": "Kano", "code": "20"}, "pu_fields": ["number", "code", "name", "registered_voters"], "total_polling_units": 1,
      "lgas": [{"key": "kano_municipal", "code": "20/21", "name": "Kano Municipal", "wards": [{"index": 2, "code": "20/21/03", "name": "Gandun Albasa", "pus": [[7, "20/21/03/007", "Polling Unit 007", 612]]}]}]}, []),
    ("get", "/public/results/", "Public", "Public results (full, or only changes since a cursor)", PUBLIC, None,
     {"mode": "live", "election_id": 1, "cursor": "2027-02-25T14:00:05.000000Z", "full": False, "public_count": 1,
      "results": [{"pu": "20/21/03/007", "registered": 612, "accredited": 301, "rejected": 4, "valid": 297, "votes": [120, 98, 51, 28], "by": "Aminu M.", "at": "2027-02-25T14:02:11+00:00", "status": "submitted"}],
      "withdrawn": []},
     [("since", "Cursor returned by the previous call. Omit for a full download.")]),
    ("get", "/public/summary/", "Public", "Totals for the state, an LGA or a ward", PUBLIC, None,
     {"election": {"id": 1, "name": "2027 Governorship – Kano State"}, "scope": {"lga": "kano_municipal", "ward_index": None},
      "polling_units_total": 140, "polling_units_reported": 12, "percent_reported": 8.6, "registered_voters": 7300,
      "accredited_voters": 3600, "rejected_votes": 50, "valid_votes": 3550, "turnout_percent": 49.3,
      "candidates": [dict(CAND_EX, votes=1400, percent=39.4)]},
     [("lga", "LGA key, e.g. kano_municipal"), ("ward", "Ward index (needs lga)")]),
    ("get", "/public/lgas/", "Public", "The 44 LGAs", PUBLIC, None,
     {"lgas": [{"key": "ajingi", "code": "20/01", "name": "Ajingi", "wards": 10}]}, []),
    ("get", "/public/lgas/{lga}/wards/", "Public", "Wards of an LGA with polling-unit counts", PUBLIC, None,
     {"lga": {"key": "kano_municipal", "code": "20/21", "name": "Kano Municipal"}, "wards": [{"index": 2, "code": "20/21/03", "name": "Gandun Albasa", "polling_units": 1}]}, []),
    ("get", "/public/lgas/{lga}/wards/{ward_index}/polling-units/", "Public", "Polling units of a ward", PUBLIC, None,
     {"lga": "kano_municipal", "ward_index": 2, "ward_name": "Gandun Albasa", "polling_units": [{"code": "20/21/03/007", "number": 7, "name": "Polling Unit 007", "lga": "kano_municipal", "lga_name": "Kano Municipal", "ward_index": 2, "ward_name": "Gandun Albasa", "registered_voters": 612, "latitude": None, "longitude": None, "is_active": True}]}, []),

    ("post", "/auth/login/", "Authentication", "Log in with phone + PIN", PUBLIC,
     {"phone": "08012345678", "pin": "493021", "device_name": "Tecno Spark 10"},
     {"token": "mnbjyn_…", "token_type": "Bearer", "expires_at": "2027-02-27T06:00:00+00:00", "agent": AGENT_EX}, []),
    ("post", "/auth/logout/", "Authentication", "Revoke the current token", AGENT, None, {"ok": True}, []),
    ("get", "/auth/me/", "Authentication", "Who am I?", AGENT, None, {"agent": AGENT_EX, "token_expires_at": "2027-02-27T06:00:00+00:00"}, []),
    ("post", "/auth/change-pin/", "Authentication", "Change PIN (mandatory after first login)", AGENT,
     {"current_pin": "493021", "new_pin": "718305"}, {"ok": True}, []),

    ("get", "/election/current/", "App", "Current election and candidate list (build the result form from this)", AGENT, None,
     {"election": {"id": 1, "name": "2027 Governorship – Kano State", "slug": "kano-gov-2027", "election_date": None, "is_current": True, "candidates": [CAND_EX]}}, []),
    ("get", "/agent/assignments/", "App", "My polling units and the state of each result", "agent", None,
     {"election": {"id": 1, "name": "…"}, "polling_units": [{"code": "20/21/03/007", "number": 7, "name": "Polling Unit 007", "lga": "kano_municipal", "lga_name": "Kano Municipal", "ward_index": 2, "ward_name": "Gandun Albasa", "registered_voters": 612, "latitude": None, "longitude": None, "is_active": True, "result": None}], "can_self_assign": False, "message": ""}, []),
    ("get", "/agent/available-polling-units/", "App", "Find active polling units available for self-assignment", "agent", None,
     {"count": 1, "page": 1, "page_size": 100, "pages": 1, "polling_units": [{"code": "20/21/03/008", "number": 8, "name": "Polling Unit 008", "lga": "kano_municipal", "lga_name": "Kano Municipal", "ward_index": 2, "ward_name": "Gandun Albasa", "registered_voters": 0, "latitude": None, "longitude": None, "is_active": True}]},
     [("lga", "Optional LGA key"), ("ward", "Optional ward index; requires lga"), ("q", "Search code, name or ward"), ("page", ""), ("page_size", "max 200")]),
    ("post", "/agent/claim-assignment/", "App", "Claim one unassigned active polling unit", "agent",
     {"polling_unit_code": "20/21/03/008"},
     {"polling_unit": {"code": "20/21/03/008", "number": 8, "name": "Polling Unit 008", "lga": "kano_municipal", "lga_name": "Kano Municipal", "ward_index": 2, "ward_name": "Gandun Albasa", "registered_voters": 0, "latitude": None, "longitude": None, "is_active": True}, "already_claimed": False}, []),
    ("post", "/results/", "Results", "Submit a polling-unit result", "agent",
     {"submission_id": UUID_EX, "polling_unit_code": "20/21/03/007", "registered_voters": 612, "accredited_voters": 301,
      "rejected_votes": 4, "valid_votes": 297, "votes": {"1": 120, "2": 98, "3": 51, "4": 28},
      "latitude": 10.3158, "longitude": 9.8442, "client_time": "2027-02-25T15:01:50+01:00", "acknowledge_anomalies": False},
     {"duplicate": False, "submission": SUBMISSION_EX}, []),
    ("post", "/results/batch/", "Results", "Submit up to 20 results at once (offline queue)", "agent",
     {"items": ["<same object as POST /results/>"]}, {"results": [{"index": 0, "ok": True, "duplicate": False, "submission": SUBMISSION_EX}], "accepted": 1}, []),
    ("get", "/results/mine/", "Results", "My submissions", "agent", None,
     {"count": 1, "page": 1, "page_size": 100, "pages": 1, "results": [SUBMISSION_EX]}, [("history", "1 = include replaced submissions"), ("page", ""), ("page_size", "max 200")]),
    ("get", "/results/{id}/", "Results", "One submission", "all roles (own / in scope)", None, {"submission": SUBMISSION_EX}, []),
    ("post", "/results/{id}/sheet/", "Results", "Upload the photo of the signed result sheet (multipart field 'sheet', JPEG/PNG/WEBP, max 4 MB)", "agent", "multipart/form-data", {"submission": SUBMISSION_EX}, []),
    ("get", "/results/{id}/sheet/", "Results", "Download the sheet photo (private)", "all roles (own / in scope)", None, "image bytes", []),
    ("get", "/results/", "Supervision", "List results in my area", REVIEW, None,
     {"count": 1, "page": 1, "page_size": 50, "pages": 1, "results": [SUBMISSION_EX]},
     [("lga", ""), ("ward", "index"), ("status", "submitted|verified|flagged|disputed|rejected|superseded"), ("history", "1"), ("page", ""), ("page_size", "")]),
    ("post", "/results/{id}/review/", "Supervision", "Verify, dispute or reject a result", REVIEW,
     {"action": "verify", "note": ""}, {"submission": SUBMISSION_EX}, []),
    ("get", "/results/summary/", "Supervision", "Totals incl. unverified, plus counts per status", REVIEW, None,
     {"polling_units_total": 140, "polling_units_reported": 12, "by_status": {"submitted": 9, "verified": 3, "flagged": 0, "disputed": 0, "rejected": 0}, "candidates": []},
     [("lga", ""), ("ward", "")]),

    ("get", "/admin/agents/", "Admin", "List agents", ADMIN, None, {"count": 1, "page": 1, "page_size": 50, "pages": 1, "agents": [AGENT_EX]}, [("role", ""), ("q", "name or phone"), ("page", "")]),
    ("post", "/admin/agents/", "Admin", "Create an agent (temporary PIN returned once)", ADMIN,
     {"full_name": "Aminu Musa", "phone": "08012345678", "role": "agent", "polling_unit_codes": ["20/21/03/007"]},
     {"agent": AGENT_EX, "temporary_pin": "493021"}, []),
    ("get", "/admin/agents/{id}/", "Admin", "One agent with assigned polling units", ADMIN, None, {"agent": AGENT_EX, "polling_units": []}, []),
    ("patch", "/admin/agents/{id}/", "Admin", "Edit / deactivate an agent", ADMIN, {"is_active": False}, {"agent": AGENT_EX}, []),
    ("post", "/admin/agents/{id}/reset-pin/", "Admin", "Issue a new temporary PIN (signs the agent out everywhere)", ADMIN, None, {"agent": AGENT_EX, "temporary_pin": "804712"}, []),
    ("post", "/admin/agents/{id}/revoke-tokens/", "Admin", "Sign the agent out everywhere", ADMIN, None, {"revoked": 2}, []),
    ("post", "/admin/agents/{id}/assignments/", "Admin", "Assign polling units to an agent", ADMIN,
     {"mode": "add", "polling_unit_codes": ["20/21/03/008"], "ward": {"lga": "kano_municipal", "ward_index": 3}}, {"agent": AGENT_EX}, []),
    ("get", "/admin/polling-units/", "Admin", "List polling units", ADMIN, None, {"count": 2466, "page": 1, "page_size": 100, "pages": 25, "polling_units": []}, [("lga", ""), ("ward", ""), ("q", ""), ("page", "")]),
    ("post", "/admin/polling-units/import/", "Admin", "Import the official polling-unit list (CSV, multipart field 'file'; optional 'replace=true')", ADMIN, "multipart/form-data", {"rows": 140, "created": 0, "updated": 140, "removed": 0, "deactivated": 0}, []),
    ("patch", "/admin/polling-units/{code}/", "Admin", "Edit a polling unit (use dashes in the URL: 20-21-03-007)", ADMIN, {"name": "Primary School, Gandun Albasa", "registered_voters": 612, "latitude": 12.0, "longitude": 8.5}, {"polling_unit": {}}, []),
    ("get", "/admin/elections/", "Admin", "List elections", ADMIN, None, {"elections": []}, []),
    ("post", "/admin/elections/", "Admin", "Create an election with candidates", ADMIN,
     {"name": "2027 Governorship", "slug": "kano-gov-2027", "election_date": "2027-02-20", "make_current": True,
      "candidates": [{"name": "Candidate A", "short_name": "A", "color": "#14B8A6"}, {"name": "Candidate B", "short_name": "B", "color": "#FFFFFF"}]},
     {"election": {}}, []),
    ("patch", "/admin/elections/{id}/", "Admin", "Edit an election (candidates only before results exist)", ADMIN, {"is_current": True}, {"election": {}}, []),
    ("get", "/admin/situation-room/", "Admin", "Situation Room mode, go-live warnings, stats", ADMIN, None,
     {"config": {"mode": "simulation", "publish_unverified": True, "refresh_seconds": 10}, "election": {}, "warnings": [{"level": "critical", "message": "…"}], "stats": {"polling_units": 2466, "agents": 0, "submissions_current": 0}}, []),
    ("patch", "/admin/situation-room/", "Admin", "Switch between simulation and live", ADMIN, {"mode": "live"}, {"config": {"mode": "live"}}, []),
    ("get", "/admin/audit/", "Admin", "Audit log", ADMIN, None, {"count": 1, "page": 1, "page_size": 100, "pages": 1, "entries": []}, [("action", ""), ("actor", "agent id"), ("page", "")]),
]


def build_spec():
    paths = {}
    for method, path, tag, summary, who, req, resp, query in ENDPOINTS:
        op = {
            "tags": [tag],
            "summary": summary,
            "description": f"Who can call it: **{who}**.",
            "responses": {
                "200": {"description": "OK", "content": {"application/json": {"example": resp}}} if isinstance(resp, dict)
                else {"description": "OK"},
                "4XX": {"description": "Error", "content": {"application/json": {"example": ERR}}},
            },
        }
        if who != PUBLIC:
            op["security"] = [{"bearerAuth": []}]
        params = [{"name": n, "in": "path", "required": True, "schema": {"type": "string"}}
                  for n in [seg[1:-1] for seg in path.split("/") if seg.startswith("{")]]
        params += [{"name": n, "in": "query", "required": False, "description": d, "schema": {"type": "string"}} for n, d in query]
        if params:
            op["parameters"] = params
        if req == "multipart/form-data":
            op["requestBody"] = {"required": True, "content": {"multipart/form-data": {"schema": {"type": "object"}}}}
        elif req is not None:
            op["requestBody"] = {"required": True, "content": {"application/json": {"example": req}}}
        paths.setdefault(path, {})[method] = op
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "MNBJYN Election Results API",
            "version": "1.0.0",
            "description": "Collects polling-unit results from the field app and serves live results to the "
                           "Situation Room. All paths live under /api/v1. Send JSON with "
                           "'Content-Type: application/json' and (except public endpoints) "
                           "'Authorization: Bearer <token>'.",
        },
        "servers": [{"url": "/api/v1"}],
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
        "paths": paths,
    }
