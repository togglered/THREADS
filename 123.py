from dotenv import load_dotenv
import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

load_dotenv()

from bot.app import start_tg_bot
from database.models import create_columns, async_session, Account
from browser.base import ThreadsManager


async def main():
    await create_columns()
    await ThreadsManager.start_browser()
    # await ThreadsManager.start_scheduler()

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == 2)
            .options(
                selectinload(Account.persona),
                selectinload(Account.owner),
                selectinload(Account.schedules),
                selectinload(Account.medias),
            )
        )
        if account:
            session = await ThreadsManager.create_session(
                account=account,
            )
            await session._scroll_feeds()
            input("Press Enter to stop...")
            await ThreadsManager.close_session(account_id=account.id)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())