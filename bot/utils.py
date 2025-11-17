from aiogram import types

from bot.manager import MessageManager


async def answer_entity(
        entity: types.Message | types.CallbackQuery,
        message: str,
        reply_markup: types.InlineKeyboardMarkup = None,
        parse_mode: str = None
        ):
    message_instance = None

    if isinstance(entity, types.CallbackQuery):
        try:
            await entity.answer()
        except Exception:
            pass
        message_instance = await entity.message.answer(message, reply_markup=reply_markup, parse_mode=parse_mode)
    elif isinstance(entity, types.Message):
        message_instance = await entity.answer(message, reply_markup=reply_markup, parse_mode=parse_mode)

    user_session = MessageManager.user_dict.get(entity.from_user.id, None)
    if user_session:
        user_session.stack.append(message_instance)

    return message_instance