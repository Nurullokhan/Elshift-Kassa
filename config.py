import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

_admin_raw = os.getenv("ADMIN_CHAT_ID", "").strip()
try:
    ADMIN_CHAT_ID = int(_admin_raw) if _admin_raw else 0
except ValueError:
    ADMIN_CHAT_ID = 0
GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "credentials.json")
GOOGLE_SHEETS_CREDENTIALS_JSON = os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON")
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL")

