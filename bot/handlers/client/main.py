from aiogram import F, types
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy import select

from database.models import User, async_session
from bot.keyboards.client import (
    get_main_menu_keyboard
)
from bot.utils import answer_entity
from bot.manager import MessageManager
from . import client_router


@client_router.callback_query(F.data == 'main_menu')
@client_router.message(CommandStart())
@MessageManager.save_message
@MessageManager.delete_messages(1)
async def command_start(entity: types.Message | types.CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = entity.from_user.id

    async with async_session() as session:
        user = await session.scalar(select(User).where(User.id == user_id))

        if not user:
            user = User(
                id=user_id
            )
            session.add(user)
            await session.commit()

    await answer_entity(
        entity,
        f"👋 Привет, {entity.from_user.first_name}",
        reply_markup=get_main_menu_keyboard()
    )


@client_router.callback_query(F.data == 'none')
async def command_start(callback: types.CallbackQuery):
    await callback.answer()