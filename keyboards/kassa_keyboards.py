from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💰 Kirim"), KeyboardButton(text="💸 Chiqim")],
            [KeyboardButton(text="🔄 Ayirboshlash")],
            [KeyboardButton(text="↩️ Oxirgini bekor qilish")],
            [KeyboardButton(text="📊 Bugungi hisobot"), KeyboardButton(text="📋 Yakuniy hisobot")],
        ],
        resize_keyboard=True,
        persistent=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True,
    )


def undo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, bekor qilish", callback_data="undo_yes"),
            InlineKeyboardButton(text="❌ Yo'q",             callback_data="undo_no"),
        ],
    ])
