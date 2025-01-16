# pcrmgmtAPP/management/commands/import_gdata_accounts.py

from django.core.management.base import BaseCommand
from pcrmgmtAPP.models import GDataAccount, LicenseKey
import csv

class Command(BaseCommand):
    help = 'Import GData Accounts from a CSV file.'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to the CSV file.')

    def handle(self, *args, **kwargs):
        csv_file = kwargs['csv_file']
        try:
            with open(csv_file, newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    lizenz_schluessel = row['Lizenzschlüssel'].strip()
                    # Ensure the license key exists and is not used
                    license_key, created = LicenseKey.objects.get_or_create(lizenz_schluessel=lizenz_schluessel)
                    if not license_key.is_used:
                        try:
                            account = GDataAccount.objects.create(
                                lizenz_schluessel=license_key,
                                initialen=row['Initialen'].strip(),
                                firma=row['Firma'].strip(),
                                nachname=row['Nachname'].strip(),
                                vorname=row['Vorname'].strip(),
                                strasse=row['Strasse'].strip(),
                                plz=row['PLZ'].strip(),
                                ort=row['Ort'].strip(),
                                benutzername=row['Benutzername'].strip(),
                                passwort=row['Passwort'].strip(),  # Ensure password is hashed
                                auftrag_typ=row['Auftrag_typ'].strip(),
                                kommentar=row['Kommentar'].strip(),
                            )
                            license_key.is_used = True
                            license_key.save()
                            self.stdout.write(self.style.SUCCESS(f"Imported account: {account.benutzername}"))
                        except IntegrityError:
                            self.stdout.write(self.style.WARNING(f"Benutzername '{row['Benutzername']}' bereits vergeben."))
                        except Exception as e:
                            self.stdout.write(self.style.ERROR(f"Fehler beim Importieren von {row['Benutzername']}: {e}"))
                    else:
                        self.stdout.write(self.style.WARNING(f"Lizenzschlüssel '{lizenz_schluessel}' ist bereits verwendet."))
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"Datei '{csv_file}' nicht gefunden."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Fehler beim Lesen der Datei: {e}"))
