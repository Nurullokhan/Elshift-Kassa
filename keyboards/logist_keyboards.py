from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def contact_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

def logist_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Faol obyektlar")],
            [KeyboardButton(text="🔙 Chiqish / Bosh menyu")]
        ],
        resize_keyboard=True
    )

def objects_keyboard(objects: list):
    keyboard = []
    for obj in objects:
        keyboard.append([InlineKeyboardButton(text=obj['name'], callback_data=f"logist_obj_{obj['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
