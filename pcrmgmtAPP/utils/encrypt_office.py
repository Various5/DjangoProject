import os
import pyodbc
from dotenv import load_dotenv
from pcrmgmtAPP.utils.encryption import encrypt_password

# .env-Datei laden
load_dotenv()

# Verbindungskonfiguration aus der .env
SERVER   = os.getenv("DB_HOST")
DATABASE = os.getenv("DB_NAME")
UID      = os.getenv("DB_USER")
PWD      = os.getenv("DB_PASSWORD")
DRIVER   = os.getenv("DB_DRIVER", "ODBC Driver 17 for SQL Server")

conn_string = (
    f"DRIVER={{{DRIVER}}};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"UID={UID};"
    f"PWD={PWD};"
    "TrustServerCertificate=yes;"
)

# Verbindung zur Datenbank herstellen
conn = pyodbc.connect(conn_string)
cursor = conn.cursor()

# Alle Einträge aus der Tabelle abfragen
cursor.execute("SELECT id, passwort FROM dbo.office_accounts")
rows = cursor.fetchall()

for row in rows:
    record_id, plain_pw = row
    # Falls das Passwort bereits verschlüsselt ist (typischerweise beginnt ein Fernet Ciphertext mit "gAAAAA")
    if plain_pw.startswith("gAAAAA"):
        continue
    # Passwort verschlüsseln
    encrypted_pw = encrypt_password(plain_pw)
    cursor.execute("UPDATE dbo.office_accounts SET passwort = ? WHERE id = ?", (encrypted_pw, record_id))
    print(f"Record {record_id} updated.")

conn.commit()
conn.close()
