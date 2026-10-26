"""Poimii pantit Alkon omista tuotesivuista; välimuisti mahdollistaa keruun jatkamisen."""
import asyncio
import json
import re
import math
from datetime import datetime,timezone
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent
CACHE=ROOT/'alko_tuotetiedot.json'

async def taydenna(page, products):
    cache=json.loads(CACHE.read_text(encoding='utf8')) if CACHE.exists() else {}
    queue=asyncio.Queue()
    for product in products:
        old=cache.get(product['id'])
        if old is None or old.get('puuttuu') or old.get('tilavuus_litraa')!=product['tilavuus_litraa']:
            queue.put_nowait(product)
    errors=[]
    done=0
    total=queue.qsize()
    def save():
        tmp=CACHE.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(cache,ensure_ascii=False,separators=(',',':')),encoding='utf8')
        tmp.replace(CACHE)
    async def worker():
        nonlocal done
        while not queue.empty():
            product=queue.get_nowait()
            pid=product['id']
            for attempt in range(4):
                try:
                    result=await page.evaluate("""async id=>{
                        const response=await fetch('/fi/tuotteet/'+id,{headers:{RSC:'1'},signal:AbortSignal.timeout(30000)});
                        return {status:response.status,text:await response.text()};
                    }""",pid)
                    if result['status']==404 or re.search(r'"digest":"NEXT_HTTP_ERROR_FALLBACK;404"',result['text']):
                        cache[pid]={'puuttuu':True,'tilavuus_litraa':product['tilavuus_litraa'],'keratty':datetime.now(timezone.utc).isoformat()}
                        break
                    if result['status']!=200:
                        raise RuntimeError(f"HTTP {result['status']}")
                    def find(value):
                        if isinstance(value,dict):
                            if value.get('productId')==pid and isinstance(value.get('valueInCents'),(int,float)):
                                deposit=value.get('deposit')
                                if deposit is None or deposit=='$undefined':deposit=0
                                if isinstance(deposit,(int,float)):
                                    return {'deposit':deposit,'total':value['valueInCents']/100}
                            for item in value.values():
                                found=find(item)
                                if found is not None:return found
                        elif isinstance(value,list):
                            for item in value:
                                found=find(item)
                                if found is not None:return found
                        return None
                    data=None
                    decoder=json.JSONDecoder()
                    # Flight-tekstikenttä voi päättyä suoraan seuraavan JSON-tietueen alkuun.
                    for match in re.finditer(r'[0-9a-f]+:(?=[{\[])',result['text']):
                        try:
                            value,_=decoder.raw_decode(result['text'],match.end())
                        except json.JSONDecodeError:
                            continue
                        data=find(value)
                        if data is not None:break
                    if data is None:
                        raise RuntimeError('Tuotteen panttitieto puuttuu')
                    deposit=float(data['deposit'])
                    total_price=product['hinta_eur']+product['pantti_eur']
                    assert math.isfinite(deposit) and 0<=deposit<total_price and deposit<=data['total'], f'Virheellinen pantti: {pid}, pantti {deposit}, kokonaishinta {total_price}'
                    cache[pid]={'pantti_eur':deposit,'tilavuus_litraa':product['tilavuus_litraa'],'keratty':datetime.now(timezone.utc).isoformat()}
                    break
                except Exception as exc:
                    if attempt==3:
                        errors.append((pid,(str(exc) or type(exc).__name__).splitlines()[0][:100]))
                        print(f'Panttitiedon virhe: {errors[-1]}',flush=True)
                        if len(errors)>=8:
                            save()
                            raise RuntimeError('Panttitietojen keruu keskeytetty toistuvien virheiden vuoksi.')
                    else:
                        await asyncio.sleep((30 if 'HTTP 403' in str(exc) or 'HTTP 429' in str(exc) else 2)*(attempt+1))
            done+=1
            queue.task_done()
            if done%50==0:
                save()
                print(f'Alkon pantit: {done}/{total}; välimuistissa {len(cache)}, virheitä {len(errors)}',flush=True)
            await asyncio.sleep(.1)
    await asyncio.gather(*(worker() for _ in range(2)))
    save()
    if errors:
        raise RuntimeError(f'Panttitiedot kesken; välimuisti tallessa: {errors[:10]}')
    products[:]=[product for product in products if not cache[product['id']].get('puuttuu')]
    for product in products:
        total_price=round(product['hinta_eur']+product['pantti_eur'],2)
        product['pantti_eur']=cache[product['id']]['pantti_eur']
        product['hinta_eur']=round(total_price-product['pantti_eur'],2)
    return products

async def main():
    from aineiston_keräys_V5 import tallenna
    products=json.loads((ROOT/'alko_tuotteet.json').read_text(encoding='utf8'))
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        try:
            page=await browser.new_page()
            await page.goto('https://www.alko.fi/fi/tuotteet',wait_until='domcontentloaded',timeout=60000)
            await page.wait_for_timeout(7000)
            await taydenna(page,products)
            tallenna('alko_tuotteet.json',products)
            print(f'Pantit täydennetty: {len(products)} tuotetta.',flush=True)
        finally:
            await browser.close()

if __name__=='__main__':
    asyncio.run(main())
