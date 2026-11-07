from django.contrib.auth import get_user_model
from django.test import TestCase

from .models import Election, GalleryImage, PollingUnit, ResultAgent


class HomeGalleryTests(TestCase):
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
