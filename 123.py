from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import asyncio

load_dotenv()

from bot.app import start_tg_bot
from database.models import create_columns, async_session, Account
from browser.base import ThreadsManager


async def main():
    await create_columns()
    await ThreadsManager.start_browser()

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == 1)
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
            session.stop_work_event = asyncio.Event()
            session.working_task = asyncio.create_task(
                session._scroll_feeds()
            )
            await asyncio.Future() 


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())