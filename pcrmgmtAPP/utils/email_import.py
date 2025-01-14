import os
import re
import pyodbc
from datetime import datetime, timedelta
from dotenv import load_dotenv
import win32com.client as win32
import logging
from logging.handlers import RotatingFileHandler

load_dotenv()

logger = logging.getLogger("EmailLogger")
logger.setLevel(logging.INFO)

# ---- NEW: log path set to /utils/logs/ next to email_import.py
THIS_DIR = os.path.dirname(__file__)
LOG_DIR = os.path.join(THIS_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "email_import.log")

if not logger.handlers:
    email_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
    email_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    email_handler.setFormatter(email_formatter)
    logger.addHandler(email_handler)

# Regex patterns
TICKETNUMMER_PATTERN = re.compile(r"CS\d+", re.IGNORECASE)
NAME_FIRMA_PATTERN    = re.compile(r"(?i)Name/Firma:\s*(.*)")
SERIENNUMMER_PATTERN  = re.compile(r"(?i)Seriennummer:\s*(.*)")
FEHLER_PATTERN        = re.compile(r"(?i)Fehlerbeschreibung:\s*(.*)")

# DB config
DB_SERVER   = os.getenv("tDB_SERVER")
DB_NAME     = os.getenv("tDB_NAME")
DB_USER     = os.getenv("tDB_USERNAME")
DB_PASSWORD = os.getenv("tDB_PASSWORD")
DB_DRIVER   = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")

# Email config
COMPUTACENTER_FOLDER = os.getenv("COMPUTACENTER_FOLDER", "Computacenter")
EMAIL_TIME_WINDOW_DAYS = int(os.getenv("EMAIL_TIME_WINDOW_DAYS", 60))

def get_db_connection():
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

def insert_ticket(ticketnummer, details, email_received_date, category="computacenter"):
    conn = get_db_connection()
    if conn is None:
        return

    cursor = conn.cursor()
    try:
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
        logger.info(f"Ticket {ticketnummer} inserted. Details: {details}")
    except pyodbc.Error as e:
        logger.error(f"Error inserting ticket {ticketnummer}: {e}")
    finally:
        conn.close()

def close_ticket(ticketnummer):
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

def find_ticketnummer(subject, body):
    """
    Finds 'CSxxxxx' in subject or body.
    """
    match = TICKETNUMMER_PATTERN.search(subject) or TICKETNUMMER_PATTERN.search(body)
    if match:
        return match.group(0).upper()
    return None

def extract_kundendaten_block(email_body):
    """
    Returns the substring from 'Kundendaten' up to 'Ref:MSG' or end of text.
    If 'Kundendaten' not found, return entire body (fallback).
    """
    lower_body = email_body.lower()
    idx_kd = lower_body.find("kundendaten")
    if idx_kd == -1:
        # No 'Kundendaten' found => fallback
        return email_body

    # Start from 'Kundendaten'
    sub = email_body[idx_kd:]
    # Optionally cut off at 'Ref:MSG' if present
    idx_ref = sub.lower().find("ref:msg")
    if idx_ref != -1:
        sub = sub[:idx_ref]

    return sub

def parse_email_details(body):
    """
    Extract firma, seriennummer, fehler from the 'kundendaten' block only.
    If not found, returns None for each.
    """
    # 1) Slice out the relevant block
    block = extract_kundendaten_block(body)

    # 2) Apply the patterns
    details = {
        "firma":        None,
        "seriennummer": None,
        "fehler":       None
    }

    # Name/Firma
    m_firma = NAME_FIRMA_PATTERN.search(block)
    if m_firma:
        details["firma"] = m_firma.group(1).strip()

    # Seriennummer
    m_serien = SERIENNUMMER_PATTERN.search(block)
    if m_serien:
        details["seriennummer"] = m_serien.group(1).strip()

    # Fehlerbeschreibung
    m_fehler = FEHLER_PATTERN.search(block)
    if m_fehler:
        details["fehler"] = m_fehler.group(1).strip()

    return details

def process_outlook_emails(folder_name=COMPUTACENTER_FOLDER, category="computacenter"):
    """
    Processes relevant emails from an Outlook folder, looking up to EMAIL_TIME_WINDOW_DAYS old.
    If 'abschluss' or 'abgeschlossen' in the body => close the ticket.
    Otherwise => parse 'kundendaten' block and insert new tickets.
    """
    try:
        outlook = win32.Dispatch("Outlook.Application").GetNamespace("MAPI")
        inbox = outlook.GetDefaultFolder(6)  # 6 = Inbox
        folder = inbox.Folders.Item(folder_name)
    except Exception as e:
        logger.warning(f"Folder '{folder_name}' not found or error: {e}")
        return

    cutoff_date = datetime.now() - timedelta(days=EMAIL_TIME_WINDOW_DAYS)
    count_processed = 0

    for message in folder.Items:
        received_time_naive = message.ReceivedTime.replace(tzinfo=None)
        if received_time_naive < cutoff_date:
            continue  # older than time window

        subject = message.Subject or ""
        body_original = message.Body or ""
        count_processed += 1

        # 1) Look for ticketnummer
        ticketnummer = find_ticketnummer(subject, body_original)
        if not ticketnummer:
            logger.debug("No Ticketnummer found in email subject/body.")
            continue

        # 2) Check if it wants to close the ticket
        body_lower = body_original.lower()
        if "abschluss" in body_lower or "abgeschlossen" in body_lower:
            close_ticket(ticketnummer)
            continue

        # 3) Parse the 'kundendaten' block for details
        details = parse_email_details(body_original)
        logger.info(f"Parsed details for {ticketnummer}: {details}")

        # 4) Insert ticket if needed
        insert_ticket(ticketnummer, details, received_time_naive, category)

    logger.info(f"Processed {count_processed} email(s) in '{folder_name}' from the last {EMAIL_TIME_WINDOW_DAYS} days.")

def run_email_import():
    logger.info("=== Email Import One-Shot Start ===")
    try:
        process_outlook_emails()
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    logger.info("=== Email Import One-Shot Complete ===")

if __name__ == "__main__":
    run_email_import()