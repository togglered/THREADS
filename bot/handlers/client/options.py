from aiogram import F, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.models import User, Account, Persona, async_session
from browser.base import ThreadsManager
from bot.utils import answer_entity
from bot.manager import MessageManager
from bot.keyboards.client import (
    get_account_options
)
from . import client_router, ERROR_SIGN, SUCCESS_SIGN, LOADING_SIGN


class ChangeOpiton(StatesGroup):
    waiting_for_new_option = State()

@client_router.callback_query(F.data.startswith('account_options'))
@MessageManager.delete_messages(1)
async def account_options(entity: types.CallbackQuery | types.Message, account_id: int = None):
    if not account_id:
        _, account_id = entity.data.split(":")

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(
                Account.id == account_id
            )
        )

        if account:
            await answer_entity(
                entity,
                (
                    f"⚙️ Настройки аккаунта {account.username}\n"
                    f"Ниже представлены настройки работы аккаунта, шансы взамиодействия с лентой новостей и задержка между чтением постов в ленте (целое количество секунд).\n"
                ),
                reply_markup=get_account_options(account)
            )


@client_router.callback_query(F.data.startswith('change_options_field'))
@MessageManager.delete_messages(1)
async def change_auth_field(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    _, account_id, field_name = callback.data.split(":")

    await state.set_state(
        ChangeOpiton.waiting_for_new_option
    )
    await state.update_data(
        account_id=account_id,
        field_name=field_name
    )
    await answer_entity(
        callback,
        f"Пришлите новое значения для поля {Account.label(field_name)}"
    )


@client_router.message(ChangeOpiton.waiting_for_new_option)
@MessageManager.save_message
@MessageManager.delete_messages(2)
async def change_auth_field_proccede(message: types.Message, state: FSMContext):
    new_value = message.text

    data = await state.get_data()

    account_id = data["account_id"]
    field_name = data["field_name"]
    field_type = getattr(Account, field_name).type.python_type
    
    if field_type in (int,):
        try:
            new_value = int(message.text)
        except ValueError:
            await answer_entity(
                message,
                f"{ERROR_SIGN} Неверный формат! Пришлите целое число!"
            )
            return
    elif field_type in (float,):
        try:
            new_value = float(message.text)
            if not 0 <= new_value <= 1:
                raise Exception
        except Exception:
            await answer_entity(
                message,
                f"{ERROR_SIGN} Неверный формат! Пришлите чило от 0 до 1!"
            )
            return

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == account_id)
        )

        if hasattr(account, field_name):
            setattr(account, field_name, new_value)
            await session.commit()

            await account_options(message, account_id)