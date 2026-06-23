from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Kirim/Chiqim tasdiqlash inline klaviaturasi."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash",  callback_data="confirm"),
            InlineKeyboardButton(text="✏️ Tahrirlash",  callback_data="edit"),
        ],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_all")],
    ])


def undo_keyboard() -> InlineKeyboardMarkup:
    """Oxirgi yozuvni o'chirish tasdiqlash klaviaturasi."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, bekor qilish", callback_data="undo_yes"),
            InlineKeyboardButton(text="❌ Yo'q",             callback_data="undo_no"),
        ],
    ])
