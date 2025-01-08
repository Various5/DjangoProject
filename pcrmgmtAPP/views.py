# pcrmgmtAPP/views.py
import os
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.http import FileResponse, HttpResponse
from django.db import connection
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db import connections
from pcrmgmtProject import settings
from .utils.encryption import decrypt_password, encrypt_password
import logging
from .models import OfficeAccount
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from io import BytesIO
import threading
import time
from django.utils import timezone
from .utils.isl_log_reader import main as run_isl_log_reader  # Assuming the main function runs the script
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import RegisterForm
from .models import UserProfile
from .models import Garantie
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from .models import Garantie
from .forms import GarantieForm
from django.db import models
from .models import RMATicket
import subprocess
import json

logger = logging.getLogger(__name__)
script_running = False
script_thread = None
script_start_time = None  # To track runtime
CONFIG_PATH = "config.json"


def run_script_in_background(interval_seconds):
    global script_running, script_start_time
    while script_running:
        script_start_time = timezone.now()
        logger.info("Starting ISL Log Reader...")
        try:
            run_isl_log_reader()
            logger.info("ISL Log Reader completed.")
        except Exception as e:
            logger.error(f"Error in ISL Log Reader: {e}")
        script_start_time = None  # Reset after completion
        if script_running:
            logger.info(f"Next run in {interval_seconds} seconds.")
            time.sleep(interval_seconds)

def start_isl_log_reader():
    global script_running, script_thread
    if not script_running:
        # Verwende einen festen Intervallwert oder passe den Wert an
        interval_minutes = getattr(settings, 'DEFAULT_INTERVAL', 10)  # Beispiel: 10 Minuten
        interval_seconds = interval_minutes * 60
        script_running = True
        script_thread = threading.Thread(target=run_script_in_background, args=(interval_seconds,), daemon=True)
        script_thread.start()

def stop_isl_log_reader():
    global script_running
    if script_running:
        script_running = False
        logger.info("ISL Log Reader stopped.")

@login_required
def settings_view(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        theme = request.POST.get('theme')
        if theme in ['light', 'dark', 'modern', 'soft-blue', 'soft-green']:
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

@login_required
def tasks_view(request):
    config = {
        "isl_script_interval": 10,
        "rma_script_interval": 15,
        "script_running": False,
        "rma_script_running": False,
        "script_start_time": None,
        "rma_script_start_time": None,
    }

    # Load config.json if it exists
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as file:
                config.update(json.load(file))
        except json.JSONDecodeError as e:
            messages.error(request, f"Error reading config.json: {e}")
            # revert to defaults if JSON is invalid
            with open(CONFIG_PATH, "w") as file:
                json.dump(config, file, indent=4)

    if request.method == "POST":
        # Handle ISL Script Start/Stop
        if "start_script" in request.POST:
            # Actually start the background thread
            config["script_running"] = True
            with open(CONFIG_PATH, "w") as file:
                json.dump(config, file, indent=4)
            messages.info(request, "Starting ISL Log Reader background thread...")
            start_isl_log_reader()  # <=== CALLS your function

        elif "stop_script" in request.POST:
            config["script_running"] = False
            with open(CONFIG_PATH, "w") as file:
                json.dump(config, file, indent=4)
            messages.info(request, "Stopping ISL Log Reader background thread...")
            stop_isl_log_reader()  # <=== CALLS your function

        # Handle Interval Changes
        elif "set_interval" in request.POST:
            new_interval = request.POST.get("script_interval")
            try:
                config["isl_script_interval"] = int(new_interval)
                messages.success(request, f"ISL Log Reader interval updated to {new_interval} minutes.")
            except ValueError:
                messages.error(request, "Invalid interval for ISL Log Reader.")

        # Handle RMA Script Start/Stop (similarly if you have a background approach for RMA)
        elif "start_rma_script" in request.POST:
            config["rma_script_running"] = True
            # ... Possibly call your RMA start function here
        elif "stop_rma_script" in request.POST:
            config["rma_script_running"] = False
            # ... Possibly call your RMA stop function here

        elif "set_rma_interval" in request.POST:
            new_rma_interval = request.POST.get("rma_script_interval")
            try:
                config["rma_script_interval"] = int(new_rma_interval)
                messages.success(request, f"RMA Email Import interval updated to {new_rma_interval} minutes.")
            except ValueError:
                messages.error(request, "Invalid interval for RMA Email Import.")

        # Save updates to config.json
        with open(CONFIG_PATH, "w") as file:
            json.dump(config, file, indent=4)

        return redirect("tasks")

    # Prepare context
    context = {
        "isl_script_interval": config.get("isl_script_interval"),
        "rma_script_interval": config.get("rma_script_interval"),
        "script_running": config.get("script_running"),
        "rma_script_running": config.get("rma_script_running"),
        "script_start_time": config.get("script_start_time"),
        "rma_script_start_time": config.get("rma_script_start_time"),
    }
    return render(request, "tasks.html", context)


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

def logs(request):
    isl_log_file = os.path.join(settings.BASE_DIR, "isl_log_reader.log")
    rma_log_file = os.path.join(settings.BASE_DIR, "email_import.log")
    isl_log_lines = []
    rma_log_lines = []

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

@login_required
def dashboard(request):
    return render(request, 'dashboard.html')

def isl_logs(request):
    search_query = request.GET.get('search', '')
    filter_user = request.GET.get('filter_user', '')
    sort_by = request.GET.get('sort_by', 'Startzeit')
    sort_order = request.GET.get('sort_order', 'DESC')
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 25))

    log_entries = []
    unique_users = set()
    try:
        with connections['isllogs'].cursor() as cursor:
            # Alle Benutzer abrufen
            cursor.execute("SELECT DISTINCT Benutzer FROM dbo.SessionLog_new")
            unique_users = [row[0] for row in cursor.fetchall()]

            # Filter für Benutzer
            user_filter_clause = "AND Benutzer = %s" if filter_user else ""
            query = f"""
                SELECT SessionID, Startzeit, Dauer, Benutzer, NameFirma, Verrechnet, Memo
                FROM dbo.SessionLog_new
                WHERE (Benutzer LIKE %s OR NameFirma LIKE %s OR Memo LIKE %s) {user_filter_clause}
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
    except Exception as e:
        logger.error(f"Error during pagination: {e}")
        paginated_entries = paginator.get_page(1)

    return render(request, 'isl_logs.html', {
        'entries': paginated_entries,
        'search_query': search_query,
        'filter_user': filter_user,
        'unique_users': unique_users,
        'sort_by': sort_by,
        'sort_order': sort_order,
        'per_page': per_page,
    })


def toggle_verrechnet(request, log_id):
    try:
        with connections['isllogs'].cursor() as cursor:
            # Fetch the current value of Verrechnet
            cursor.execute("SELECT Verrechnet FROM dbo.SessionLog_new WHERE SessionID = %s", [log_id])
            current_value = cursor.fetchone()
            logger.debug(f"Current Verrechnet value for SessionID {log_id}: {current_value}")

            if current_value is None:
                logger.warning(f"Log with SessionID {log_id} not found.")
                messages.error(request, "Log entry not found.")
                return redirect('isl_logs')

            # Toggle the value
            new_value = not current_value[0]
            cursor.execute("UPDATE dbo.SessionLog_new SET Verrechnet = %s WHERE SessionID = %s", [new_value, log_id])
            logger.info(f"Toggled Verrechnet for SessionID {log_id} to {new_value}.")
        messages.success(request, "Verrechnet status toggled successfully.")
        return redirect('isl_logs')  # Redirect back to the ISL logs page
    except Exception as e:
        logger.error(f"Error toggling Verrechnet for log {log_id}: {e}")
        messages.error(request, "Failed to toggle Verrechnet status.")
        return HttpResponse("Error toggling Verrechnet", status=500)


def edit_isl_log(request, log_id):
    try:
        with connections['isllogs'].cursor() as cursor:
            cursor.execute("SELECT * FROM dbo.SessionLog_new WHERE SessionID = %s", [log_id])
            log_entry = cursor.fetchone()
            logger.debug(f"Fetched log entry for SessionID {log_id}: {log_entry}")
    except Exception as e:
        logger.error(f"Error fetching ISL log {log_id}: {e}")
        return HttpResponse("Error fetching log", status=500)

    if not log_entry:
        logger.warning(f"Log entry not found for SessionID {log_id}.")
        return HttpResponse("Log not found", status=404)

    if request.method == "POST":
        # Process form data
        startzeit = request.POST.get("startzeit")
        dauer = request.POST.get("dauer")
        benutzer = request.POST.get("benutzer")
        name_firma = request.POST.get("name_firma")
        verrechnet = request.POST.get("verrechnet") in ['True', 'true', '1', 'yes']
        memo = request.POST.get("memo")

        try:
            with connections['isllogs'].cursor() as cursor:
                cursor.execute("""
                    UPDATE dbo.SessionLog_new
                    SET Startzeit = %s, Dauer = %s, Benutzer = %s, NameFirma = %s, Verrechnet = %s, Memo = %s
                    WHERE SessionID = %s
                """, [startzeit, dauer, benutzer, name_firma, verrechnet, memo, log_id])
                logger.info(f"Updated log entry for SessionID {log_id}.")
            messages.success(request, "Log entry updated successfully.")
            return redirect('isl_logs')
        except Exception as e:
            logger.error(f"Error updating ISL log {log_id}: {e}")
            messages.error(request, "Failed to update log entry.")
            return redirect('edit_isl_log', log_id=log_id)

    return render(request, 'edit_isl_log.html', {'log_entry': log_entry})


# Delete an ISL log entry
def delete_isl_log(request, log_id):
    try:
        with connections['isllogs'].cursor() as cursor:
            cursor.execute("DELETE FROM dbo.SessionLog_new WHERE SessionID = %s", [log_id])
            logger.info(f"Deleted log entry for SessionID {log_id}.")
        messages.success(request, "Log entry deleted successfully.")
        return redirect('isl_logs')
    except Exception as e:
        logger.error(f"Error deleting ISL log {log_id}: {e}")
        messages.error(request, "Failed to delete log entry.")
        return HttpResponse("Error deleting log", status=500)


# Print an ISL log entry
def print_isl_log(request, log_id):
    try:
        with connections['isllogs'].cursor() as cursor:
            cursor.execute("SELECT * FROM dbo.SessionLog_new WHERE SessionID = %s", [log_id])
            log_entry = cursor.fetchone()
            logger.debug(f"Fetched log entry for printing SessionID {log_id}: {log_entry}")
    except Exception as e:
        logger.error(f"Error fetching ISL log {log_id} for printing: {e}")
        return HttpResponse("Error fetching log", status=500)

    if not log_entry:
        logger.warning(f"Log entry not found for SessionID {log_id}.")
        return HttpResponse("Log not found", status=404)

    return render(request, 'print_isl_log.html', {'log_entry': log_entry})


# Download a PDF for an ISL log entry
def download_isl_pdf(request, log_id):
    try:
        with connections['isllogs'].cursor() as cursor:
            cursor.execute("SELECT * FROM dbo.SessionLog_new WHERE SessionID = %s", [log_id])
            log_entry = cursor.fetchone()
            logger.debug(f"Fetched ISL log for PDF: {log_entry}")
    except Exception as e:
        logger.error(f"Error fetching ISL log {log_id} for PDF: {e}")
        return HttpResponse("Error fetching log", status=500)

    if not log_entry:
        logger.warning(f"Log not found for SessionID: {log_id}.")
        return HttpResponse("Log not found", status=404)

    # Generate the PDF
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"ISL Log {log_id}")

    pdf.drawString(100, 750, f"ISL Log Details")
    pdf.drawString(100, 730, f"SessionID: {log_entry[0]}")
    pdf.drawString(100, 710, f"Startzeit: {log_entry[1]}")
    pdf.drawString(100, 690, f"Dauer: {log_entry[2]}")
    pdf.drawString(100, 670, f"Benutzer: {log_entry[3]}")
    pdf.drawString(100, 650, f"NameFirma: {log_entry[4]}")
    pdf.drawString(100, 630, f"Verrechnet: {'Yes' if log_entry[5] else 'No'}")
    pdf.drawString(100, 610, f"Memo: {log_entry[6]}")

    pdf.save()
    buffer.seek(0)

    return FileResponse(buffer, as_attachment=True, filename=f"ISL_Log_{log_id}.pdf")


# Toggle Verrechnet status
def toggle_verrechnet(request, log_id):
    try:
        with connections['isllogs'].cursor() as cursor:
            # Abrufen des aktuellen Status von Verrechnet
            cursor.execute("SELECT Verrechnet FROM dbo.SessionLog_new WHERE SessionID = %s", [log_id])
            current_value = cursor.fetchone()
            logger.debug(f"Current Verrechnet value for SessionID {log_id}: {current_value}")

            if current_value is None:
                logger.warning(f"Log with SessionID {log_id} not found.")
                messages.error(request, "Log entry not found.")
                return HttpResponse("Log not found", status=404)

            # Umschalten des Status
            new_value = not current_value[0]
            cursor.execute("UPDATE dbo.SessionLog_new SET Verrechnet = %s WHERE SessionID = %s", [new_value, log_id])
            logger.info(f"Toggled Verrechnet for SessionID {log_id} to {new_value}.")
        return JsonResponse({"success": True, "new_value": new_value})
    except Exception as e:
        logger.error(f"Error toggling Verrechnet for log {log_id}: {e}")
        return JsonResponse({"success": False, "error": str(e)}, status=500)

def office_accounts(request):
    search_query = request.GET.get('search', '')  # Suchtext
    sort_by = request.GET.get('sort', 'vorname')  # Sortierspalte
    order = request.GET.get('order', 'asc')  # Sortierreihenfolge
    page = int(request.GET.get('page', 1))  # Aktuelle Seite
    per_page = int(request.GET.get('per_page', 25))  # Einträge pro Seite

    accounts = []
    try:
        with connection.cursor() as cursor:
            # Sichere Sortierspalten festlegen
            allowed_sort_columns = ['id', 'vorname', 'nachname', 'firma', 'email', 'passwort', 'kommentar', 'erstelldatum']
            if sort_by not in allowed_sort_columns:
                sort_by = 'vorname'
            if order not in ['asc', 'desc']:
                order = 'asc'

            query = f"""
                SELECT id, vorname, nachname, firma, email, passwort, kommentar, erstelldatum 
                FROM dbo.office_accounts
                WHERE vorname LIKE %s OR nachname LIKE %s OR firma LIKE %s OR email LIKE %s
                ORDER BY {sort_by} {order.upper()}
            """
            like_query = f"%{search_query}%"
            cursor.execute(query, [like_query, like_query, like_query, like_query])
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()

            for row in rows:
                account = dict(zip(columns, row))
                try:
                    account['passwort'] = decrypt_password(account['passwort']) or "Decryption Failed"
                except Exception as e:
                    logger.error(f"Password decryption failed for account ID {account['id']}: {e}")
                    account['passwort'] = "Decryption Failed"
                accounts.append(account)

    except Exception as e:
        logger.error(f"Error fetching office accounts: {e}")
        messages.error(request, "Could not retrieve accounts. Please try again later.")
        accounts = []

    if request.method == "POST":
        vorname = request.POST.get("vorname")
        nachname = request.POST.get("nachname")
        firma = request.POST.get("firma")
        email = request.POST.get("email")
        password = request.POST.get("password")
        kommentar = request.POST.get("kommentar")

        if not vorname or not nachname or not firma or not email or not password:
            messages.error(request, "Please fill in all required fields.")
        else:
            try:
                encrypted_password = encrypt_password(password)
                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO dbo.office_accounts (vorname, nachname, firma, email, passwort, kommentar, erstelldatum)
                        VALUES (%s, %s, %s, %s, %s, %s, GETDATE())
                    """, [vorname, nachname, firma, email, encrypted_password, kommentar])
                    messages.success(request, f"New account for {vorname} {nachname} added.")
                return redirect('office_accounts')
            except Exception as e:
                logger.error(f"Error adding new account: {e}")
                messages.error(request, "Could not add account. Please try again later.")

    paginator = Paginator(accounts, per_page)
    try:
        paginated_accounts = paginator.get_page(page)
    except Exception as e:
        logger.error(f"Pagination error: {e}")
        paginated_accounts = paginator.get_page(1)

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
        password = request.POST.get("password")
        kommentar = request.POST.get("kommentar")

        # Validate required fields
        if not vorname or not nachname or not firma or not email:
            messages.error(request, "Please fill in all required fields.")
        else:
            try:
                with connection.cursor() as cursor:
                    if password:
                        encrypted_password = encrypt_password(password)
                        cursor.execute("""
                            UPDATE dbo.office_accounts
                            SET vorname = ?, nachname = ?, firma = ?, email = ?, passwort = ?, kommentar = ?
                            WHERE id = ?
                        """, [vorname, nachname, firma, email, encrypted_password, kommentar, account_id])
                        logger.info(f"Updated office account {account_id} with new password.")
                    else:
                        cursor.execute("""
                            UPDATE dbo.office_accounts
                            SET vorname = ?, nachname = ?, firma = ?, email = ?, kommentar = ?
                            WHERE id = ?
                        """, [vorname, nachname, firma, email, kommentar, account_id])
                        logger.info(f"Updated office account {account_id} without changing password.")
                messages.success(request, "Office account updated successfully.")
                return redirect('office_accounts')
            except Exception as e:
                logger.error(f"Error updating account {account_id}: {e}")
                messages.error(request, "Failed to update office account.")

    account = get_object_or_404(OfficeAccount, id=account_id)
    return render(request, 'office_edit_account.html', {'account': account})

def delete_account(request, account_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM dbo.office_accounts WHERE id = ?", [account_id])
            logger.info(f"Deleted office account with id {account_id}.")
        messages.success(request, "Office account deleted successfully.")
        return redirect('office_accounts')
    except Exception as e:
        logger.error(f"Error deleting account {account_id}: {e}")
        messages.error(request, "Failed to delete office account.")
        return HttpResponse("Error deleting account", status=500)

def print_account(request, account_id):
    try:
        account = get_object_or_404(OfficeAccount, id=account_id)
        # Entschlüsseln des Passworts für die Druckansicht
        account.passwort = decrypt_password(account.passwort) or "Decryption Failed"
    except Exception as e:
        logger.error(f"Error fetching account {account_id} for printing: {e}")
        messages.error(request, "Error fetching account details.")
        return redirect('office_accounts')

    return render(request, 'office_print_account.html', {'account': account})


def download_pdf(request, account_id):
    try:
        account = get_object_or_404(OfficeAccount, id=account_id)
        # Entschlüsseln des Passworts für die PDF-Erstellung
        account.passwort = decrypt_password(account.passwort) or "Decryption Failed"

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        pdf.setTitle(f"Office Account - {account.vorname} {account.nachname}")

        pdf.drawString(100, 750, f"Office Account Details")
        pdf.drawString(100, 730, f"ID: {account.id}")
        pdf.drawString(100, 710, f"Vorname: {account.vorname}")
        pdf.drawString(100, 690, f"Nachname: {account.nachname}")
        pdf.drawString(100, 670, f"Firma: {account.firma}")
        pdf.drawString(100, 650, f"Email: {account.email}")
        pdf.drawString(100, 630, f"Passwort: {account.passwort}")  # Klartextpasswort einfügen
        pdf.drawString(100, 610, f"Kommentar: {account.kommentar}")
        pdf.drawString(100, 590, f"Erstelldatum: {account.erstelldatum}")

        pdf.save()
        buffer.seek(0)

        return FileResponse(buffer, as_attachment=True, filename=f"OfficeAccount_{account.id}.pdf")
    except Exception as e:
        logger.error(f"Error generating PDF for account {account_id}: {e}")
        messages.error(request, "Error generating PDF.")
        return redirect('office_accounts')


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
            buffer = BytesIO()
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

def garantie_tracker(request):
    return render(request, 'garantie_tracker.html')  # Placeholder template

def gdata_accounts(request):
    return render(request, 'gdata_accounts.html')  # Placeholder template

def rma_manager(request):
    return render(request, 'rma_manager.html')  # Placeholder template

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



def autocomplete_warranty(request):
    query = request.GET.get('query', '').strip()
    if not query:
        return JsonResponse([], safe=False)

    results = Garantie.objects.filter(
        models.Q(vorname__icontains=query) |
        models.Q(nachname__icontains=query) |
        models.Q(firma__icontains=query) |
        models.Q(seriennummer__icontains=query)
    )[:10]

    data = [
        {
            "typ": g.typ,
            "vorname": g.vorname,
            "nachname": g.nachname,
            "firma": g.firma,
            "email": g.email,
            "startdatum": g.startdatum.isoformat(),
            "ablaufdatum": g.ablaufdatum.isoformat(),
            "seriennummer": g.seriennummer,
            "kommentar": g.kommentar or "",
        }
        for g in results
    ]
    return JsonResponse(data, safe=False)



def autocomplete_customer(request):
    query = request.GET.get('query', '').strip()
    if not query:
        return JsonResponse([], safe=False)

    try:
        with connections['address_db'].cursor() as cursor:
            sql_query = """
                SELECT TOP 10 
                    CRM_ADRESSEN_ID, Name, Vorname, Firma, Strasse, Ort, PLZ, Telefon1, Telefon3, Email
                FROM dbo.CRM_ADRESSEN
                WHERE 
                    LOWER(Name) LIKE %s OR LOWER(Vorname) LIKE %s OR LOWER(Firma) LIKE %s
                ORDER BY Name ASC
            """
            like_query = f"%{query.lower()}%"
            cursor.execute(sql_query, [like_query, like_query, like_query])
            rows = cursor.fetchall()

        results = [
            {
                "adresse_id": row[0],
                "name": row[1],
                "vorname": row[2],
                "firma": row[3],
                "strasse": row[4],
                "ort": row[5],
                "plz": row[6],
                "telefon1": row[7],
                "telefon3": row[8],
                "email": row[9],
            }
            for row in rows
        ]
        return JsonResponse(results, safe=False)
    except Exception as e:
        logger.error(f"Error fetching autocomplete data: {e}")
        return JsonResponse([], safe=False)

from django.db.utils import OperationalError
from django.db import connections
from django.http import JsonResponse

def database_status(request):
    databases = ['default', 'isllogs', 'address_db']
    status = {}

    for db in databases:
        try:
            connection = connections[db]
            connection.ensure_connection()
            status[db] = "Connected"
        except OperationalError as e:
            status[db] = f"Disconnected: {str(e)}"
        except KeyError:
            status[db] = "Not Configured"
        except Exception as e:
            status[db] = f"Error: {str(e)}"

    return JsonResponse(status)

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Registration successful! You are now logged in.")
            login(request, user)  # Benutzer automatisch einloggen
            return redirect('dashboard')  # Weiterleitung nach erfolgreicher Registrierung
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = RegisterForm()

    return render(request, 'registration/register.html', {'form': form})

@login_required
def profile(request):
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        theme = request.POST.get('theme')
        valid_themes = [
            'light', 'dark', 'modern', 'soft-blue', 'soft-green',
            'vintage', 'high-contrast', 'elegant', 'sunset', 'neon', 'pastel'
        ]
        if theme in valid_themes:
            profile.theme = theme
            profile.save()
            messages.success(request, "Theme updated successfully.")
        else:
            messages.error(request, "Invalid theme selected.")

    context = {
        'user': request.user,
        'profile': profile,
        'themes': valid_themes,
    }
    return render(request, 'profile.html', context)

def garantie_list(request):
    garantien = Garantie.objects.all()
    return render(request, 'garantie_tracker.html', {'garantien': garantien})

def garantie_create(request):
    form = GarantieForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Garantie erfolgreich hinzugefügt.")
            return redirect('garantie_list')
    return render(request, 'garantie_form.html', {'form': form, 'garantie': None})

def garantie_delete(request, pk):
    garantie = get_object_or_404(Garantie, pk=pk)
    if request.method == 'POST':
        garantie.delete()
        messages.success(request, "Garantie erfolgreich gelöscht.")
        return redirect('garantie_list')
    return render(request, 'garantie_confirm_delete.html', {'garantie': garantie})

def garantie_update(request, pk):
    garantie = get_object_or_404(Garantie, pk=pk)
    form = GarantieForm(request.POST or None, instance=garantie)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Garantie erfolgreich aktualisiert.")
            return redirect('garantie_list')
    return render(request, 'garantie_form.html', {'form': form, 'garantie': garantie})

def rma_manager_selection(request):
    return render(request, 'rma_manager_selection.html')

def general_rma(request):
    tickets = RMATicket.objects.filter(category='general')
    return render(request, 'rma_general.html', {'tickets': tickets})

def computacenter_rma(request):
    tickets = RMATicket.objects.filter(category='computacenter')
    return render(request, 'computacenter_rma.html', {'tickets': tickets})

def rma_logs(request):
    log_file = "rma_log_reader.log"
    log_lines = []

    try:
        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-8") as file:
                log_lines = file.readlines()[-100:]
        else:
            log_lines = ["Log file not found."]
    except Exception as e:
        log_lines = [f"Error reading log file: {str(e)}"]
        logger.error(f"Error reading log file: {e}")

    return render(request, 'rma_logs.html', {'log_lines': log_lines})

def run_email_import_script():
    while True:
        try:
            import subprocess
            subprocess.run(["python", "email_import.py"])
        except Exception as e:
            logger.error(f"Error running email import script: {e}")
        time.sleep(900)  # 15 Minuten warten

threading.Thread(target=run_email_import_script, daemon=True).start()

def start_rma_email_import(request):
    try:
        # Vollständigen Pfad zum Skript angeben
        script_path = os.path.join(settings.BASE_DIR, 'utils', 'email_import.py')
        subprocess.Popen(["python", script_path])
        messages.success(request, "RMA Email Import Script started.")
    except Exception as e:
        messages.error(request, f"Failed to start RMA Email Import script: {e}")
    return redirect('tasks')

def rma_list(request):
    query = request.GET.get('q', '').strip()
    # Search across multiple fields:
    tickets = RMATicket.objects.all()
    if query:
        tickets = tickets.filter(
            Q(ticketnummer__icontains=query) |
            Q(firma__icontains=query) |
            Q(modell__icontains=query) |
            Q(seriennummer__icontains=query) |
            Q(fehler__icontains=query)
        )

    # Separate open vs. closed
    open_tickets = tickets.filter(abgeschlossen=False).order_by('-created_at')
    closed_tickets = tickets.filter(abgeschlossen=True).order_by('-created_at')

    return render(request, 'rma_list.html', {
        'query': query,
        'open_tickets': open_tickets,
        'closed_tickets': closed_tickets,
    })

def close_ticket_view(request, ticket_id):
    try:
        ticket = RMATicket.objects.get(id=ticket_id)
        ticket.abgeschlossen = True
        ticket.save()
    except RMATicket.DoesNotExist:
        pass
    # Depending on category, redirect to the appropriate page
    return redirect('computacenter_rma')  # or 'general_rma'

def reopen_ticket_view(request, ticket_id):
    try:
        ticket = RMATicket.objects.get(id=ticket_id)
        ticket.abgeschlossen = False
        ticket.save()
    except RMATicket.DoesNotExist:
        pass
    # Depending on category, redirect to the appropriate page
    return redirect('computacenter_rma')  # or 'general_rma'



def computacenter_rma(request):
    # 1) Handle optional search query
    query = request.GET.get('q', '').strip()

    # 2) Query all tickets in 'computacenter' category
    all_tickets = RMATicket.objects.filter(category='computacenter')

    # 3) If there is a search query, filter across multiple fields
    if query:
        all_tickets = all_tickets.filter(
            Q(ticketnummer__icontains=query) |
            Q(firma__icontains=query) |
            Q(modell__icontains=query) |
            Q(seriennummer__icontains=query) |
            Q(fehler__icontains=query)
        )

    # 4) Separate open vs. closed
    open_tickets = all_tickets.filter(abgeschlossen=False).order_by('-created_at')
    closed_tickets = all_tickets.filter(abgeschlossen=True).order_by('-created_at')

    # 5) If it's a POST, assume the user is creating a new ticket
    if request.method == "POST":
        ticketnummer = request.POST.get("ticketnummer", "").strip()
        firma = request.POST.get("firma", "").strip()
        modell = request.POST.get("modell", "").strip()
        seriennummer = request.POST.get("seriennummer", "").strip()
        fehler = request.POST.get("fehler", "").strip()

        # For demonstration, set created_at to now (or allow user input)
        created_time = timezone.now()

        if ticketnummer:  # minimal requirement
            RMATicket.objects.create(
                ticketnummer=ticketnummer,
                firma=firma,
                modell=modell,
                seriennummer=seriennummer,
                fehler=fehler,
                created_at=created_time,
                abgeschlossen=False,
                category='computacenter'
            )
        return redirect('computacenter_rma')  # Refresh page

    # 6) Render the template, passing open_tickets and closed_tickets
    context = {
        'query': query,
        'open_tickets': open_tickets,
        'closed_tickets': closed_tickets,
    }
    return render(request, 'computacenter_rma.html', context)

def edit_ticket(request, ticket_id):
    # 1) Fetch the ticket
    ticket = get_object_or_404(RMATicket, id=ticket_id)

    if request.method == "POST":
        # 2) Update the fields
        ticket.ticketnummer = request.POST.get("ticketnummer", ticket.ticketnummer)
        ticket.firma = request.POST.get("firma", ticket.firma)
        ticket.modell = request.POST.get("modell", ticket.modell)
        ticket.seriennummer = request.POST.get("seriennummer", ticket.seriennummer)
        ticket.fehler = request.POST.get("fehler", ticket.fehler)
        ticket.save()

        messages.success(request, "Ticket updated successfully.")
        # Optionally, redirect back to the same category:
        if ticket.category == 'computacenter':
            return redirect('computacenter_rma')
        return redirect('general_rma')

    # For GET, show an edit form:
    return render(request, 'rma_edit_ticket.html', {'ticket': ticket})

def delete_ticket(request, ticket_id):
    ticket = get_object_or_404(RMATicket, id=ticket_id)
    if request.method == "POST":
        ticket.delete()
        messages.success(request, "Ticket deleted successfully.")
        if ticket.category == 'computacenter':
            return redirect('computacenter_rma')
        return redirect('general_rma')

    # If GET, maybe show a confirm delete template:
    return render(request, 'rma_confirm_delete.html', {'ticket': ticket})

def print_ticket(request, ticket_id):
    # 1) fetch the ticket
    ticket = get_object_or_404(RMATicket, id=ticket_id)
    return render(request, 'rma_print_ticket.html', {'ticket': ticket})

def pdf_ticket(request, ticket_id):
    ticket = get_object_or_404(RMATicket, id=ticket_id)

    # 2) generate PDF via ReportLab or any other library
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

