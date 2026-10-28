"""Tarkista GitHub-ajoympäristön yhteys kauppojen julkisiin sivuihin."""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        page = await browser.new_page()
        statuses = []
        page.on('response', lambda response: statuses.append(response.status)
                if '/kr-api/v2/product-search/' in response.url else None)
        s = await page.goto('https://www.s-kaupat.fi/tuotteet/alkoholi-ja-virvoitusjuomat/oluet?storeId=513971200', wait_until='domcontentloaded', timeout=60000)
        s_ok = s is not None and s.status == 200 and await page.locator('script#__NEXT_DATA__').count() > 0
        print(f'S-ryhmä: HTTP {s.status if s else "ei vastausta"}, tuotedata {s_ok}', flush=True)
        k = await page.goto('https://www.k-ruoka.fi/kauppa/tuotteet/juomat/oluet', wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(12000)
        k_ok = k is not None and k.status == 200 and 200 in statuses
        print(f'K-ryhmä: HTTP {k.status if k else "ei vastausta"}, tuotehaku {k_ok}', flush=True)
        await browser.close()
        if not s_ok or not k_ok:
            raise SystemExit('Kaikkien kauppojen tuotetietoja ei saatu.')

if __name__ == '__main__':
    asyncio.run(main())
