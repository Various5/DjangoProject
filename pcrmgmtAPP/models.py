from django.db import models
from django.contrib.auth.models import User

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
        db_table = 'office_accounts'  # Explicit table name
        managed = False

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
        db_table = 'tickets'  # <--- The EXACT name of your existing table
        managed = False       # <--- Don’t let Django create/modify it