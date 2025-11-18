from aiogram import F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.models import User, Account, Persona, async_session
from browser.base import ThreadsManager
from bot.utils import answer_entity
from bot.manager import MessageManager
from bot.keyboards.client import (
    get_accounts_list, get_account_info_keyboard
)
from . import client_router, ERROR_SIGN, LOADING_SIGN
from config.logger import bot_logger


@client_router.callback_query(F.data.startswith('accounts'))
@client_router.message(Command('accounts'))
@MessageManager.save_message
@MessageManager.delete_messages(1)
async def show_accounts_handler(entity: types.Message | types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = entity.from_user.id

    length, offset = 10, 0
    if isinstance(entity, types.CallbackQuery):
        try:
            _, length, offset = entity.data.split(":")
            length, offset = int(length), int(offset)
        except Exception:
            pass

    async with async_session() as session:
        user = await session.scalar(
            select(User)
            .where(User.id == user_id)
            .options(
                selectinload(User.accounts),
            )
        )

        if not user:
            return

        await answer_entity(
            entity,
            "🔑 <b>Ваши аккаунты</b>:",
            reply_markup=get_accounts_list(user.accounts, length, offset),
            parse_mode="HTML"
            )


@client_router.callback_query(F.data.startswith('add_account'))
@client_router.message(Command('add_account'))
@MessageManager.save_message
@MessageManager.delete_messages(1)
async def add_account_handler(entity: types.Message | types.CallbackQuery, state: FSMContext):
    user_id = entity.from_user.id

    async with async_session() as session:
        user = await session.scalar(select(User).where(User.id == user_id))

        if not user:
            return
        
        account = Account(
            owner=user,
            persona=Persona()
        )

        session.add(account)
        bot_logger.info(
            f"User {user_id} has just created an account {account.id}"
        )
        await session.commit()

    await show_accounts_handler(entity, state)


@client_router.callback_query(F.data.startswith('delete_account'))
@MessageManager.save_message
@MessageManager.delete_messages(1)
async def delete_account_handler(callback: types.CallbackQuery, state: FSMContext):
    _, account_id = callback.data.split(":")

    await callback.answer()
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
            await session.delete(account)
            bot_logger.info(
                f"User {callback.from_user.id} has just deleted account {account.id}!"
            )
            await session.commit()

            await show_accounts_handler(callback, state)


@client_router.callback_query(F.data.startswith("toggle_account_work"))
@MessageManager.save_message
async def toggle_account_work(callback: types.CallbackQuery):
    _, account_id = callback.data.split(':')

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
            is_working = await ThreadsManager.is_runned(account.id)

            if not is_working:
                await callback.answer(
                    f"{LOADING_SIGN} Загрузка..."
                )
                session = await ThreadsManager.create_session(
                    account=account,
                )
            else:
                await callback.answer()
                await ThreadsManager.close_session(
                    account_id=account.id,
                )
            await select_account_handler(callback)


@client_router.callback_query(F.data.startswith('select_account'))
@MessageManager.save_message
@MessageManager.delete_messages(1)
async def select_account_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    account_id = callback.data.split(':')[-1]

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
        await callback.answer()

        if (not account) or (account.owner_id != user_id):
            await answer_entity(callback, f"{ERROR_SIGN} Не смогли найти Ваш аккаунт!")
            return

        status = account.status.label
        await answer_entity(
            callback,
            (
                f"👥 Аккаунт <b>{account.username}</b>:\n"
                f"📊 Статус: <b>{status}</b>\n"
            ),
            parse_mode="HTML",
            reply_markup=await get_account_info_keyboard(account)
        )