# pcrmgmtAPP/views.py
import os
from django.http import FileResponse, HttpResponse
from django.db import connection
from django.http import JsonResponse
from django.db import connections
from django.views.decorators.http import require_GET
from pcrmgmtProject import settings
from .utils.encryption import decrypt_password, encrypt_password
import logging
from .models import OfficeAccount
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
import threading
import time
from .utils.isl_log_reader import main as run_isl_log_reader  # Assuming the main function runs the script
from django.contrib.auth import login
from .forms import RegisterForm
from .models import UserProfile
from .models import Garantie
from .forms import GarantieForm
from .models import RMATicket
import subprocess
import json
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.utils.safestring import mark_safe
from django.http import JsonResponse
from .models import GDataAccount, LicenseKey

logger = logging.getLogger(__name__)

# Global variables for the ISL script
script_running = False
script_thread = None
script_start_time = None  # For tracking ISL script last run
CONFIG_PATH = "config.json"

#############################################
# Helper: run script in background
#############################################
def run_script_in_background(interval_seconds):
    global script_running, script_start_time
    while script_running:
        script_start_time = timezone.now()
        logger.info("Starting ISL Log Reader...")
        try:
            run_isl_log_reader()
            logger.info("ISL Log Reader completed successfully.")
        except Exception as e:
            logger.error(f"Error in ISL Log Reader: {e}")
        script_start_time = None
        if script_running:
            logger.info(f"Next run in {interval_seconds} seconds.")
            time.sleep(interval_seconds)

def start_isl_log_reader():
    global script_running, script_thread
    if not script_running:
        # get interval from config or default 10 min
        interval_minutes = 10
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                conf = json.load(f)
                interval_minutes = conf.get("isl_script_interval", 10)
        interval_seconds = interval_minutes * 60
        script_running = True
        script_thread = threading.Thread(
            target=run_script_in_background,
            args=(interval_seconds,),
            daemon=True
        )
        script_thread.start()

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
@login_required
def tasks_view(request):
    config = {
        "isl_script_interval": 10,
        "rma_script_interval": 15,
        "script_running": False,
        "rma_script_running": False,
        "script_start_time": None,
        "rma_script_start_time": None,
        "last_script_success": True,
        "last_rma_success": True,
    }

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as file:
                config.update(json.load(file))
        except json.JSONDecodeError as e:
            messages.error(request, f"Error reading config.json: {e}")
            with open(CONFIG_PATH, "w") as file:
                json.dump(config, file, indent=4)

    if request.method == "POST":
        # ISL script
        if "start_script" in request.POST:
            config["script_running"] = True
            with open(CONFIG_PATH, "w") as file:
                json.dump(config, file, indent=4)
            messages.info(request, "Starting ISL Log Reader background thread...")
            start_isl_log_reader()

        elif "stop_script" in request.POST:
            config["script_running"] = False
            with open(CONFIG_PATH, "w") as file:
                json.dump(config, file, indent=4)
            messages.info(request, "Stopping ISL Log Reader background thread...")
            stop_isl_log_reader()

        elif "set_interval" in request.POST:
            new_interval = request.POST.get("script_interval")
            try:
                config["isl_script_interval"] = int(new_interval)
                messages.success(request, f"ISL Log Reader interval updated to {new_interval} minutes.")
            except ValueError:
                messages.error(request, "Invalid interval for ISL Log Reader.")

        # RMA script
        elif "start_rma_script" in request.POST:
            config["rma_script_running"] = True
            messages.info(request, "Starting RMA Email Import script (stub).")
            # if you have a real function, call it here

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

        with open(CONFIG_PATH, "w") as file:
            json.dump(config, file, indent=4)

        return redirect("tasks")

    context = {
        "isl_script_interval": config.get("isl_script_interval"),
        "rma_script_interval": config.get("rma_script_interval"),
        "script_running": config.get("script_running"),
        "rma_script_running": config.get("rma_script_running"),
        "last_script_success": config.get("last_script_success"),
        "last_rma_success": config.get("last_rma_success"),
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
            startzeit_dt = datetime.datetime.strptime(startzeit_str, "%Y-%m-%dT%H:%M")
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
    Returns JSON array of matching customers from the CRM_ADRESSEN table.
    We'll fetch up to 200 matches and also return extra fields for street, plz, ort, etc.
    """
    query = request.GET.get('query', '').strip()
    results = []
    if query:
        like_pattern = f"%{query}%"
        try:
            with connections['address_db'].cursor() as cursor:
                # Select columns needed for autocomplete
                sql = """
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
                    WHERE (
                        [Vorname]  LIKE %s OR
                        [Name]     LIKE %s OR
                        [Firma]    LIKE %s OR
                        [Strasse]  LIKE %s OR
                        [Ort]      LIKE %s OR
                        [PLZ]      LIKE %s OR
                        [Email]    LIKE %s
                    )
                    ORDER BY [Name], [Vorname]
                """
                # We'll pass the same pattern 7 times
                params = [like_pattern] * 7
                cursor.execute(sql, params)
                rows = cursor.fetchall()

                for row in rows:
                    # row => (Vorname, Name, Firma, Strasse, PLZ, Ort, Telefon1, Telefon3, Email)
                    results.append({
                        'vorname':   row[0] or "",
                        'nachname':  row[1] or "",  # [Name] if it is last name
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
    while True:
        try:
            import subprocess
            subprocess.run(["python", "pcrmgmtAPP/utils/email_import.py"])
        except Exception as e:
            logger.error(f"Error running email import script: {e}")
        time.sleep(900)  # 15 Minuten warten
threading.Thread(target=run_email_import_script, daemon=True).start()

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