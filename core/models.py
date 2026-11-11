from django.core.validators import RegexValidator
from django.db import models

from .lga_data import KANO_LGAS

# All 44 Local Government Areas of Kano State, plus "Other".
LGA_CHOICES = [(key, name) for key, name, _ in KANO_LGAS] + [
    ("other", "Other (outside Kano State)"),
]
WARD_LGA_CHOICES = [(key, name) for key, name, _ in KANO_LGAS]

GENDER_CHOICES = [("male", "Male"), ("female", "Female")]

AGE_CHOICES = [
    ("18-24", "18 – 24"),
    ("25-30", "25 – 30"),
    ("31-35", "31 – 35"),
    ("36-40", "36 – 40"),
    ("40+", "Above 40"),
]

STATUS_CHOICES = [
    ("student", "Student"),
    ("employed", "Employed"),
    ("self_employed", "Self-employed / Business"),
    ("unemployed", "Seeking employment"),
    ("corper", "NYSC Corps member"),
    ("other", "Other"),
]

PVC_CHOICES = [
    ("yes", "Yes, I have my PVC"),
    ("registered", "Registered, yet to collect"),
    ("no", "Not yet registered"),
]

INTEREST_CHOICES = [
    ("ward_coordinator", "Ward coordination / door-to-door mobilization"),
    ("voter_education", "Political & voter education"),
    ("digital_media", "Digital media & social media"),
    ("publicity", "Publicity, radio & press"),
    ("students", "Students’ mobilization"),
    ("women", "Women mobilization & gender affairs"),
    ("pwd", "Inclusion of persons with disabilities (PWDs)"),
    ("welfare_logistics", "Welfare & logistics"),
    ("election_duty", "Election duty (INEC ad hoc staff, agent or observer)"),
    ("situation_room", "Situation room / data & results monitoring"),
    ("general", "General member / wherever needed"),
]
INTEREST_LABELS = dict(INTEREST_CHOICES)

phone_validator = RegexValidator(
    regex=r"^\+?[0-9]{10,15}$",
    message="Enter a valid phone number using digits only (e.g. 08012345678).",
)


class StoredFile(models.Model):
    """An uploaded file kept in the database (see core/storage.py)."""

    name = models.CharField(max_length=255, unique=True)
    data = models.BinaryField()
    content_type = models.CharField(max_length=100, default="application/octet-stream")
    size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Stored file"

    def __str__(self):
        return self.name


class SiteSettings(models.Model):
    """Single row holding editable site-wide media (e.g. the hero photo)."""

    hero_image = models.ImageField(
        "Hero image",
        upload_to="hero/",
        blank=True,
        help_text="Portrait photo of Malam Nasiru Bala Ja'oji shown on the home page. "
        "A tall/portrait image (about 4:5) works best.",
    )
    hero_caption = models.CharField(
        max_length=120,
        blank=True,
        default="MNBJYN Kano State",
        help_text="Short caption displayed under the hero image.",
    )

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce a single row
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # never delete the singleton
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class GalleryImage(models.Model):
    image = models.ImageField(upload_to="gallery/")
    caption = models.CharField(max_length=160, blank=True)
    event_date = models.DateField(null=True, blank=True)
    is_published = models.BooleanField(default=True)
    order = models.PositiveIntegerField(
        default=0, help_text="Lower numbers appear first."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "Gallery photo"
        verbose_name_plural = "Gallery photos"

    def __str__(self):
        return self.caption or f"Photo #{self.pk}"


class Person(models.Model):
    """Shared fields for people shown on the public site."""

    name = models.CharField(max_length=120, help_text="Full name, e.g. Aminu Musa Ibrahim")
    subname = models.CharField(
        "Sub-name / title", max_length=160, blank=True,
        help_text="Shown under the name, e.g. Zonal Chairman.",
    )
    image = models.ImageField(
        "Photo", upload_to="people/", blank=True,
        help_text="Portrait or square photo. Large photos are resized automatically.",
    )
    order = models.PositiveIntegerField(default=0, help_text="Lower numbers appear first.")
    is_published = models.BooleanField("Show on website", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["order", "id"]

    def __str__(self):
        return self.name

    @property
    def initials(self):
        parts = [p for p in self.name.split() if p]
        return "".join(p[0] for p in parts[:2]).upper()


class Executive(Person):
    class Meta(Person.Meta):
        verbose_name = "Executive"
        verbose_name_plural = "Executives"


class TeamMember(Person):
    class Meta(Person.Meta):
        verbose_name = "Team member"
        verbose_name_plural = "Team members"


class Registration(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        REVIEWED = "reviewed", "Reviewed"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    full_name = models.CharField(max_length=150)
    gender = models.CharField(max_length=10, choices=GENDER_CHOICES)
    age_range = models.CharField("Age range", max_length=10, choices=AGE_CHOICES)
    phone = models.CharField(
        max_length=16, unique=True, validators=[phone_validator],
        help_text="Used to prevent duplicate sign-ups.",
    )
    email = models.EmailField(blank=True)

    lga = models.CharField("Local Government Area", max_length=20, choices=LGA_CHOICES)
    ward = models.CharField(max_length=120, blank=True)
    community = models.CharField("Town / community", max_length=150, blank=True)

    occupation_status = models.CharField(
        "Current status", max_length=20, choices=STATUS_CHOICES
    )
    institution_or_workplace = models.CharField(
        "Institution / workplace", max_length=150, blank=True
    )
    has_disability = models.BooleanField("Person living with disability", default=False)

    pvc_status = models.CharField("PVC status", max_length=12, choices=PVC_CHOICES)
    interests = models.CharField(
        max_length=400, blank=True, help_text="Comma-separated interest keys."
    )
    message = models.TextField(blank=True)
    consent = models.BooleanField(default=False)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.NEW, db_index=True
    )
    admin_notes = models.TextField("Internal notes", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Registration"
        verbose_name_plural = "Registrations"

    def __str__(self):
        return f"{self.full_name} ({self.get_lga_display()})"

    @property
    def interest_list(self):
        return [
            INTEREST_LABELS.get(k, k) for k in self.interests.split(",") if k
        ]

    @property
    def reference(self):
        return f"MNBJYN-{self.pk:05d}"


# ===========================================================================
# Election-day results: polling units, result agents, submissions
# (used by the REST API in core/api/ and by the Situation Room "live" mode)
# ===========================================================================
import hashlib

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from .lga_data import LGA_NAMES


class Election(models.Model):
    """An election whose results are being collected."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=60, unique=True)
    election_date = models.DateField(null=True, blank=True)
    is_current = models.BooleanField(
        default=False,
        help_text="The election agents report on and the Situation Room shows. Only one can be current.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.is_current:
            Election.objects.exclude(pk=self.pk).filter(is_current=True).update(is_current=False)

    @classmethod
    def current(cls):
        return cls.objects.filter(is_current=True).first()


class Candidate(models.Model):
    """A candidate / party column on the result sheet."""

    election = models.ForeignKey(Election, on_delete=models.CASCADE, related_name="candidates")
    name = models.CharField(max_length=120)
    short_name = models.CharField(max_length=12, help_text="Short label, e.g. APC, PDP, MNBJ.")
    color = models.CharField(max_length=7, default="#FFFFFF", help_text="Hex colour, e.g. #14B8A6.")
    order = models.PositiveSmallIntegerField(default=0, help_text="Lower numbers appear first.")

    class Meta:
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["election", "short_name"], name="uniq_candidate_short_per_election"),
        ]

    def __str__(self):
        return f"{self.short_name} – {self.name}"


class SituationRoomConfig(models.Model):
    """Single row controlling what the home-page Situation Room shows."""

    class Mode(models.TextChoices):
        LIVE = "live", "Live (real results from agents)"

    mode = models.CharField(max_length=12, choices=Mode.choices, default=Mode.LIVE)
    publish_unverified = models.BooleanField(
        "Show results before a supervisor verifies them",
        default=True,
        help_text="If off, only results a supervisor has verified appear on the Situation Room.",
    )
    refresh_seconds = models.PositiveSmallIntegerField(
        default=10, help_text="How often the page asks for new results (5 to 120 seconds).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Situation Room setting"
        verbose_name_plural = "Situation Room settings"

    def __str__(self):
        return f"Situation Room: {self.get_mode_display()}"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.refresh_seconds = max(5, min(120, self.refresh_seconds or 10))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Ward(models.Model):
    """Editable ward catalog; ward_index remains stable for polling-unit codes."""

    lga = models.CharField(max_length=20, choices=WARD_LGA_CHOICES, db_index=True)
    ward_index = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=120)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["lga", "sort_order", "ward_index"]
        constraints = [
            models.UniqueConstraint(fields=["lga", "ward_index"], name="uniq_ward_index_per_lga"),
        ]

    def __str__(self):
        return f"{self.name} · {self.lga_name}"

    @property
    def lga_name(self):
        return LGA_NAMES.get(self.lga, self.lga)

    def save(self, *args, **kwargs):
        if self.pk:
            previous_name = Ward.objects.filter(pk=self.pk).values_list("name", flat=True).first()
            if previous_name is not None and previous_name != self.name:
                super().save(*args, **kwargs)
                PollingUnit.objects.filter(ward_record_id=self.pk).update(ward_name=self.name)
                return
        super().save(*args, **kwargs)


class PollingUnit(models.Model):
    """One INEC polling unit, belonging to a ward of an LGA (see core/lga_data.py)."""

    lga = models.CharField("LGA key", max_length=20, db_index=True)
    ward_index = models.PositiveSmallIntegerField(help_text="Stable ward code index (0-based).")
    ward_name = models.CharField(max_length=120)
    ward_record = models.ForeignKey(
        Ward, on_delete=models.PROTECT, related_name="polling_units",
        null=True, blank=False,
    )
    number = models.PositiveSmallIntegerField(help_text="Polling unit number inside the ward, e.g. 7.")
    code = models.CharField(max_length=20, unique=True, help_text="INEC style code, e.g. 20/21/03/007.")
    name = models.CharField(max_length=200, blank=True, help_text="Location name, e.g. Primary School, Majidadi.")
    registered_voters = models.PositiveIntegerField(default=0)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["lga", "ward_index", "number"]
        constraints = [
            models.UniqueConstraint(fields=["lga", "ward_index", "number"], name="uniq_pu_number_per_ward"),
        ]
        indexes = [models.Index(fields=["lga", "ward_index"], name="core_pu_lga_ward_idx")]

    def __str__(self):
        return f"{self.code} · {self.name or self.ward_name}"

    @property
    def lga_name(self):
        return LGA_NAMES.get(self.lga, self.lga)

    @property
    def display_name(self):
        return self.name or f"Polling Unit {self.number:03d}"


class ResultAgent(models.Model):
    """A person who uses the results app (polling-unit agent, supervisor or admin)."""

    class Role(models.TextChoices):
        AGENT = "agent", "Polling-unit agent"
        SUPERVISOR = "supervisor", "Collation supervisor"
        ADMIN = "admin", "Results administrator"

    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=16, unique=True, validators=[phone_validator])
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.AGENT)
    pin_hash = models.CharField(max_length=256, blank=True)
    must_change_pin = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    lga_scope = models.CharField(
        "Supervisor LGA", max_length=20, blank=True,
        help_text="Supervisors only: limit them to one LGA (key, e.g. kano_municipal). Blank = whole state.",
    )
    polling_units = models.ManyToManyField(PollingUnit, blank=True, related_name="agents")
    failed_logins = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]
        verbose_name = "Result agent"

    def __str__(self):
        return f"{self.full_name} ({self.get_role_display()})"

    def set_pin(self, raw_pin):
        self.pin_hash = make_password(raw_pin)

    def check_pin(self, raw_pin):
        return bool(self.pin_hash) and check_password(raw_pin, self.pin_hash)

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    @property
    def public_name(self):
        """'Aminu M.' - the form of the name shown on the public Situation Room."""
        parts = self.full_name.split()
        if not parts:
            return "Agent"
        return parts[0] if len(parts) == 1 else f"{parts[0]} {parts[-1][0]}."


class ApiToken(models.Model):
    """A login session of the app. Only the SHA-256 of the token is stored."""

    agent = models.ForeignKey(ResultAgent, on_delete=models.CASCADE, related_name="tokens")
    key_hash = models.CharField(max_length=64, unique=True)
    prefix = models.CharField(max_length=8)
    device_name = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.prefix}… ({self.agent_id})"

    @staticmethod
    def hash_key(raw):
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @property
    def is_valid(self):
        return self.revoked_at is None and self.expires_at > timezone.now()


class ResultSubmission(models.Model):
    """One polling-unit result sheet. Rows are never edited: a correction is a new row."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Submitted"
        VERIFIED = "verified", "Verified"
        FLAGGED = "flagged", "Flagged (needs review)"
        DISPUTED = "disputed", "Disputed"
        REJECTED = "rejected", "Rejected"
        SUPERSEDED = "superseded", "Superseded by a newer submission"

    submission_id = models.UUIDField(unique=True, help_text="Generated by the app; makes retries safe.")
    election = models.ForeignKey(Election, on_delete=models.PROTECT, related_name="submissions")
    polling_unit = models.ForeignKey(PollingUnit, on_delete=models.PROTECT, related_name="submissions")
    agent = models.ForeignKey(ResultAgent, on_delete=models.PROTECT, related_name="submissions")

    registered_voters = models.PositiveIntegerField()
    accredited_voters = models.PositiveIntegerField()
    rejected_votes = models.PositiveIntegerField()
    valid_votes = models.PositiveIntegerField()
    votes = models.JSONField(default=dict, help_text='{"<candidate id>": votes}')

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    is_current = models.BooleanField(default=True, db_index=True)
    flags = models.JSONField(default=list, blank=True)
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        ResultAgent, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    client_time = models.DateTimeField(null=True, blank=True)
    payload_hash = models.CharField(max_length=64)
    sheet_name = models.CharField(max_length=255, blank=True, help_text="Photo of the signed result sheet.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["election", "polling_unit"],
                condition=models.Q(is_current=True),
                name="uniq_current_result_per_pu",
            ),
        ]
        indexes = [models.Index(fields=["election", "updated_at"], name="core_sub_elec_upd_idx")]

    def __str__(self):
        return f"{self.polling_unit.code} · {self.get_status_display()}"


class AuditLog(models.Model):
    """Who did what, when, from where. Append-only."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(ResultAgent, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=40, db_index=True)
    target = models.CharField(max_length=120, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} {self.target}"
