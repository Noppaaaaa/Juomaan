"""K-Ruoan julkinen kauppakohtainen valikoima Crawl4AI:n selainistunnosta."""
import asyncio
import json
import math
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from esto import rajoita, tarkista_sivu
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode, BrowserConfig

ROOT = Path(__file__).resolve().parent
GROUPS = {'oluet': 'Oluet', 'siiderit': 'Siiderit', 'lonkerot': 'Väkevät',
          'juomasekoitukset': 'Väkevät', 'viinit': 'Viinit', 'kausijuomat': 'Viinit'}

def save(path, value):
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')), encoding='utf8')
    tmp.replace(path)

def product(raw, sid, kind):
    if raw.get('store', {}).get('id') != sid:
        raise ValueError('Tuotteen myymälä ei vastaa hakua')
    if not raw.get('isAvailable') or not raw.get('availability', {}).get('store'):
        return None
    attrs = raw.get('productAttributes') or {}
    slug = attrs.get('urlSlug')
    images = raw.get('images') or []
    name = raw.get('localizedName', {}).get('finnish', '').strip()
    pricing = raw.get('mobilescan', {}).get('pricing', {})
    normal = pricing.get('normal', {})
    discount = pricing.get('discount', {})
    # Vain kaikille voimassa oleva yhden myyntipakkauksen tarjous; ei Plussa-/nippuhintoja.
    offer = discount if discount.get('discountType') == 'STANDARD' and discount.get('soldBy', {}).get('kind') == 'piece' else normal
    gross, deposit = offer.get('price', 0), offer.get('componentPrice', normal.get('componentPrice', 0))
    unit = offer.get('unitPrice') or normal.get('unitPrice') or {}
    measurements = attrs.get('measurements') or {}
    volume = measurements.get('contentSize', 0) if measurements.get('contentUnit') == 'l' else 0
    if not volume and unit.get('unit') == 'l':
        volume = unit.get('contentSize', 0)
    if not name or not slug or '/' in slug or not images or not images[0].startswith('https://'):
        return None
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in [gross, deposit, volume]):
        raise ValueError(f'Virheellinen hinta tai tilavuus: {raw["id"]}')
    if not 0 < volume <= 100 or not 0 <= deposit < gross:
        return None
    abv = re.search(r'\balk(?:oholi)?\.?\s*(\d+(?:[.,]\d+)?)\s*%', name, re.I)
    if not abv:
        percentages = list(re.finditer(r'(\d+(?:[.,]\d+)?)\s*%', name))
        abv = percentages[-1] if percentages else None
    return {'id':raw['id'], 'lahde':'kryhma', 'nimi':name, 'tyyppi':kind,
            'alkoholi_prosentti':float(abv[1].replace(',', '.')) if abv else None,
            'tilavuus_litraa':volume, 'hinta_eur':round(gross-deposit, 2), 'pantti_eur':deposit,
            'linkki':'https://www.k-ruoka.fi/kauppa/tuote/'+slug, 'kuva_url':images[0]}

def kirjoita_valikoima(stores, folder):
    merged, collected = {}, set()
    for store in stores:
        path = folder/(store['id']+'.json')
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf8'))
        if data.get('id') != store['id'] or set(data.get('totals', {})) != set(GROUPS):
            raise ValueError(f"Virheellinen välimuisti: {path.name}")
        collected.add(store['id'])
        for p in data['products']:
            target = merged.setdefault(p['id'], dict(p, myymalat=[]))
            target['myymalat'].append([store['id'], p['hinta_eur'], p['pantti_eur']])
            if p['hinta_eur']+p['pantti_eur'] < target['hinta_eur']+target['pantti_eur']:
                target.update(hinta_eur=p['hinta_eur'], pantti_eur=p['pantti_eur'])
    for p in merged.values():
        p['myymälät_maara'] = len(p['myymalat'])
    if len(merged) < 100:
        return len(merged), len(collected)
    save(ROOT/'k_ryhma_tuotteet.json', list(merged.values()))
    save(ROOT/'k_ryhma_keruu.json', dict(
        keratty=datetime.now(timezone.utc).isoformat(), myymaloita=len(stores),
        kerattyja_myymaloita=len(collected),
        puuttuvat_myymalat=[s['id'] for s in stores if s['id'] not in collected],
        tuotteita=len(merged)))
    from kokoa_valikoimat import paivita_k_tiedot
    paivita_k_tiedot()
    return len(merged), len(collected)

async def main():
    stores = json.loads((ROOT/'k_ryhma_myymalat.json').read_text(encoding='utf8'))
    folder = ROOT/'k_aineisto'
    folder.mkdir(exist_ok=True)
    tuotteita, valmiita = kirjoita_valikoima(stores, folder)
    print(f'K-aineisto: {tuotteita} tuotetta, {valmiita}/{len(stores)} myymälää', flush=True)
    pages, headers = [], []
    async with AsyncWebCrawler(config=BrowserConfig(headless=os.getenv('K_NAKYVA_SELAIN') != '1')) as crawler:
        async def capture(request):
            if '/kr-api/v2/product-search/' in request.url:
                h = await request.all_headers()
                headers.append({k:v for k,v in h.items() if k in ['accept','x-k-build-number','x-k-experiments']})
        tasks = []
        async def hook(page, **kwargs):
            pages.append(page)
            page.on('request', lambda r: tasks.append(asyncio.create_task(capture(r))))
            return page
        crawler.crawler_strategy.set_hook('before_goto', hook)
        result = await crawler.arun(url='https://www.k-ruoka.fi/kauppa/tuotteet/juomat/oluet',
            config=CrawlerRunConfig(cache_mode=CacheMode.BYPASS, session_id='k-keruu', delay_before_return_html=12))
        await asyncio.gather(*tasks)
        tarkista_sivu(getattr(result, "status_code", None), getattr(result, "html", ""), getattr(result, "response_headers", None))
        if not result.success or not headers:
            raise RuntimeError('K-Ruoan julkinen tuotehaku ei latautunut. Nykyistä valikoimaa ei muutettu.')
        page, request_headers = pages[-1], headers[-1]
        request_lock=asyncio.Lock()
        snapshot_lock=asyncio.Lock()
        async def snapshot():
            async with snapshot_lock:
                tuotteita, valmiita = kirjoita_valikoima(stores, folder)
                print(f'K-aineisto: {tuotteita} tuotetta, {valmiita}/{len(stores)} myymälää', flush=True)
                if os.getenv('GITHUB_ACTIONS') == 'true' and tuotteita >= 100:
                    subprocess.run(['git', 'add', '--', 'k_ryhma_tuotteet.json', 'k_ryhma_keruu.json', 'valikoima_tiedot.json'], check=True)
                    changed = subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode
                    if changed:
                        subprocess.run(['git', 'commit', '-m', 'data: update Kesko catalogue'], check=True)
                        subprocess.run(['git', 'fetch', 'origin', 'main'], check=True)
                        subprocess.run(['git', 'rebase', 'origin/main'], check=True)
                        subprocess.run(['git', 'push', 'origin', 'HEAD:main'], check=True)
        next_request=0
        pause_until=0
        async def fetch(sid, group, offset):
            nonlocal next_request,pause_until
            loop=asyncio.get_running_loop()
            for attempt in range(6):
                async with request_lock:
                    await asyncio.sleep(max(0,next_request-loop.time(),pause_until-loop.time()))
                    next_request=loop.time()+.4
                response = await page.evaluate('''async args=>{
                    const u=new URL('/kr-api/v2/product-search/',location.origin);
                    for(const [k,v] of Object.entries({offset:args.offset,language:'fi',categoryPath:'juomat/'+args.group,storeId:args.sid,limit:100,discountFilter:false,isTrOffer:false}))u.searchParams.set(k,v);
                    const r=await fetch(u,{method:'POST',headers:args.headers,signal:AbortSignal.timeout(45000)});
                    const text=await r.text(); let data=null;
                    if(r.ok){try {data=JSON.parse(text)} catch (_) {}}
                    return {status:r.status,retryAfter:r.headers.get('retry-after'),body:data===null?text.slice(0,20000):'',data};
                }''', dict(sid=sid, group=group, offset=offset, headers=request_headers))
                if response['status'] == 200:
                    tarkista_sivu(response['status'], response.get('body', ''), {})
                    data = response['data']
                    if not isinstance(data, dict):
                        raise RuntimeError('K-ryhmän tuotehaku ei palauttanut JSON-aineistoa.')
                    assert data['storeId'] == sid and isinstance(data['totalHits'], int)
                    return data
                if response['status'] in (403, 429):
                    await snapshot()
                    rajoita(response['status'], response.get('retryAfter'))
                if response['status'] not in [500, 502, 503, 504]:
                    await snapshot()
                    raise RuntimeError(f'K-tuotehaku HTTP {response["status"]}: {sid}/{group}. Keruu pysäytetty.')
                await asyncio.sleep(10*(attempt+1))
            await snapshot()
            raise RuntimeError(f'K-tuotehaku HTTP {response["status"]}: {sid}/{group} ei vastaa uusintayrityksiin')
        queue = asyncio.Queue()
        for store in stores:
            if not (folder/(store['id']+'.json')).exists():
                queue.put_nowait(store)
        completed = len(stores)-queue.qsize()
        failures = []
        async def worker():
            nonlocal completed
            while not queue.empty():
                store = queue.get_nowait()
                try:
                    sid, products, totals = store['id'], {}, {}
                    for group, kind in GROUPS.items():
                        for pagination_attempt in range(3):
                            offset, seen, other_rows, rows_read = 0, set(), 0, 0
                            while rows_read < totals.get(group, 0) or offset == 0:
                                data = await fetch(sid, group, offset)
                                totals[group] = data['totalHits']
                                rows = data.get('result')
                                if not isinstance(rows, list):
                                    raise RuntimeError(f'K-tuotehaku palautti virheellisen sivun: {sid}/{group}')
                                if not rows:
                                    break
                                for row in rows:
                                    if row.get('type') != 'product':
                                        other_rows += 1
                                        continue
                                    raw = row['product']; seen.add(raw['id'])
                                    parsed = product(raw, sid, kind)
                                    if parsed: products[parsed['id']] = parsed
                                rows_read += len(rows)
                                offset += len(rows)
                                if rows_read < totals[group]:
                                    await asyncio.sleep(.15)
                            if len(seen) + other_rows >= totals[group]:
                                break
                            print(
                                f'K-sivutus vajaa: {sid}/{group}: '
                                f'{len(seen)} tuotetta + {other_rows} muuta riviä '
                                f'({rows_read}/{totals[group]} sivutettu) '
                                f'(yritys {pagination_attempt + 1}/3)',
                                flush=True,
                            )
                            await asyncio.sleep(2 * (pagination_attempt + 1))
                        else:
                            raise RuntimeError(
                                f'K-sivutus vajaa uusintayritysten jälkeen: '
                                f'{sid}/{group}: {len(seen)}/{totals[group]}'
                            )
                    save(folder/(sid+'.json'), dict(id=sid, products=list(products.values()), totals=totals))
                except RuntimeError as error:
                    if not any('HTTP '+str(status) in str(error) for status in [500,502,503,504]):
                        raise
                    failures.append(dict(id=store['id'],error=str(error)))
                    print(str(error),flush=True)
                    continue
                completed += 1
                if completed % 10 == 0 or completed == len(stores):
                    print(f'K-myymälät {completed}/{len(stores)}', flush=True)
                    await snapshot()
        await asyncio.gather(*(worker() for _ in range(1)))
        if failures:
            retry=failures[:];failures.clear()
            for failure in retry:queue.put_nowait(next(store for store in stores if store['id']==failure['id']))
            await asyncio.sleep(30)
            await worker()
        save(ROOT/'k_hakuvirheet.json',failures)
    tuotteita, valmiita = kirjoita_valikoima(stores, folder)
    if tuotteita < 100:
        raise RuntimeError('K-keruu tuotti epäuskottavan vähän tuotteita.')
    print(f'K-keruu valmis: {tuotteita} tuotetta, {valmiita}/{len(stores)} myymälää', flush=True)

if __name__ == '__main__':
    asyncio.run(main())
