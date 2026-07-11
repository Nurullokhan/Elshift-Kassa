import logging
import json
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

from config import GOOGLE_SHEETS_CREDENTIALS_FILE, GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SHEET_URL

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

_client = None
_spreadsheet = None

# Auth natijalarini keshlash (Google Sheets ga har safar murojaat qilmaslik uchun)
_auth_cache: dict[int, tuple[bool, str, float]] = {}
AUTH_CACHE_TTL = 300  # 5 daqiqa


# ─── Ulanish ─────────────────────────────────────────────────────────────────

def _get_client():
    global _client
    if _client is None:
        try:
            json_str = GOOGLE_SHEETS_CREDENTIALS_JSON or GOOGLE_SHEETS_CREDENTIALS_FILE
            if json_str and json_str.strip().startswith("{"):
                creds_info = json.loads(json_str)
                creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
            else:
                creds = Credentials.from_service_account_file(
                    GOOGLE_SHEETS_CREDENTIALS_FILE, scopes=SCOPES
                )
            _client = gspread.authorize(creds)
            logging.info("Google Sheets ga ulandi.")
        except Exception as e:
            logging.error(f"Google Sheets ulanish xatosi: {e}")
            return None
    return _client


def _get_spreadsheet():
    global _spreadsheet
    if _spreadsheet is None:
        client = _get_client()
        if client is None:
            return None
        try:
            _spreadsheet = client.open_by_url(GOOGLE_SHEET_URL)
        except Exception as e:
            logging.error(f"Spreadsheet ochishda xato: {e}")
            return None
    return _spreadsheet


def _reset_cache():
    global _client, _spreadsheet
    _client = None
    _spreadsheet = None


def _get_kassabot_ws() -> gspread.Worksheet | None:
    """'KassaBot' varag'ini qaytaradi, yo'q bo'lsa 6 ustunli yaratadi."""
    spreadsheet = _get_spreadsheet()
    if spreadsheet is None:
        return None
    try:
        try:
            return spreadsheet.worksheet("KassaBot")
        except gspread.exceptions.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title="KassaBot", rows=1000, cols=6)
            ws.append_row(["Vaqt", "Telegram ID", "Status", "Summa", "Valyuta", "Izoh"])
            ws.format("A1:F1", {"textFormat": {"bold": True}})
            logging.info("'KassaBot' varag'i yaratildi (6 ustun).")
            return ws
    except Exception as e:
        logging.error(f"'KassaBot' varag'ini olishda xato: {e}")
        return None


# ─── Auth ─────────────────────────────────────────────────────────────────────

def is_allowed_user(telegram_id: int, retry: bool = True) -> tuple[bool, str]:
    """
    'Foydalanuvchilar' varag'ida tasdiqlangan foydalanuvchini tekshiradi.
    Natija 5 daqiqa keshda saqlanadi.
    Qaytaradi: (ruxsat_bormi, to'liq_ismi)
    """
    now = time.time()
    if telegram_id in _auth_cache:
        allowed, name, ts = _auth_cache[telegram_id]
        if now - ts < AUTH_CACHE_TTL:
            return allowed, name

    spreadsheet = _get_spreadsheet()
    if spreadsheet is None:
        return False, ""

    try:
        try:
            ws = spreadsheet.worksheet("Foydalanuvchilar")
        except gspread.exceptions.WorksheetNotFound:
            logging.error("'Foydalanuvchilar' varag'i topilmadi!")
            return False, ""

        for row in ws.get_all_values()[1:]:
            if len(row) < 5:
                continue
            sheet_id, fullname, _, _, status = row[0], row[1], row[2], row[3], row[4]
            if str(telegram_id) == sheet_id.strip() and status.strip().lower() == "tasdiqlandi":
                _auth_cache[telegram_id] = (True, fullname.strip(), now)
                return True, fullname.strip()

        _auth_cache[telegram_id] = (False, "", now)
        return False, ""

    except Exception as e:
        logging.error(f"Auth tekshirishda xato: {e}")
        if retry:
            _reset_cache()
            return is_allowed_user(telegram_id, retry=False)
        return False, ""


def is_admin_user(telegram_id: int, retry: bool = True) -> bool:
    """Admin, Rahbar yoki Boss ekanligini tekshiradi."""
    spreadsheet = _get_spreadsheet()
    if spreadsheet is None:
        return False

    try:
        try:
            ws = spreadsheet.worksheet("Foydalanuvchilar")
        except gspread.exceptions.WorksheetNotFound:
            return False

        for row in ws.get_all_values()[1:]:
            if len(row) < 5:
                continue
            sheet_id, _, _, position, status = row[0], row[1], row[2], row[3], row[4]
            if (str(telegram_id) == sheet_id.strip()
                    and status.strip().lower() == "tasdiqlandi"
                    and position.strip().lower() in ["admin", "rahbar", "boss"]):
                return True

        return False

    except Exception as e:
        logging.error(f"Admin tekshirishda xato: {e}")
        if retry:
            _reset_cache()
            return is_admin_user(telegram_id, retry=False)
        return False


# ─── KassaBot CRUD ────────────────────────────────────────────────────────────

def save_kassa(
    telegram_id: int, status: str, summa: str, valyuta: str, izoh: str,
    retry: bool = True
) -> tuple[bool, dict]:
    """
    'KassaBot' varag'iga bir qator yozadi.
    Ustunlar: Vaqt | Telegram ID | Status | Summa | Valyuta | Izoh
    Qaytaradi: (muvaffaqiyatli, entry_dict)
    """
    ws = _get_kassabot_ws()
    if ws is None:
        return False, {}

    try:
        vaqt = datetime.now().strftime("%d/%m/%Y %H:%M")
        raw_summa = float(summa.replace(" ", "").replace(",", "")) if '.' in summa or ',' in summa else int(summa.replace(" ", "").replace(",", ""))
        
        row = [vaqt, str(telegram_id), status, raw_summa, valyuta, izoh]
        ws.append_row(row, value_input_option="USER_ENTERED")
        logging.info(f"[{status}] saqlandi — {telegram_id} | {summa} {valyuta} | {izoh}")
        entry = {
            "vaqt": vaqt,
            "tg_id": str(telegram_id),
            "status": status,
            "summa": summa,
            "valyuta": valyuta,
            "izoh": izoh,
        }
        return True, entry

    except Exception as e:
        logging.error(f"Saqlashda xato: {e}")
        if retry:
            _reset_cache()
            return save_kassa(telegram_id, status, summa, valyuta, izoh, retry=False)
        return False, {}


def delete_kassa_entry(entry: dict, retry: bool = True) -> bool:
    """
    entry_dict ga mos qatorni kontent bo'yicha topib o'chiradi.
    entry keys: vaqt, tg_id, status, summa, valyuta, izoh
    """
    ws = _get_kassabot_ws()
    if ws is None:
        return False

    try:
        all_data = ws.get_all_values()
        for i, row in enumerate(all_data):
            if i == 0:
                continue  # sarlavha
            if (len(row) >= 6
                    and row[0] == entry["vaqt"]
                    and row[1] == entry["tg_id"]
                    and row[2] == entry["status"]
                    and str(row[3]).replace(" ", "").replace(",", "") == str(entry["summa"]).replace(" ", "").replace(",", "")
                    and row[4] == entry["valyuta"]
                    and row[5] == entry["izoh"]):
                ws.delete_rows(i + 1)
                logging.info(f"Qator o'chirildi: {entry}")
                return True

        logging.warning(f"O'chiriladigan qator topilmadi: {entry}")
        return False

    except Exception as e:
        logging.error(f"O'chirishda xato: {e}")
        if retry:
            _reset_cache()
            return delete_kassa_entry(entry, retry=False)
        return False


def get_today_report(retry: bool = True) -> dict:
    """
    Bugungi barcha yozuvlarni o'qib hisobot qaytaradi.
    Ustunlar: Vaqt(0) | TgID(1) | Status(2) | Summa(3) | Valyuta(4) | Izoh(5)
    """
    ws = _get_kassabot_ws()
    if ws is None:
        return {}

    try:
        today = datetime.now().strftime("%d/%m/%Y")
        result = {
            "kirim_count": 0, "kirim_som": 0.0, "kirim_usd": 0.0,
            "chiqim_count": 0, "chiqim_som": 0.0, "chiqim_usd": 0.0,
            "entries": [],
        }

        for row in ws.get_all_values()[1:]:
            if len(row) < 6:
                continue
            vaqt, _, status, summa, valyuta, izoh = (
                row[0], row[1], row[2], row[3], row[4], row[5]
            )
            if not vaqt.startswith(today):
                continue

            result["entries"].append({
                "vaqt": vaqt, "tur": status,
                "summa": summa, "valyuta": valyuta, "izoh": izoh
            })

            # Raqamni tozalash
            clean = summa.replace(" ", "").replace(",", "").strip()
            try:
                amount = float(clean)
            except Exception:
                amount = 0.0

            is_usd = valyuta.strip() == "$"

            if status.lower() == "kirim":
                result["kirim_count"] += 1
                if is_usd:
                    result["kirim_usd"] += amount
                else:
                    result["kirim_som"] += amount
            elif status.lower() == "chiqim":
                result["chiqim_count"] += 1
                if is_usd:
                    result["chiqim_usd"] += amount
                else:
                    result["chiqim_som"] += amount

        return result

    except Exception as e:
        logging.error(f"Hisobot olishda xato: {e}")
        if retry:
            _reset_cache()
            return get_today_report(retry=False)
        return {}


def get_overall_report(retry: bool = True) -> dict:
    """
    Barcha vaqtdagi yozuvlarni o'qib umumiy hisobot qaytaradi.
    """
    ws = _get_kassabot_ws()
    if ws is None:
        return {}

    try:
        result = {
            "kirim_count": 0, "kirim_som": 0.0, "kirim_usd": 0.0,
            "chiqim_count": 0, "chiqim_som": 0.0, "chiqim_usd": 0.0,
        }

        for row in ws.get_all_values()[1:]:
            if len(row) < 6:
                continue
            _, _, status, summa, valyuta, _ = (
                row[0], row[1], row[2], row[3], row[4], row[5]
            )

            # Raqamni tozalash
            clean = str(summa).replace(" ", "").replace(",", "").strip()
            try:
                amount = float(clean)
            except Exception:
                amount = 0.0

            is_usd = str(valyuta).strip() == "$"

            if str(status).lower() == "kirim":
                result["kirim_count"] += 1
                if is_usd:
                    result["kirim_usd"] += amount
                else:
                    result["kirim_som"] += amount
            elif str(status).lower() == "chiqim":
                result["chiqim_count"] += 1
                if is_usd:
                    result["chiqim_usd"] += amount
                else:
                    result["chiqim_som"] += amount

        return result

    except Exception as e:
        logging.error(f"Umumiy hisobot olishda xato: {e}")
        if retry:
            _reset_cache()
            return get_overall_report(retry=False)
        return {}


def get_last_entries(n: int = 10, retry: bool = True) -> list[dict]:
    """Oxirgi n ta yozuvni qaytaradi (eng yangi birinchi)."""
    ws = _get_kassabot_ws()
    if ws is None:
        return []

    try:
        data = ws.get_all_values()[1:]
        last = data[-n:] if len(data) >= n else data
        return [
            {
                "vaqt": r[0], "tg_id": r[1], "tur": r[2],
                "summa": r[3], "valyuta": r[4], "izoh": r[5]
            }
            for r in reversed(last)
            if len(r) >= 6
        ]
    except Exception as e:
        logging.error(f"Oxirgi yozuvlarda xato: {e}")
        if retry:
            _reset_cache()
            return get_last_entries(n, retry=False)
        return []
