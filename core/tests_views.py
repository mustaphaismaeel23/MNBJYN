from django.test import TestCase

from .models import GalleryImage


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
