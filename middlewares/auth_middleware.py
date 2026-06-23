import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

from services.google_sheets import is_allowed_user


class AuthMiddleware(BaseMiddleware):
    """
    Faqat 'Foydalanuvchilar' varag'ida 'Tasdiqlandi' statusli
    foydalanuvchilarni botga kirgazadi.
    /start buyrug'i har doim o'tib ketadi — handler o'zi hal qiladi.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:

        # /start uchun autentifikatsiya tekshirilmaydi — handler o'zi bajaradi
        if isinstance(event, Message):
            if event.text and event.text.startswith("/start"):
                return await handler(event, data)

            user = event.from_user
            allowed, name = is_allowed_user(user.id)

            if not allowed:
                await event.answer(
                    "❌ <b>Sizda bu botdan foydalanish huquqi yo'q.</b>\n\n"
                    "Qo'shilish uchun admin bilan bog'laning.",
                    parse_mode="HTML",
                )
                return  # handlerni chaqirmaymiz

            data["user_name"] = name

        elif isinstance(event, CallbackQuery):
            user = event.from_user
            allowed, name = is_allowed_user(user.id)

            if not allowed:
                await event.answer("❌ Ruxsat yo'q.", show_alert=True)
                return

            data["user_name"] = name

        return await handler(event, data)
