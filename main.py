import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers.kassa_handlers import router as kassa_router
from handlers.admin_handlers import router as admin_router
from handlers.logist_handlers import router as logist_router
from middlewares.auth_middleware import AuthMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())

    # Auth middleware — barcha xabarlarga va callback larga qo'llanadi
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # Routerlar (admin birinchi — /hisobot va boshqa buyruqlar oldin ishlansin)
    dp.include_router(admin_router)
    dp.include_router(logist_router)
    dp.include_router(kassa_router)

    print("Kassa boti ishga tushirildi...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Xato: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot to'xtatildi.")
