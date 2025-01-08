from django.contrib import admin
from .models import UserProfile

@admin.register(UserProfile)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ['theme']  # Nur das Theme-Feld bleibt übrig
