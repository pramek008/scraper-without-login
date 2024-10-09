from playwright.async_api import async_playwright
import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class PlaywrightManager:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.lock = asyncio.Lock()
        self.last_used = 0
        self.close_task = None

    async def initialize(self):
        async with self.lock:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
                self.browser = await self.playwright.chromium.launch(headless=True)
            if self.context is None:
                self.context = await self.browser.new_context()
            self.last_used = asyncio.get_event_loop().time()
            self.schedule_close()

    def schedule_close(self):
        if self.close_task:
            self.close_task.cancel()
        self.close_task = asyncio.create_task(self.auto_close())

    async def auto_close(self, delay=900):
        await asyncio.sleep(delay)
        async with self.lock:
            if asyncio.get_event_loop().time() - self.last_used >= delay:
                await self.close()

    async def close(self):
        logger.info("Closing Playwright resources")
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self.playwright = self.browser = self.context = None
        logger.info("Playwright resources closed")

    @asynccontextmanager
    async def get_page(self):
        await self.initialize()
        page = await self.context.new_page()
        try:
            yield page
        finally:
            await page.close()

playwright_manager = PlaywrightManager()

async def get_page():
    return playwright_manager.get_page()

# Helper function for common page operations
async def navigate_and_wait(page, url, timeout=30000):
    try:
        await page.goto(url, timeout=timeout, wait_until="networkidle")
    except Exception as e:
        logger.error(f"Navigation error: {str(e)}")
        raise