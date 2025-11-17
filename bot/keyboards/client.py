from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.models import Account, Persona
from database.enums import DatabaseEnums
from bot.handlers.client import LIST_SEPARATOR, SUCCESS_SIGN


def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Список аккаунтов", callback_data=f"accounts:10:0")],
    ])

def get_accounts_list(accounts: list[Account], length, offset):
    markup = InlineKeyboardMarkup(inline_keyboard=[])

    for account in accounts[offset * length : (offset + 1) * length]:
        markup.inline_keyboard.append(
            [InlineKeyboardButton(
                text=f"{account.username}",
                callback_data=f"select_account:{account.id}"
            )]
        )

    nav_buttons = []

    if length * (offset - 1) >= 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"accounts:{length}:{offset - 1}"))
    else:
        nav_buttons.append(InlineKeyboardButton(text=" ", callback_data=f"none"))
    if len(accounts) > length * (offset + 1):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"accounts:{length}:{offset + 1}"))
    else:
        nav_buttons.append(InlineKeyboardButton(text=" ", callback_data=f"none"))

    if nav_buttons and (nav_buttons[0].text != " " or nav_buttons[1].text != " "):
        markup.inline_keyboard.append(nav_buttons)

    markup.inline_keyboard.extend([
        [InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data=f"add_account")],
        [InlineKeyboardButton(text="Главное меню", callback_data=f"main_menu")]
    ])

    return markup

async def get_account_info_keyboard(account: Account):
    status = account.status.action

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=status, callback_data=f"toggle_account_work:{account.id}")],
        [InlineKeyboardButton(text="🗓 Расписание", callback_data=f"show_schedule:{account.id}")],
        [InlineKeyboardButton(text="🔑 Аутентификация", callback_data=f"auth_options:{account.id}")],
        [InlineKeyboardButton(text="👥 Личность", callback_data=f"select_persona:{account.persona.id}")],
        [InlineKeyboardButton(text="🖼 Фото", callback_data=f"media_options:{account.id}")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data=f"account_options:{account.id}")],
        [InlineKeyboardButton(text="🗑 Удалить аккаунт", callback_data=f"delete_account:{account.id}")],
        [InlineKeyboardButton(text=f"⬅️ Назад", callback_data=f"main_menu")],
    ])

def get_persona_info_keyboard(persona: Persona):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🪧 Имя: {persona.name}", callback_data=f"change_field:{persona.id}:string:name")],
        [InlineKeyboardButton(text=f"🔞 Возраст: {persona.age}", callback_data=f"change_field:{persona.id}:int:age")],

        [InlineKeyboardButton(text=f"👫 Пол: {persona.gender.value}", callback_data=f"change_enum_field:{persona.id}:gender")],

        [InlineKeyboardButton(text=f"🏳️ Страна: {persona.country}", callback_data=f"change_field:{persona.id}:string:country")],
        [InlineKeyboardButton(text=f"🌆 Город: {persona.city}", callback_data=f"change_field:{persona.id}:string:city")],
        [InlineKeyboardButton(text=f"🎭 Роль: {persona.role}", callback_data=f"change_field:{persona.id}:string:role")],

        [InlineKeyboardButton(text=f"😎 Стиль общения: {persona.style.value}", callback_data=f"change_enum_field:{persona.id}:style")],
        [InlineKeyboardButton(text=f"❗️ Триггерность: {persona.engagement_level.value}", callback_data=f"change_enum_field:{persona.id}:engagement_level")],

        [InlineKeyboardButton(text=f"🤔 Поменять ценности", callback_data=f"change_field:{persona.id}:JSON:values")],
        [InlineKeyboardButton(text=f"❓ Поменять интересы", callback_data=f"change_field:{persona.id}:JSON:interests")],
        [InlineKeyboardButton(text=f"❗️ Поменять триггеры", callback_data=f"change_field:{persona.id}:string:triggers")],
        [InlineKeyboardButton(text=f"🗂 Поменять категории триггеров", callback_data=f"change_field:{persona.id}:JSON:engagement_categorioes")],
        [InlineKeyboardButton(text=f"📄 Поменять примеры", callback_data=f"change_field:{persona.id}:JSON:examples")],
        [InlineKeyboardButton(text=f"🤖 Поменять промт для текстового поста", callback_data=f"change_field:{persona.id}:string:text_prompt")],
        [InlineKeyboardButton(text=f"🤖 Поменять промт для поста с картинкой", callback_data=f"change_field:{persona.id}:string:photo_prompt")],
        [InlineKeyboardButton(text=f"🤖 Поменять промт для комментинга", callback_data=f"change_field:{persona.id}:string:comment_prompt")],

        [InlineKeyboardButton(text=f"⬅️ Назад", callback_data=f"select_account:{persona.account.id}")],
    ])

def get_account_schedule(account: Account):
    sorted_days = sorted(
        account.schedules,
        key=lambda x: x.day_of_week.value
    )
    rows = [
        [InlineKeyboardButton(
            text=f"{schedule.day_of_week.label} {LIST_SEPARATOR} \
{schedule.start_time.strftime('%H:%M')} - {schedule.end_time.strftime('%H:%M')} {LIST_SEPARATOR} \
{schedule.post_count}",
            callback_data=f"delete_schedule:{schedule.id}"
        )]
        for schedule in sorted_days
    ]

    rows.append(
        [InlineKeyboardButton(text=f"➕ Добавить расписание", callback_data=f"add_schedule:{account.id}")]
    )
    rows.append(
        [InlineKeyboardButton(text=f"⬅️ Назад", callback_data=f"select_account:{account.id}")]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)

def get_days(account_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{day.label}", callback_data=f"add_day:{day.name}:{account_id}")] for day in DatabaseEnums.DayOfWeek
    ])

def get_choice_markup(persona: Persona, field_name: str, field_type):
    markup =  InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=
            f"{SUCCESS_SIGN} {elem.value}" if getattr(persona, field_name, None) == elem else f"{elem.value}",
            callback_data=f"choose_choice:{persona.id}:{field_name}:{elem.value}")]
            for elem in field_type
    ])
    markup.inline_keyboard.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"select_persona:{persona.id}")
    ])
    return markup

def get_multichoice_markup(persona: Persona, field_name: str, field_type):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=
            f"{SUCCESS_SIGN} {elem.value}" if getattr(persona, field_name, None) == elem else f"{elem.value}",
            callback_data=f"choose_multichoice")]
            for elem in field_type
    ])

def get_media_nav_markup(account: Account, from_idx: int, to_idx: int):
    markup =  InlineKeyboardMarkup(inline_keyboard=[])

    row = []

    if from_idx - 10 >= 0:
        row.append(
            InlineKeyboardButton(text="⬅️", callback_data=f"show_media:{account.id}:{from_idx - 10}:{to_idx - 10}")
        )
    
    if from_idx + 10 < len(account.medias):
        row.append(
        InlineKeyboardButton(text="➡️", callback_data=f"show_media:{account.id}:{from_idx + 10}:{to_idx + 10}")
        )

    markup.inline_keyboard.append(row)

    return markup

def get_media_options(account: Account):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🖼 Посмотреть фото", callback_data=f"show_media:{account.id}:0:10")],
        [InlineKeyboardButton(text="⬆️ Загрузить фото", callback_data=f"upload_media:{account.id}")],
        [InlineKeyboardButton(text="🛜 Опубликовать пост с фото", callback_data=f"create_media_post:{account.id}")],
        [InlineKeyboardButton(text="🗑 Удалить фото", callback_data=f"delete_media:{account.id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"select_account:{account.id}")],
    ])

def get_account_auth_markup(account: Account):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Поменять прокси", callback_data=f"change_auth_field:{account.id}:proxy")],
        [InlineKeyboardButton(text="Поменять имя пользователя", callback_data=f"change_auth_field:{account.id}:username")],
        [InlineKeyboardButton(text="Поменять пароль", callback_data=f"change_auth_field:{account.id}:password")],
        [InlineKeyboardButton(text="Поменять cookie", callback_data=f"change_cookie:{account.id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"select_account:{account.id}")],
    ])

def get_account_options(account: Account):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"❤️ Лайк {account.like_chance}", callback_data=f"change_options_field:{account.id}:like_chance")],
        [InlineKeyboardButton(text=f"✉️ Комментарий {account.comment_chance}", callback_data=f"change_options_field:{account.id}:comment_chance")],
        [InlineKeyboardButton(text=f"⚡️ Скорость чтения {account.scroll_feed_delay}", callback_data=f"change_options_field:{account.id}:scroll_feed_delay")],
        [InlineKeyboardButton(text=f"⬅️ Назад", callback_data=f"select_account:{account.id}")],
    ])