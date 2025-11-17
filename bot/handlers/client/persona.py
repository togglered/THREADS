from aiogram import F, types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from database.models import Persona, async_session
from bot.utils import answer_entity
from bot.manager import MessageManager
from bot.keyboards.client import (
    get_persona_info_keyboard, get_choice_markup
)
from . import client_router, ERROR_SIGN, LIST_SEPARATOR


class EditPersona(StatesGroup):
    waiting_for_new_field = State()

@client_router.callback_query(F.data.startswith('select_persona'))
@MessageManager.delete_messages(1)
async def select_persona_handler(entity: types.CallbackQuery | types.Message, persona_id: int = None):
    if not persona_id:
        persona_id = entity.data.split(':')[-1]

    async with async_session() as session:
        persona = await session.scalar(
            select(Persona)
            .where(Persona.id == persona_id)
            .options(
                selectinload(Persona.account),
            )
        )

        if not persona:
            await answer_entity(
                entity,
                "Не смогли найти Вашу личность!"
                )
            return
        
        values_str = LIST_SEPARATOR.join(str(value) for value in persona.values) if persona.values else '❌'
        interests_str = LIST_SEPARATOR.join(str(value) for value in persona.interests) if persona.interests else '❌'
        triggers_str = persona.triggers if persona.triggers else '❌'
        triggers_cat_str = LIST_SEPARATOR.join(str(value) for value in persona.engagement_categorioes) if persona.engagement_categorioes else '❌'
        examples_str = LIST_SEPARATOR.join(str(value) for value in persona.examples) if persona.examples else '❌'
        
        await answer_entity(
            entity,
            (
                f"👥 <b>Персона</b> {persona.name}:\n"
                f"🤔 <b>Ценности</b>: {values_str}\n"
                f"❓ <b>Инетересы</b>: {interests_str}\n"
                f"❗️ <b>Триггеры</b>: {triggers_str}\n"
                f"🗂 <b>Категории триггеров</b>: {triggers_cat_str}\n"
                f"📄 <b>Примеры общения</b>: {examples_str}\n"
                f"🤖 <b>Промт обращения к ИИ (генерация тексового поста)</b>: {persona.text_prompt if persona.text_prompt else '❌'}\n"
                f"🤖 <b>Промт обращения к ИИ (генерация поста по фото)</b>: {persona.photo_prompt if persona.photo_prompt else '❌'}\n"
                f"🤖 <b>Промт обращения к ИИ (комментария на основе содержимого поста)</b>: {persona.comment_prompt if persona.comment_prompt else '❌'}\n"
            ),
            reply_markup=get_persona_info_keyboard(persona),
            parse_mode='HTML'
        )


@client_router.callback_query(F.data.startswith('change_field'))
@MessageManager.delete_messages(1)
async def change_field_handler(callback: types.CallbackQuery, state: FSMContext):
    _, persona_id, field_type, field_name = callback.data.split(':')

    await callback.answer()
    
    if field_type in ('string', 'int'):
        await answer_entity(
            callback,
            f"Пришлите новое значение для поля {Persona.label(field_name)}"
            )
    elif field_type in ('JSON',):
        await answer_entity(
            callback,
            (
                f"Пришлите новый список для поля {Persona.label(field_name)}\n"
                f"Например: 'Значение 1 {LIST_SEPARATOR} Значение 2 {LIST_SEPARATOR} Значение 3'"
            ),
        )

    await state.update_data(
        persona_id=persona_id,
        field_type=field_type,
        field_name=field_name
    )

    await state.set_state(EditPersona.waiting_for_new_field)


@client_router.message(EditPersona.waiting_for_new_field)
@MessageManager.save_message
@MessageManager.delete_messages(2)
async def change_field_handler_proceede(message: types.Message, state: FSMContext):
    user_id = message.from_user.id

    data = await state.get_data()
    field_name = data["field_name"]
    persona_id = data["persona_id"]
    field_type = data["field_type"]

    new_value = None
    if field_type in ('string',):
        new_value = message.text
    elif field_type in ('int',):
        try:
            new_value = int(message.text)
        except ValueError:
            await answer_entity(
                message,
                f"{ERROR_SIGN} Неверный формат! Пришлите целое число!"
                )
            return
    elif field_type in ('JSON',):
        new_value = message.text.split(LIST_SEPARATOR)
        for index in range(len(new_value)):
            new_value[index] = new_value[index].strip()

    async with async_session() as session:
        persona = await session.scalar(
            select(Persona)
            .where(Persona.id == int(persona_id))
            .options(
                selectinload(Persona.account),
            )
        )

        if (not persona) or (persona.account.owner_id != user_id):
            await answer_entity(
                message,
                f"{ERROR_SIGN} Не смогли найти Вашу личность!"
                )
            return
        
        
        setattr(persona, field_name, new_value)
        flag_modified(persona, field_name)
        
        await session.commit()
        await state.clear()

        await select_persona_handler(message, int(persona_id))


@client_router.callback_query(F.data.startswith('change_enum_field'))
@MessageManager.delete_messages(1)
async def change_enum_field_handler(entity: types.CallbackQuery | types.Message, persona_id: int = None, field_name: str = None):
    if not persona_id or not field_name:
        _, persona_id, field_name = entity.data.split(':')

    field_type = getattr(Persona, field_name).type.enum_class

    async with async_session() as session:
        persona = await session.scalar(
                select(Persona)
                .where(Persona.id == persona_id)
                .options(
                    selectinload(Persona.account),
                )
            )

        await answer_entity(
            entity,
            f"Выберите новое значение для поля {Persona.label(field_name)}",
            reply_markup=get_choice_markup(persona, field_name, field_type)
        )


@client_router.callback_query(F.data.startswith('choose_choice'))
@MessageManager.delete_messages(1)
async def choose_choice(callback: types.CallbackQuery):
    _, persona_id, field_name, value = callback.data.split(':')
    
    await callback.answer()

    field_type = getattr(Persona, field_name).type.enum_class

    async with async_session() as session:
        persona = await session.scalar(
            select(Persona)
            .where(Persona.id == persona_id)
            .options(
                selectinload(Persona.account)
            )
        )

        await session.refresh(persona, attribute_names=[field_name])

        for enum in field_type:
            if enum.value == value:
                setattr(persona, field_name, enum)

        await answer_entity(
            callback,
            f"Выберите новое значение для поля {Persona.label(field_name)}",
            reply_markup=get_choice_markup(persona, field_name, field_type)
        )

        await session.commit()