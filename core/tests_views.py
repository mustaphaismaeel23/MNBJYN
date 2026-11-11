from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Election, GalleryImage, PollingUnit, ResultAgent, Ward


class HomeGalleryTests(TestCase):
    def test_location_pickers_use_the_editable_ward_catalog(self):
        ward = Ward.objects.get(lga="kano_municipal", ward_index=2)
        ward.name = "Editable ward name"
        ward.save()

        for path in ("/", "/register/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                lga = next(item for item in response.context["lga_data"] if item["key"] == ward.lga)
                self.assertIn(
                    {"index": ward.ward_index, "name": "Editable ward name"},
                    lga["wards"],
                )

    def test_supplied_photos_render_when_gallery_is_empty(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "/static/core/img/gallery/nasiru-bala-jaoji-portrait.jpg",
        )
        header = response.content.decode().split('<header class="site-header', 1)[1].split("</header>", 1)[0]
        self.assertIn('class="brand-mark" src="/static/core/img/gallery/nasiru-bala-jaoji-portrait.jpg"', header)
        hero = response.content.decode().split('<figure class="hero-photo">', 1)[1].split("</figure>", 1)[0]
        self.assertIn("nasiru-bala-jaoji-portrait.jpg", hero)
        self.assertIn("Portrait of Malam Nasiru Bala Ja'oji", hero)
        for photo in (
            "nasiru-bala-jaoji-speaking.jpg",
            "nasiru-bala-jaoji-gathering.jpg",
            "nasiru-bala-jaoji-event.jpg",
            "nasiru-bala-jaoji-portrait.jpg",
            "nasiru-bala-jaoji-address.jpg",
        ):
            with self.subTest(photo=photo):
                self.assertContains(response, photo)

    def test_published_gallery_photos_override_supplied_defaults(self):
        GalleryImage.objects.create(
            image="gallery/admin-upload.jpg",
            caption="Recent community event",
            is_published=True,
        )

        response = self.client.get("/")

        self.assertContains(response, "Recent community event")
        self.assertContains(response, "/media/gallery/admin-upload.jpg")
        self.assertNotContains(response, "nasiru-bala-jaoji-speaking.jpg")


class AdminDashboardTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser(
            username="dashboard-admin",
            email="admin@example.com",
            password="test-password",
        )
        self.client.force_login(user)

    def test_admin_login_uses_branded_light_template(self):
        self.client.logout()
        response = self.client.get("/admin/login/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/login.html")
        self.assertContains(response, "Welcome back")
        self.assertContains(response, "core/css/admin.css")

    def test_dashboard_links_to_registration_and_field_management(self):
        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 200)
        for label in (
            "All registrations",
            "Elections",
            "Wards",
            "Polling units",
            "Result agents",
            "Result submissions",
            "Situation Room settings",
            "Audit log",
        ):
            with self.subTest(label=label):
                self.assertContains(response, label)

    def test_dashboard_reports_current_election_and_active_counts(self):
        election = Election.objects.create(name="Test election", slug="test-election", is_current=True)
        PollingUnit.objects.create(
            lga="kano_municipal",
            ward_index=0,
            ward_name="Test ward",
            number=1,
            code="20/21/01/001",
            is_active=True,
        )
        agent = ResultAgent(full_name="Test Agent", phone="08012345678", is_active=True)
        agent.set_pin("123456")
        agent.save()

        response = self.client.get("/admin/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_election"], election)
        self.assertEqual(response.context["stats"]["active_agents"], 1)
        self.assertEqual(response.context["stats"]["active_polling_units"], 1)

    def test_renaming_a_ward_updates_its_polling_units(self):
        ward = Ward.objects.get(lga="kano_municipal", ward_index=2)
        PollingUnit.objects.create(
            lga=ward.lga,
            ward_index=ward.ward_index,
            ward_name=ward.name,
            ward_record=ward,
            number=1,
            code="20/21/03/001",
        )

        ward.name = "Updated ward name"
        ward.save()

        self.assertTrue(PollingUnit.objects.filter(ward_record=ward, ward_name="Updated ward name").exists())

    def test_admin_can_add_a_ward_at_the_next_code_index(self):
        response = self.client.post(
            "/admin/core/ward/add/",
            {"lga": "kano_municipal", "name": "New ward", "sort_order": 99},
        )

        self.assertEqual(response.status_code, 302)
        ward = Ward.objects.get(lga="kano_municipal", name="New ward")
        self.assertEqual(ward.ward_index, 13)

    def test_admin_cannot_delete_a_ward_with_polling_units(self):
        ward = Ward.objects.get(lga="kano_municipal", ward_index=2)
        PollingUnit.objects.create(
            lga=ward.lga,
            ward_index=ward.ward_index,
            ward_name=ward.name,
            ward_record=ward,
            number=1,
            code="20/21/03/001",
        )

        response = self.client.get(f"/admin/core/ward/{ward.pk}/delete/")

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Ward.objects.filter(pk=ward.pk).exists())

    def test_polling_unit_popup_generates_code_and_rejects_duplicate_number(self):
        ward = Ward.objects.get(lga="kano_municipal", ward_index=2)
        popup_url = "/admin/core/pollingunit/add/?_to_field=id&_popup=1"
        page = self.client.get(popup_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="ward_record"')
        self.assertContains(page, 'name="number"')
        self.assertNotContains(page, 'name="code"')

        payload = {
            "ward_record": ward.pk,
            "number": 997,
            "name": "New polling location",
            "registered_voters": 100,
            "is_active": "on",
            "_popup": "1",
            "_to_field": "id",
        }
        response = self.client.post(popup_url, payload)

        self.assertEqual(response.status_code, 200)
        polling_unit = PollingUnit.objects.get(name="New polling location")
        self.assertEqual(polling_unit.code, "20/21/03/997")
        self.assertContains(response, "django-admin-popup-response-constants")
        self.assertContains(response, "20/21/03/997")

        payload["name"] = "Duplicate polling location"
        response = self.client.post(popup_url, payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists in the selected ward")
        self.assertFalse(PollingUnit.objects.filter(name="Duplicate polling location").exists())

    def test_result_agent_creation_assigns_selected_polling_unit(self):
        ward = Ward.objects.get(lga="kano_municipal", ward_index=2)
        polling_unit = PollingUnit.objects.create(
            lga=ward.lga,
            ward_index=ward.ward_index,
            ward_name=ward.name,
            ward_record=ward,
            number=991,
            code="20/21/03/991",
            name="Test polling unit",
        )

        page = self.client.get("/admin/core/resultagent/add/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "id_assignment_lga")
        self.assertContains(page, "id_assignment_ward")
        self.assertContains(page, "id_assignment_polling_unit")
        self.assertContains(page, "core/js/result_agent_location.js")
        self.assertEqual(
            self.client.get(f"/api/v1/public/lgas/{ward.lga}/wards/").status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/public/lgas/{ward.lga}/wards/{ward.ward_index}/polling-units/"
            ).status_code,
            200,
        )

        response = self.client.post(
            "/admin/core/resultagent/add/",
            {
                "full_name": "New Field Agent",
                "phone": "08011112222",
                "role": "agent",
                "lga_scope": "",
                "assignment_lga": ward.lga,
                "assignment_ward": ward.ward_index,
                "assignment_polling_unit": polling_unit.code,
            },
        )

        self.assertEqual(response.status_code, 302)
        agent = ResultAgent.objects.get(phone="08011112222")
        self.assertQuerySetEqual(agent.polling_units.all(), [polling_unit], transform=lambda pu: pu)

    def test_result_agent_creation_rejects_polling_unit_outside_selected_ward(self):
        ward = Ward.objects.get(lga="kano_municipal", ward_index=2)
        other_ward = Ward.objects.get(lga="kano_municipal", ward_index=3)
        polling_unit = PollingUnit.objects.create(
            lga=other_ward.lga,
            ward_index=other_ward.ward_index,
            ward_name=other_ward.name,
            ward_record=other_ward,
            number=991,
            code="20/21/04/991",
            name="Other ward polling unit",
        )

        response = self.client.post(
            "/admin/core/resultagent/add/",
            {
                "full_name": "Unassigned Field Agent",
                "phone": "08011113333",
                "role": "agent",
                "lga_scope": "",
                "assignment_lga": ward.lga,
                "assignment_ward": ward.ward_index,
                "assignment_polling_unit": polling_unit.code,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ResultAgent.objects.filter(phone="08011113333").exists())

    def test_existing_ward_lga_is_read_only(self):
        ward = Ward.objects.get(lga="kano_municipal", ward_index=2)

        response = self.client.get(f"/admin/core/ward/{ward.pk}/change/")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="lga"')
