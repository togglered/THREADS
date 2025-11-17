from dotenv import load_dotenv
import asyncio

load_dotenv()

from bot.app import start_tg_bot
from database.models import create_columns
from browser.base import ThreadsManager


async def main():
    await create_columns()
    await ThreadsManager.start_browser()
    # await ThreadsManager.start_scheduler()

    await start_tg_bot()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())