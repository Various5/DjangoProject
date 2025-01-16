# pcrmgmtAPP/models.py

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.contrib.auth.hashers import make_password, check_password


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
        db_table = 'office_accounts'  # Exact existing table name
        managed = False  # Django does not manage this table

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
        db_table = 'tickets'  # Exact existing table name
        managed = False  # Django does not manage this table


class LicenseKey(models.Model):
    lizenz_schluessel = models.CharField(max_length=255, unique=True)
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return self.lizenz_schluessel

class GDataAccount(models.Model):
    lizenz_schluessel = models.ForeignKey(LicenseKey, on_delete=models.PROTECT, null=True, blank=True)
    datum = models.DateField(auto_now_add=True)  # Date Created
    initialen = models.CharField(max_length=150)  # Username
    firma = models.CharField(max_length=255)
    nachname = models.CharField(max_length=255)
    vorname = models.CharField(max_length=255)
    strasse = models.CharField(max_length=255)
    plz = models.CharField(max_length=20)
    ort = models.CharField(max_length=100)
    benutzername = models.CharField(max_length=150, unique=True)
    passwort = models.CharField(max_length=255)  # Will be hashed in the save method
    email = models.EmailField(max_length=254, blank=True, null=True)
    auftrag_typ = models.CharField(max_length=20, choices=[
        ('1_jahr', '1 Jahr'),
        ('2_jahre', '2 Jahre'),
        ('3_jahre', '3 Jahre'),
    ], default='1_jahr')
    kommentar = models.TextField(blank=True, null=True)

    # New fields
    email_sent = models.BooleanField(default=False)
    email_sent_timestamp = models.DateTimeField(null=True, blank=True)

    # New field for expiration date
    expiration_date = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'gdata_accounts'  # Specify custom table name
        managed = True  # Django manages this table

    @property
    def days_left(self):
        """Calculate days left until expiration."""
        if self.expiration_date:
            return (self.expiration_date - timezone.now().date()).days
        return None

    def save(self, *args, **kwargs):
        # Hash the password before saving
        if not self.pk or GDataAccount.objects.get(pk=self.pk).passwort != self.passwort:
            self.passwort = make_password(self.passwort)

        # Set expiration_date based on auftrag_typ if not set
        if not self.expiration_date:
            if self.auftrag_typ == '1_jahr':
                self.expiration_date = self.datum + timezone.timedelta(days=365)
            elif self.auftrag_typ == '2_jahre':
                self.expiration_date = self.datum + timezone.timedelta(days=365*2)
            elif self.auftrag_typ == '3_jahre':
                self.expiration_date = self.datum + timezone.timedelta(days=365*3)

        super().save(*args, **kwargs)

    def check_password(self, raw_password):
        return check_password(raw_password, self.passwort)
