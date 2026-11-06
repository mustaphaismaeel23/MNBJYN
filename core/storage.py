"""Store uploaded images in the database instead of on disk.

Serverless hosts such as Vercel have a read-only / throw-away filesystem, so
photos uploaded in /admin (hero image, gallery, executives, team) would
disappear or fail to save. Keeping them in the database (served by
core.views.media) makes uploads permanent as long as DATABASE_URL points at a
persistent database such as Postgres.
"""
import io
import mimetypes
import os

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

MAX_SIDE = 1600  # longest edge in pixels; larger uploads are scaled down


def _optimise(name, data):
    """Downscale/recompress big photos so the database stays small."""
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").upper()
        if fmt not in ("JPEG", "PNG", "WEBP"):
            return data
        img = ImageOps.exif_transpose(img)
        if max(img.size) <= MAX_SIDE and len(data) < 800_000:
            return data
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = io.BytesIO()
        if fmt == "PNG" and img.mode in ("RGBA", "LA", "P"):
            img.save(out, "PNG", optimize=True)
        else:
            img.convert("RGB").save(out, "JPEG", quality=85, optimize=True)
        return out.getvalue()
    except Exception:
        return data


@deconstructible
class DatabaseStorage(Storage):
    def _model(self):
        from .models import StoredFile
        return StoredFile

    def _open(self, name, mode="rb"):
        obj = self._model().objects.get(name=name)
        return ContentFile(bytes(obj.data), name=name)

    def _save(self, name, content):
        data = content.read()
        data = _optimise(name, data)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self._model().objects.update_or_create(
            name=name, defaults={"data": data, "content_type": ctype, "size": len(data)}
        )
        return name

    def exists(self, name):
        return self._model().objects.filter(name=name).exists()

    def delete(self, name):
        self._model().objects.filter(name=name).delete()

    def size(self, name):
        return self._model().objects.get(name=name).size

    def url(self, name):
        return "/media/" + name.lstrip("/")

    def get_available_name(self, name, max_length=None):
        # Keep names unique so a new upload never shows a cached older image.
        root, ext = os.path.splitext(name)
        candidate = name
        from django.utils.crypto import get_random_string
        while self.exists(candidate) or (max_length and len(candidate) > max_length):
            candidate = f"{root}_{get_random_string(7)}{ext}"
        return candidate
