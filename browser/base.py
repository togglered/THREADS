from playwright.async_api import async_playwright, Playwright, Page, BrowserContext, Browser
from playwright._impl import _errors
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import date, datetime, timedelta
from pytz import timezone
from enum import Enum
import traceback
import asyncio
import random
import copy
import re
import os

from config.logger import browser_logger, scheduler_logger
from ai.base import AiManager
from bot.nofitications import notify_user
from bot.handlers.client import ERROR_SIGN, SUCCESS_SIGN
from database.models import async_session, Account, Persona, Schedule
from .exceptions import CustomExceptions
from .enums import BrowserConstants
from utils import generate_publish_times, get_chance


def with_context(func):
    """
        Декоратор для открытия контекста браузера и отдельной страницы.
    """
    async def wrapper(self: 'Session', *args, **kwargs):
        if ThreadsManager.browser is None:
            await ThreadsManager.start_browser()
        
        proxy = self.account.proxy
        if proxy:
            try:
                server = proxy.split('@')[0]
            except ValueError:
                await notify_user(
                    self.account.owner_id,
                    f"{ERROR_SIGN} Неправильный формат прокси для аккаунта {self.account.id}!"
                )
                return
            try:
                username = proxy.split('@')[1].split(':')[0]
                password = proxy.split('@')[1].split(':')[1]
            except ValueError:
                pass

        if not self.browser_context:
            self.browser_context = await ThreadsManager.browser.new_context(
                locale="de-DE",
                storage_state={"cookies": self.account.cookies} if self.account.cookies else None,
                proxy={
                    'server': server,
                    'username': username,
                    'password': password
                } if self.account.proxy else None
            )

        new_page = await self.browser_context.new_page()
        self.pages.append(new_page)
        
        try:
            return await func(self, *args, page=new_page, **kwargs)
        except _errors.Error as e:
            msg = str(e)
            if "net::ERR_INVALID_AUTH_CREDENTIALS" in msg:
                browser_logger.error(
                    f"A proxy validation error for account {self.account.id}!\n" + traceback.format_exc()
                )
                await notify_user(
                    self.account.owner_id,
                    f"{ERROR_SIGN} Ошибка в проверке прокси для аккаунта {self.account.id}!"
                )
                return
            else:
                browser_logger.error(
                    f"A Playwright error was occured in account {self.account.id}!\n" + traceback.format_exc()
                )
                await notify_user(
                    self.account.owner_id,
                    f"{ERROR_SIGN} Произошла ошибка работы браузера для аккаунта {self.account.id}!"
                )
        finally:
            if new_page:
                await new_page.close()
                self.pages.remove(new_page)
            if self.browser_context and not self.pages:
                await self.browser_context.close()
                self.browser_context = None
    
    return wrapper

class Session:
    """Представляет сессию одного аккаунта в браузере."""
    def __init__(self, account: Account):
        self.account = account
        self.browser_context: BrowserContext = None
        self.pages: list[Page] = []
        self.scheduler = AsyncIOScheduler(timezone=timezone("Europe/Moscow"))

        self.working_task: asyncio.Task = None
        self.stop_work_event: asyncio.Event = None

        self.scheduler.start()

    async def start_working(self, schedule: Schedule):
        """
            Главная функция работы аккаунта.
            Запускает планировщик, чтение ленты новостей.
        """
        self.stop_work_event = asyncio.Event()
        await self._schedule_posts(schedule)
        self.working_task = asyncio.create_task(
            self._scroll_feeds()
        )
        browser_logger.info(
            f"Account {self.account.id} has just started scheduled work!"
        )
        await notify_user(
            self.account.owner_id,
            f"{SUCCESS_SIGN} Аккаунт {self.account.username} начал работу по расписанию!"
        )

    async def stop_working(self):
        """
            Функция остановки работы аккаунта.
        """
        if self.stop_work_event:
            self.stop_work_event.set()
            self.stop_work_event = None
        if self.working_task:
            await self.working_task
            self.working_task = None
            browser_logger.info(
                f"Account {self.account.id} has just finished scheduled work!"
            )
            await notify_user(
                self.account.owner_id,
                f"{SUCCESS_SIGN} Аккаунт {self.account.username} завершил работу по расписанию!"
            )

    async def _configure_scheduler(self):
        """
            Создает расписание работы, публикации постов и переконфигурация расписания на завтра.
        """
        browser_logger.info(
            f"Starting scheduler for account {self.account.id}..."
        )
        self.scheduler.remove_all_jobs()

        today_date = date.today()
        tomorrow_date = today_date + timedelta(days=1)

        tomorrows_sessions = []

        async def schedule_day(day_date):
            for schedule in self.account.schedules:
                if schedule.day_of_week == day_date.weekday():
                    start_dt = datetime.combine(day_date, schedule.start_time)
                    end_dt = datetime.combine(day_date, schedule.end_time)

                    if start_dt > datetime.now():
                        self.scheduler.add_job(
                            self.start_working,
                            'date',
                            args=[schedule],
                            next_run_time=start_dt
                        )
                        
                        scheduler_logger.info(
                            f"Account {self.account.id} got a start job at {start_dt.strftime('%d/%m/%Y, %H:%M:%S')}!"
                        )
                    elif start_dt < datetime.now() < end_dt:
                        await self.start_working(schedule)
                    
                    if end_dt > datetime.now():
                        self.scheduler.add_job(
                            self.stop_working,
                            'date',
                            next_run_time=end_dt
                        )
                        scheduler_logger.info(
                            f"Account {self.account.id} got an end job at {start_dt.strftime('%d/%m/%Y, %H:%M:%S')}!"
                        )
                    if day_date == tomorrow_date:
                        tomorrows_sessions.append(schedule)

        await schedule_day(today_date)
        await schedule_day(tomorrow_date)

        if tomorrows_sessions:
            last_session = sorted(tomorrows_sessions, key=lambda s: s.end_time)[-1]
            next_run_time = datetime.combine(tomorrow_date, last_session.end_time)
        else:
            next_run_time = datetime.now() + timedelta(days=1)

        self.scheduler.add_job(
            self._configure_scheduler,
            'date',
            next_run_time=next_run_time
        )
        scheduler_logger.info(
            f"Account {self.account.id} got a configure job at {next_run_time.strftime('%d/%m/%Y, %H:%M:%S')}!"
        )

    async def _check_myslef(self):
        """
            Проверяет валидность данных аккаунта: авторизационные данные.
        """
        if self.account.cookies:
            if await self._check_cookie_validness():
                return True
            else:
                raise CustomExceptions.CookieInvalid
        else:
            raise CustomExceptions.NoCookiesProvided

    async def _schedule_posts(self, schedule: Schedule):
        """
            Создает задачи для публикации постов.
        """
        today = date.today()
        start_dt = datetime.combine(today, schedule.start_time)
        end_dt = datetime.combine(today, schedule.end_time)

        now = datetime.now()

        publish_times = generate_publish_times(
            start_dt=start_dt,
            end_dt=end_dt,
            post_count=schedule.post_count,
            jitter_spread=0.2,
            min_margin=timedelta(seconds=5)
        )

        for pt in publish_times:
            if pt <= now:
                continue
            self.scheduler.add_job(
                self._publish_ai_post,
                'date',
                next_run_time=pt
            )
            scheduler_logger.info(
                f"Account {self.account.id} sheduled a publish post job at {pt.strftime('%d/%m/%Y, %H:%M:%S')}!"
            )

    async def _parse_promt(self, promt: str):
        """
            Принимает промт и заменяет поля [ ] на данные из аккаунта.
        """
        def _parse(match):
            attr_label = match.group(1)

            for key, value in Persona.__field_labels__.items():
                if value.lower() == attr_label.lower().strip():
                    attr_name = key
                    break
            else:
                loop = asyncio.get_running_loop()
                loop.create_task(notify_user(
                    self.account.owner.id,
                    f"{ERROR_SIGN} Ошибка в промте! Поля {attr_label} не существует!"
                ))
                return

            if hasattr(self.account.persona, attr_name):
                if attr := getattr(self.account.persona, attr_name, None):
                    if isinstance(attr, Enum):
                        return attr.value
                    return str(attr)
                return
            loop = asyncio.get_running_loop()
            loop.create_task(notify_user(
                self.account.owner.id,
                f"{ERROR_SIGN} Ошибка в промте! Поля {attr_label} не существует!"
            ))
            return

        raw_promt = promt
        if raw_promt:
            return re.sub(r"\[(.*?)\]", _parse, raw_promt)
        await notify_user(
            self.account.owner.id,
            f"{ERROR_SIGN} Ошибка в промте! Промт пуст!"
        )
        return

    async def _publish_ai_post(self):
        """Публикует пост с помощью ИИ"""
        if self.stop_work_event and not self.stop_work_event.is_set():
            promt = await self._parse_promt(self.account.persona.text_prompt)

            if promt:
                post_text = await AiManager.request_ai(
                    promt=promt
                )

                if await self._create_text_post(post_text=post_text[:500]):
                    browser_logger.info(
                        f"Account {self.account.id} published a text post at {datetime.now().strftime('%d/%m/%Y, %H:%M:%S')}!"
                    )
                    await notify_user(
                        self.account.owner_id,
                        f"{SUCCESS_SIGN} Аккаунт {self.account.username} выложил новый пост!"
                    )
    
    async def _publish_ai_media_post(self):
        """
            Публикует пост с картиной с помощью ИИ
            ИИ анализирует фото и генерирует текст для поста по промту photo_prompt.
        """
        prompt = await self._parse_promt(self.account.persona.photo_prompt)

        try:
            photo = self.account.medias[0]

            if prompt and photo:
                post_text = await AiManager.request_ai(
                    promt=prompt,
                    image_paths=[photo.filepath]
                )

                await self._create_media_post(
                    post_text=post_text[:500],
                    media_path=photo.filepath
                )

                async with async_session() as session:
                    account = await session.scalar(
                        select(Account)
                        .where(Account.id == self.account.id)
                        .options(
                            selectinload(Account.medias),
                        )
                    )

                    for media in account.medias:
                        if media.filepath == photo.filepath:
                            await session.delete(media)
                            await ThreadsManager.refresh_account_data(account.id)
                            await session.commit()
                    browser_logger.info(
                        f"Account {self.account.id} has just posted a media post!"
                    )
                    return True

        except IndexError:
            await notify_user(
                self.account.owner_id,
                f"{ERROR_SIGN} Произошла ошибка при отправке текстового поста с картинкой! Список фото аккаунта пуст!"
            )
        except Exception:
            browser_logger.error(f"A error was occured while publishing a media post throw account {self.account.id}")
            browser_logger.error(traceback.format_exc())
            await notify_user(
                self.account.owner_id,
                f"{ERROR_SIGN} Произошла непредвиденная ошибка при отправке текстового поста с картинкой!"
            )

    @with_context
    async def _check_cookie_validness(self, page: Page) -> bool:
        """
            Проверяет валидность cookie аккаунта
        """
        try:
            browser_logger.info(
                f"Checking cookie for account {self.account.id}..."
            )
            if not self.account.cookies:
                browser_logger.error(
                    f"{self.account.id} account's cookie is invalid!"
                )
                return False
            
            await page.goto("https://www.threads.net/", wait_until="networkidle", timeout=60000)
            if "login" in page.url.lower():
                browser_logger.error(
                    f"{self.account.id} account's cookie is invalid!"
                )
                return False
            new_post_button = page.locator(
                'div[id="barcelona-page-layout"] div div div[role="region"][tabindex="0"] div div[style="--x-paddingInline: var(--barcelona-columns-item-horizontal-padding);"] div div[role="button"][tabindex="0"]',
            ).first

            if not new_post_button:
                browser_logger.error(
                    f"{self.account.id} account's cookie is invalid!"
                )
                return False
            
            try:
                await new_post_button.wait_for(state="visible", timeout=15000)
            except _errors.TimeoutError:
                browser_logger.error(
                    f"{self.account.id} account's cookie is invalid!"
                )
                return False
            
            browser_logger.info(
                f"{self.account.id} account's cookie is valid!"
            )
            return True
        except Exception:
            os.makedirs("screenshots", exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = f"screenshots/error_{timestamp}.png"

            await page.screenshot(path=path, full_page=True)

            browser_logger.error(
                f"A error was occured while checking cookie validness for account {self.account.id}!\n" + traceback.format_exc()
            )
            await notify_user(
                self.account.owner_id,
                f"{ERROR_SIGN} Произошла непредвиденная ошибка проверке cookie для аккаунта {self.account.id}!"
            )

    @with_context
    async def _set_cookie(self, page: Page):
        """
            Обновление cookie с помощью авторизации по лоигну и паролю
        """
        browser_logger.info(
            f"Setting cookie for account {self.account.id}..."
        )
        await page.goto("https://www.threads.com/login/")
        await page.wait_for_load_state("load")
        await asyncio.sleep(10)

        form = await page.query_selector("form")

        if form:
            username_input = await form.query_selector("input[type='text']")
            password_input = await form.query_selector("input[type='password']")

            submit_btn = await form.query_selector("div[role='button']")

            await username_input.fill(self.account.username)
            await password_input.fill(self.account.password)

            try:
                async with page.expect_navigation(timeout=25000):
                    await submit_btn.click()
                    await asyncio.sleep(10)
                await page.wait_for_load_state("load")
                if "login" in page.url.lower():
                    browser_logger.error(
                        f"{self.account.id} account's login credentials are invalid!"
                    )
                    raise CustomExceptions.LoginCredentialsInvalid
            except _errors.TimeoutError:
                browser_logger.error(
                    f"{self.account.id} account's login credentials are invalid!"
                )
                raise CustomExceptions.LoginCredentialsInvalid

            await page.wait_for_load_state("load")

        cookies = await page.context.cookies()
        async with async_session() as session:
            account = await session.scalar(select(Account).where(Account.id == self.account.id))

            if account:
                account.cookies = cookies
                await session.commit()
            
        self.account.cookies = cookies
        
        browser_logger.info(
            f"Cookies for account {self.account.id} has been set!"
        )
        return True

    @with_context
    async def _scroll_feeds(self, page: Page):
        """
            Прокручивает главную страницу.
            С шансом comment_chance оставляет комментарий, с шансом like_chance оставляет лайк.
        """
        try:
            browser_logger.info(
                f"Account {self.account.id} is now starting to scroll feed..."
            )
            while True: # self.stop_work_event and not self.stop_work_event.is_set():
                await page.goto("https://www.threads.net/", wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(10)

                like_btns_locator = page.locator(BrowserConstants.like_btn_selector.value)
                comment_btns_locator = page.locator(BrowserConstants.leave_comment_btn.value)

                comment_btns = await comment_btns_locator.all()
                like_btns = await like_btns_locator.all()

                for like_btn, comment_btn in zip(like_btns, comment_btns):
                    if True: # self.stop_work_event and not self.stop_work_event.is_set():
                        await like_btn.scroll_into_view_if_needed()
                        if get_chance(self.account.like_chance):
                            # leave a like
                            await like_btn.click()
                            await asyncio.sleep(15)
                        if get_chance(self.account.comment_chance):
                            # leave a comment
                            await comment_btn.click()
                            await page.wait_for_selector('div[role="dialog"]', timeout=15000)

                            comment_input = page.locator(
                                'div[role="dialog"] div[data-lexical-editor="true"]'
                            ).first

                            if not await comment_input.count():
                                continue

                            post_text_locator = await page.locator(
                                'div[role="dialog"] span[dir="auto"] > span'
                            ).all()

                            pictures = await page.locator(
                                'div[role="dialog"] picture img'
                            ).all()

                            image_urls = []
                            for picture in pictures:
                                src = await picture.get_attribute("src")
                                if src:
                                    image_urls.append(src)

                            block = post_text_locator[1]

                            post_text = await block.text_content()

                            comment_text = await AiManager.request_ai(
                                promt=self.account.persona.comment_prompt,
                                post_text=post_text,
                                image_paths=image_urls
                            )

                            await comment_input.fill(comment_text[:500])
                            
                            final_post_button = page.locator(
                                'div[role="dialog"] div[aria-hidden="false"] div div div div div div[role="button"][tabindex="0"] div'
                            )
                            
                            final_post_button = (await final_post_button.all())[8]

                            await final_post_button.click()

                            await asyncio.sleep(random.uniform(5, 8))
                        
                    await asyncio.sleep(self.account.scroll_feed_delay)
        except Exception:
            os.makedirs("screenshots", exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = f"screenshots/error_{timestamp}.png"

            await page.screenshot(path=path, full_page=True)

            browser_logger.error(
                f"A error was occured while scrolling feed for account {self.account.id}!\n" + traceback.format_exc()
            )
            await notify_user(
                self.account.owner_id,
                f"{ERROR_SIGN} Произошла непредвиденная ошибка скроллинге ленты для аккаунта {self.account.id}!"
            )

    @with_context
    async def _create_text_post(self, page: Page, post_text: str):
        """
            Создает текстовый пост.
        """
        try:
            await page.goto("https://www.threads.net/", wait_until="networkidle", timeout=60000)
            
            new_post_button = page.locator(
                'div[id="barcelona-page-layout"] div div div[role="region"][tabindex="0"] div div[style="--x-paddingInline: var(--barcelona-columns-item-horizontal-padding);"] div div[role="button"][tabindex="0"]',
            ).first

            if not new_post_button:
                return False

            await new_post_button.wait_for(state="visible", timeout=60000)
            await new_post_button.click()

            post_input_field = page.locator(
                'div[role="dialog"] div[data-lexical-editor="true"]'
            ).first
            
            if not post_input_field:
                return False

            await post_input_field.fill(post_text)

            final_post_button = page.locator(
                'div[role="dialog"] div[aria-hidden="false"] div div div div div div[role="button"][tabindex="0"] div'
            )
            
            final_post_button = (await final_post_button.all())[9]
            
            if not final_post_button:
                return False

            await final_post_button.click()
            await asyncio.sleep(random.uniform(5, 8))

            return True
        except Exception:
            os.makedirs("screenshots", exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = f"screenshots/error_{timestamp}.png"

            await page.screenshot(path=path, full_page=True)

            browser_logger.error(
                f"A error was occured while creating text post for account {self.account.id}!\n" + traceback.format_exc()
            )
            await notify_user(
                self.account.owner_id,
                f"{ERROR_SIGN} Произошла непредвиденная ошибка при отправке текстового поста для аккаунта {self.account.id}!"
            )
            return False
            
    @with_context
    async def _create_media_post(self, page: Page, media_path: str, post_text: str):
        """
            Создает текстовый пост с фото.
        """
        try:
            browser_logger.info(
                f"Creating media post for account {self.account.id}..."
            )
            await page.goto("https://www.threads.net/", wait_until="networkidle", timeout=60000)
            
            new_post_button = page.locator(
                'div[id="barcelona-page-layout"] div div div[role="region"][tabindex="0"] div div[style="--x-paddingInline: var(--barcelona-columns-item-horizontal-padding);"] div div[role="button"][tabindex="0"]',
            ).first

            if not new_post_button:
                return False

            await new_post_button.wait_for(state="visible", timeout=15000)
            await new_post_button.click()

            post_input_field = page.locator(
                'div[role="dialog"] div[data-lexical-editor="true"]'
            ).first
            if not post_input_field:
                return False

            await post_input_field.fill(post_text)
            
            add_photo_btn = page.locator(
                BrowserConstants.add_photo_btn_selector.value
            ).first

            async with page.expect_file_chooser() as fc_info:
                await add_photo_btn.click()

            file_chooser = await fc_info.value
            await file_chooser.set_files(media_path)

            final_post_button = page.locator(
                'div[role="dialog"] div[aria-hidden="false"] div div div div div div[role="button"][tabindex="0"] div'
            )
            final_post_button = (await final_post_button.all())[5]

            # for idx, btn in enumerate(await final_post_button.all()):
            #     html = await btn.evaluate("(el) => el.outerHTML")
            #     print(f'{idx} {html}')
            # input("Press Enter to continue...")
            
            if not final_post_button:
                return False

            await final_post_button.click()
            await asyncio.sleep(15)

            browser_logger.info(
                f"A media post for account {self.account.id} has been created!"
            )

            return True
        except Exception:
            os.makedirs("screenshots", exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = f"screenshots/error_{timestamp}.png"

            await page.screenshot(path=path, full_page=True)

            browser_logger.error(
                f"A error was occured while creating media post for account {self.account.id}!\n" + traceback.format_exc()
            )
            return False
        
    @with_context
    async def _fetch_stat(self, page: Page) -> dict | None:
        """"
            Получает статистику аккаунта.
         """
        try:
            await page.goto("https://www.threads.net/", wait_until="networkidle", timeout=60000)

            profile_button = page.locator(BrowserConstants.profile_btn_selector.value).first
            await profile_button.click()

            await asyncio.sleep(5)

            followers_locator = page.locator('span[title]').first
            followers_count = await followers_locator.get_attribute("title")

            like_locator = page.locator('div[role="button"][tabindex="0"] div div div[style="--x-width: 1ch;"]')
            
            items = await like_locator.all()
        except Exception:
            os.makedirs("screenshots", exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = f"screenshots/error_{timestamp}.png"

            await page.screenshot(path=path, full_page=True)

            browser_logger.error(
                f"A error was occured while fetching stats for account {self.account.id}!\n" + traceback.format_exc()
            )
            return None


class ThreadsManager:
    """
        Менеджер для работы с сессиями.
    """
    browser: Browser = None
    playwright: Playwright = None
    sessions: dict[int, Session] = {}
    scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone=timezone("Europe/Moscow"))

    @classmethod
    async def is_runned(cls, account_id: int) -> bool:
        """
            Проверяет заупщенн ли аккаунт.
        """
        return account_id in ThreadsManager.sessions.keys()

    @classmethod
    async def start_browser(cls):
        """
            Запуск браузера.
        """
        try:
            browser_logger.info(
                f"Starting browser..."
            )
            if cls.browser is None:
                playwright = await async_playwright().start()
                cls.playwright = playwright
                cls.browser = await playwright.chromium.launch(headless=os.getenv("HEADLESS", "True").lower() == "true")
            browser_logger.info(
                f"Browser has successfully started up!"
            )
        except Exception:
            browser_logger.error(
                f"A error was occured while starting a browser!\n" + traceback.format_exc()
            )

    @classmethod
    async def stop_browser(cls):
        """
            Остановка браузера.
        """
        try:
            browser_logger.info(
                f"Stopping the browser..."
            )
            if cls.browser:
                await cls.browser.close()
            if cls.playwright:
                await cls.playwright.stop()
            cls.browser = None
            cls.playwright = None
            browser_logger.info(
                f"Browser has been stopped."
            )
        except Exception:
            browser_logger.error(
                f"A error was occured while spotting a browser!\n" + traceback.format_exc()
            )

    @classmethod
    def get_session(cls, account_id: int) -> Session:
        """
            Получает сессию по account_id.
        """
        return cls.sessions.get(
            int(account_id),
            None
        )

    @classmethod
    async def create_session(cls, account: Account, configure_scheduler: bool = True):
        """
            Создание сессии.
        """
        try:
            browser_logger.info(
                f"Creating a session for account {account.id}..."
            )
            session = cls.sessions.get(account.id, None)
            if session:
                browser_logger.info(
                    f"A session for account {account.id} already exists!"
                )
                return session

            session = Session(
                account=account
            )
            cls.sessions[account.id] = session
            
            try:
                await session._check_myslef()
            except (CustomExceptions.CookieInvalid, CustomExceptions.NoCookiesProvided):
                try:
                    await session._set_cookie()
                except CustomExceptions.LoginCredentialsInvalid:
                    await notify_user(
                        account.owner_id,
                        f"{ERROR_SIGN} Неправильные логин или пароль для аккаунта {account.id}!"
                    )
                    browser_logger.error(
                        f"Login credentials are invalid for account {account.id}!"
                    )
                    del cls.sessions[account.id]
                    return None    
            
            if configure_scheduler:
                await session._configure_scheduler()

            browser_logger.info(
                f"A session {account.id} has been created!"
            )
            return cls.sessions[account.id]
        except Exception:
            browser_logger.error(
                f"A error was occured while starting a session for account {account.id}!\n" + traceback.format_exc()
            )

    @classmethod
    async def close_session(cls, account_id: int):
        """
            Закрытие сессии.
        """
        try:
            browser_logger.info(
                f"Closing {account_id} session..."
            )
            if cls.sessions.get(account_id, None):
                await cls.sessions[account_id].stop_working()
                del cls.sessions[account_id]
                
            browser_logger.info(
                f"Session {account_id} has been  closed!"
            )
        except Exception:
            browser_logger.error(
                f"A error was occured while closing a session for account {account_id}!\n" + traceback.format_exc()
            )

    @classmethod
    async def refresh_account_data(cls, account_id: int):
        """
            Обновление информации для сессии.
        """
        try:
            browser_logger.info(
                f"Refreshing data for account {account_id}..."
            )
            session = cls.sessions.get(account_id, None)

            if not session:
                return

            async with async_session() as db_session:
                account = await db_session.scalar(
                    select(Account)
                    .where(Account.id == account_id)
                    .options(
                        selectinload(Account.persona),
                        selectinload(Account.owner),
                        selectinload(Account.schedules),
                        selectinload(Account.medias),
                    )
                )

                if account:
                    session.account = copy.deepcopy(account)
            await session._configure_scheduler()
            browser_logger.info(
                f"Refreshed data for account {account_id}."
            )
        except Exception:
            browser_logger.error(
                f"A error was occured while refreshing data for account {account_id}!\n" + traceback.format_exc()
            )

    @classmethod
    async def start_scheduler(cls):
        """
            Запуск планировщика для получения статистики.
        """
        try:
            scheduler_logger.info(
                f"Starting ThreadsManager scheduler..."
            )
            cls.scheduler.add_job(
                cls.fetch_stats,
                'interval',
                hours=os.getenv("STATS_FETCH_INTERVAL_HOURS", 4),
                next_run_time=datetime.now()
            )
            cls.scheduler.start()
            scheduler_logger.info(
                f"ThreadsManager scheduler has been started!"
            )
        except Exception:
            scheduler_logger.error(
                f"A error was occured while starting ThreadsManager scheduler!\n" + traceback.format_exc()
            )

    @classmethod
    async def fetch_stats(cls):
        try:
            browser_logger.info(
                f"Fetching stats for all accounts..."
            )
            async with async_session() as session:
                accounts = await session.scalars(
                    select(Account)
                )

                for account in accounts:
                    refreshed_account = await session.scalars(
                        select(Account)
                        .where(Account.id == account.id)
                        .options(
                            selectinload(Account.persona),
                            selectinload(Account.owner),
                            selectinload(Account.schedules),
                            selectinload(Account.medias),
                        )
                    )
                    session = await cls.create_session(
                        refreshed_account,
                        configure_scheduler=False
                    )
                    stats = await session._fetch_stat()
        except Exception:
            browser_logger.error(
                f"A error was occured while fetching stats for all accounts!\n" + traceback.format_exc()
            )