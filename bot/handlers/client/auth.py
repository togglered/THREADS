from aiogram import F, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import tempfile
import aiofiles
import json
import os

from database.models import User, Account, Persona, async_session
from browser.base import ThreadsManager
from bot.utils import answer_entity
from bot.manager import MessageManager
from bot.keyboards.client import (
    get_account_auth_markup
)
from . import client_router, ERROR_SIGN, SUCCESS_SIGN
from browser.exceptions import CustomExceptions


class ChangeField(StatesGroup):
    waiting_for_new_value = State()
    waiting_for_cookie = State()

@client_router.callback_query(F.data.startswith('auth_options'))
@MessageManager.save_message
@MessageManager.delete_messages(1)
async def auth_options(entity: types.CallbackQuery | types.Message, account_id: int = None):
    if isinstance(entity, types.CallbackQuery):
        _, account_id = entity.data.split(":")

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == account_id)
        )

        await answer_entity(
            entity,
            (
                f"👥 Аккаунт {account.username}\n"
                f"🔑 Пароль: <tg-spoiler>{account.password}</tg-spoiler>\n"
                f"🌐 Прокси: <tg-spoiler>{account.proxy}</tg-spoiler>\n"
                f"🍪 Cookie: {SUCCESS_SIGN if account.cookies else '❌'}"
            ),
            parse_mode="HTML",
            reply_markup=get_account_auth_markup(account)
        )


@client_router.callback_query(F.data.startswith('change_auth_field'))
@MessageManager.save_message
@MessageManager.delete_messages(1)
async def change_auth_field(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    _, account_id, field_name = callback.data.split(":")

    await state.set_state(
        ChangeField.waiting_for_new_value
    )
    await state.update_data(
        account_id=account_id,
        field_name=field_name
    )
    await answer_entity(
        callback,
        f"Пришлите новое значения для поля {Account.label(field_name)}"
    )


@client_router.message(ChangeField.waiting_for_new_value)
@MessageManager.save_message
@MessageManager.delete_messages(2)
async def change_auth_field_proccede(message: types.Message, state: FSMContext):
    new_value = message.text

    data = await state.get_data()

    account_id = data["account_id"]
    field_name = data["field_name"]

    if field_name == "proxy" and new_value.lower() == "нет":
        new_value = None

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == account_id)
        )

        if hasattr(account, field_name):
            setattr(account, field_name, new_value)
            await session.commit()

            await auth_options(message, int(account_id))


@client_router.callback_query(F.data.startswith('change_cookie'))
@MessageManager.save_message
@MessageManager.delete_messages(1)
async def change_cookie(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    _, account_id = callback.data.split(":")

    await state.set_state(
        ChangeField.waiting_for_cookie
    )
    await state.update_data(
        account_id=account_id,
    )
    await answer_entity(
        callback,
        f"Пришлите новый файл cookie в формате json."
    )


@client_router.message(ChangeField.waiting_for_cookie)
@MessageManager.save_message
@MessageManager.delete_messages(2)
async def change_cookie_proccede(message: types.Message, state: FSMContext):
    data = await state.get_data()
    account_id = data["account_id"]

    try:
        file = await message.bot.get_file(message.document.file_id)
    except Exception:
        await answer_entity(message, f"{ERROR_SIGN} Произошла ошибка при чтении файла!")
        return

    if not file.file_path.endswith(".json"):
        await answer_entity(message, f"{ERROR_SIGN} Неверный формат файла!")
        return

    async with async_session() as session:
        account = await session.scalar(
            select(Account).where(Account.id == account_id)
        )

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        tmp_path = tmp.name
        tmp.close()

        await message.bot.download_file(file.file_path, destination=tmp_path)

        try:
            async with aiofiles.open(tmp_path, mode="r", encoding="utf-8") as f:
                content = await f.read()
            new_cookie = json.loads(content)
        except Exception:
            await answer_entity(message, f"{ERROR_SIGN} Ошибка при чтении JSON файла!")
            return
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        if isinstance(new_cookie, list):
            for cookie in new_cookie:
                if isinstance(cookie, dict):
                    cookie["sameSite"] = "Lax"
        elif isinstance(new_cookie, dict):
            new_cookie["sameSite"] = "Lax"

        account.cookies = new_cookie
        await session.commit()

    await auth_options(message, int(account_id))
