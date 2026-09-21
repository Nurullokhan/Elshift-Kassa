import logging
from datetime import datetime
from services.google_sheets import _get_spreadsheet, _reset_cache, _auth_cache
import time
import gspread

def check_and_update_user_by_phone(phone_number: str, telegram_id: int, retry: bool = True) -> tuple[bool, str, str]:
    """
    Telefon raqami bo'yicha qidiradi. Agar topilsa va logist bo'lsa, Telegram ID sini yangilaydi.
    Qaytaradi: (muvaffaqiyatli, ism_sharif)
    """
    spreadsheet = _get_spreadsheet()
    if spreadsheet is None:
        return False, ""
    
    try:
        try:
            ws = spreadsheet.worksheet("Foydalanuvchilar")
        except gspread.exceptions.WorksheetNotFound:
            logging.error("'Foydalanuvchilar' varag'i topilmadi!")
            return False, ""
            
        all_data = ws.get_all_values()
        
        # Phone number formatting: normalize to numeric string
        clean_phone = "".join(filter(str.isdigit, phone_number))
        if clean_phone.startswith("998") and len(clean_phone) == 12:
            clean_phone = clean_phone[3:]
            
        for i, row in enumerate(all_data):
            if i == 0:
                continue
            if len(row) < 5:
                continue
            
            sheet_id, fullname, phone, position, status = row[0], row[1], row[2], row[3], row[4]
            row_phone = "".join(filter(str.isdigit, phone))
            
            if clean_phone in row_phone or row_phone in clean_phone:
                if status.strip().lower() == "tasdiqlandi":
                    # Update Telegram ID if it's empty or different
                    if str(sheet_id).strip() != str(telegram_id):
                        ws.update_cell(i + 1, 1, str(telegram_id))
                        logging.info(f"Foydalanuvchi {fullname} uchun Telegram ID yangilandi: {telegram_id}")
                    
                    _auth_cache[telegram_id] = (True, fullname.strip(), time.time())
                    # Return success, fullname, and role
                    return True, fullname.strip(), position.strip()
                else:
                    logging.info(f"Topildi, lekin status 'Tasdiqlandi' emas: {fullname}")
                    
        return False, "", ""
    except Exception as e:
        logging.error(f"check_and_update_user_by_phone xato: {e}")
        if retry:
            _reset_cache()
            return check_and_update_user_by_phone(phone_number, telegram_id, retry=False)
        return False, "", ""

def get_active_objects(retry: bool = True) -> list[dict]:
    spreadsheet = _get_spreadsheet()
    if spreadsheet is None:
        return []
        
    try:
        try:
            ws = spreadsheet.worksheet("Obyektlar")
        except gspread.exceptions.WorksheetNotFound:
            logging.error("'Obyektlar' varag'i topilmadi!")
            return []
            
        all_data = ws.get_all_values()
        active_objects = []
        for i, row in enumerate(all_data):
            if i == 0:
                continue
            if len(row) < 6:
                continue
            
            oid = row[0]
            status = row[4]
            name = row[5]
            
            if status.strip().lower() in ["jarayonda", "faol"]:
                active_objects.append({"id": oid, "name": name})
                
        return active_objects
    except Exception as e:
        logging.error(f"get_active_objects xato: {e}")
        if retry:
            _reset_cache()
            return get_active_objects(retry=False)
        return []

def save_logist_report(logist_id: int, object_id: str, text_id: str, photo_id: str, video_id: str, retry: bool = True) -> bool:
    spreadsheet = _get_spreadsheet()
    if spreadsheet is None:
        return False
        
    try:
        try:
            ws = spreadsheet.worksheet("LogistData")
        except gspread.exceptions.WorksheetNotFound:
            ws = spreadsheet.add_worksheet(title="LogistData", rows=1000, cols=6)
            ws.append_row(["Logist ID", "Obyekt ID", "Text Msg ID", "Photo Msg ID", "Video Msg ID", "Vaqt"])
            
        vaqt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([str(logist_id), str(object_id), str(text_id), str(photo_id), str(video_id), vaqt])
        return True
    except Exception as e:
        logging.error(f"save_logist_report xato: {e}")
        if retry:
            _reset_cache()
            return save_logist_report(logist_id, object_id, text_id, photo_id, video_id, retry=False)
        return False

def get_delivered_messages(object_id: str, retry: bool = True) -> list[dict]:
    spreadsheet = _get_spreadsheet()
    if spreadsheet is None:
        return []
        
    try:
        try:
            ws = spreadsheet.worksheet("LogistData")
        except gspread.exceptions.WorksheetNotFound:
            return []
            
        all_data = ws.get_all_values()
        messages = []
        for i, row in enumerate(all_data):
            if i == 0:
                continue
            if len(row) < 5:
                continue
            
            row_obj_id = str(row[1]).strip()
            if row_obj_id == str(object_id).strip():
                messages.append({
                    "text_id": row[2] if len(row) > 2 else "",
                    "photo_id": row[3] if len(row) > 3 else "",
                    "video_id": row[4] if len(row) > 4 else ""
                })
        return messages
    except Exception as e:
        logging.error(f"get_delivered_messages xato: {e}")
        if retry:
            _reset_cache()
            return get_delivered_messages(object_id, retry=False)
        return []

