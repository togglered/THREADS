from .app import BOT


async def notify_user(user_id: int, message: str):
    await BOT.send_message(
        user_id,
        message
    )