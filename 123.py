import asyncio
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
        )
        context = await browser.new_context(
            ignore_https_errors=True
        )
        page = await context.new_page()
        await page.goto("https://2ip.ru/")
        print(await page.title())
        input("Press Enter to close the browser...")
        await browser.close()


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())