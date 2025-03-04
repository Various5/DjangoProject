# pcrmgmtAPP/views.py

import io
import os
import threading
import json
import logging
import subprocess
import time as pytime
import calendar

from weasyprint import HTML, CSS
# Wichtig: Wir laden die Klasse datetime, date, time, timedelta
from datetime import datetime, date, time, timedelta


from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader

import pytz
from dateutil.relativedelta import relativedelta
from .models import MaintenanceTask
from django.contrib.auth.models import User
from django.http import (FileResponse, HttpResponse, HttpResponseNotAllowed,
                         JsonResponse)
from django.db import (connection, connections, IntegrityError, transaction)
from django.views.decorators.http import require_GET, require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.auth import login
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.utils.safestring import mark_safe
from django.utils import timezone  # nur für .now(), .localtime(), etc.

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from pcrmgmtProject import settings
from .utils.encryption import decrypt_password, encrypt_password
from .utils.isl_log_reader import main as run_isl_log_reader

from weasyprint import HTML, CSS
from django.template.loader import render_to_string
import tempfile

from .forms import (
    RegisterForm, GarantieForm, MaintenanceConfigForm,
    MaintenanceTaskForm, MaintenanceLogForm, MaintenanceFullForm
)
from .models import (
    OfficeAccount, UserProfile, Garantie, RMATicket,
    GDataAccount, LicenseKey,
    MaintenanceConfig, MaintenanceTask, MaintenanceLog
)

STANDARD_SUB_CHECKS = [
    "Eventlogs check",
    "Windows Updates check",
    "Backup check",
    "Serverstorage check",
    "Backupstorage check inkl. Systemupdates",
    "Filesystem cleanup durchführen",
    "Security check",
    "Firewall check"
]

logger = logging.getLogger(__name__)

script_running = False
script_thread = None
script_start_time = None

CONFIG_PATH = "config.json"
#############################################
# Helper: run script in background
#############################################
def run_script_in_background(default_interval_seconds):
    global script_running, script_start_time
    while script_running:
        # Setze das Startzeitfeld (z. B. als nächster Lauf)
        script_start_time = timezone.now() + timedelta(hours=1)
        logger.info("Starting ISL Log Reader at %s..." % script_start_time)

        try:
            run_isl_log_reader()  # Hier wird die eigentliche Arbeit durchgeführt.
            logger.info("ISL Log Reader completed successfully.")
        except Exception as e:
            logger.error(f"Error in ISL Log Reader: {e}")

        # Lese aktuell das Intervall aus der Konfiguration
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                conf = json.load(f)
            interval_minutes = conf.get("isl_script_interval", default_interval_seconds // 60)
            interval_seconds = interval_minutes * 60
        except Exception as e:
            logger.error(f"Error reading config: {e}")
            interval_seconds = default_interval_seconds  # Fallback

        logger.info(f"Next run in {interval_seconds} seconds.")
        pytime.sleep(interval_seconds)

def start_isl_log_reader():
    global script_running, script_thread
    if not script_running:
        # read config or default
        interval_minutes = 10
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                conf = json.load(f)
                interval_minutes = conf.get("isl_script_interval", 10)
        interval_seconds = interval_minutes * 60

        script_running = True
        # Optionally set next run epoch in config
        next_run = timezone.now() + timezone.timedelta(minutes=interval_minutes)
        # For the front-end countdown
        with open(CONFIG_PATH, "r") as f:
            conf = json.load(f)
        conf["next_isl_run_epoch"] = int(next_run.timestamp())
        with open(CONFIG_PATH, "w") as f:
            json.dump(conf, f, indent=4)

        # Start the background thread
        script_thread = threading.Thread(
            target=run_script_in_background,
            args=(interval_seconds,),
            daemon=True
        )
        script_thread.start()
        logger.info("ISL Log Reader background thread started.")

def stop_isl_log_reader():
    global script_running
    if script_running:
        script_running = False
        logger.info("ISL Log Reader stopped.")

#############################################
# Dashboard
#############################################
@login_required
def dashboard(request):
    return render(request, 'dashboard.html')

#############################################
# Settings + Themes
#############################################
@login_required
def settings_view(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    valid_themes = [
        'light', 'dark', 'modern', 'soft-blue', 'soft-green',
        'vintage', 'high-contrast', 'elegant', 'sunset', 'neon', 'pastel'
    ]

    if request.method == 'POST':
        theme = request.POST.get('theme')
        if theme in valid_themes:
            profile.theme = theme
            profile.save()
            messages.success(request, "Theme updated successfully.")
        else:
            messages.error(request, "Invalid theme selected.")
        return redirect('settings')

    context = {
        'current_theme': profile.theme,
    }
    return render(request, 'settings.html', context)

#############################################
# Tasks view
#############################################
def tasks_view(request):
    # Standardwerte
    config = {
        "isl_script_interval": 10,
        "rma_script_interval": 15,
        "script_running": False,
        "rma_script_running": False,
        "script_start_time": None,
        "rma_script_start_time": None,
        "last_script_success": True,
        "last_rma_success": True,

        # Wichtig: Hier standardmäßig 0 setzen
        "next_isl_run_epoch": 0,
        "next_rma_run_epoch": 0,
    }

    # config.json laden und das Dictionary aktualisieren
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as file:
                loaded = json.load(file)
                config.update(loaded)
        except json.JSONDecodeError as e:
            messages.error(request, f"Error reading config.json: {e}")
            # Falls kaputt, überschreiben wir die Datei mit unseren Defaultwerten:
            with open(CONFIG_PATH, "w", encoding="utf-8") as file:
                json.dump(config, file, indent=4)

    if request.method == "POST":
        if "start_script" in request.POST:
            # ISL Log Reader starten
            config["script_running"] = True

            # Nächsten Run definieren
            interval_minutes = config.get("isl_script_interval", 10)
            next_run = timezone.now() + timezone.timedelta(minutes=interval_minutes)
            config["next_isl_run_epoch"] = int(next_run.timestamp())

            # Hintergrund-Thread starten
            start_isl_log_reader()
            messages.info(request, "Starting ISL Log Reader background thread...")

        elif "stop_script" in request.POST:
            # ISL Log Reader stoppen
            config["script_running"] = False
            stop_isl_log_reader()
            messages.info(request, "Stopping ISL Log Reader background thread...")

        elif "set_interval" in request.POST:
            # Intervall für ISL Reader ändern
            new_interval = request.POST.get("script_interval")
            try:
                config["isl_script_interval"] = int(new_interval)
                messages.success(request, f"ISL Log Reader interval updated to {new_interval} minutes.")
            except ValueError:
                messages.error(request, "Invalid interval for ISL Log Reader.")

        elif "start_rma_script" in request.POST:
            # RMA Script starten (Stub)
            config["rma_script_running"] = True

            # Optional: Nächster RMA-Run
            rma_interval_minutes = config.get("rma_script_interval", 15)
            next_run = timezone.now() + timezone.timedelta(minutes=rma_interval_minutes)
            config["next_rma_run_epoch"] = int(next_run.timestamp())

            messages.info(request, "Starting RMA Email Import script (stub).")

        elif "stop_rma_script" in request.POST:
            config["rma_script_running"] = False
            messages.info(request, "Stopping RMA Email Import script (stub).")

        elif "set_rma_interval" in request.POST:
            new_rma_interval = request.POST.get("rma_script_interval")
            try:
                config["rma_script_interval"] = int(new_rma_interval)
                messages.success(request, f"RMA Email Import interval updated to {new_rma_interval} minutes.")
            except ValueError:
                messages.error(request, "Invalid interval for RMA Email Import.")

        # Abschließend config.json mit aktualisierten Werten speichern
        with open(CONFIG_PATH, "w", encoding="utf-8") as file:
            json.dump(config, file, indent=4)

        return redirect("tasks")

    # Template‐Kontext: Hier **alle** wichtigen Felder, inkl. next_*_epoch
    context = {
        "isl_script_interval": config.get("isl_script_interval"),
        "rma_script_interval": config.get("rma_script_interval"),
        "script_running": config.get("script_running"),
        "rma_script_running": config.get("rma_script_running"),
        "last_script_success": config.get("last_script_success"),
        "last_rma_success": config.get("last_rma_success"),
        "next_isl_run_epoch": config.get("next_isl_run_epoch", 0),
        "next_rma_run_epoch": config.get("next_rma_run_epoch", 0),
    }
    return render(request, "tasks.html", context)


#############################################
# Logs view
#############################################
def logs(request):
    isl_log_file = os.path.join(settings.BASE_DIR, "pcrmgmtAPP", "utils", "logs", "isl_log_reader.log")
    rma_log_file = os.path.join(settings.BASE_DIR, "pcrmgmtAPP", "utils", "logs", "email_import.log")
    isl_log_lines = []
    rma_log_lines = []

    if request.method == "POST":
        if "clear_isl_log" in request.POST:
            open(isl_log_file, 'w').close()
            messages.success(request, "ISL log file cleared successfully.")
        elif "clear_rma_log" in request.POST:
            open(rma_log_file, 'w').close()
            messages.success(request, "RMA log file cleared successfully.")

    try:
        if os.path.exists(isl_log_file):
            with open(isl_log_file, "r", encoding="utf-8") as file:
                isl_log_lines = file.readlines()[-100:]
        if os.path.exists(rma_log_file):
            with open(rma_log_file, "r", encoding="utf-8") as file:
                rma_log_lines = file.readlines()[-100:]
    except Exception as e:
        logger.error(f"Error reading log files: {e}")

    return render(request, 'logs.html', {
        'isl_log_lines': isl_log_lines,
        'rma_log_lines': rma_log_lines,
    })


def clear_log(request):
    if request.method == 'POST':
        try:
            log_file = "isl_log_reader.log"
            if os.path.exists(log_file):
                open(log_file, 'w').close()
                messages.success(request, "Log file cleared successfully.")
            else:
                messages.error(request, "Log file does not exist.")
        except Exception as e:
            logger.error(f"Error clearing log file: {e}")
            messages.error(request, "Failed to clear log file.")
        return redirect('logs')
    else:
        return redirect('logs')

#############################################
# ISL Logs listing
#############################################
def isl_logs(request):
    search_query = request.GET.get('search', '')
    filter_user = request.GET.get('filter_user', '')
    sort_by = request.GET.get('sort_by', 'Startzeit')
    sort_order = request.GET.get('sort_order', 'DESC')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 25))

    log_entries = []
    unique_users = []

    try:
        with connections['isllogs'].cursor() as cursor:
            # fetch distinct users
            cursor.execute("SELECT DISTINCT Benutzer FROM dbo.SessionLog_new")
            unique_users = [row[0] for row in cursor.fetchall()]

            user_filter_clause = "AND Benutzer = %s" if filter_user else ""
            query = f"""
                SELECT SessionID, Startzeit, Dauer, Benutzer, NameFirma, Verrechnet, Memo
                FROM dbo.SessionLog_new
                WHERE (Benutzer LIKE %s OR NameFirma LIKE %s OR Memo LIKE %s)
                {user_filter_clause}
                ORDER BY {sort_by} {sort_order}
            """
            params = [f"%{search_query}%"] * 3
            if filter_user:
                params.append(filter_user)
            cursor.execute(query, params)
            logs = cursor.fetchall()

            for log in logs:
                log_entries.append(log)

    except Exception as e:
        logger.error(f"Error fetching ISL logs: {e}")

    paginator = Paginator(log_entries, per_page)
    try:
        paginated_entries = paginator.get_page(page)
    except:
        paginated_entries = paginator.get_page(1)

    context = {
        'entries': paginated_entries,
        'search_query': search_query,
        'filter_user': filter_user,
        'unique_users': unique_users,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'per_page': per_page,
    }
    return render(request, 'isl_logs.html', context)
def toggle_verrechnet(request, log_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Must be POST"}, status=405)
    try:
        with connections['isllogs'].cursor() as cursor:
            cursor.execute("SELECT Verrechnet FROM dbo.SessionLog_new WHERE SessionID = %s", [log_id])
            current_value = cursor.fetchone()
            if current_value is None:
                return JsonResponse({"success": False, "error": "Log entry not found"}, status=404)
            new_value = not current_value[0]
            cursor.execute("UPDATE dbo.SessionLog_new SET Verrechnet = %s WHERE SessionID = %s",
                           [new_value, log_id])
        return JsonResponse({"success": True, "new_value": new_value})
    except Exception as e:
        logger.error(f"Error toggling Verrechnet for {log_id}: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)
def edit_isl_log(request, log_id):
    log_entry = None
    try:
        with connections['isllogs'].cursor() as cursor:
            cursor.execute("""
                SELECT SessionID, Startzeit, Dauer, Benutzer, NameFirma, Verrechnet, Memo
                FROM dbo.SessionLog_new
                WHERE SessionID = %s
            """, [log_id])
            log_entry = cursor.fetchone()
    except Exception as e:
        logger.error(f"Error fetching ISL log {log_id}: {e}")
        return HttpResponse("Error fetching log", status=500)

    if not log_entry:
        return HttpResponse("Log not found", status=404)

    if request.method == "POST":
        startzeit_str = request.POST.get("startzeit")
        dauer = request.POST.get("dauer")
        benutzer = request.POST.get("benutzer")
        name_firma = request.POST.get("name_firma")
        verrechnet = request.POST.get("verrechnet") in ['True','true','1','yes']
        memo = request.POST.get("memo")

        # parse the datetime-local
        try:
            startzeit_dt = datetime.strptime(startzeit_str, "%Y-%m-%dT%H:%M")
        except ValueError:
            messages.error(request, "Invalid date/time format.")
            return redirect('edit_isl_log', log_id=log_id)

        try:
            with connections['isllogs'].cursor() as cursor:
                cursor.execute("""
                    UPDATE dbo.SessionLog_new
                    SET Startzeit = %s,
                        Dauer = %s,
                        Benutzer = %s,
                        NameFirma = %s,
                        Verrechnet = %s,
                        Memo = %s
                    WHERE SessionID = %s
                """, [startzeit_dt, dauer, benutzer, name_firma, verrechnet, memo, log_id])
            messages.success(request, "Log entry updated successfully.")
            return redirect('isl_logs')
        except Exception as e:
            logger.error(f"Error updating ISL log {log_id}: {e}")
            messages.error(request, "Failed to update log entry.")
            return redirect('edit_isl_log', log_id=log_id)

    return render(request, 'edit_isl_log.html', {'log_entry': log_entry})
def delete_isl_log(request, log_id):
    if request.method == "POST":
        try:
            with connections['isllogs'].cursor() as cursor:
                cursor.execute("DELETE FROM dbo.SessionLog_new WHERE SessionID = %s", [log_id])
            messages.success(request, "Log entry deleted successfully.")
            return redirect('isl_logs')
        except Exception as e:
            logger.error(f"Error deleting ISL log {log_id}: {e}")
            messages.error(request, "Failed to delete log entry.")
            return HttpResponse("Error deleting log", status=500)
    else:
        return redirect('isl_logs')
def print_isl_log(request, log_id):
    log_entry = None
    try:
        with connections['isllogs'].cursor() as cursor:
            cursor.execute("SELECT * FROM dbo.SessionLog_new WHERE SessionID = %s", [log_id])
            log_entry = cursor.fetchone()
    except Exception as e:
        logger.error(f"Error fetching ISL log {log_id} for printing: {e}")
        return HttpResponse("Error fetching log", status=500)
    if not log_entry:
        return HttpResponse("Log not found", status=404)
    return render(request, 'print_isl_log.html', {'log_entry': log_entry})
def download_isl_pdf(request, log_id):
    import io
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    log_entry = None
    try:
        with connections['isllogs'].cursor() as cursor:
            cursor.execute("SELECT * FROM dbo.SessionLog_new WHERE SessionID = %s", [log_id])
            log_entry = cursor.fetchone()
    except Exception as e:
        logger.error(f"Error fetching ISL log {log_id} for PDF: {e}")
        return HttpResponse("Error fetching log", status=500)

    if not log_entry:
        return HttpResponse("Log not found", status=404)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"ISL Log {log_id}")

    pdf.drawString(100, 750, "ISL Log Details")
    pdf.drawString(100, 730, f"SessionID: {log_entry[0]}")
    pdf.drawString(100, 710, f"Startzeit: {log_entry[1]}")
    pdf.drawString(100, 690, f"Dauer: {log_entry[2]}")
    pdf.drawString(100, 670, f"Benutzer: {log_entry[3]}")
    pdf.drawString(100, 650, f"NameFirma: {log_entry[4]}")
    pdf.drawString(100, 630, f"Verrechnet: {'Yes' if log_entry[5] else 'No'}")
    pdf.drawString(100, 610, f"Memo: {log_entry[6] or ''}")

    pdf.save()
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f"ISL_Log_{log_id}.pdf")

#############################################
# Office Accounts
#############################################
def office_accounts(request):
    search_query = request.GET.get('search', '')
    sort_by = request.GET.get('sort', 'vorname')
    order = request.GET.get('order', 'asc')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 25))

    accounts = []
    try:
        with connection.cursor() as cursor:
            allowed_sort = ['id','vorname','nachname','firma','email','passwort','kommentar','erstelldatum']
            if sort_by not in allowed_sort:
                sort_by = 'vorname'
            if order not in ['asc','desc']:
                order = 'asc'

            query = f"""
                SELECT id, vorname, nachname, firma, email, passwort, kommentar, erstelldatum
                FROM dbo.office_accounts
                WHERE vorname LIKE %s OR nachname LIKE %s OR firma LIKE %s OR email LIKE %s
                ORDER BY {sort_by} {order.upper()}
            """
            like_query = f"%{search_query}%"
            cursor.execute(query, [like_query, like_query, like_query, like_query])
            rows = cursor.fetchall()
            cols = [desc[0] for desc in cursor.description]

            for row in rows:
                data = dict(zip(cols, row))
                # Decrypt password
                try:
                    data['passwort'] = decrypt_password(data['passwort']) or "Decryption Failed"
                except:
                    data['passwort'] = "Decryption Failed"
                accounts.append(data)
    except Exception as e:
        logger.error(f"Error fetching office accounts: {e}")
        messages.error(request, "Could not retrieve accounts.")

    # If POST => Add new account
    if request.method == "POST":
        vorname = request.POST.get("vorname")
        nachname = request.POST.get("nachname")
        firma = request.POST.get("firma")
        email = request.POST.get("email")
        password = request.POST.get("password")
        kommentar = request.POST.get("kommentar")

        if not all([vorname, nachname, firma, email, password]):
            messages.error(request, "Please fill in all required fields.")
        else:
            try:
                enc_pw = encrypt_password(password)
                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO dbo.office_accounts
                        (vorname, nachname, firma, email, passwort, kommentar, erstelldatum)
                        VALUES (%s, %s, %s, %s, %s, %s, GETDATE())
                    """, [vorname, nachname, firma, email, enc_pw, kommentar])
                messages.success(request, f"New account for {vorname} {nachname} added.")
                return redirect('office_accounts')
            except Exception as e:
                logger.error(f"Error adding account: {e}")
                messages.error(request, "Could not add account.")

    paginator = Paginator(accounts, per_page)
    paginated_accounts = paginator.get_page(page)

    return render(request, 'office_accounts.html', {
        'accounts': paginated_accounts,
        'search_query': search_query,
        'sort_by': sort_by,
        'order': order,
        'per_page': per_page,
    })

def edit_account(request, account_id):
    if request.method == "POST":
        vorname = request.POST.get("vorname")
        nachname = request.POST.get("nachname")
        firma = request.POST.get("firma")
        email = request.POST.get("email")
        new_pw = request.POST.get("password")
        kommentar = request.POST.get("kommentar")

        if not all([vorname, nachname, firma, email]):
            messages.error(request, "Please fill in all required fields.")
        else:
            try:
                with connection.cursor() as cursor:
                    if new_pw:
                        enc_pw = encrypt_password(new_pw)
                        cursor.execute("""
                            UPDATE dbo.office_accounts
                            SET vorname = %s,
                                nachname = %s,
                                firma = %s,
                                email = %s,
                                passwort = %s,
                                kommentar = %s
                            WHERE id = %s
                        """, [vorname, nachname, firma, email, enc_pw, kommentar, account_id])
                    else:
                        cursor.execute("""
                            UPDATE dbo.office_accounts
                            SET vorname = %s,
                                nachname = %s,
                                firma = %s,
                                email = %s,
                                kommentar = %s
                            WHERE id = %s
                        """, [vorname, nachname, firma, email, kommentar, account_id])
                messages.success(request, "Office account updated successfully.")
                return redirect('office_accounts')
            except Exception as e:
                logger.error(f"Error updating account {account_id}: {e}")
                messages.error(request, "Failed to update office account.")

    account = get_object_or_404(OfficeAccount, id=account_id)
    return render(request, 'office_edit_account.html', {'account': account})

def delete_account(request, account_id):
    if request.method == "POST":
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM dbo.office_accounts WHERE id = %s", [account_id])
            messages.success(request, "Office account deleted successfully.")
            return redirect('office_accounts')
        except Exception as e:
            logger.error(f"Error deleting account {account_id}: {e}")
            messages.error(request, "Failed to delete office account.")
            return HttpResponse("Error", status=500)
    return redirect('office_accounts')

def print_account(request, account_id):
    account = get_object_or_404(OfficeAccount, id=account_id)
    account.passwort = decrypt_password(account.passwort) or "Decryption Failed"
    return render(request, 'office_print_account.html', {'account': account})

def download_pdf(request, account_id):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    import io

    account = get_object_or_404(OfficeAccount, id=account_id)
    account.passwort = decrypt_password(account.passwort) or "Decryption Failed"

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"Office Account {account_id}")

    pdf.drawString(100, 750, "Office Account Details")
    pdf.drawString(100, 730, f"ID: {account.id}")
    pdf.drawString(100, 710, f"Vorname: {account.vorname}")
    pdf.drawString(100, 690, f"Nachname: {account.nachname}")
    pdf.drawString(100, 670, f"Firma: {account.firma}")
    pdf.drawString(100, 650, f"Email: {account.email}")
    pdf.drawString(100, 630, f"Passwort: {account.passwort}")
    pdf.drawString(100, 610, f"Kommentar: {account.kommentar}")
    pdf.drawString(100, 590, f"Erstelldatum: {account.erstelldatum}")

    pdf.save()
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f"OfficeAccount_{account.id}.pdf")



#############################################
# Garantie
#############################################
def garantie_tracker(request):
    return render(request, 'garantie_tracker.html')

@login_required
def garantie_list(request):
    # 1) Sort-Parameter abfragen
    sort_by = request.GET.get('sort', 'vorname')
    order = request.GET.get('order', 'asc')

    # 2) Erlaubte Sortfelder definieren
    allowed_sort = ['vorname', 'nachname', 'firma', 'email', 'startdatum', 'ablaufdatum', 'typ', 'seriennummer']
    if sort_by not in allowed_sort:
        sort_by = 'vorname'
    if order not in ['asc', 'desc']:
        order = 'asc'

    # 3) Queryset
    garantien = Garantie.objects.all()

    # 4) Sortierung anwenden
    if order == 'desc':
        sort_by = '-' + sort_by
    garantien = garantien.order_by(sort_by)

    return render(request, 'garantie_tracker.html', {
        'garantien': garantien,
        'sort_by': sort_by.lstrip('-'),  # ohne '-'
        'order': order,
    })

def garantie_create(request):
    form = GarantieForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Garantie erfolgreich hinzugefügt.")
            return redirect('garantie_list')
    return render(request, 'garantie_form.html', {'form': form, 'garantie': None})

def garantie_update(request, pk):
    garantie = get_object_or_404(Garantie, pk=pk)
    form = GarantieForm(request.POST or None, instance=garantie)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Garantie erfolgreich aktualisiert.")
            return redirect('garantie_list')
    return render(request, 'garantie_form.html', {'form': form, 'garantie': garantie})

def garantie_delete(request, pk):
    garantie = get_object_or_404(Garantie, pk=pk)
    if request.method == 'POST':
        garantie.delete()
        messages.success(request, "Garantie erfolgreich gelöscht.")
        return redirect('garantie_list')
    return render(request, 'garantie_confirm_delete.html', {'garantie': garantie})

#############################################
# RMA Manager
#############################################
def rma_manager_selection(request):
    return render(request, 'rma_manager_selection.html')

def rma_logs(request):
    log_file = os.path.join(settings.BASE_DIR, "pcrmgmtAPP", "utils", "logs", "rma_log_reader.log")
    lines = []
    try:
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-100:]
    except Exception as e:
        logger.error(f"Error reading RMA log: {e}")
    return render(request, 'rma_logs.html', {'log_lines': lines})


def general_rma(request):
    """
    A simpler general_rma view:
    - No extra address fields are passed to RMATicket.objects.create().
    - We only store: ticketnummer, firma, modell, seriennummer, fehler, etc.
    """

    # 1) Query only 'general' category tickets
    tickets = RMATicket.objects.filter(category='general').order_by('-created_at')

    # 2) Optional search
    query = request.GET.get('q', '').strip()
    if query:
        tickets = tickets.filter(
            Q(ticketnummer__icontains=query) |
            Q(firma__icontains=query) |
            Q(modell__icontains=query) |
            Q(seriennummer__icontains=query) |
            Q(fehler__icontains=query)
        )

    # 3) Split into open vs. closed
    open_tickets = tickets.filter(abgeschlossen=False)
    closed_tickets = tickets.filter(abgeschlossen=True)

    # 4) If POST => create a new ticket
    if request.method == "POST":
        ticketnummer = request.POST.get("ticketnummer", "").strip()
        firma = request.POST.get("firma", "").strip()
        geraetebezeichnung = request.POST.get("geraetebezeichnung", "").strip()
        seriennummer = request.POST.get("seriennummer", "").strip()
        fehler = request.POST.get("fehler", "").strip()

        # Possibly read 'auftrag_typ' or 'kommentar', but only if your model actually has them:
        # auftrag_typ = request.POST.get("auftrag_typ", "").strip()
        # kommentar = request.POST.get("kommentar", "").strip()

        if not ticketnummer:
            messages.error(request, "Bitte eine Ticketnummer angeben.")
            return redirect('general_rma')

        # Try to create. If there's a UNIQUE KEY constraint, we catch the IntegrityError
        try:
            RMATicket.objects.create(
                ticketnummer=ticketnummer,
                firma=firma,
                modell=geraetebezeichnung,
                seriennummer=seriennummer,
                fehler=fehler,
                created_at=timezone.now(),
                abgeschlossen=False,
                category='general'
                # Not passing any extra fields that your model doesn't have
            )
            messages.success(request, f"Ticket '{ticketnummer}' wurde erfolgreich angelegt.")
        except IntegrityError as e:
            messages.error(request, f"Ticketnummer '{ticketnummer}' ist bereits vergeben!")

        return redirect('general_rma')

    # 5) Render the template with open/closed tickets
    context = {
        'query': query,
        'open_tickets': open_tickets,
        'closed_tickets': closed_tickets,
    }
    return render(request, 'rma_general.html', context)

def computacenter_rma(request):
    tickets = RMATicket.objects.filter(category='computacenter').order_by('-created_at')
    query = request.GET.get('q', '').strip()
    if query:
        tickets = tickets.filter(
            Q(ticketnummer__icontains=query) |
            Q(firma__icontains=query) |
            Q(modell__icontains=query) |
            Q(seriennummer__icontains=query) |
            Q(fehler__icontains=query)
        )

    open_tickets = tickets.filter(abgeschlossen=False)
    closed_tickets = tickets.filter(abgeschlossen=True)

    if request.method == "POST":
        ticketnummer = request.POST.get("ticketnummer", "").strip()
        firma = request.POST.get("firma", "").strip()
        modell = request.POST.get("modell", "").strip()
        seriennummer = request.POST.get("seriennummer", "").strip()
        fehler = request.POST.get("fehler", "").strip()

        if not ticketnummer:
            messages.error(request, "Bitte Ticketnummer angeben.")
            return redirect('computacenter_rma')

        from django.db import IntegrityError
        try:
            RMATicket.objects.create(
                ticketnummer=ticketnummer,
                firma=firma,
                modell=modell,
                seriennummer=seriennummer,
                fehler=fehler,
                created_at=timezone.now(),
                abgeschlossen=False,
                category='computacenter'
            )
            messages.success(request, f"Ticket '{ticketnummer}' wurde erfolgreich angelegt.")
        except IntegrityError:
            messages.error(request, f"Ticketnummer '{ticketnummer}' ist bereits vergeben!")

        return redirect('computacenter_rma')

    context = {
        'query': query,
        'open_tickets': open_tickets,
        'closed_tickets': closed_tickets,
    }
    return render(request, 'computacenter_rma.html', context)

#############################################
# Ticket actions
#############################################
def close_ticket_view(request, ticket_id):
    try:
        ticket = RMATicket.objects.get(id=ticket_id)
        ticket.abgeschlossen = True
        ticket.save()
    except RMATicket.DoesNotExist:
        pass
    if ticket.category == 'computacenter':
        return redirect('computacenter_rma')
    return redirect('general_rma')

def reopen_ticket_view(request, ticket_id):
    try:
        ticket = RMATicket.objects.get(id=ticket_id)
        ticket.abgeschlossen = False
        ticket.save()
    except RMATicket.DoesNotExist:
        pass
    if ticket.category == 'computacenter':
        return redirect('computacenter_rma')
    return redirect('general_rma')

def edit_ticket(request, ticket_id):
    ticket = get_object_or_404(RMATicket, id=ticket_id)
    if request.method == "POST":
        ticket.ticketnummer = request.POST.get("ticketnummer", ticket.ticketnummer)
        ticket.firma = request.POST.get("firma", ticket.firma)
        ticket.modell = request.POST.get("modell", ticket.modell)
        ticket.seriennummer = request.POST.get("seriennummer", ticket.seriennummer)
        ticket.fehler = request.POST.get("fehler", ticket.fehler)
        ticket.save()
        messages.success(request, "Ticket updated successfully.")
        if ticket.category == 'computacenter':
            return redirect('computacenter_rma')
        return redirect('general_rma')
    return render(request, 'rma_edit_ticket.html', {'ticket': ticket})

def delete_ticket(request, ticket_id):
    ticket = get_object_or_404(RMATicket, id=ticket_id)
    if request.method == "POST":
        ticket.delete()
        messages.success(request, "Ticket deleted successfully.")
        if ticket.category == 'computacenter':
            return redirect('computacenter_rma')
        return redirect('general_rma')
    return render(request, 'rma_confirm_delete.html', {'ticket': ticket})

def print_ticket(request, ticket_id):
    ticket = get_object_or_404(RMATicket, id=ticket_id)
    return render(request, 'rma_print_ticket.html', {'ticket': ticket})

def pdf_ticket(request, ticket_id):
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    import io

    ticket = get_object_or_404(RMATicket, id=ticket_id)

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"Ticket {ticket.ticketnummer}")

    pdf.drawString(100, 750, "Ticket Details")
    pdf.drawString(100, 730, f"Ticketnummer: {ticket.ticketnummer}")
    pdf.drawString(100, 710, f"Firma: {ticket.firma}")
    pdf.drawString(100, 690, f"Modell: {ticket.modell}")
    pdf.drawString(100, 670, f"Seriennummer: {ticket.seriennummer}")
    pdf.drawString(100, 650, f"Fehler: {ticket.fehler}")
    pdf.drawString(100, 630, f"Erstellt am: {ticket.created_at}")
    status_text = "Abgeschlossen" if ticket.abgeschlossen else "Offen"
    pdf.drawString(100, 610, f"Status: {status_text}")

    pdf.save()
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f"Ticket_{ticket.ticketnummer}.pdf")


#############################################
# Registration + Profile
#############################################
def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Registration successful! You are now logged in.")
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})

@login_required
def profile(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    valid_themes = [
        'light','dark','modern','soft-blue','soft-green',
        'vintage','high-contrast','elegant','sunset','neon','pastel'
    ]

    password_form = PasswordChangeForm(user=request.user)
    if request.method == 'POST':
        if 'theme_change' in request.POST:
            theme = request.POST.get('theme')
            if theme in valid_themes:
                profile.theme = theme
                profile.save()
                messages.success(request, "Theme updated successfully.")
            else:
                messages.error(request, "Invalid theme selected.")
        elif 'password_change' in request.POST:
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password changed successfully.")
            else:
                messages.error(request, "Please correct the errors below.")

    context = {
        'user': request.user,
        'profile': profile,
        'themes': valid_themes,
        'password_form': password_form,
    }
    return render(request, 'profile.html', context)

#############################################
# Database status
#############################################
from django.db.utils import OperationalError
def database_status(request):
    databases = ['default','isllogs','address_db']
    status = {}
    for db in databases:
        try:
            c = connections[db]
            c.ensure_connection()
            status[db] = "Connected"
        except OperationalError as e:
            status[db] = f"Disconnected: {str(e)}"
        except KeyError:
            status[db] = "Not Configured"
        except Exception as e:
            status[db] = f"Error: {str(e)}"
    return JsonResponse(status, safe=False)

#############################################
# Gdata Accounts
#############################################
@login_required
def gdata_accounts(request):
    search_query = request.GET.get('search', '').strip()
    per_page = int(request.GET.get('per_page', 25))

    # Auto-fill 'initialen' with the logged-in user's username
    initialen = request.user.username

    if request.method == "POST":
        if 'create_activation' in request.POST:
            # Extract form data
            firma = request.POST.get('firma', '').strip()
            nachname = request.POST.get('nachname', '').strip()
            vorname = request.POST.get('vorname', '').strip()
            strasse = request.POST.get('strasse', '').strip()
            plz = request.POST.get('plz', '').strip()
            ort = request.POST.get('ort', '').strip()
            benutzername = request.POST.get('benutzername', '').strip()
            passwort = request.POST.get('passwort', '').strip()
            auftrag_typ = request.POST.get('auftrag_typ', '').strip()
            kommentar = request.POST.get('kommentar', '').strip()
            email = request.POST.get('email', '').strip()

            with transaction.atomic():
                # Auto-assign an available license key
                try:
                    license_key = LicenseKey.objects.select_for_update().filter(is_used=False).first()
                    if not license_key:
                        messages.error(request, "Keine verfügbaren Lizenzschlüssel.")
                        return redirect('gdata_accounts')
                except LicenseKey.DoesNotExist:
                    messages.error(request, "Keine verfügbaren Lizenzschlüssel.")
                    return redirect('gdata_accounts')

                # Create GDataAccount
                try:
                    account = GDataAccount.objects.create(
                        lizenz_schluessel=license_key,
                        initialen=initialen,
                        firma=firma,
                        nachname=nachname,
                        vorname=vorname,
                        strasse=strasse,
                        plz=plz,
                        ort=ort,
                        benutzername=benutzername,
                        passwort=passwort,  # Will be hashed in the model's save method
                        email=email,
                        auftrag_typ=auftrag_typ,
                        kommentar=kommentar,
                        expiration_date=None  # Will be set in the model's save method
                    )
                    # Mark the license key as used
                    license_key.is_used = True
                    license_key.save()

                    # Prepare the success message with the assigned license key and copy button
                    success_message = mark_safe(
                        f"GData Account für <strong>{benutzername}</strong> erfolgreich erstellt.<br>"
                        f"Lizenzschlüssel: <span id='license-key-{account.id}'>{license_key.lizenz_schluessel}</span> "
                        f"<button type='button' class='btn btn-sm btn-outline-secondary' onclick=\"copyToClipboard('license-key-{account.id}')\">Copy</button>"
                    )
                    messages.success(request, success_message)
                except IntegrityError:
                    messages.error(request, "Benutzername bereits vergeben.")
                except Exception as e:
                    messages.error(request, f"Fehler beim Erstellen des Accounts: {e}")

            return redirect('gdata_accounts')

        elif 'upload_keys' in request.POST:
            # Handle license key upload
            keys_file = request.FILES.get('keys_file')
            if not keys_file:
                messages.error(request, "Bitte eine Datei hochladen.")
                return redirect('gdata_accounts')
            if not keys_file.name.endswith('.txt'):
                messages.error(request, "Nur TXT-Dateien sind erlaubt.")
                return redirect('gdata_accounts')

            # Read keys from file
            try:
                keys = keys_file.read().decode('utf-8').splitlines()
                added = 0
                for key in keys:
                    key = key.strip()
                    if key:
                        created, _ = LicenseKey.objects.get_or_create(
                            lizenz_schluessel=key,
                            defaults={'is_used': False}
                        )
                        if created:
                            added += 1
                messages.success(request, f"{added} Lizenzschlüssel hinzugefügt.")
            except Exception as e:
                messages.error(request, f"Fehler beim Hochladen der Lizenzschlüssel: {e}")

            return redirect('gdata_accounts')

    # Fetch GDataAccounts
    accounts = GDataAccount.objects.all()

    if search_query:
        accounts = accounts.filter(
            Q(benutzername__icontains=search_query) |
            Q(firma__icontains=search_query) |
            Q(nachname__icontains=search_query) |
            Q(vorname__icontains=search_query) |
            Q(email__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(accounts, per_page)
    page_number = request.GET.get('page')
    accounts_page = paginator.get_page(page_number)

    # Count Keys Left
    keys_left = LicenseKey.objects.filter(is_used=False).count()

    context = {
        'accounts': accounts_page,
        'search_query': search_query,
        'per_page': per_page,
        'keys_left': keys_left,
    }

    return render(request, 'gdata_accounts.html', context)

@login_required
@transaction.atomic
def toggle_email_sent(request, account_id):
    """
    Toggle the 'email_sent' status of a GDataAccount.
    """
    if request.method == 'POST':
        account = get_object_or_404(GDataAccount, id=account_id)
        account.email_sent = not account.email_sent
        if account.email_sent:
            account.email_sent_timestamp = timezone.now()
        else:
            account.email_sent_timestamp = None
        account.save()
        return JsonResponse({'success': True, 'email_sent': account.email_sent})
    return JsonResponse({'success': False}, status=400)


@login_required
@transaction.atomic
def update_license(request, account_id):
    """
    Update the license runtime for a GDataAccount by adding years.
    """
    if request.method == 'POST':
        account = get_object_or_404(GDataAccount, id=account_id)
        try:
            data = json.loads(request.body)
            years = int(data.get('years', 1))
            if years not in [1, 2, 3]:
                return JsonResponse({'success': False, 'error': 'Ungültige Anzahl an Jahren.'}, status=400)
        except:
            return JsonResponse({'success': False, 'error': 'Ungültige Daten.'}, status=400)

        # Extend the expiration date by the specified years
        if account.expiration_date:
            account.expiration_date += timezone.timedelta(days=365 * years)
        else:
            # If no expiration date is set, initialize it based on 'auftrag_typ'
            if account.auftrag_typ == '1_jahr':
                account.expiration_date = account.datum + timezone.timedelta(days=365 * years)
            elif account.auftrag_typ == '2_jahre':
                account.expiration_date = account.datum + timezone.timedelta(days=365 * 2 * years)
            elif account.auftrag_typ == '3_jahre':
                account.expiration_date = account.datum + timezone.timedelta(days=365 * 3 * years)
            else:
                account.expiration_date = account.datum + timezone.timedelta(days=365 * years)

        account.save()
        return JsonResponse({'success': True, 'new_expiration_date': account.expiration_date})
    return JsonResponse({'success': False}, status=400)

def edit_gdata_account(request, account_id):
    """
    Edit an existing GDataAccount.
    """
    account = get_object_or_404(GDataAccount, id=account_id)

    if request.method == "POST":
        # Process the form
        lizenz_schluessel = request.POST.get('lizenz_schluessel').strip()
        initialen = request.POST.get('initialen').strip()
        firma = request.POST.get('firma').strip()
        nachname = request.POST.get('nachname').strip()
        vorname = request.POST.get('vorname').strip()
        strasse = request.POST.get('strasse').strip()
        plz = request.POST.get('plz').strip()
        ort = request.POST.get('ort').strip()
        benutzername = request.POST.get('benutzername').strip()
        passwort = request.POST.get('passwort').strip()
        auftrag_typ = request.POST.get('auftrag_typ').strip()
        kommentar = request.POST.get('kommentar').strip()

        # Optionally, handle updating the license key if allowed
        if lizenz_schluessel != account.lizenz_schluessel.lizenz_schluessel:
            # Unmark the old key
            old_key = account.lizenz_schluessel
            old_key.is_used = False
            old_key.save()
            # Assign new key
            try:
                new_key = LicenseKey.objects.get(lizenz_schluessel=lizenz_schluessel, is_used=False)
                account.lizenz_schluessel = new_key
                new_key.is_used = True
                new_key.save()
            except LicenseKey.DoesNotExist:
                messages.error(request, "Neue Lizenzschlüssel ist ungültig oder bereits verwendet.")
                return redirect('edit_gdata_account', account_id=account_id)

        # Update other fields
        account.initialen = initialen
        account.firma = firma
        account.nachname = nachname
        account.vorname = vorname
        account.strasse = strasse
        account.plz = plz
        account.ort = ort
        account.benutzername = benutzername
        account.passwort = passwort  # Should hash/encrypt
        account.auftrag_typ = auftrag_typ
        account.kommentar = kommentar

        try:
            account.save()
            messages.success(request, "GData Account aktualisiert.")
        except IntegrityError:
            messages.error(request, "Benutzername bereits vergeben.")
        except Exception as e:
            messages.error(request, f"Fehler beim Aktualisieren des Accounts: {e}")

        return redirect('gdata_accounts')

    return render(request, 'edit_gdata_account.html', {'account': account})


def delete_gdata_account(request, account_id):
    """
    Delete an existing GDataAccount.
    """
    account = get_object_or_404(GDataAccount, id=account_id)
    if request.method == "POST":
        # Unmark the license key
        license_key = account.lizenz_schluessel
        license_key.is_used = False
        license_key.save()
        account.delete()
        messages.success(request, "GData Account gelöscht.")
        return redirect('gdata_accounts')
    return render(request, 'delete_gdata_account_confirm.html', {'account': account})

#############################################
# Placeholder: generate_report, api_logs, etc.
#############################################
def api_logs(request):
    log_file = "isl_log_reader.log"  # Path to your log file
    log_lines = []

    try:
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8") as file:
                    log_lines = file.readlines()[-100:]
                logger.debug(f"Fetched {len(log_lines)} log lines.")
            except UnicodeDecodeError:
                with open(log_file, "r", encoding="latin-1") as file:
                    log_lines = file.readlines()[-100:]
                logger.debug(f"Fetched {len(log_lines)} log lines with fallback encoding.")
        else:
            log_lines = ["Log file not found."]
            logger.warning("Log file not found.")
    except Exception as e:
        log_lines = [f"Error reading log file: {str(e)}"]
        logger.error(f"Error reading log file: {e}")

    # Prepare logs for JSON response with HTML formatting
    formatted_logs = []
    for line in log_lines:
        if 'INFO' in line:
            color = 'green'
        elif 'WARNING' in line:
            color = 'orange'
        elif 'ERROR' in line or 'CRITICAL' in line:
            color = 'red'
        else:
            color = 'black'
        formatted_line = f'<span style="color: {color};">{line}</span>'
        formatted_logs.append(formatted_line)

    return JsonResponse({'logs': formatted_logs})

@require_GET
def autocomplete_customer(request):
    """
    Multi-token search: 'marco müller' or 'müller marco' or 'xyz marco',
    ignoring case/accent issues.
    """
    query = request.GET.get('query', '').strip()
    results = []

    if query:
        tokens = query.split()  # e.g. "marco m" => ["marco","m"]
        if not tokens:
            return JsonResponse(results, safe=False)

        conditions = []
        params = []
        # For each token => build (column1 LIKE '%token%' OR column2 LIKE '%token%' ...)
        # joined by AND.
        for t in tokens:
            like_pattern = f"%{t}%"
            part = (
                "("
                "[Vorname]  LIKE %s COLLATE SQL_Latin1_General_CP1_CI_AI "
                " OR [Name]  LIKE %s COLLATE SQL_Latin1_General_CP1_CI_AI "
                " OR [Firma] LIKE %s COLLATE SQL_Latin1_General_CP1_CI_AI "
                " OR [Strasse] LIKE %s COLLATE SQL_Latin1_General_CP1_CI_AI "
                " OR [Ort] LIKE %s COLLATE SQL_Latin1_General_CP1_CI_AI "
                " OR [PLZ] LIKE %s COLLATE SQL_Latin1_General_CP1_CI_AI "
                " OR [Email] LIKE %s COLLATE SQL_Latin1_General_CP1_CI_AI "
                ")"
            )
            conditions.append(part)
            # 7 placeholders per token
            params.extend([like_pattern]*7)

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT TOP (200)
                [Vorname],
                [Name],       -- last name
                [Firma],
                [Strasse],
                [PLZ],
                [Ort],
                [Telefon1],
                [Telefon3],
                [Email]
            FROM [SL_MCR001].[dbo].[CRM_ADRESSEN]
            WHERE {where_clause}
            ORDER BY [Name], [Vorname]
        """

        try:
            with connections['address_db'].cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                for row in rows:
                    results.append({
                        'vorname':   row[0] or "",
                        'nachname':  row[1] or "",
                        'firma':     row[2] or "",
                        'strasse':   row[3] or "",
                        'plz':       row[4] or "",
                        'ort':       row[5] or "",
                        'telefon1':  row[6] or "",
                        'telefon3':  row[7] or "",
                        'email':     row[8] or "",
                    })
        except Exception as e:
            logger.error(f"Autocomplete Customer Error: {e}")

    return JsonResponse(results, safe=False)

def run_email_import_script():
    """
    Continuously run the email_import script every 15 minutes in a background thread.
    """
    while True:
        try:
            # Call the external Python script or function that handles email imports
            subprocess.run(["python", "pcrmgmtAPP/utils/email_import.py"])
        except Exception as e:
            logger.error(f"Error running email import script: {e}")

        # Sleep for 15 minutes between runs
        pytime.sleep(900)  # 900 seconds = 15 minutes

def start_rma_email_import(request):
    try:
        # Vollständigen Pfad zum Skript angeben
        script_path = os.path.join(settings.BASE_DIR, 'pcrmgmtAPP/utils/email_import.py')
        subprocess.Popen(["python", script_path])
        messages.success(request, "RMA Email Import Script started.")
    except Exception as e:
        messages.error(request, f"Failed to start RMA Email Import script: {e}")
    return redirect('tasks')

def generate_report(request):
    if request.method == "POST":
        timespan_days = request.POST.get("timespan_days")
        include_verrechnet = request.POST.get("include_verrechnet") == "include_verrechnet"

        try:
            timespan_days = int(timespan_days)
            if timespan_days < 1 or timespan_days > 365:
                raise ValueError("Timespan must be between 1 and 365 days.")

            # Fetch relevant logs based on timespan_days
            with connections['isllogs'].cursor() as cursor:
                query = """
                    SELECT SessionID, Startzeit, Dauer, Benutzer, NameFirma, Verrechnet, Memo
                    FROM dbo.SessionLog_new
                    WHERE Startzeit >= DATEADD(day, -?, GETDATE())
                """
                cursor.execute(query, [timespan_days])
                logs = cursor.fetchall()
                logger.debug(f"Fetched {len(logs)} logs for report generation.")

            # Generate statistics
            total_logs = len(logs)
            verrechnet_count = sum(1 for log in logs if log[5])
            nicht_verrechnet_count = total_logs - verrechnet_count

            # Create PDF
            buffer = io.BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=letter)
            pdf.setTitle("ISL Logs Report")

            # Title
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawCentredString(300, 750, "ISL Logs Report")

            # Summary
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(50, 720, f"Report Duration: Last {timespan_days} days")
            pdf.drawString(50, 700, f"Total Logs: {total_logs}")
            pdf.drawString(50, 680, f"Verrechnet: {verrechnet_count}")
            pdf.drawString(50, 660, f"Nicht Verrechnet: {nicht_verrechnet_count}")

            # Conditional Report Options
            if include_verrechnet:
                pdf.drawString(50, 640, f"Verrechnet Status Included in Report.")

            # Table Header
            pdf.setFont("Helvetica-Bold", 10)
            y = 620
            pdf.drawString(50, y, "SessionID")
            pdf.drawString(150, y, "Startzeit")
            pdf.drawString(250, y, "Dauer")
            pdf.drawString(330, y, "Benutzer")
            pdf.drawString(430, y, "NameFirma")
            if include_verrechnet:
                pdf.drawString(520, y, "Verrechnet")
                memo_x = 600
            else:
                memo_x = 520
            pdf.drawString(memo_x, y, "Memo")
            y -= 20

            pdf.setFont("Helvetica", 10)
            for log in logs:
                if y < 50:
                    pdf.showPage()
                    y = 750
                    # Re-draw header on new page
                    pdf.setFont("Helvetica-Bold", 10)
                    pdf.drawString(50, y, "SessionID")
                    pdf.drawString(150, y, "Startzeit")
                    pdf.drawString(250, y, "Dauer")
                    pdf.drawString(330, y, "Benutzer")
                    pdf.drawString(430, y, "NameFirma")
                    if include_verrechnet:
                        pdf.drawString(520, y, "Verrechnet")
                        memo_x = 600
                    else:
                        memo_x = 520
                    pdf.drawString(memo_x, y, "Memo")
                    y -= 20
                    pdf.setFont("Helvetica", 10)

                pdf.drawString(50, y, log[0])
                startzeit_formatted = log[1].strftime("%Y-%m-%d %H:%M:%S") if log[1] else "N/A"
                pdf.drawString(150, y, startzeit_formatted)
                pdf.drawString(250, y, log[2] if log[2] else "N/A")
                pdf.drawString(330, y, log[3] if log[3] else "N/A")
                pdf.drawString(430, y, log[4] if log[4] else "N/A")
                if include_verrechnet:
                    verrechnet_text = "Yes" if log[5] else "No"
                    pdf.drawString(520, y, verrechnet_text)
                memo = (log[6] or "")[:40] + "..." if log[6] and len(log[6]) > 40 else (log[6] or "")
                pdf.drawString(memo_x, y, memo)
                y -= 20

            pdf.save()
            buffer.seek(0)

            logger.info("Report generated successfully.")
            return FileResponse(buffer, as_attachment=True, filename="ISL_Logs_Report.pdf")
        except ValueError as ve:
            messages.error(request, f"Invalid timespan value: {ve}")
            logger.error(f"Invalid timespan value: {ve}")
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            messages.error(request, "Failed to generate report.")

    # For GET requests, redirect to dashboard or show a form
    return redirect('dashboard')  # Redirect to dashboard after report generation


@login_required
def autocomplete_address(request):
    """
    Autocomplete view for Address_DB.
    """
    query = request.GET.get('query', '').strip()
    results = []
    if query:
        try:
            with connections['address_db'].cursor() as cursor:
                # Adjust the SQL query based on your Address_DB schema
                cursor.execute("""
                    SELECT Vorname, Nachname, Firma, Email
                    FROM dbo.AddressTable  -- Replace with your actual table name
                    WHERE Vorname LIKE ? OR Nachname LIKE ? OR Firma LIKE ? OR Email LIKE ?
                    ORDER BY Vorname, Nachname
                    OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY
                """, [f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"])
                rows = cursor.fetchall()
                for row in rows:
                    results.append({
                        'vorname': row[0],
                        'nachname': row[1],
                        'firma': row[2],
                        'email': row[3],
                    })
        except Exception as e:
            logger.error(f"Autocomplete Address Error: {e}")

    return JsonResponse(results, safe=False)


#############################################
# Maintenance Dashboard
#############################################
@login_required
def maintenance_dashboard(request):
    now = timezone.now()

    # Berechne Start und Ende der aktuellen Woche (angenommen: Montag bis Sonntag)
    start_of_week = now - timedelta(days=now.weekday())
    end_of_week = start_of_week + timedelta(days=6, hours=23, minutes=59, seconds=59)

    # Berechne Start und Ende des aktuellen Monats
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = calendar.monthrange(now.year, now.month)[1]
    end_of_month = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)

    current_week_tasks = MaintenanceTask.objects.filter(
        config__frequency='weekly',
        due_date__gte=start_of_week,
        due_date__lte=end_of_week,
        status__in=['open', 'claimed']
    ).order_by('due_date')

    current_month_tasks = MaintenanceTask.objects.filter(
        config__frequency__in=['monthly', '2months'],
        due_date__gte=start_of_month,
        due_date__lte=end_of_month,
        status__in=['open', 'claimed']
    ).order_by('due_date')

    done_tasks = MaintenanceTask.objects.filter(status='done').order_by('-due_date')

    context = {
        'current_week_tasks': current_week_tasks,
        'current_month_tasks': current_month_tasks,
        'done_tasks': done_tasks,
        'now': now,
    }
    return render(request, 'maintenance/maintenance_dashboard.html', context)

#############################################
# Maintenance Config CRUD
#############################################
@login_required
def config_list(request):
    configs = MaintenanceConfig.objects.all().order_by('-id')
    return render(request, 'maintenance/config_list.html', {'configs': configs})

@login_required
def config_create(request):
    if request.method == 'POST':
        form = MaintenanceConfigForm(request.POST)
        if form.is_valid():
            config = form.save(commit=False)
            config.created_by = request.user
            config.save()
            messages.success(request, "Maintenance config created.")
            return redirect('maintenance_config_list')
    else:
        form = MaintenanceConfigForm()
    return render(request, 'maintenance/task_form.html', {'form': form})

@login_required
def config_edit(request, pk):
    config = get_object_or_404(MaintenanceConfig, pk=pk)
    if request.method == 'POST':
        form = MaintenanceConfigForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Maintenance config updated.")
            return redirect('maintenance_config_list')
    else:
        form = MaintenanceConfigForm(instance=config)
    return render(request, 'maintenance/task_form.html', {'form': form, 'config': config})

@login_required
def config_delete(request, pk):
    config = get_object_or_404(MaintenanceConfig, pk=pk)
    if request.method == 'POST':
        config.delete()
        messages.success(request, "Maintenance config deleted.")
        return redirect('maintenance_config_list')
    return render(request, 'maintenance/config_confirm_delete.html', {'config': config})


@login_required
def maintenance_report_pdf(request, config_id):
    """Erzeugt einen ausführlichen Maintenance-PDF-Report inkl. Bilder."""
    config = get_object_or_404(MaintenanceConfig, pk=config_id)
    # Dazugehörige erledigte UND offene Tasks:
    tasks = config.tasks.select_related('assigned_to').prefetch_related('logs').all().order_by('due_date')

    # Optional: ein Firmenlogo / eigenes Logo:
    # Pfad ins static-Verzeichnis oder an anderer Stelle
    logo_path = os.path.join(settings.STATIC_ROOT, 'img', 'mycompany_logo.png')
    # falls WeasyPrint absolute URLs braucht => build_absolute_uri,
    # aber hier nur als Bsp. (ggf. config. in Template einbauen)

    # Kontext vorbereiten
    context = {
        'config': config,
        'tasks': tasks,
        'logo_url': request.build_absolute_uri('/static/img/mycompany_logo.png'),
        # oder: 'logo_url': request.build_absolute_uri(static('img/mycompany_logo.png'))
    }

    # 1) HTML-Template in String rendern
    html_string = render_to_string('maintenance/pdf/maintenance_report.html', context, request=request)

    # 2) WeasyPrint-Aufruf: PDF generieren
    #    Falls du ein eigenes CSS-File einbinden möchtest, kannst du das so machen:
    pdf_styles = os.path.join(settings.STATIC_ROOT, 'css', 'maintenance_pdf.css')
    #    -> Du musst darauf achten, dass maintenance_pdf.css wirklich in /static/css/ liegt
    #    -> und in production collectstatic korrekt funktioniert.

    # HTML-Objekt erstellen:
    pdf_file = HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(
        stylesheets=[CSS(pdf_styles)]
    )

    # 3) Antwort als PDF zurückgeben
    response = HttpResponse(pdf_file, content_type='application/pdf')
    filename = f"Maintenance_Report_{config_id}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response



# ---------------------
# Maintenance Tasks
# ---------------------

@login_required
def task_list(request):
    filter_status = request.GET.get('status', '')
    tasks = MaintenanceTask.objects.select_related('config').order_by('due_date')
    if filter_status in ['open', 'claimed', 'done']:
        tasks = tasks.filter(status=filter_status)
    return render(request, 'maintenance/task_list.html', {
        'tasks': tasks,
        'filter_status': filter_status,
    })

@login_required
def task_detail(request, task_id):
    task = get_object_or_404(MaintenanceTask, pk=task_id)
    return render(request, 'maintenance/task_detail.html', {
        'task': task,
        'logs': task.logs.all(),
    })

@login_required
def task_delete(request, task_id):
    task = get_object_or_404(MaintenanceTask, pk=task_id)
    if request.method == 'POST':
        task.delete()
        messages.success(request, "Task deleted.")
        return redirect('maintenance_task_list')
    return render(request, 'maintenance/task_confirm_delete.html', {'task': task})


@login_required
def maintenance_task_edit(request, task_id):
    """
    Diese View ermöglicht das Bearbeiten eines Maintenance-Tasks inklusive der Sub-checks.
    Wird per AJAX (Fetch) aufgerufen, liefert sie eine JSON-Antwort zurück.
    """
    task = get_object_or_404(MaintenanceTask, pk=task_id)
    logs = task.logs.all()
    user_list = User.objects.all().order_by('username')

    if request.method == "POST":
        # Zuweisung aktualisieren
        new_assignee_id = request.POST.get('assigned_to')
        if new_assignee_id:
            try:
                new_user = User.objects.get(pk=new_assignee_id)
                task.assigned_to = new_user
                if task.status == 'open':
                    task.status = 'claimed'
                    task.claimed_at = timezone.now()
            except User.DoesNotExist:
                return JsonResponse({"success": False, "error": "Der angegebene Benutzer existiert nicht."})
        else:
            task.assigned_to = None

        # Aktualisiere Start- und Fälligkeitsdatum
        start_date_str = request.POST.get("start_date")
        due_date_str = request.POST.get("due_date")
        if start_date_str:
            try:
                task.start_date = timezone.make_aware(datetime.strptime(start_date_str, "%Y-%m-%dT%H:%M"))
            except Exception:
                return JsonResponse({"success": False, "error": "Ungültiges Startdatum-Format."})
        if due_date_str:
            try:
                task.due_date = timezone.make_aware(datetime.strptime(due_date_str, "%Y-%m-%dT%H:%M"))
            except Exception:
                return JsonResponse({"success": False, "error": "Ungültiges Fälligkeitsdatum-Format."})

        # Optional: Falls das Formular ein neues Status-Feld übermittelt:
        new_status = request.POST.get("status")
        if new_status:
            task.status = new_status

        # Optional: Aktualisiere die Dauer, falls übermittelt
        duration = request.POST.get("duration_minutes")
        if duration:
            try:
                task.duration_minutes = int(duration)
            except ValueError:
                pass

        task.save()

        # Aktualisiere die Sub-checks
        for log_item in logs:
            desc = request.POST.get(f"desc_{log_item.id}", "")
            is_done = request.POST.get(f"done_{log_item.id}") == "on"
            log_item.description = desc
            log_item.is_done = is_done
            if f"screenshot_{log_item.id}" in request.FILES:
                log_item.screenshot = request.FILES[f"screenshot_{log_item.id}"]
            log_item.save()

        # Falls der Request per AJAX kommt, gib JSON zurück:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True})
        else:
            messages.success(request, "Maintenance Task wurde erfolgreich aktualisiert.")
            return redirect("maintenance_dashboard")

    else:
        context = {
            'task': task,
            'logs': logs,
            'user_list': user_list,
            'start_date_formatted': task.start_date.strftime("%Y-%m-%dT%H:%M") if task.start_date else "",
            'due_date_formatted': task.due_date.strftime("%Y-%m-%dT%H:%M") if task.due_date else "",
        }
        return render(request, "maintenance/task_claim_details_edit.html", context)


@login_required
def task_claim_details(request, task_id):
    task = get_object_or_404(MaintenanceTask, pk=task_id)
    existing_logs = list(task.logs.all())
    existing_names = {log.sub_check_name for log in existing_logs}
    # Füge Dummy-Einträge für fehlende Standard-Checks hinzu
    for check in STANDARD_SUB_CHECKS:
        if check not in existing_names:
            # Hier erzeugen wir ein Dummy-Objekt (als dict), dessen id mit "new_" beginnt.
            dummy = {
                'id': f"new_{check.replace(' ', '_')}",
                'sub_check_name': check,
                'is_done': False,
                'description': ""
            }
            existing_logs.append(dummy)

    if request.method == 'POST':
        # Zuerst den neuen bzw. bestehenden Logs aktualisieren
        # Für jeden Standard-Check:
        for check in STANDARD_SUB_CHECKS:
            field_done = f"done_{check.replace(' ', '_')}"
            field_desc = f"desc_{check.replace(' ', '_')}"
            # Prüfe, ob im POST die Checkbox gesetzt ist
            if request.POST.get(field_done):
                # Falls ein Log für diesen Check existiert, aktualisieren wir es; andernfalls erstellen wir es
                log = task.logs.filter(sub_check_name=check).first()
                if log:
                    log.is_done = True
                    log.description = request.POST.get(field_desc, "")
                    log.save()
                else:
                    MaintenanceLog.objects.create(
                        task=task,
                        sub_check_name=check,
                        is_done=True,
                        description=request.POST.get(field_desc, "")
                    )
            else:
                # Falls der Check nicht gesetzt ist, löschen wir – falls vorhanden – das Log
                log = task.logs.filter(sub_check_name=check).first()
                if log:
                    log.delete()

        messages.success(request, "Task aktualisiert.")
        return redirect('maintenance_task_claim_details', task_id=task.id)

    # GET: Übergib eine kombinierte Liste (bestehende Logs plus Dummy-Daten)
    context = {
        'task': task,
        'logs': existing_logs,
        'user_list': list(User.objects.all().order_by('username')),
    }
    return render(request, 'maintenance/task_claim_details.html', context)

def maintenance_task_complete(request, task_id):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    task = get_object_or_404(MaintenanceTask, pk=task_id)
    if task.status not in ['open', 'claimed']:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Task already completed or invalid status.'})
        messages.warning(request, "Task ist bereits abgeschlossen oder hat ungültigen Status.")
        return redirect('maintenance_task_list')

    # Task abschließen
    task.status = 'done'
    task.completed_at = timezone.now()
    if task.claimed_at:
        delta = task.completed_at - task.claimed_at
        task.duration_minutes = int(delta.total_seconds() // 60)
    task.save()

    # Nächsten Task anlegen, basierend auf config.frequency
    frequency = task.config.frequency
    old_due = task.due_date
    if frequency == 'weekly':
        next_due = old_due + relativedelta(weeks=1)
    elif frequency == '2months':
        next_due = old_due + relativedelta(months=2)
    else:
        # standard monthly
        next_due = old_due + relativedelta(months=1)

    new_task = MaintenanceTask.objects.create(
        config=task.config,
        due_date=next_due,
        status='open'
    )
    new_task.create_default_checkpoints()

    messages.success(request, f"Task #{task.id} abgeschlossen. Neuer Task fällig am {next_due.strftime('%Y-%m-%d')}.")

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'new_task_due_date': next_due.strftime('%Y-%m-%d')})

    return redirect('maintenance_dashboard')


@login_required
def task_create(request):
    if request.method == "POST":
        form = MaintenanceTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            task.status = 'open'
            task.save()
            task.create_default_checkpoints()
            messages.success(request, "Neuer Maintenance Task erstellt!")
            return redirect('maintenance_task_list')
    else:
        form = MaintenanceTaskForm()
    return render(request, 'maintenance/task_form.html', {'form': form})


@login_required
def maintenance_full_create(request):
    if request.method == "POST":
        form = MaintenanceFullForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            # Config ohne "notes"
            config = MaintenanceConfig.objects.create(
                customer_firma=data.get('customer_firma'),
                customer_vorname=data.get('customer_vorname'),
                customer_nachname=data.get('customer_nachname'),
                customer_strasse=data.get('customer_strasse'),
                customer_plz=data.get('customer_plz'),
                customer_ort=data.get('customer_ort'),
                frequency=data.get('frequency'),
                created_by=request.user,
            )
            start_date = data.get('start_date')
            due_date = calculate_due_date(start_date, data.get('frequency'))
            task = MaintenanceTask.objects.create(
                config=config,
                start_date=start_date,
                due_date=due_date,
                status='open'
            )
            # Liste der Standard-Sub-Checks (ohne Notizen)
            sub_checks = []
            if data.get('eventlogs_check'):
                sub_checks.append("Eventlogs check")
            if data.get('windows_updates_check'):
                sub_checks.append("Windows Updates check")
            if data.get('backup_check'):
                sub_checks.append("Backup check")
            if data.get('serverstorage_check'):
                sub_checks.append("Serverstorage check")
            if data.get('backupstorage_check'):
                sub_checks.append("Backupstorage check inkl. Systemupdates")
            if data.get('filesystem_cleanup_check'):
                sub_checks.append("Filesystem cleanup durchführen")
            if data.get('security_check'):
                sub_checks.append("Security check")
            if data.get('firewall_check'):
                sub_checks.append("Firewall check")
            for check_name in sub_checks:
                MaintenanceLog.objects.create(
                    task=task,
                    sub_check_name=check_name,
                    is_done=False,
                    description=""
                )
            messages.success(request, "Neue MaintenanceConfig und Task wurden angelegt!")
            return redirect('maintenance_dashboard')
        else:
            messages.error(request, "Bitte korrigiere die Formularfehler.")
    else:
        form = MaintenanceFullForm()
    return render(request, 'maintenance/maintenance_full_create.html', {'form': form})
@login_required
def maintenance_overview(request):
    """
    Kurze Übersicht aller MaintenanceConfig-Einträge
    """
    configs = MaintenanceConfig.objects.all().order_by('customer_firma')
    return render(request, 'maintenance/maintenance_overview.html', {'configs': configs})

def maintenance_task_pdf(request, task_id):
    task = get_object_or_404(MaintenanceTask, pk=task_id)
    config = task.config
    logs = task.logs.all()

    context = {
        'task': task,
        'config': config,
        'logs': logs,
        'now': timezone.now(),
        'logo_url': request.build_absolute_uri('/static/img/company_logo.png'),  # Pfad zu Ihrem Firmenlogo
    }

    # Rendern des HTML-Inhalts
    html_string = render_to_string('maintenance/maintenance_task_pdf.html', context, request=request)

    # WeasyPrint benötigt einen Base URL, um auf statische und Medienressourcen zugreifen zu können
    base_url = request.build_absolute_uri()

    # Optional: CSS-Datei für PDF-Styling
    css = CSS(settings.STATIC_ROOT / 'css' / 'maintenance_pdf.css')  # Stellen Sie sicher, dass diese Datei existiert

    # PDF generieren
    pdf_file = HTML(string=html_string, base_url=base_url).write_pdf(stylesheets=[css])

    # Rückgabe des PDFs als Download
    return FileResponse(io.BytesIO(pdf_file), as_attachment=True, filename=f"Maintenance_Task_{task.id}.pdf")

#Calculate Due Date
def calculate_due_date(start_date, frequency):
    if frequency == 'weekly':
        # wöchentlich: 7 Tage später
        return start_date + timedelta(days=7)
    elif frequency == 'monthly':
        # monatlich: letztes Datum im selben Monat
        year = start_date.year
        month = start_date.month
        last_day = calendar.monthrange(year, month)[1]
        return start_date.replace(day=last_day)
    elif frequency == '2months':
        # 2-monatlich: letztes Datum des Monats, der zwei Monate später liegt
        month = start_date.month + 2
        year = start_date.year
        if month > 12:
            month -= 12
            year += 1
        last_day = calendar.monthrange(year, month)[1]
        return start_date.replace(year=year, month=month, day=last_day)
    else:
        return start_date