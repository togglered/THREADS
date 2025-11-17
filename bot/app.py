from aiogram import Bot, Dispatcher
import os


BOT = Bot(os.getenv("BOT_TOKEN"))

from .handlers.client import client_router
from config.logger import bot_logger


async def start_tg_bot():
    dispatcher = Dispatcher()

    dispatcher.include_router(client_router)

    bot_logger.info(
        f"Starting the bot..."
    )
    await dispatcher.start_polling(BOT)