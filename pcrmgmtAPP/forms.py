from django import forms
from .models import UserProfile
from django.contrib.auth.models import User
from .models import Garantie

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
        """Override to ensure the password is properly hashed."""
        user = super().save(commit=False)
        raw_password = self.cleaned_data["password"]
        user.set_password(raw_password)  # <--- crucial!
        if commit:
            user.save()
        return user


    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match")

class SettingsForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['theme']  # Nur das Theme-Feld bleibt übrig
        widgets = {
            'theme': forms.Select(attrs={'id': 'theme', 'class': 'form-select'}),
        }

class GarantieForm(forms.ModelForm):
    class Meta:
        model = Garantie
        fields = ['vorname', 'nachname', 'firma', 'email', 'startdatum', 'ablaufdatum', 'seriennummer', 'typ', 'kommentar']
        widgets = {
            'startdatum': forms.DateInput(attrs={'type': 'date'}),
            'ablaufdatum': forms.DateInput(attrs={'type': 'date'}),
        }