# email_import.py
import os
import re
import pyodbc
from datetime import datetime, timedelta
from dotenv import load_dotenv
import win32com.client as win32
import logging
from logging.handlers import RotatingFileHandler

# Load environment variables from .env file
load_dotenv()

# Set up logging
logger = logging.getLogger("EmailLogger")
logger.setLevel(logging.INFO)
if not logger.handlers:
    email_handler = RotatingFileHandler("email_import.log", maxBytes=5*1024*1024, backupCount=3)
    email_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    email_handler.setFormatter(email_formatter)
    logger.addHandler(email_handler)

# Regex patterns
TICKETNUMMER_PATTERN = re.compile(r"CS\d+", re.IGNORECASE)
FIRMA_PATTERN = re.compile(r"Name/Firma:\s*(.*)", re.IGNORECASE)
SERIENNUMMER_PATTERN = re.compile(r"Seriennummer:\s*(.*)", re.IGNORECASE)
FEHLER_PATTERN = re.compile(r"Fehlerbeschreibung:\s*(.*)", re.IGNORECASE)

# DB config from environment
DB_SERVER = os.getenv("tDB_SERVER")
DB_NAME = os.getenv("tDB_NAME")
DB_USER = os.getenv("tDB_USERNAME")
DB_PASSWORD = os.getenv("tDB_PASSWORD")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")

# Email config
COMPUTACENTER_FOLDER = os.getenv("COMPUTACENTER_FOLDER", "Computacenter")
EMAIL_TIME_WINDOW_DAYS = int(os.getenv("EMAIL_TIME_WINDOW_DAYS", 60))

def get_db_connection():
    """
    Returns a pyodbc connection or None on error.
    """
    try:
        conn = pyodbc.connect(
            f"DRIVER={{{DB_DRIVER}}};"
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_NAME};"
            f"UID={DB_USER};"
            f"PWD={DB_PASSWORD};"
            "TrustServerCertificate=yes;"
        )
        return conn
    except pyodbc.Error as e:
        logger.error(f"Error connecting to Ticket Database: {e}")
        return None

def find_ticketnummer(subject, body):
    """
    Finds a ticket number ('CSxxxxx') in either subject or body.
    """
    match = TICKETNUMMER_PATTERN.search(subject) or TICKETNUMMER_PATTERN.search(body)
    if match:
        return match.group(0).upper()
    return None

def strip_repeated_disclaimers(full_text):
    """
    Removes repeated disclaimers or boilerplate from the email text.
    Cuts off at certain keywords like 'Freundliche Grüsse' or
    'Wichtige Info vor der Reparatur!'.
    """
    disclaimers = [
        "Freundliche Grüsse",
        "Kind Regards",
        "Wichtige Info vor der Reparatur!"
        # etc...
    ]
    lines = full_text.splitlines()
    cleaned = []
    for line in lines:
        if any(disc.lower() in line.lower() for disc in disclaimers):
            break
        cleaned.append(line)
    return "\n".join(cleaned).strip()

def extract_email_details(body):
    """
    Extract 'firma', 'seriennummer', 'fehler' from cleaned email body.
    """
    details = {"firma": None, "seriennummer": None, "fehler": None}

    firma_match = FIRMA_PATTERN.search(body)
    serien_match = SERIENNUMMER_PATTERN.search(body)
    fehler_match = FEHLER_PATTERN.search(body)

    if firma_match:
        details["firma"] = firma_match.group(1).strip()
    if serien_match:
        details["seriennummer"] = serien_match.group(1).strip()
    if fehler_match:
        details["fehler"] = fehler_match.group(1).strip()

    return details

def insert_ticket(ticketnummer, details, email_received_date, category="computacenter"):
    """
    Insert a new ticket into the 'tickets' table if it doesn't already exist.
    Uses email_received_date as created_at.
    """
    conn = get_db_connection()
    if conn is None:
        return

    cursor = conn.cursor()
    try:
        # Check if ticket already exists
        cursor.execute("SELECT 1 FROM tickets WHERE ticketnummer = ?", (ticketnummer,))
        if cursor.fetchone():
            logger.info(f"Ticket {ticketnummer} already exists; skipping insertion.")
            return

        cursor.execute("""
            INSERT INTO tickets (
                ticketnummer, firma, seriennummer, fehler,
                created_at, abgeschlossen, category
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            ticketnummer,
            details.get("firma"),
            details.get("seriennummer"),
            details.get("fehler"),
            email_received_date,
            False,
            category
        ))
        conn.commit()
        logger.info(f"Ticket {ticketnummer} successfully inserted.")
    except pyodbc.Error as e:
        logger.error(f"Error inserting ticket {ticketnummer}: {e}")
    finally:
        conn.close()

def close_ticket(ticketnummer):
    """
    Marks a ticket as closed (abgeschlossen = 1).
    """
    logger.info(f"Closing ticket {ticketnummer}...")
    conn = get_db_connection()
    if conn is None:
        return

    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE tickets
            SET abgeschlossen = 1
            WHERE ticketnummer = ?
        """, (ticketnummer,))
        conn.commit()

        if cursor.rowcount > 0:
            logger.info(f"Ticket {ticketnummer} successfully closed.")
        else:
            logger.info(f"No open ticket found for {ticketnummer}.")
    except pyodbc.Error as e:
        logger.error(f"Error closing ticket {ticketnummer}: {e}")
    finally:
        conn.close()

def process_outlook_emails(folder_name=COMPUTACENTER_FOLDER, category="computacenter"):
    """
    Processes emails from an Outlook folder within EMAIL_TIME_WINDOW_DAYS.
    - Checks for 'abschluss' or 'abgeschlossen' to close tickets.
    - Otherwise, extracts info and inserts new tickets.
    """
    try:
        outlook = win32.Dispatch("Outlook.Application").GetNamespace("MAPI")
        inbox = outlook.GetDefaultFolder(6)  # 6 = Inbox
        folder = inbox.Folders.Item(folder_name)
    except Exception as e:
        logger.warning(f"Folder '{folder_name}' not found or error: {e}")
        return

    # We'll compare naive datetimes to avoid offset issues
    time_window = timedelta(days=EMAIL_TIME_WINDOW_DAYS)
    cutoff_date = datetime.now() - time_window  # naive

    count_processed = 0
    for message in folder.Items:
        # Convert message.ReceivedTime to a naive datetime by stripping tzinfo
        received_time_naive = message.ReceivedTime.replace(tzinfo=None)

        # Only parse if the email is within the time window
        if received_time_naive < cutoff_date:
            continue

        count_processed += 1
        subject = message.Subject or ""
        body_original = message.Body or ""

        # 1) Find ticket number
        ticketnummer = find_ticketnummer(subject, body_original)
        if not ticketnummer:
            continue

        # 2) Check for closure keywords
        body_lower = body_original.lower()
        if "abschluss" in body_lower or "abgeschlossen" in body_lower:
            close_ticket(ticketnummer)
            continue

        # 3) Clean disclaimers and parse details
        cleaned_body = strip_repeated_disclaimers(body_original)
        details = extract_email_details(cleaned_body)

        # 4) Insert new ticket with the real email date
        insert_ticket(
            ticketnummer,
            details,
            email_received_date=received_time_naive,
            category=category
        )

    logger.info(f"Processed {count_processed} email(s) in '{folder_name}' from the last {EMAIL_TIME_WINDOW_DAYS} days.")

def run_email_import():
    """
    One-shot email import process.
    """
    logger.info("=== Email Import One-Shot Start ===")
    try:
        process_outlook_emails()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    logger.info("=== Email Import One-Shot Complete ===")

if __name__ == "__main__":
    run_email_import()
