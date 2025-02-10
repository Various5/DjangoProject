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
    # Definiere das Startdatum als zusätzliches Feld,
    # z. B. mit einem datetime-local Widget
    start_date = forms.DateTimeField(
        widget=DateTimeInput(attrs={'type': 'datetime-local'}),
        label="Startdatum"
    )

    class Meta:
        model = MaintenanceConfig
        # Entferne "start_date" aus den Meta‑fields, da es nicht im Model existiert
        fields = [
            'customer_firma',
            'customer_vorname',
            'customer_nachname',
            'customer_strasse',
            'customer_plz',
            'customer_ort',
            'frequency',
            'notes'
        ]

    def save(self, commit=True):
        # Speichere zuerst das Config-Objekt, ohne start_date, da dieses nicht im Model ist
        config = super().save(commit=False)
        # Hier kannst Du optional zusätzliche Logik einbauen,
        # z. B. das Fälligkeitsdatum (next_due_date) basierend auf dem start_date und der Frequenz berechnen.
        start_date = self.cleaned_data.get('start_date')
        frequency = self.cleaned_data.get('frequency')

        # Beispiel: Automatische Berechnung von next_due_date
        if start_date:
            if frequency == 'weekly':
                # Fälligkeitsdatum = Startdatum + 6 Tage (bei Start am Montag = Sonntag)
                config.next_due_date = start_date.date() + forms.fields.timedelta(days=6)
            elif frequency == 'monthly':
                # Fälligkeitsdatum = letzter Tag des Monats, in dem start_date liegt
                import calendar
                last_day = calendar.monthrange(start_date.year, start_date.month)[1]
                config.next_due_date = start_date.replace(day=last_day).date()
            elif frequency == '2months':
                # Beispiel für 2-monatlich: 2 Monate hinzufügen und letzten Tag des Zielmonats setzen
                from dateutil.relativedelta import relativedelta
                new_date = start_date + relativedelta(months=2)
                import calendar
                last_day = calendar.monthrange(new_date.year, new_date.month)[1]
                config.next_due_date = new_date.replace(day=last_day).date()

        if commit:
            config.save()
        return config