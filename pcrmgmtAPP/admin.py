from django.contrib import admin
from .models import UserProfile
from .models import LicenseKey, GDataAccount

@admin.register(UserProfile)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ['theme']  # Nur das Theme-Feld bleibt übrig

@admin.register(LicenseKey)
class LicenseKeyAdmin(admin.ModelAdmin):
    list_display = ('lizenz_schluessel', 'is_used')
    search_fields = ('lizenz_schluessel',)

@admin.register(GDataAccount)
class GDataAccountAdmin(admin.ModelAdmin):
    list_display = ('benutzername', 'firma', 'vorname', 'nachname', 'auftrag_typ', 'datum', 'days_left')
    search_fields = ('benutzername', 'firma', 'nachname', 'vorname', 'email')
    list_filter = ('auftrag_typ',)