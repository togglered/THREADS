from aiogram import F, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import asyncio
import os

from database.models import User, Account, Media, async_session
from browser.base import ThreadsManager
from bot.utils import answer_entity
from bot.manager import MessageManager
from bot.keyboards.client import (
    get_media_nav_markup, get_media_options
)
from . import client_router, SUCCESS_SIGN, ERROR_SIGN, LOADING_SIGN

class ChangeMedia(StatesGroup):
    waiting_for_photo = State()
    waiting_for_photo_deleting = State()

album_buffer = {}
album_timers = {}

@client_router.callback_query(F.data.startswith('media_options'))
@MessageManager.delete_messages(1)
async def media_options(callback: types.CallbackQuery):
    _, account_id = callback.data.split(':')
    await callback.answer()
    
    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == account_id)
        )

        if account:
            await answer_entity(
                callback,
                f"🗾 Медиа аккаунта {account.username}",
                reply_markup=get_media_options(account)
            )


@client_router.callback_query(F.data.startswith('create_media_post'))
async def media_options(callback: types.CallbackQuery):
    _, account_id = callback.data.split(':')
    await callback.answer(
        f"{LOADING_SIGN} Загрузка..."
    )

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == account_id)
            .options(
                selectinload(Account.medias),
                selectinload(Account.persona),
                selectinload(Account.owner),
                selectinload(Account.schedules),
            )
        )
        session = await ThreadsManager.create_session(
            account,
            configure_scheduler=False
        )
        await ThreadsManager.refresh_account_data(
            account_id
        )

        try:
            if await session._publish_ai_media_post():
                await answer_entity(
                    callback,
                    f"{SUCCESS_SIGN} Пост был успешно опубликован!"
                )
        finally:
            if not session.working_task:
                await ThreadsManager.close_session(
                    int(account_id)
                )


@client_router.callback_query(F.data.startswith('show_media'))
@MessageManager.delete_messages(1)
async def show_media(callback: types.CallbackQuery):
    await callback.answer()

    _, account_id, from_idx, to_idx = callback.data.split(":")

    from_idx, to_idx = int(from_idx), int(to_idx)

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == account_id)
            .options(
                selectinload(Account.medias)
            )
        )

        if account:
            if account.medias and from_idx - to_idx <= 10:
                album = [
                    types.InputMediaPhoto(media=types.FSInputFile(media.filepath)) for media in account.medias[from_idx:to_idx]
                ]

                if len(album):
                    await callback.bot.send_media_group(
                        chat_id=callback.from_user.id,
                        media=album
                    )
                    indexes = [str(i) for i in range(from_idx + 1, from_idx + len(album) + 1)]
                    await answer_entity(
                        callback,
                        f"Фото {', '.join(indexes)}",
                        reply_markup=get_media_nav_markup(account, from_idx, to_idx)
                    )
            else:
                markup = types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"media_options:{account_id}")]
                ])
                await answer_entity(
                    callback,
                    f"{ERROR_SIGN} У аккаунта нету фото!",
                    reply_markup=markup
                )

@client_router.callback_query(F.data.startswith('delete_media'))
async def delete_media(callback: types.CallbackQuery, state: FSMContext):
    _, account_id = callback.data.split(':')
    await callback.answer()
    
    await state.set_state(
        ChangeMedia.waiting_for_photo_deleting
    )
    await state.update_data(
        account_id=account_id
    )
    await answer_entity(
        callback,
        "Пожалуйста, пришлите индекс удаляемого фото."
    )

@client_router.message(ChangeMedia.waiting_for_photo_deleting)
@MessageManager.delete_messages(2)
@MessageManager.save_message
async def delete_media(message: types.Message, state: FSMContext):
    try:
        indexes = message.text.split(":")
        indexes = [int(i) - 1 for i in range(int(indexes[0]), int(indexes[1]) + 1)]
    except (ValueError, IndexError):
        indexes = [int(message.text) - 1]

    data = await state.get_data()

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == data["account_id"])
            .options(
                selectinload(Account.medias)
            )
        )

        for idx in indexes:
            try:
                await session.delete(account.medias[idx])
            except Exception as e:
                await answer_entity(
                    message,
                    f"{ERROR_SIGN} Произошла ошибка!"
                )
                return
        await session.commit()
        await answer_entity(
            message,
            f"{SUCCESS_SIGN} Фотографии были удалены!"
        )
    await state.clear()

@client_router.callback_query(F.data.startswith('upload_media'))
async def upload_media(callback: types.CallbackQuery, state: FSMContext):
    _, account_id = callback.data.split(":")
    await callback.answer()

    async with async_session() as session:
        account = await session.scalar(
            select(Account)
            .where(Account.id == account_id)
        )
        if not account:
            return
        
        await answer_entity(
            callback,
            "Пришлите от одного до 10 фото"
        )
        await state.set_state(
            ChangeMedia.waiting_for_photo
        )
        await state.update_data(
            account_id=account_id
        )

@client_router.message(ChangeMedia.waiting_for_photo)
@MessageManager.save_message
async def handle_media(message: types.Message, state: FSMContext):
    data = await state.get_data()

    if not message.photo:
        await message.answer("Отправьте фото, а не что-то другое 😅")
        return

    group_id = message.media_group_id
    file_id = message.photo[-1].file_id

    if group_id:
        if group_id not in album_buffer:
            album_buffer[group_id] = []
        album_buffer[group_id].append(file_id)

        if group_id in album_timers:
            album_timers[group_id].cancel()

        async def process_album():
            await asyncio.sleep(0.5)
            if group_id in album_buffer:
                photos_ids = album_buffer.pop(group_id, [])
                async with async_session() as session:
                    account = await session.scalar(
                        select(Account)
                        .where(Account.id == data["account_id"])
                        .options(
                            selectinload(Account.medias)
                        )
                    )
                    if account and (len(account.medias) + len(photos_ids) > int(os.getenv("MAX_PHOTOS"))):
                        await answer_entity(message, f"{ERROR_SIGN} Превышен лимит фото!")
                        return
                    for fid in photos_ids:
                        session.add(Media(
                            account=account,
                            file_id=fid,
                            filepath=os.path.join(
                                    'media',
                                    str(data["account_id"]),
                                    f"{fid}.png"
                                )
                            ))
                    await session.commit()
                    markup = types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"media_options:{data['account_id']}")]
                    ])
                    await answer_entity(message, f"{SUCCESS_SIGN} Фото сохранены!", reply_markup=markup)
                if group_id in album_timers:
                    del album_timers[group_id]
            await state.clear()

        album_timers[group_id] = asyncio.create_task(process_album())
    else:
        photos_ids = [file_id]
        async with async_session() as session:
            account = await session.scalar(
                select(Account)
                .where(Account.id == data["account_id"])
                .options(
                    selectinload(Account.medias)
                )
            )
            if account and (len(account.medias) + len(photos_ids) > int(os.getenv("MAX_PHOTOS"))):
                await answer_entity(message, f"{ERROR_SIGN} Превышен лимит фото!")
                return
            for fid in photos_ids:
                session.add(Media(
                    account=account,
                    file_id=fid,
                    filepath=os.path.join(
                            'media',
                            str(data["account_id"]),
                            f"{file_id}.png"
                        )
                    ))
            await session.commit()
        markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"media_options:{data['account_id']}")]
        ])
        await answer_entity(message, f"{SUCCESS_SIGN} Фото сохранено!", reply_markup=markup)
        await state.clear()