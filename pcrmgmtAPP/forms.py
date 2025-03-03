# pcrmgmtAPP/forms.py

from django import forms
from django.contrib.auth.models import User
from django.forms.widgets import DateTimeInput
from .models import (
    UserProfile,
    Garantie,
    MaintenanceConfig,
    MaintenanceTask,
    MaintenanceLog,
    FREQUENCY_CHOICES,
)

class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    confirm_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        raw_password = self.cleaned_data["password"]
        user.set_password(raw_password)
        if commit:
            user.save()
        return user

class SettingsForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['theme']
        widgets = {
            'theme': forms.Select(attrs={'id': 'theme', 'class': 'form-select'}),
        }

class GarantieForm(forms.ModelForm):
    class Meta:
        model = Garantie
        fields = [
            'vorname', 'nachname', 'firma', 'email',
            'startdatum', 'ablaufdatum', 'seriennummer',
            'typ', 'kommentar'
        ]
        widgets = {
            'startdatum': forms.DateInput(attrs={'type': 'date'}),
            'ablaufdatum': forms.DateInput(attrs={'type': 'date'}),
        }

#
# Maintenance Forms
#
class MaintenanceConfigForm(forms.ModelForm):
    next_due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control',
                'placeholder': 'yyyy-mm-dd'
            },
            format='%Y-%m-%d'
        )
    )

    class Meta:
        model = MaintenanceConfig
        fields = [
            'customer_firma', 'customer_vorname', 'customer_nachname',
            'customer_strasse', 'customer_plz', 'customer_ort',
            'frequency', 'next_due_date', 'notes'
        ]

class MaintenanceTaskForm(forms.ModelForm):
    class Meta:
        model = MaintenanceTask
        fields = ['assigned_to', 'status', 'duration_minutes', 'due_date']

class MaintenanceLogForm(forms.ModelForm):
    class Meta:
        model = MaintenanceLog
        fields = ['sub_check_name', 'description', 'is_done', 'screenshot']

class MaintenanceFullForm(forms.ModelForm):
    start_date = forms.DateTimeField(
        widget=DateTimeInput(attrs={'type': 'datetime-local'}),
        label="Startdatum"
    )
    # Checkboxen für die Sub-Checks:
    eventlogs_check = forms.BooleanField(required=False, label="Eventlogs check")
    windows_updates_check = forms.BooleanField(required=False, label="Windows Updates check")
    backup_check = forms.BooleanField(required=False, label="Backup check")
    serverstorage_check = forms.BooleanField(required=False, label="Serverstorage check")
    backupstorage_check = forms.BooleanField(required=False, label="Backupstorage check inkl. Systemupdates")
    filesystem_cleanup_check = forms.BooleanField(required=False, label="Filesystem cleanup durchführen")
    security_check = forms.BooleanField(required=False, label="Security check")
    firewall_check = forms.BooleanField(required=False, label="Firewall check")

    class Meta:
        model = MaintenanceConfig
        fields = [
            'customer_firma',
            'customer_vorname',
            'customer_nachname',
            'customer_strasse',
            'customer_plz',
            'customer_ort',
            'frequency',
            # Den Field "notes" lassen wir außen vor – somit wird er nicht gerendert.
        ]