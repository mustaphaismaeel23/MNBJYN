"""End-to-end tests of the results API. Run:  python manage.py test core"""
import io
import json
import uuid

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from core.models import ApiToken, Election, PollingUnit, ResultAgent, ResultSubmission, SituationRoomConfig, Ward

NO_CACHE = {"default": {"BACKEND": "django.core.cache.backends.dummy.DummyCache"}}
PIN = "493021"


def make_agent(name, phone, role="agent", pin=PIN, must_change=False, **kw):
    agent = ResultAgent(full_name=name, phone=phone, role=role, must_change_pin=must_change, **kw)
    agent.set_pin(pin)
    agent.save()
    return agent


@override_settings(CACHES=NO_CACHE)
class ApiTests(TestCase):
    def setUp(self):
        self.election = Election.current()          # created by migration 0006
        self.cands = list(self.election.candidates.all())
        self.pu1 = PollingUnit.objects.create(lga="kano_municipal", ward_index=2, ward_name="Gandun Albasa",
                                              number=1, code="20/21/03/001", registered_voters=600)
        self.pu2 = PollingUnit.objects.create(lga="kano_municipal", ward_index=2, ward_name="Gandun Albasa",
                                              number=2, code="20/21/03/002", registered_voters=500)
        self.admin = make_agent("Admin One", "08000000001", "admin")
        self.sup = make_agent("Sup One", "08000000002", "supervisor", lga_scope="kano_municipal")
        self.agent = make_agent("Aminu Musa", "08000000003")
        self.agent.polling_units.add(self.pu1)
        self.other = make_agent("Other Agent", "08000000004")
        self.other.polling_units.add(self.pu2)

    # ---------------------------------------------------------------- helpers
    def call(self, method, path, body=None, token=None, **extra):
        kwargs = {}
        if token:
            kwargs["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        if body is not None and not isinstance(body, bytes):
            kwargs["data"] = json.dumps(body)
            kwargs["content_type"] = "application/json"
        kwargs.update(extra)
        return getattr(self.client, method)("/api/v1" + path, **kwargs)

    def login(self, agent, pin=PIN):
        r = self.call("post", "/auth/login/", {"phone": agent.phone, "pin": pin})
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["token"]

    def result_body(self, pu_code="20/21/03/001", **over):
        ids = [str(c.pk) for c in self.cands]
        body = {"submission_id": str(uuid.uuid4()), "polling_unit_code": pu_code, "registered_voters": 600,
                "accredited_voters": 300, "rejected_votes": 4,
                "votes": {ids[0]: 120, ids[1]: 90, ids[2]: 60, ids[3]: 26}}
        body.update(over)
        return body

    def test_kano_public_location_catalog(self):
        response = self.call("get", "/public/lgas/")
        self.assertEqual(response.status_code, 200)
        lgas = response.json()["lgas"]
        self.assertEqual(len(lgas), 44)
        self.assertEqual(sum(lga["wards"] for lga in lgas), 484)
        self.assertEqual(lgas[20], {
            "key": "kano_municipal",
            "code": "20/21",
            "name": "Kano Municipal",
            "wards": 13,
        })

        config = self.call("get", "/public/config/").json()
        self.assertEqual(config["state"], {"name": "Kano", "code": "20"})
        self.assertEqual(config["election"]["slug"], "kano-gov-2027")
        self.assertEqual(config["election"]["candidates"][0]["name"], "Malam Nasiru Bala Ja'oji")

    def test_public_ward_catalog_uses_database_names_and_display_order(self):
        first, second = list(Ward.objects.filter(lga="kano_municipal").order_by("sort_order")[:2])
        first.name = "Renamed ward"
        first.sort_order = 1
        first.save()
        second.sort_order = 0
        second.save()

        response = self.call("get", "/public/lgas/kano_municipal/wards/")
        wards = response.json()["wards"]
        self.assertEqual(response.status_code, 200)
        self.assertEqual([ward["index"] for ward in wards[:2]], [second.ward_index, first.ward_index])
        self.assertEqual(next(w["name"] for w in wards if w["index"] == first.ward_index), "Renamed ward")

        structure = self.call("get", "/public/structure/").json()
        municipal = next(lga for lga in structure["lgas"] if lga["key"] == "kano_municipal")
        self.assertEqual([ward["index"] for ward in municipal["wards"][:2]], [second.ward_index, first.ward_index])

    def test_registered_agent_can_claim_one_available_polling_unit(self):
        pu = PollingUnit.objects.create(
            lga="kano_municipal", ward_index=2, ward_name="Gandun Albasa",
            number=3, code="20/21/03/003",
        )
        agent = make_agent("Self Assign Agent", "08000000007")
        token = self.login(agent)

        assignments = self.call("get", "/agent/assignments/", token=token).json()
        self.assertTrue(assignments["can_self_assign"])
        self.assertIn("do not need an administrator", assignments["message"])

        available = self.call("get", "/agent/available-polling-units/", token=token)
        self.assertEqual(available.status_code, 200)
        self.assertEqual([row["code"] for row in available.json()["polling_units"]], [pu.code])

        claimed = self.call(
            "post", "/agent/claim-assignment/",
            {"polling_unit_code": pu.code.replace("/", "-")}, token=token,
        )
        self.assertEqual(claimed.status_code, 201, claimed.content)
        self.assertEqual(claimed.json()["polling_unit"]["code"], pu.code)

        repeated = self.call(
            "post", "/agent/claim-assignment/", {"polling_unit_code": pu.code}, token=token
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertTrue(repeated.json()["already_claimed"])
        self.assertEqual(self.call("get", "/agent/assignments/", token=token).json()["can_self_assign"], False)

        other_agent = make_agent("Second Agent", "08000000008")
        conflict = self.call(
            "post", "/agent/claim-assignment/",
            {"polling_unit_code": pu.code}, token=self.login(other_agent),
        )
        self.assertEqual((conflict.status_code, conflict.json()["error"]["code"]), (409, "polling_unit_claimed"))

    def test_self_assignment_is_limited_to_one_unit(self):
        agent = make_agent("One Unit Agent", "08000000009")
        token = self.login(agent)
        pu = PollingUnit.objects.create(
            lga="kano_municipal", ward_index=2, ward_name="Gandun Albasa",
            number=3, code="20/21/03/003",
        )
        another = PollingUnit.objects.create(
            lga="kano_municipal", ward_index=2, ward_name="Gandun Albasa",
            number=4, code="20/21/03/004",
        )
        self.assertEqual(self.call(
            "post", "/agent/claim-assignment/", {"polling_unit_code": pu.code}, token=token
        ).status_code, 201)
        response = self.call(
            "post", "/agent/claim-assignment/", {"polling_unit_code": another.code}, token=token
        )
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "assignment_limit_reached"))
        self.assertFalse(agent.polling_units.filter(pk=another.pk).exists())

    def test_openapi_documents_self_assignment_endpoints(self):
        response = self.client.get("/api/v1/openapi.json")

        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertIn("/agent/available-polling-units/", paths)
        self.assertIn("/agent/claim-assignment/", paths)

    # ---------------------------------------------------------------- auth
    def test_login_pin_change_and_token_storage(self):
        agent = make_agent("New Agent", "08000000005", must_change=True)
        r = self.call("post", "/auth/login/", {"phone": "+234 800 000 0005", "pin": PIN})
        self.assertEqual(r.status_code, 200)
        token = r.json()["token"]
        self.assertTrue(r.json()["agent"]["must_change_pin"])
        self.assertFalse(ApiToken.objects.filter(key_hash=token).exists())       # raw token never stored
        self.assertTrue(ApiToken.objects.filter(key_hash=ApiToken.hash_key(token)).exists())
        r = self.call("get", "/agent/assignments/", token=token)
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "pin_change_required"))
        r = self.call("post", "/auth/change-pin/", {"current_pin": PIN, "new_pin": "111111"}, token=token)
        self.assertEqual(r.status_code, 422)
        r = self.call("post", "/auth/change-pin/", {"current_pin": PIN, "new_pin": "718305"}, token=token)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.call("get", "/agent/assignments/", token=token).status_code, 200)

    def test_bad_credentials_are_generic_and_lock(self):
        r = self.call("post", "/auth/login/", {"phone": "08099999999", "pin": "123789"})
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (401, "invalid_credentials"))
        for _ in range(5):
            r = self.call("post", "/auth/login/", {"phone": self.agent.phone, "pin": "000111"})
            self.assertEqual(r.status_code, 401)
        r = self.call("post", "/auth/login/", {"phone": self.agent.phone, "pin": PIN})   # correct PIN, but locked
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (429, "account_locked"))

    def test_missing_or_bad_token(self):
        self.assertEqual(self.call("get", "/auth/me/").status_code, 401)
        self.assertEqual(self.call("get", "/auth/me/", token="mnbjyn_nope").status_code, 401)

    def test_logout_revokes(self):
        token = self.login(self.agent)
        self.assertEqual(self.call("post", "/auth/logout/", token=token).status_code, 200)
        self.assertEqual(self.call("get", "/auth/me/", token=token).status_code, 401)

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                                           "LOCATION": "throttle-test"}})
    def test_login_rate_limit(self):
        cache.clear()
        codes = [self.call("post", "/auth/login/", {"phone": "08077777777", "pin": "123789"}).status_code
                 for _ in range(12)]
        self.assertIn(429, codes)

    # ---------------------------------------------------------------- submitting
    def test_submit_replay_and_permissions(self):
        token = self.login(self.agent)
        body = self.result_body()
        r = self.call("post", "/results/", body, token=token)
        self.assertEqual(r.status_code, 201, r.content)
        sub = r.json()["submission"]
        self.assertEqual((sub["valid_votes"], sub["status"]), (296, "submitted"))
        r = self.call("post", "/results/", body, token=token)                      # retry after a dropped connection
        self.assertEqual((r.status_code, r.json()["duplicate"]), (200, True))
        self.assertEqual(ResultSubmission.objects.count(), 1)
        other = dict(body, accredited_voters=299)
        r = self.call("post", "/results/", other, token=token)                     # same id, different figures
        self.assertEqual(r.json()["error"]["code"], "submission_id_reused")
        r = self.call("post", "/results/", self.result_body("20/21/03/002"), token=token)   # not my PU
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "not_assigned"))
        r = self.call("post", "/results/", self.result_body("20/21/03/099"), token=token)
        self.assertEqual(r.status_code, 404)
        sup = self.login(self.sup)
        r = self.call("post", "/results/", self.result_body(), token=sup)           # supervisors cannot submit
        self.assertEqual(r.status_code, 403)

    def test_validation_and_anomalies(self):
        token = self.login(self.agent)
        ids = [str(c.pk) for c in self.cands]
        r = self.call("post", "/results/", self.result_body(valid_votes=5), token=token)
        self.assertEqual((r.status_code, "valid_votes" in r.json()["error"]["fields"]), (422, True))
        r = self.call("post", "/results/", self.result_body(votes={ids[0]: 1}), token=token)
        self.assertEqual(r.status_code, 422)
        r = self.call("post", "/results/", self.result_body(accredited_voters=700), token=token)
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (422, "anomalies_detected"))
        self.assertEqual(ResultSubmission.objects.count(), 0)
        body = self.result_body(accredited_voters=700, acknowledge_anomalies=True)
        r = self.call("post", "/results/", body, token=token)
        self.assertEqual((r.status_code, r.json()["submission"]["status"]), (201, "flagged"))
        self.assertEqual(self.call("post", "/results/", data=b"{not json", content_type="application/json",
                                   HTTP_AUTHORIZATION=f"Bearer {token}").status_code, 400)

    def test_batch(self):
        token = self.login(self.agent)
        r = self.call("post", "/results/batch/", {"items": [self.result_body(), self.result_body("20/21/03/002")]}, token=token)
        data = r.json()
        self.assertEqual(data["accepted"], 1)
        self.assertEqual(data["results"][1]["error"]["code"], "not_assigned")

    def test_correction_supersedes_and_verified_locks(self):
        token, sup = self.login(self.agent), self.login(self.sup)
        first = self.call("post", "/results/", self.result_body(), token=token).json()["submission"]
        fixed = self.result_body(rejected_votes=5, votes={str(self.cands[0].pk): 121, str(self.cands[1].pk): 90,
                                                           str(self.cands[2].pk): 60, str(self.cands[3].pk): 24})
        second = self.call("post", "/results/", fixed, token=token).json()["submission"]
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(ResultSubmission.objects.get(pk=first["id"]).status, "superseded")
        self.assertEqual(ResultSubmission.objects.filter(is_current=True).count(), 1)
        r = self.call("post", f"/results/{second['id']}/review/", {"action": "verify"}, token=sup)
        self.assertEqual(r.json()["submission"]["status"], "verified")
        again = self.result_body(rejected_votes=6, acknowledge_anomalies=True)
        r = self.call("post", "/results/", again, token=token)
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (409, "already_verified"))
        r = self.call("post", f"/results/{second['id']}/review/", {"action": "reject", "note": "wrong sheet"}, token=sup)
        self.assertEqual(r.json()["submission"]["status"], "rejected")
        self.assertEqual(self.call("post", "/results/", again, token=token).status_code, 201)

    def test_agents_cannot_see_each_others_results(self):
        a, b = self.login(self.agent), self.login(self.other)
        sid = self.call("post", "/results/", self.result_body(), token=a).json()["submission"]["id"]
        self.assertEqual(self.call("get", f"/results/{sid}/", token=a).status_code, 200)
        self.assertEqual(self.call("get", f"/results/{sid}/", token=b).status_code, 404)
        self.assertEqual(self.call("get", "/results/", token=a).status_code, 403)
        self.assertEqual(self.call("get", "/results/", token=self.login(self.sup)).status_code, 200)

    def test_supervisor_scope(self):
        pu = PollingUnit.objects.create(lga="misau", ward_index=0, ward_name="x", number=1, code="05/14/01/001")
        ag = make_agent("Misau Agent", "08000000006")
        ag.polling_units.add(pu)
        sid = self.call("post", "/results/", self.result_body("05/14/01/001"),
                        token=self.login(ag)).json()["submission"]["id"]
        self.assertEqual(self.call("get", f"/results/{sid}/", token=self.login(self.sup)).status_code, 404)
        self.assertEqual(self.call("get", f"/results/{sid}/", token=self.login(self.admin)).status_code, 200)

    # ---------------------------------------------------------------- public data
    def test_public_results_visibility_and_cursor(self):
        token, sup = self.login(self.agent), self.login(self.sup)
        self.assertEqual(self.call("get", "/public/results/").json()["results"], [])
        flagged = self.result_body(accredited_voters=700, acknowledge_anomalies=True)
        sid = self.call("post", "/results/", flagged, token=token).json()["submission"]["id"]
        self.assertEqual(self.call("get", "/public/results/").json()["results"], [])      # flagged is held back
        self.call("post", f"/results/{sid}/review/", {"action": "verify"}, token=sup)
        data = self.call("get", "/public/results/").json()
        self.assertEqual(len(data["results"]), 1)
        row = data["results"][0]
        self.assertEqual((row["pu"], row["valid"], row["by"]), ("20/21/03/001", 296, "Aminu M."))
        self.assertEqual(row["votes"], [120, 90, 60, 26])
        inc = self.call("get", "/public/results/", QUERY_STRING="since=" + data["cursor"]).json()
        self.assertFalse(inc["full"])
        self.call("post", f"/results/{sid}/review/", {"action": "dispute", "note": "doubtful figures"}, token=sup)
        inc = self.call("get", "/public/results/", QUERY_STRING="since=2000-01-01T00:00:00Z").json()
        self.assertEqual(inc["withdrawn"], ["20/21/03/001"])
        self.assertEqual(self.call("get", "/public/results/", QUERY_STRING="since=garbage").status_code, 422)

    def test_unverified_toggle(self):
        token = self.login(self.agent)
        self.call("post", "/results/", self.result_body(), token=token)
        self.assertEqual(len(self.call("get", "/public/results/").json()["results"]), 1)
        cfg = SituationRoomConfig.load(); cfg.publish_unverified = False; cfg.save()
        self.assertEqual(self.call("get", "/public/results/").json()["results"], [])

    def test_summary_and_structure(self):
        self.call("post", "/results/", self.result_body(), token=self.login(self.agent))
        s = self.call("get", "/public/summary/").json()
        self.assertEqual((s["polling_units_total"], s["polling_units_reported"], s["valid_votes"]), (2, 1, 296))
        self.assertEqual(s["candidates"][0]["votes"], 120)
        st = self.call("get", "/public/structure/").json()
        self.assertEqual(len(st["lgas"]), 44)
        municipal = next(lga for lga in st["lgas"] if lga["key"] == "kano_municipal")
        ward = next(w for w in municipal["wards"] if w["index"] == 2)
        self.assertEqual(ward["pus"][0][:2], [1, "20/21/03/001"])
        self.assertEqual(self.call("get", "/public/summary/", QUERY_STRING="lga=nowhere").status_code, 422)

    def test_public_endpoints_need_no_login_but_cors_is_restricted(self):
        r = self.call("get", "/public/config/", HTTP_ORIGIN="https://evil.example")
        self.assertEqual(r["Access-Control-Allow-Origin"], "*")
        r = self.call("post", "/auth/login/", {"phone": "08000000003", "pin": PIN}, HTTP_ORIGIN="https://evil.example")
        self.assertNotIn("Access-Control-Allow-Origin", r)

    def test_unknown_path_is_json_404(self):
        r = self.call("post", "/nope/")
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (404, "not_found"))

    # ---------------------------------------------------------------- sheet photo
    def test_sheet_upload_is_private(self):
        from PIL import Image

        token = self.login(self.agent)
        sid = self.call("post", "/results/", self.result_body(), token=token).json()["submission"]["id"]
        buf = io.BytesIO(); Image.new("RGB", (40, 40), "white").save(buf, "PNG")
        up = SimpleUploadedFile("sheet.png", buf.getvalue(), content_type="image/png")
        r = self.client.post(f"/api/v1/results/{sid}/sheet/", {"sheet": up}, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(r.status_code, 200, r.content)
        name = ResultSubmission.objects.get(pk=sid).sheet_name
        self.assertTrue(name.startswith("sheets/"))
        self.assertEqual(self.client.get("/media/" + name).status_code, 404)              # not public
        self.assertEqual(self.call("get", f"/results/{sid}/sheet/", token=token).status_code, 200)
        self.assertEqual(self.call("get", f"/results/{sid}/sheet/", token=self.login(self.other)).status_code, 404)
        bad = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
        r = self.client.post(f"/api/v1/results/{sid}/sheet/", {"sheet": bad}, HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(r.status_code, 422)

    # ---------------------------------------------------------------- admin
    def test_admin_creates_agent_and_assigns(self):
        adm = self.login(self.admin)
        r = self.call("post", "/admin/agents/", {"full_name": "Field Agent", "phone": "08111111111",
                      "polling_unit_codes": ["20/21/03/001"]}, token=adm)
        self.assertEqual(r.status_code, 201, r.content)
        pin = r.json()["temporary_pin"]
        agent_id = r.json()["agent"]["id"]
        self.assertTrue(ResultAgent.objects.get(pk=agent_id).must_change_pin)
        r = self.call("post", f"/admin/agents/{agent_id}/assignments/", {"mode": "add", "ward": {"lga": "kano_municipal", "ward_index": 2}}, token=adm)
        self.assertEqual(r.json()["agent"]["assigned_polling_units"], 2)
        r = self.call("post", "/auth/login/", {"phone": "08111111111", "pin": pin})
        self.assertEqual(r.status_code, 200)
        old_token = r.json()["token"]
        self.assertEqual(self.call("post", "/admin/agents/", {"full_name": "Dup", "phone": "08111111111"}, token=adm).status_code, 422)
        self.assertEqual(self.call("get", "/admin/agents/", token=self.login(self.agent)).status_code, 403)
        r = self.call("post", f"/admin/agents/{agent_id}/reset-pin/", token=adm)
        self.assertNotEqual(r.json()["temporary_pin"], pin)
        self.assertEqual(self.call("get", "/auth/me/", token=old_token).status_code, 401)   # signed out everywhere

    def test_admin_switch_to_live_and_import(self):
        adm = self.login(self.admin)
        self.assertEqual(self.call("get", "/public/config/").json()["mode"], "simulation")
        r = self.call("patch", "/admin/situation-room/", {"mode": "live"}, token=adm)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["config"]["mode"], "live")
        self.assertEqual(self.call("get", "/public/config/").json()["mode"], "live")
        csv_bytes = b"lga,ward,pu_number,name,registered_voters\nKano Municipal,Gandun Albasa,1,Primary School,612\n"
        up = SimpleUploadedFile("pus.csv", csv_bytes, content_type="text/csv")
        r = self.client.post("/api/v1/admin/polling-units/import/", {"file": up}, HTTP_AUTHORIZATION=f"Bearer {adm}")
        self.assertEqual(
            (r.status_code, r.json()["created"], r.json()["updated"]),
            (200, 0, 1),
            r.content,
        )
        self.assertTrue(PollingUnit.objects.filter(code="20/21/03/001", registered_voters=612).exists())
        bad = SimpleUploadedFile("pus.csv", b"lga,ward,pu_number\nKano Municipal,Nowhere,1\n", content_type="text/csv")
        r = self.client.post("/api/v1/admin/polling-units/import/", {"file": bad}, HTTP_AUTHORIZATION=f"Bearer {adm}")
        self.assertEqual(r.status_code, 422)

    def test_cannot_go_live_without_polling_units(self):
        PollingUnit.objects.all().delete()
        r = self.call("patch", "/admin/situation-room/", {"mode": "live"}, token=self.login(self.admin))
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (409, "not_ready"))

    def test_audit_trail(self):
        self.call("post", "/auth/login/", {"phone": self.agent.phone, "pin": "000111"})
        token = self.login(self.agent)
        self.call("post", "/results/", self.result_body(), token=token)
        r = self.call("get", "/admin/audit/", token=self.login(self.admin))
        actions = {e["action"] for e in r.json()["entries"]}
        self.assertTrue({"login_failed", "login", "submit_result"} <= actions)
