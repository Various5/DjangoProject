# pcrmgmtAPP/models.py

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password
from ckeditor_uploader.fields import RichTextUploadingField  # CHANGED for image upload


FREQUENCY_CHOICES = [
    ('weekly', 'Weekly'),
    ('monthly', 'Monthly'),
    ('2months', 'Every 2 Months'),
]

class OfficeAccount(models.Model):
    id = models.AutoField(primary_key=True)
    vorname = models.CharField(max_length=100)
    nachname = models.CharField(max_length=100)
    firma = models.CharField(max_length=100)
    email = models.CharField(max_length=100)
    passwort = models.CharField(max_length=255)
    kommentar = models.CharField(max_length=255, null=True, blank=True)
    erstelldatum = models.DateTimeField()

    class Meta:
        db_table = 'office_accounts'
        managed = False  # external table

    def __str__(self):
        return f"{self.vorname} {self.nachname}"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    theme = models.CharField(
        max_length=20,
        choices=[
            ('light', 'Light'),
            ('dark', 'Dark'),
            ('modern', 'Modern'),
            ('soft-blue', 'Soft Blue'),
            ('soft-green', 'Soft Green'),
            ('vintage', 'Vintage'),
            ('high-contrast', 'High Contrast'),
            ('elegant', 'Elegant'),
            ('sunset', 'Sunset'),
            ('neon', 'Neon'),
            ('pastel', 'Pastel'),
        ],
        default='dark'
    )

    def __str__(self):
        return f"{self.user.username}'s Profile"

class Garantie(models.Model):
    TYP_CHOICES = [
        ('garantie', 'Garantie'),
        ('lizenz', 'Lizenz'),
    ]
    vorname = models.CharField(max_length=100)
    nachname = models.CharField(max_length=100)
    firma = models.CharField(max_length=100)
    email = models.EmailField()
    startdatum = models.DateField()
    ablaufdatum = models.DateField()
    seriennummer = models.CharField(max_length=100, unique=True)
    typ = models.CharField(max_length=20, choices=TYP_CHOICES, default='garantie')
    kommentar = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"{self.typ.capitalize()}: {self.vorname} {self.nachname} - {self.seriennummer}"

class RMATicket(models.Model):
    ticketnummer = models.CharField(max_length=100, unique=True)
    firma = models.CharField(max_length=255, blank=True, null=True)
    modell = models.CharField(max_length=255, blank=True, null=True)
    seriennummer = models.CharField(max_length=255, blank=True, null=True)
    fehler = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    abgeschlossen = models.BooleanField(default=False)
    category = models.CharField(max_length=50, choices=[('general', 'General'), ('computacenter', 'Computacenter')])

    class Meta:
        db_table = 'tickets'
        managed = False

    def __str__(self):
        return f"{self.ticketnummer}"

class LicenseKey(models.Model):
    lizenz_schluessel = models.CharField(max_length=255, unique=True)
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return self.lizenz_schluessel

class GDataAccount(models.Model):
    lizenz_schluessel = models.ForeignKey(LicenseKey, on_delete=models.PROTECT, null=True, blank=True)
    datum = models.DateField(auto_now_add=True)
    initialen = models.CharField(max_length=150)
    firma = models.CharField(max_length=255)
    nachname = models.CharField(max_length=255)
    vorname = models.CharField(max_length=255)
    strasse = models.CharField(max_length=255)
    plz = models.CharField(max_length=20)
    ort = models.CharField(max_length=100)
    benutzername = models.CharField(max_length=150, unique=True)
    passwort = models.CharField(max_length=255)
    email = models.EmailField(max_length=254, blank=True, null=True)
    auftrag_typ = models.CharField(max_length=20, choices=[
        ('1_jahr', '1 Jahr'),
        ('2_jahre', '2 Jahre'),
        ('3_jahre', '3 Jahre'),
    ], default='1_jahr')
    kommentar = models.TextField(blank=True, null=True)

    email_sent = models.BooleanField(default=False)
    email_sent_timestamp = models.DateTimeField(null=True, blank=True)
    expiration_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'gdata_accounts'
        managed = True

    def __str__(self):
        return f"GData {self.benutzername}"

    @property
    def days_left(self):
        if self.expiration_date:
            return (self.expiration_date - timezone.now().date()).days
        return None

    def save(self, *args, **kwargs):
        if self.pk:
            existing = GDataAccount.objects.get(pk=self.pk)
            if existing.passwort != self.passwort:
                self.passwort = make_password(self.passwort)
        else:
            self.passwort = make_password(self.passwort)

        if not self.expiration_date:
            if self.auftrag_typ == '1_jahr':
                self.expiration_date = self.datum + timezone.timedelta(days=365)
            elif self.auftrag_typ == '2_jahre':
                self.expiration_date = self.datum + timezone.timedelta(days=365 * 2)
            elif self.auftrag_typ == '3_jahre':
                self.expiration_date = self.datum + timezone.timedelta(days=365 * 3)

        super().save(*args, **kwargs)

    def check_password(self, raw_password):
        return check_password(raw_password, self.passwort)


#
# ================== MAINTENANCE MODELS ==================
#

class MaintenanceConfig(models.Model):
    customer_firma = models.CharField(max_length=255)
    customer_vorname = models.CharField(max_length=255, blank=True)
    customer_nachname = models.CharField(max_length=255, blank=True)
    customer_strasse = models.CharField(max_length=255, blank=True)
    customer_plz = models.CharField(max_length=20, blank=True)
    customer_ort = models.CharField(max_length=100, blank=True)

    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='monthly')
    # Neu hinzugefügt, damit Formular und Template funktionieren:
    next_due_date = models.DateField(null=True, blank=True)

    notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name='created_maint_configs'
    )

    def __str__(self):
        return f"{self.customer_firma} ({self.get_frequency_display()})"

    def get_days_delta(self):
        """
        Falls du weiterhin mit reinen Tagen rechnen willst.
        Wird in manchen Stellen verwendet, kann aber durch relativedelta ersetzt werden.
        """
        if self.frequency == 'weekly':
            return 7
        elif self.frequency == '2months':
            return 60
        # Default: monthly => 30 Tage
        return 30


class MaintenanceTask(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('claimed', 'Claimed'),
        ('done', 'Done'),
    ]

    config = models.ForeignKey(MaintenanceConfig, on_delete=models.CASCADE, related_name='tasks')
    due_date = models.DateTimeField()
    assigned_to = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='maintenance_tasks'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    claimed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Task #{self.id} for {self.config.customer_firma} ({self.due_date.date()})"

    def create_default_checkpoints(self):
        """
        Erstellt Standard-Sub-Checks im Log, z.B. Backup prüfen, etc.
        """
        from .models import MaintenanceLog
        default_checkpoints = [
            "Backup überprüfen",
            "Server Status checken",
            "NAS-Backup checken",
            "Dateisystem aufräumen",
            "Firmwareupdates",
            "Virensoftware prüfen",
        ]
        for cp in default_checkpoints:
            MaintenanceLog.objects.create(
                task=self,
                sub_check_name=cp,
                description="",
                is_done=False
            )

class MaintenanceLog(models.Model):
    task = models.ForeignKey(MaintenanceTask, on_delete=models.CASCADE, related_name='logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    sub_check_name = models.CharField(max_length=200, blank=True)
    description = RichTextUploadingField(blank=True)  # oder TextField
    is_done = models.BooleanField(default=False)
    screenshot = models.FileField(upload_to='maintenance_screenshots/', null=True, blank=True)

    def __str__(self):
        return f"Log {self.sub_check_name} (Task #{self.task.id})"
