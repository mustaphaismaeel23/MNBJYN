"""Polling units, result agents, API tokens, result submissions, Situation Room mode."""
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def seed_defaults(apps, schema_editor):
    """Create a starter election (edit it in /admin) and the Situation Room settings row."""
    Election = apps.get_model("core", "Election")
    Candidate = apps.get_model("core", "Candidate")
    Config = apps.get_model("core", "SituationRoomConfig")

    Config.objects.get_or_create(pk=1)
    if Election.objects.exists():
        return
    election = Election.objects.create(
        name="2027 Governorship – Kano State", slug="kano-gov-2027", is_current=True,
    )
    for order, (name, short, color) in enumerate([
        ("Malam Nasiru Bala Ja'oji", "MNBJ", "#14B8A6"),
        ("Candidate B", "B", "#FFFFFF"),
        ("Candidate C", "C", "#99F6E4"),
        ("Others", "OTH", "#6F86A6"),
    ]):
        Candidate.objects.create(
            election=election, name=name, short_name=short, color=color, order=order,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_people_and_stored_files"),
    ]

    operations = [
        migrations.CreateModel(
            name="Election",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150)),
                ("slug", models.SlugField(max_length=60, unique=True)),
                ("election_date", models.DateField(blank=True, null=True)),
                (
                    "is_current",
                    models.BooleanField(
                        default=False,
                        help_text="The election agents report on and the Situation Room shows. Only one can be current.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="Candidate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                (
                    "short_name",
                    models.CharField(help_text="Short label, e.g. APC, PDP, SSB.", max_length=12),
                ),
                (
                    "color",
                    models.CharField(default="#FFFFFF", help_text="Hex colour, e.g. #14B8A6.", max_length=7),
                ),
                (
                    "order",
                    models.PositiveSmallIntegerField(default=0, help_text="Lower numbers appear first."),
                ),
                (
                    "election",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="candidates",
                        to="core.election",
                    ),
                ),
            ],
            options={"ordering": ["order", "id"]},
        ),
        migrations.AddConstraint(
            model_name="candidate",
            constraint=models.UniqueConstraint(
                fields=("election", "short_name"), name="uniq_candidate_short_per_election"
            ),
        ),
        migrations.CreateModel(
            name="SituationRoomConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "mode",
                    models.CharField(
                        choices=[
                            ("simulation", "Simulation (sample data)"),
                            ("live", "Live (real results from agents)"),
                        ],
                        default="simulation",
                        max_length=12,
                    ),
                ),
                (
                    "publish_unverified",
                    models.BooleanField(
                        default=True,
                        help_text="If off, only results a supervisor has verified appear on the Situation Room.",
                        verbose_name="Show results before a supervisor verifies them",
                    ),
                ),
                (
                    "refresh_seconds",
                    models.PositiveSmallIntegerField(
                        default=10,
                        help_text="How often the page asks for new results (5 to 120 seconds).",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Situation Room setting",
                "verbose_name_plural": "Situation Room settings",
            },
        ),
        migrations.CreateModel(
            name="PollingUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "lga",
                    models.CharField(db_index=True, max_length=20, verbose_name="LGA key"),
                ),
                (
                    "ward_index",
                    models.PositiveSmallIntegerField(
                        help_text="Position of the ward in core/lga_data.py (0-based)."
                    ),
                ),
                ("ward_name", models.CharField(max_length=120)),
                (
                    "number",
                    models.PositiveSmallIntegerField(
                        help_text="Polling unit number inside the ward, e.g. 7."
                    ),
                ),
                (
                    "code",
                    models.CharField(
                        help_text="INEC style code, e.g. 05/02/03/007.", max_length=20, unique=True
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        blank=True,
                        help_text="Location name, e.g. Primary School, Majidadi.",
                        max_length=200,
                    ),
                ),
                ("registered_voters", models.PositiveIntegerField(default=0)),
                ("latitude", models.FloatField(blank=True, null=True)),
                ("longitude", models.FloatField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={"ordering": ["lga", "ward_index", "number"]},
        ),
        migrations.AddConstraint(
            model_name="pollingunit",
            constraint=models.UniqueConstraint(
                fields=("lga", "ward_index", "number"), name="uniq_pu_number_per_ward"
            ),
        ),
        migrations.AddIndex(
            model_name="pollingunit",
            index=models.Index(fields=["lga", "ward_index"], name="core_pu_lga_ward_idx"),
        ),
        migrations.CreateModel(
            name="ResultAgent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=150)),
                (
                    "phone",
                    models.CharField(
                        max_length=16,
                        unique=True,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="Enter a valid phone number using digits only (e.g. 08012345678).",
                                regex="^\\+?[0-9]{10,15}$",
                            )
                        ],
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("agent", "Polling-unit agent"),
                            ("supervisor", "Collation supervisor"),
                            ("admin", "Results administrator"),
                        ],
                        default="agent",
                        max_length=12,
                    ),
                ),
                ("pin_hash", models.CharField(blank=True, max_length=256)),
                ("must_change_pin", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "lga_scope",
                    models.CharField(
                        blank=True,
                        help_text="Supervisors only: limit them to one LGA (key, e.g. bauchi). Blank = whole state.",
                        max_length=20,
                        verbose_name="Supervisor LGA",
                    ),
                ),
                ("failed_logins", models.PositiveSmallIntegerField(default=0)),
                ("locked_until", models.DateTimeField(blank=True, null=True)),
                ("last_login_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "polling_units",
                    models.ManyToManyField(blank=True, related_name="agents", to="core.pollingunit"),
                ),
            ],
            options={"verbose_name": "Result agent", "ordering": ["full_name"]},
        ),
        migrations.CreateModel(
            name="ApiToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key_hash", models.CharField(max_length=64, unique=True)),
                ("prefix", models.CharField(max_length=8)),
                ("device_name", models.CharField(blank=True, max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tokens",
                        to="core.resultagent",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ResultSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "submission_id",
                    models.UUIDField(
                        help_text="Generated by the app; makes retries safe.", unique=True
                    ),
                ),
                ("registered_voters", models.PositiveIntegerField()),
                ("accredited_voters", models.PositiveIntegerField()),
                ("rejected_votes", models.PositiveIntegerField()),
                ("valid_votes", models.PositiveIntegerField()),
                (
                    "votes",
                    models.JSONField(default=dict, help_text='{"<candidate id>": votes}'),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("submitted", "Submitted"),
                            ("verified", "Verified"),
                            ("flagged", "Flagged (needs review)"),
                            ("disputed", "Disputed"),
                            ("rejected", "Rejected"),
                            ("superseded", "Superseded by a newer submission"),
                        ],
                        db_index=True,
                        default="submitted",
                        max_length=12,
                    ),
                ),
                ("is_current", models.BooleanField(db_index=True, default=True)),
                ("flags", models.JSONField(blank=True, default=list)),
                ("review_note", models.TextField(blank=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("latitude", models.FloatField(blank=True, null=True)),
                ("longitude", models.FloatField(blank=True, null=True)),
                ("client_time", models.DateTimeField(blank=True, null=True)),
                ("payload_hash", models.CharField(max_length=64)),
                (
                    "sheet_name",
                    models.CharField(
                        blank=True,
                        help_text="Photo of the signed result sheet.",
                        max_length=255,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submissions",
                        to="core.resultagent",
                    ),
                ),
                (
                    "election",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submissions",
                        to="core.election",
                    ),
                ),
                (
                    "polling_unit",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submissions",
                        to="core.pollingunit",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviews",
                        to="core.resultagent",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="resultsubmission",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_current", True)),
                fields=("election", "polling_unit"),
                name="uniq_current_result_per_pu",
            ),
        ),
        migrations.AddIndex(
            model_name="resultsubmission",
            index=models.Index(fields=["election", "updated_at"], name="core_sub_elec_upd_idx"),
        ),
        migrations.CreateModel(
            name="AuditLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("action", models.CharField(db_index=True, max_length=40)),
                ("target", models.CharField(blank=True, max_length=120)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=255)),
                ("detail", models.JSONField(blank=True, default=dict)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="core.resultagent",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.RunPython(seed_defaults, migrations.RunPython.noop),
    ]
