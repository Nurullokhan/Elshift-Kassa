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
    row = []
    for obj in objects:
        row.append(KeyboardButton(text=obj['name']))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([KeyboardButton(text="🔙 Chiqish / Bosh menyu")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def object_action_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Yetkazilgan mahsulotlar"), KeyboardButton(text="✅ Yetkazildi")],
            [KeyboardButton(text="🔙 Orqaga")]
        ],
        resize_keyboard=True
    )
