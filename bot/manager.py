from aiogram import types
import functools
import traceback


class UserSession:
    def __init__(self, user_id: int):
        self.id = user_id
        self.stack: list[types.Message] = []


class MessageManager:
    user_dict: dict[int, UserSession] = {}

    @classmethod
    def save_message(cls, func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            entity: types.Message = None

            if "entity" in kwargs:
                entity = kwargs["entity"]
            elif "message" in kwargs:
                entity = kwargs["message"]
            elif len(args) > 0:
                entity = args[0]

            if not isinstance(entity, types.CallbackQuery):
                user_session = cls.user_dict.get(entity.from_user.id, None)
                if not user_session:
                    cls.user_dict[entity.from_user.id] = user_session = UserSession(
                        user_id=entity.from_user.id
                    )

                user_session.stack.append(entity)
            
            result = await func(*args, **kwargs)
            return result
        return wrapper
    
    @classmethod
    def delete_messages(cls, count: int = 1):
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                entity: types.Message = None

                if "entity" in kwargs:
                    entity = kwargs["entity"]
                elif "message" in kwargs:
                    entity = kwargs["message"]
                elif len(args) > 0:
                    entity = args[0]

                user_id = entity.from_user.id
                user_session = cls.user_dict.get(user_id, None)
                for _ in range(count):
                    try:
                        last_msg = user_session.stack.pop()
                        await entity.bot.delete_message(user_id, last_msg.message_id)
                    except Exception:
                        pass
                return await func(*args, **kwargs)
            return wrapper
        return decorator