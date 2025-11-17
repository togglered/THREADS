from aiogram import F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import time, date

from config.logger import bot_logger
from browser.base import ThreadsManager
from database.models import Account, Schedule, async_session
from database.enums import DatabaseEnums
from bot.utils import answer_entity
from bot.manager import MessageManager
from bot.keyboards.client import (
    get_account_schedule, get_days
)
from . import client_router, ERROR_SIGN


class ScheduleChange(StatesGroup):
    waiting_for_hours = State()
    waiting_for_post_count = State()

@client_router.callback_query(F.data.startswith("show_schedule"))
@MessageManager.delete_messages(1)
async def show_schedule(entity: types.CallbackQuery | types.Message, account_id: int = None):
    if not account_id and isinstance(entity, types.CallbackQuery):
        _, account_id = entity.data.split(':')

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == account_id)
            .options(
                selectinload(Account.persona),
                selectinload(Account.owner),
                selectinload(Account.schedules),
            )
        )

        if account:
            await answer_entity(
                entity,
                f"Расписание аккаутна {account.username}",
                reply_markup=get_account_schedule(account)
            )


@client_router.callback_query(F.data.startswith('delete_schedule'))
@MessageManager.delete_messages(1)
async def delete_schedule(callback: types.CallbackQuery):
    _, schedule_id = callback.data.split(':')
    
    async with async_session() as session:
        schedule = await session.scalar(select(Schedule).where(Schedule.id == schedule_id))

        if schedule:
            account_id = schedule.account_id
            await session.delete(schedule)
            bot_logger.info(
                f"User {callback.from_user.id} has just deleted a schedule {schedule.id}!"
            )
            await session.commit()
            await ThreadsManager.refresh_account_data(
                account_id
            )

            await show_schedule(callback, account_id)


@client_router.callback_query(F.data.startswith('add_schedule'))
@MessageManager.delete_messages(1)
async def add_schedule(callback: types.CallbackQuery):
    _, account_id = callback.data.split(':')

    await callback.answer()
    await answer_entity(
        callback,
        "Выберите день для добавления расписания:",
        reply_markup=get_days(account_id)
    )


@client_router.callback_query(F.data.startswith('add_day'))
async def add_day(callback: types.CallbackQuery, state: FSMContext):
    _, day, account_id = callback.data.split(':')

    await callback.answer()
    
    await answer_entity(
        callback,
        "Пришлите время работы в формате ЧЧ:ММ - ЧЧ:ММ"
    )

    await state.update_data(
        day=day,
        account_id=account_id
    )
    await state.set_state(ScheduleChange.waiting_for_hours)


@client_router.message(ScheduleChange.waiting_for_hours)
@MessageManager.save_message
async def add_hours(message: types.Message, state: FSMContext):
    try:
        start, end = message.text.split('-')
        start, end = start.strip(), end.strip()

        start_hour, start_minute = map(int, start.split(':'))
        end_hour, end_minute = map(int, end.split(':'))
        start_time = time(start_hour, start_minute)
        end_time = time(end_hour, end_minute)
        if not 0 <= start_minute < 60 or not 0 <= end_minute < 60 or \
            not 0 <= start_hour < 24 or not 0 <= end_hour < 24:
            await answer_entity(
                message,
                f"{ERROR_SIGN} Невалидный формат! Пришлите время работы в формате ЧЧ:ММ - ЧЧ:ММ!"
            )
            return
        
        async with async_session() as session:
            data = await state.get_data()

            account = await session.scalar(
                select(Account)
                .where(Account.id == data['account_id'])
                .options(
                    selectinload(Account.schedules),
                )
            )

            today = date.today()

            for schedule in account.schedules:
                if schedule.day_of_week == today.weekday():
                    if start_time <= schedule.start_time <= end_time or \
                        start_time <= schedule.end_time <= end_time:
                        await answer_entity(
                            message,
                            f"{ERROR_SIGN} Расписание пересекается с имеющимся!"
                        )
                        return

    except ValueError:
        await answer_entity(
            message,
            f"{ERROR_SIGN} Невалидный формат! Пришлите время работы в формате ЧЧ:ММ - ЧЧ:ММ!"
        )
        return

    await state.update_data(
        start=start_time,
        end=end_time
    )

    await answer_entity(
        message,
        "Пришлите количество постов, требуемых для публикации в этот период"
    )

    await state.set_state(
        ScheduleChange.waiting_for_post_count
    )

@client_router.message(ScheduleChange.waiting_for_post_count)
@MessageManager.save_message
@MessageManager.delete_messages(4)
async def add_post_count(message: types.Message, state: FSMContext):
    try:
        post_count = int(message.text)
    except ValueError:
        await answer_entity(
            message,
            f"{ERROR_SIGN} Невалидный формат! Пришлите целое число!"
        )
        return
    
    data = await state.get_data()
    day = data['day']
    start = data['start']
    end = data['end']
    account_id = data['account_id']
    
    async with async_session() as session:
        account = await session.scalar(select(Account).where(Account.id == account_id))

        schedule = Schedule(
            day_of_week=DatabaseEnums.DayOfWeek[day],
            start_time=start,
            end_time=end,
            post_count=post_count,
            account_id=account.id
        )

        session.add(schedule)
        bot_logger.info(
            f"User {message.from_user.id} has just added a schedule {schedule.id}!"
        )
        await session.commit()
        await ThreadsManager.refresh_account_data(
            int(account_id)
        )

    await state.clear()
    await show_schedule(message, int(account_id))