"""Alkon nykyinen tuotehaku selaimella; hinnat, litrat ja saatavuus JSON-datasta."""
import asyncio
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parent

async def hae(page, path, payload=None):
    error='tuntematon virhe'
    for attempt in range(3):
        try:
            result = await page.evaluate("""async ({path,payload}) => {
                const options={signal:AbortSignal.timeout(30000)};
                if(payload!==null){options.method='POST';options.headers={'Content-Type':'application/json'};options.body=JSON.stringify(payload)}
                const response=await fetch(path,options);
                return {status:response.status,text:await response.text()};
            }""", {"path":path,"payload":payload})
            error=f"HTTP {result['status']}"
            if result['status']==200:
                return json.loads(result['text'])
        except Exception as exc:
            error=type(exc).__name__
        await asyncio.sleep(2+attempt)
    raise RuntimeError(f"Alkon tuotedata ei latautunut: {path} ({error})")


def muunna(product, store_ids):
    volume = product.get('volume')
    if not volume or 'lahja- ja juomatarvikkeet' in product.get('mainGroupName', []):
        return None
    pid = product['id']
    assert pid.isdigit(), f"Virheellinen tuotetunnus: {pid}"
    price, abv = float(product['price']), float(product['abv'])
    assert 0 < float(volume) <= 100 and price > 0 and 0 <= abv <= 100, f"Virheelliset luvut: {pid}"
    stores = sorted(set(product.get('storeId', [])) & store_ids)
    groups = ', '.join(dict.fromkeys(product.get('productGroupName', []) + product.get('mainGroupName', [])))
    return {
        'id':pid, 'nimi':product['name'], 'hinta_eur':price,
        'tilavuus_litraa':float(volume), 'alkoholi_prosentti':abv,
        'tyyppi':groups, 'linkki':f'https://www.alko.fi/fi/tuotteet/{pid}',
        'kuva_url':product.get('imageUrlSmall') or product.get('imageUrl') or '',
        'myymalat':stores, 'myymälät_maara':len(stores), 'pantti_eur':0,
        'lahde':'alko'
    }


def tallenna(name, data):
    path = ROOT / name
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + '.before-refresh.bak'))
    temporary.replace(path)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto('https://www.alko.fi/fi/tuotteet', wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(5000)
            store_data = await hae(page, '/api/stores')
            stores = [{'id':s['id'],'name':s['name'],'city':s['city']} for s in store_data['data'] if s['outletType']=='1']
            store_ids = {s['id'] for s in stores}
            products, seen, expected, skip = [], set(), None, 0
            while expected is None or skip < expected:
                data = await hae(page, '/api/search/product?lang=fi', {
                    'top':500, 'skip':skip, 'sort':'name_asc', 'includeFacets':False
                })
                expected = data['@odata.count'] if expected is None else expected
                batch = data['value']
                if not batch:
                    raise RuntimeError(f"Sivutus katkesi kohdassa {skip}/{expected}; vanha aineisto säilyy.")
                for raw in batch:
                    if raw['id'] in seen:
                        raise RuntimeError(f"Sivutuksessa toistuva tuote {raw['id']}; vanha aineisto säilyy.")
                    seen.add(raw['id'])
                    product = muunna(raw, store_ids)
                    if product:
                        products.append(product)
                skip += len(batch)
                print(f'Alko: {skip}/{expected}, juomia {len(products)}', flush=True)
                await asyncio.sleep(.25)
            assert len(seen) == expected and expected > 5000, 'Valikoiman kattavuus ei täsmää.'
            assert len(stores) > 300 and all(t['kuva_url'] for t in products)
            from paivita_alko_tuotetiedot import taydenna
            ennen_tuotesivujen_tarkistusta=len(products)
            await taydenna(page,products)
            tallenna('alko_myymalat.json', stores)
            tallenna('alko_tuotteet.json', products)
            tallenna('alko_keruu.json', {'keratty':datetime.now(timezone.utc).isoformat(), 'lahde':'https://www.alko.fi/fi/tuotteet', 'hakutuloksia':expected, 'juomia':len(products), 'myymaloita':len(stores), 'ohitetut_tarvikkeet':expected-ennen_tuotesivujen_tarkistusta,'puuttuvat_tuotesivut':ennen_tuotesivujen_tarkistusta-len(products)})
            print(f'Tallennettu {len(products)} juomaa, {len(stores)} myymälää.', flush=True)
        finally:
            await browser.close()

if __name__ == '__main__':
    asyncio.run(main())
