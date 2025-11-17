from sqlalchemy import event, DateTime, Time, Column, Integer, ForeignKey, String, JSON, Text, Enum, Float
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from datetime import datetime, timezone
import asyncio
import os

from .enums import DatabaseEnums
from bot.app import BOT


engine = create_async_engine(url = os.getenv("DB_LINK"),
    connect_args={"check_same_thread": False})

async_session = async_sessionmaker(engine)

class Base(AsyncAttrs, DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, unique=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))

    accounts = relationship("Account", back_populates="owner", cascade="all, delete-orphan")

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, unique=True, nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # auth params
    proxy = Column(String, nullable=True)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)
    cookies = Column(JSON, nullable=True)

    # chances
    like_chance = Column(Float, nullable=False, default=0.3)
    comment_chance = Column(Float, nullable=False, default=0.3)
    scroll_feed_delay = Column(Integer, nullable=False, default=15)

    created_at = Column(DateTime, default=datetime.now(timezone.utc))

    persona = relationship("Persona", back_populates="account", cascade="all, delete-orphan", uselist=False)
    owner = relationship("User", back_populates="accounts")
    schedules = relationship("Schedule", back_populates="account", cascade="all, delete-orphan")
    medias = relationship("Media", back_populates="account", cascade="all, delete-orphan")
    stats = relationship("Stat", backref="account", cascade="all, delete-orphan")
    
    __field_labels__ = {
        "proxy": "Прокси",
        "username": "Имя пользователя",
        "password": "Пароль",
        "cookies": "Cookie",
        "like_chance": "Шанс оставить лайк",
        "comment_chance": "Шанс оставить комментарий",
        "scroll_feed_delay": "Задержка между чтением постов",
    }

    @property
    def status(self):
        from browser.base import ThreadsManager
        from browser.enums import Condition


        session = ThreadsManager.get_session(self.id)
        if session:
            if session.working_task:
                return Condition.working
            return Condition.waiting
        
        return Condition.stopped

    @classmethod
    def label(cls, field_name: str) -> str:
        return cls.__field_labels__.get(field_name, field_name)

class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    # schedule settings
    day_of_week = Column(Enum(DatabaseEnums.DayOfWeek), nullable=False)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    post_count = Column(Integer, nullable=False, default=0)

    account = relationship("Account", back_populates="schedules")

class Persona(Base):
    __tablename__ = "personas"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    account = relationship("Account", back_populates="persona")

    # personal data
    name = Column(String, nullable=True, default="Пользователь")
    age = Column(Integer, nullable=True, default=30)
    gender = Column(Enum(DatabaseEnums.Sex), nullable=True, default=DatabaseEnums.Sex.male)
    
    # location data
    country = Column(String, default="")
    city = Column(String, default="")

    # lifestyle
    role = Column(String, default="") # life role
    style = Column(Enum(DatabaseEnums.CommunicationStyle), nullable=False, default=DatabaseEnums.CommunicationStyle.friendly) # communication style

    values = Column(JSON, default=[]) # life values
    interests = Column(JSON, default=[])
    triggers = Column(String(4096))
    examples = Column(JSON, default=[])

    text_prompt = Column(Text, nullable=True, default="Привет, напиши мне пост для Threads.")
    photo_prompt = Column(Text, nullable=True, default="Привет, проанализируй фото и напиши мне пост для Threads.")
    comment_prompt = Column(Text, nullable=True, default="Привет, проанализируй пост в Threads и напиши комментрий у нему.")

    # engagement
    engagement_level = Column(Enum(DatabaseEnums.EngagementLevel), nullable=False, default=DatabaseEnums.EngagementLevel.neutral)
    engagement_categorioes = Column(JSON, default=[])

    __field_labels__ = {
        "id": "ID",
        "name": "Имя",
        "age": "Возраст",
        "gender": "Пол",
        "country": "Страна",
        "city": "Город",
        "role": "Роль",
        "style": "Стиль общения",
        "values": "Ценности",
        "interests": "Интересы",
        "triggers": "Триггеры",
        "examples": "Примеры общения",
        "text_prompt": "ИИ промт (генерация текста)",
        "photo_prompt": "ИИ промт (генерация текста на основе фото)",
        "comment_prompt": "ИИ промт (генерация комментария на основе текста поста и его фото)",
        "engagement_level": "Триггерность",
        "engagement_categorioes": "Категории триггеров",
    }

    @classmethod
    def label(cls, field_name: str) -> str:
        return cls.__field_labels__.get(field_name, field_name)


class Media(Base):
    __tablename__ = "media"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    filepath = Column(String, nullable=False)
    tags = Column(JSON)
    uploaded_at = Column(DateTime, default=datetime.now(timezone.utc))

    def __init__(self, *args, file_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_id = file_id

    account = relationship("Account", back_populates="medias")

class Stat(Base):
    __tablename__ = "stats"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))

    followers = Column(Integer, nullable=False, default=0)
    likes = Column(Integer, nullable=False, default=0)
    replies = Column(Integer, nullable=False, default=0)

@event.listens_for(Media, 'before_delete')
def before_delete_media(mapper, connection, target):
    try:
        os.remove(target.filepath)
    except Exception:
        pass

@event.listens_for(Media, 'before_insert')
def before_insert_media(mapper, connection, target):
    account_id = target.account_id
    file_id = target.file_id
    filepath = target.filepath

    if not os.path.exists(os.path.join('media', str(account_id))):
        os.mkdir(
            os.path.join('media', str(account_id))
        )

    async def download():
        file = await BOT.get_file(file_id)
        file_path = file.file_path
        await BOT.download_file(
            file_path,
            destination=filepath
        )
    loop = asyncio.get_running_loop()
    loop.create_task(download())

@event.listens_for(Account, 'after_insert')
def after_insert_account(mapper, connection, target):
    from browser.base import ThreadsManager

    loop = asyncio.get_running_loop()
    loop.create_task(ThreadsManager.refresh_account_data(
        target.id
    ))

@event.listens_for(Account, 'after_update')
def after_update_account(mapper, connection, target):
    from browser.base import ThreadsManager

    loop = asyncio.get_running_loop()
    loop.create_task(ThreadsManager.refresh_account_data(
        target.id
    ))

@event.listens_for(Persona, 'after_insert')
def after_insert_persona(mapper, connection, target):
    from browser.base import ThreadsManager

    loop = asyncio.get_running_loop()
    loop.create_task(ThreadsManager.refresh_account_data(
        target.account_id
    ))

@event.listens_for(Persona, 'after_update')
def after_update_persona(mapper, connection, target):
    from browser.base import ThreadsManager

    loop = asyncio.get_running_loop()
    loop.create_task(ThreadsManager.refresh_account_data(
        target.account_id
    ))
    
async def create_columns():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)