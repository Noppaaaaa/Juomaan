"""Täydentää kerättyjen S-tuotteiden pakkauskoot lähteen litrahinnoista."""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 's_ryhma_tuotetiedot.json'

async def main():
    products, valid_images = {}, set()
    for file in ROOT.glob('s_ryhma_tuotteet_*.json'):
        store = file.stem.rsplit('_', 1)[1]
        for product in json.loads(file.read_text(encoding='utf8')):
            ean=product['linkki'].rsplit('/',1)[1]
            products.setdefault(ean, (product['linkki'], store))
            if product['kuva_url'].startswith('https://'):valid_images.add(ean)
    cache = json.loads(CACHE.read_text(encoding='utf8')) if CACHE.exists() else {}
    queue = asyncio.Queue()
    for ean, item in products.items():
        if ean not in cache or (ean not in valid_images and 'kuva_url' not in cache[ean]):
            queue.put_nowait((ean, *item))
    errors = []
    def save():
        temp = CACHE.with_suffix('.json.tmp')
        temp.write_text(json.dumps(cache,ensure_ascii=False,indent=2),encoding='utf8')
        temp.replace(CACHE)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        async def worker():
            page = await browser.new_page(java_script_enabled=False)
            await page.route('**/*', lambda route: route.continue_() if route.request.resource_type=='document' else route.abort())
            while not queue.empty():
                ean, link, store = queue.get_nowait()
                for attempt in range(3):
                    try:
                        response = await page.goto(f'{link}?storeId={store}',wait_until='domcontentloaded',timeout=45000)
                        if response.status != 200:
                            raise RuntimeError(f'HTTP {response.status}')
                        raw = json.loads(await page.locator('#__NEXT_DATA__').text_content(timeout=5000))
                        apollo = raw['props']['pageProps']['apolloState']
                        product = next(t for k,t in apollo.items() if k.startswith('Product:{') and str(t.get('ean'))==ean)
                        cache[ean] = {k:product.get(k) for k in ['name','description','pricing','price','comparisonPrice','comparisonUnit','depositPrice','isAgeLimitedByAlcohol']}
                        image=(((product.get('productDetails') or {}).get('productImages') or {}).get('mainImage') or {}).get('urlTemplate','')
                        cache[ean]['kuva_url']=image.replace('{MODIFIERS}','w280h280@_q75').replace('{EXTENSION}','webp') or 'https://www.s-kaupat.fi/icons/missing-product-image.svg'
                        break
                    except Exception as exc:
                        if attempt == 2:
                            errors.append((ean,str(exc)[:90]))
                        else:
                            await asyncio.sleep(3*(attempt+1))
                queue.task_done()
                if len(cache) % 25 == 0:
                    save()
                    print(f'S-tuotetiedot: {len(cache)}/{len(products)}; virheitä {len(errors)}',flush=True)
                await asyncio.sleep(.2)
            await page.close()
        await asyncio.gather(*(worker() for _ in range(3)))
        await browser.close()
    save()
    print(f'Valmis: {len(cache)}/{len(products)}, virheet {errors}',flush=True)
    if errors:
        raise RuntimeError('Kaikkia tuotetietoja ei saatu; välimuisti säilytettiin uudelleenyritykseen.')

if __name__=='__main__':
    asyncio.run(main())
