import os
import re
import pyodbc
import requests
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta
import calendar
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import json5

# Load environment variables from .env file
load_dotenv()

# Setup Logging
logger = logging.getLogger("ISLLogger")
logger.setLevel(logging.INFO)
if not logger.handlers:
    isl_handler = RotatingFileHandler("isl_log_reader.log", maxBytes=5 * 1024 * 1024, backupCount=3)
    isl_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    isl_handler.setFormatter(isl_formatter)
    logger.addHandler(isl_handler)

# Database Configuration
DB_SERVER = os.getenv("nDB_SERVER")
DB_NAME = os.getenv("nDB_NAME")
DB_USER = os.getenv("nDB_USER")
DB_PASSWORD = os.getenv("nDB_PASSWORD")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")

# API Configuration
BASE_URL = os.getenv("BASE_URL", "http://localhost:7615")
LOGIN_URL = f"{BASE_URL}/conf"
LOGIN_API_URL = f"{BASE_URL}/conf/api/login"
SESSION_HISTORY_URL = f"{BASE_URL}/conf"

USERNAME = os.getenv("ISL_USERNAME")
PASSWORD = os.getenv("ISL_PASSWORD")
SHOW_DELETED = os.getenv("SHOW_DELETED", "")


def get_db_connection():
    """
    Establish a connection to the database.
    Returns a pyodbc.Connection or None if it fails.
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
        logger.info("Successfully connected to the database.")
        return conn
    except pyodbc.Error as e:
        logger.error(f"Database connection failed: {e}")
        return None


def setup_database():
    """
    Create the SessionLog_new table if it doesn't exist.
    """
    conn = get_db_connection()
    if conn is None:
        logger.fatal("Database connection failed. Setup aborted.")
        return
    cursor = conn.cursor()
    try:
        cursor.execute("""
            IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='SessionLog_new' AND xtype='U')
            CREATE TABLE dbo.SessionLog_new (
                SessionID NVARCHAR(255) PRIMARY KEY,
                Startzeit DATETIME,
                Dauer NVARCHAR(50),
                Benutzer NVARCHAR(255),
                NameFirma NVARCHAR(255),
                Verrechnet BIT,
                Memo NVARCHAR(MAX)
            )
        """)
        conn.commit()
        logger.info("Database setup completed successfully.")
    except pyodbc.Error as e:
        logger.error(f"Error setting up the database: {e}")
    finally:
        conn.close()


def get_last_session_time():
    """
    Returns the maximum Startzeit (UTC) from SessionLog_new, or None if table empty.
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(Startzeit) FROM dbo.SessionLog_new")
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            # This is a Python datetime in UTC (assuming it was stored as UTC).
            return row[0]
        return None
    except Exception as e:
        logger.error(f"Error retrieving last session time: {e}")
        return None


def extract_data_variable(html_text):
    """
    Extract the 'data' variable from the HTML <script> tags. Returns dict or None.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    script_tags = soup.find_all("script", string=lambda text: text and "data=" in text)
    for script_tag in script_tags:
        script_content = script_tag.string
        match = re.search(r"data\s*=\s*({.*?});", script_content, re.DOTALL)
        if match:
            data_str = match.group(1)
            try:
                return json5.loads(data_str)
            except Exception as e:
                logger.error(f"Error parsing data variable: {e}")
    logger.error("No valid data variable found in HTML.")
    return None


def extract_value(cell):
    """
    Safely extract and clean string value from a cell, which might be dict or str.
    """
    if isinstance(cell, dict):
        return cell.get('text') or cell.get('value') or ""
    elif isinstance(cell, str):
        return cell.strip()
    return ""


def parse_bit(value):
    """
    Parse 'true', '1', 'yes' → True; else False. Also handle bool directly.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ['true', '1', 'yes']
    return bool(value)


def login_to_isl(session):
    """
    Logs into the ISL system, sets cookies, etc. Returns True if successful.
    """
    try:
        logger.info("Accessing login page...")
        response = session.get(LOGIN_URL, allow_redirects=True)
        if response.status_code != 200:
            logger.error(f"Failed to retrieve login page: {response.status_code}")
            return False

        data = extract_data_variable(response.text)
        if not data:
            logger.error("No data variable found on the login page.")
            return False

        post_token = data.get('post_token')
        origin = data.get('secure_origin')
        cpsessid = data.get('CPSESSID')
        if not post_token or not origin:
            logger.error("Required tokens are missing on the login page.")
            return False

        payload = {
            "username": USERNAME,
            "password": PASSWORD,
            "post_token": post_token,
            "origin": origin,
        }
        headers = {
            "Cookie": f"CPSESSID={cpsessid}",
            "User-Agent": "Mozilla/5.0",
            "Referer": LOGIN_URL,
            "Origin": BASE_URL,
        }
        logger.info("Submitting login form...")
        login_response = session.post(LOGIN_API_URL, data=payload, headers=headers, allow_redirects=True)
        if login_response.status_code == 200:
            new_cpsessid = session.cookies.get('CPSESSID')
            if (new_cpsessid and new_cpsessid != cpsessid) or ("Logout" in login_response.text):
                logger.info("Login successful.")
                return True
            else:
                logger.error("Login failed (CPSESSID not updated and 'Logout' not found).")
                return False
        else:
            logger.error(f"Login failed: {login_response.status_code}, {login_response.text}")
            return False
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return False


def get_username_from_sessiondata(sessionData):
    """
    Extract the username from sessionData (an array of keys/values) if available.
    """
    for field in sessionData:
        if isinstance(field, list) and len(field) == 2:
            key = field[0]
            val = field[1]
            if key == "User" and isinstance(val, dict):
                user_val = val.get('value', "")
                # Example: remove domain prefix if needed
                user_val = user_val.replace("\\\\pcrepair.local\\", "")
                return user_val
    return ""


def get_session_details(session, session_id):
    """
    Retrieves extra info for a session (Memo, NameFirma, Verrechnet, user override).
    """
    detail_url = f"{BASE_URL}/conf?page=configuration%23isllight_session&id={session_id}"
    logger.debug(f"Fetching details for Session ID: {session_id}")
    response = session.get(detail_url, allow_redirects=True)
    if response.status_code != 200:
        logger.error(f"Failed to retrieve details: {response.status_code}")
        return {"Memo": "", "NameFirma": "", "Verrechnet": False, "User": ""}

    data = extract_data_variable(response.text)
    if not data:
        logger.error("No data variable found on the detail page.")
        return {"Memo": "", "NameFirma": "", "Verrechnet": False, "User": ""}

    sessionData = data.get('sessionData', [])
    if not isinstance(sessionData, list):
        sessionData = []
    user_val = get_username_from_sessiondata(sessionData)

    messages = data.get('messages')
    if not messages:
        return {"Memo": "", "NameFirma": "", "Verrechnet": False, "User": user_val}

    msg_columns = messages.get('columns', [])
    msg_rows = messages.get('rows', [])
    column_titles = [col.get('title', '').strip('"') for col in msg_columns]

    def find_col_idx(col_name):
        for i, title in enumerate(column_titles):
            if col_name.lower() in title.lower():
                return i
        return None

    memo_idx = find_col_idx("Memo")
    name_firma_idx = find_col_idx("NameFirma")
    rechnung_idx = find_col_idx("RechnungErstellt")
    client_id_idx = find_col_idx("ClientID")

    if not msg_rows:
        return {"Memo": "", "NameFirma": "", "Verrechnet": False, "User": user_val}

    last_msg = msg_rows[-1]

    def safe_get(row, idx):
        if idx is not None and idx < len(row):
            return extract_value(row[idx])
        return ""

    memo = safe_get(last_msg, memo_idx)
    name_firma = safe_get(last_msg, name_firma_idx)
    rechnung_val = safe_get(last_msg, rechnung_idx)
    verrechnet = parse_bit(rechnung_val)
    client_id_val = safe_get(last_msg, client_id_idx)

    # If "ISL-AlwaysOn", override user
    if client_id_val == "ISL-AlwaysOn":
        user_val = "ISL Always On"

    return {
        "Memo": memo,
        "NameFirma": name_firma,
        "Verrechnet": verrechnet,
        "User": user_val
    }


def get_sessions_from_history(session, created_after_utc, created_before_utc):
    """
    Retrieves sessions from ISL history in [created_after_utc, created_before_utc].
    Times are UTC. We convert them to int (Unix epoch).
    """
    logger.info("Fetching sessions from history...")
    if created_after_utc is None:
        # If DB is empty, define some safe earliest date
        created_after_utc = datetime(2020, 1, 1, tzinfo=timezone.utc)

    search_from = int(created_after_utc.timestamp())
    search_to = int(created_before_utc.timestamp())

    logger.info(f"Search window (UTC epoch): {search_from} to {search_to}")
    logger.info(f"Search window (UTC datetime): {created_after_utc} to {created_before_utc}")

    params = {
        "page": "sessions#isllight#history",
        "search_from": search_from,
        "search_to": search_to,
        "search_user": "",
        "show_deleted": SHOW_DELETED
    }
    response = session.get(SESSION_HISTORY_URL, params=params, allow_redirects=True)
    if response.status_code != 200:
        logger.error(f"Failed to retrieve history: {response.status_code}")
        return []

    data = extract_data_variable(response.text)
    if not data:
        logger.error("No data retrieved from the history page.")
        return []

    light_session = data.get('lightSession')
    if not light_session:
        logger.warning("No 'lightSession' data found.")
        return []

    rows = light_session.get('rows', [])
    columns = light_session.get('columns', [])
    column_titles = [col.get('title', '').strip('"') for col in columns]

    # Map columns
    try:
        idx_session_id = column_titles.index("Session ID")
        idx_created_on = column_titles.index("Created on")
        idx_duration = column_titles.index("Duration")
        idx_user = column_titles.index("User")
    except ValueError as ve:
        logger.error(f"Expected column missing: {ve}")
        return []

    sessions = []
    for row in rows:
        if not isinstance(row, list):
            logger.error(f"Unexpected row format: {row}")
            continue

        session_id_raw = row[idx_session_id] if idx_session_id < len(row) else {}
        created_on_raw = row[idx_created_on] if idx_created_on < len(row) else {}
        duration_raw = row[idx_duration] if idx_duration < len(row) else {}
        user_raw = row[idx_user] if idx_user < len(row) else {}

        session_id = extract_value(session_id_raw)
        created_on_str = extract_value(created_on_raw)
        duration = extract_value(duration_raw)
        user = extract_value(user_raw)

        startzeit = None
        if created_on_str and created_on_str.isdigit():
            ts = int(created_on_str)
            startzeit = datetime.fromtimestamp(ts, tz=timezone.utc)

        if not session_id or not startzeit:
            logger.warning(f"Invalid session row: SessionID={session_id}, Startzeit={startzeit}")
            continue

        sessions.append({
            "SessionID": session_id,
            "Startzeit": startzeit,
            "Dauer": duration,
            "Benutzer": user
        })

    logger.info(f"Found {len(sessions)} sessions in history.")
    return sessions


def upsert_session_to_db(session_data):
    """
    Inserts a new session or updates existing (without overwriting Verrechnet).
    """
    try:
        conn = get_db_connection()
        if conn is None:
            logger.error("Cannot upsert session without a database connection.")
            return
        cursor = conn.cursor()
        try:
            # Try to INSERT
            cursor.execute("""
                INSERT INTO SessionLog_new (
                    SessionID, Startzeit, Dauer, Benutzer, NameFirma, Verrechnet, Memo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                session_data["SessionID"],
                session_data["Startzeit"],
                session_data["Dauer"],
                session_data["Benutzer"],
                session_data["NameFirma"],
                session_data["Verrechnet"],
                session_data["Memo"]
            ))
            conn.commit()
            logger.info(f"Session {session_data['SessionID']} inserted successfully.")
        except pyodbc.IntegrityError:
            # Already exists => update without overwriting Verrechnet
            logger.info(f"Session {session_data['SessionID']} exists. Updating (preserve Verrechnet).")
            try:
                cursor.execute("""
                    UPDATE SessionLog_new
                    SET Startzeit = ?, 
                        Dauer = ?, 
                        Benutzer = ?, 
                        NameFirma = ?, 
                        Memo = ?
                    WHERE SessionID = ?
                """, (
                    session_data["Startzeit"],
                    session_data["Dauer"],
                    session_data["Benutzer"],
                    session_data["NameFirma"],
                    session_data["Memo"],
                    session_data["SessionID"]
                ))
                conn.commit()
                logger.info(f"Session {session_data['SessionID']} updated successfully.")
            except pyodbc.Error as e:
                logger.error(f"Error updating session {session_data['SessionID']}: {e}")
        except Exception as e:
            logger.error(f"Error inserting session {session_data['SessionID']}: {e}")
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Unexpected error during upsert: {e}")


def process_sessions():
    """
    Incrementally fetch new sessions from the last known Startzeit to now.
    Preserve 'Verrechnet' for existing entries.
    """
    try:
        # 1) Figure out the last known session time from DB
        last_session_time_in_db = get_last_session_time()
        if last_session_time_in_db:
            logger.info(f"Last session time in DB: {last_session_time_in_db}")
        else:
            logger.info("No sessions in DB yet. Will fetch from default earliest date.")

        # 2) We'll fetch up to "now + small buffer" in UTC
        created_before_utc = datetime.now(timezone.utc) + timedelta(minutes=1)

        # 3) Login to ISL
        session = requests.Session()
        # (Optional) add retry logic
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            retries = Retry(total=5, backoff_factor=1, status_forcelist=[502, 503, 504])
            adapter = HTTPAdapter(max_retries=retries)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
        except ImportError:
            pass

        if not login_to_isl(session):
            logger.fatal("Login failed. Cannot process sessions.")
            return

        # 4) Get new sessions from [last_session_time_in_db, now]
        sessions = get_sessions_from_history(session, last_session_time_in_db, created_before_utc)
        if not sessions:
            logger.info("No new sessions found in the specified range.")
            return

        logger.info(f"Processing {len(sessions)} new or updated sessions...")
        for s in sessions:
            try:
                # Get detail data (Memo, NameFirma, Verrechnet, possibly corrected User)
                details = get_session_details(session, s["SessionID"])
                # Merge
                session_data = {
                    "SessionID": s["SessionID"],
                    "Startzeit": s["Startzeit"],
                    "Dauer": s["Dauer"],
                    "Benutzer": details.get("User", s["Benutzer"]),
                    "NameFirma": details.get("NameFirma", ""),
                    "Verrechnet": details.get("Verrechnet", False),
                    "Memo": details.get("Memo", "")
                }
                upsert_session_to_db(session_data)
            except Exception as e:
                logger.error(f"Error processing session {s['SessionID']}: {e}")

        logger.info("Session processing completed successfully.")

    except Exception as e:
        logger.error(f"Unexpected error in process_sessions: {e}")


def main():
    logger.info("=== ISL Log Reader Start ===")
    try:
        setup_database()
    except Exception as e:
        logger.fatal(f"Database setup failed: {e}")
        return

    process_sessions()

    logger.info("=== ISL Log Reader Complete ===")


def run_isl_log_reader():
    """
    Wrapper function if you prefer to call run_isl_log_reader() externally.
    """
    main()


if __name__ == "__main__":
    run_isl_log_reader()
