"""Paikallisen valikoiman, kaupunkirajauksen ja eri näyttökokojen tarkistus."""
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent

def data_checks():
    alko=json.loads((ROOT/'alko_tuotteet.json').read_text(encoding='utf8'))
    s=json.loads((ROOT/'s_ryhma_tuotteet.json').read_text(encoding='utf8'))
    metadata=json.loads((ROOT/'valikoima_tiedot.json').read_text(encoding='utf8'))
    assert len(alko)>11000 and len(s)>1000
    astores={x['id']:x for x in metadata['alko_myymalat']}
    sstores={x['id']:x for x in metadata['s_myymalat']}
    for items,stores in [(alko,astores),(s,sstores)]:
        assert len({t['id'] for t in items})==len(items)
        for t in items:
            assert t['linkki'].startswith('https://') and t['kuva_url'].startswith('https://')
            assert 0<t['tilavuus_litraa']<=100 and t['hinta_eur']>0
            ids=[e[0] if isinstance(e,list) else e for e in t['myymalat']]
            assert len(set(ids))==len(ids)==t['myymälät_maara']
            assert all(id in stores for id in ids)
    lookup={t['id']:t for t in s}
    assert lookup['6430078531450']['tilavuus_litraa']==.5
    assert lookup['9310415019773']['tilavuus_litraa']==.375
    if '--final' in sys.argv:
        cache=json.loads((ROOT/'alko_tuotetiedot.json').read_text(encoding='utf8'))
        report=json.loads((ROOT/'alko_keruu.json').read_text(encoding='utf8'))
        assert report['juomia']==len(alko)
        assert all(t['id'] in cache and not cache[t['id']].get('puuttuu') and t['pantti_eur']==cache[t['id']]['pantti_eur'] for t in alko)
        assert next(t for t in alko if t['id']=='700098')['pantti_eur']==.15
        keg=next(t for t in alko if t['id']=='959618')
        assert keg['tilavuus_litraa']==30 and keg['pantti_eur']>10
    return alko,s,metadata

async def main():
    alko,s,metadata=data_checks()
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        page=await browser.new_page(viewport={'width':1280,'height':800})
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        # Tarkistus ei lähetä ääniä eikä tarvitse tuotannon äänestyspalvelua.
        await page.route('**/api/aanet**',lambda route:route.abort())
        await page.goto('http://127.0.0.1:8766/',wait_until='domcontentloaded')
        await page.wait_for_function("document.querySelector('#info').textContent.includes('Koko Suomi:')")
        assert await page.locator('.alaotsikko').inner_text()=='Halvan alkoholin perässä – Hintavertailu & suorat linkit Alkoon ja S-ryhmän kauppoihin'
        assert await page.locator('#kaupunkiValinta').input_value()==''
        assert await page.locator('#myymalaDropdown, #myymalaToggle, #myymalaSlider, #myymalaNumero').count()==0
        assert await page.locator('#btnAlko').get_attribute('aria-pressed')=='true'
        assert await page.locator('#btnSRyhma').get_attribute('aria-pressed')=='true'
        assert f'{len(alko)} Alkon ja {len(s)} S-ryhmän tuotetta.' in await page.locator('#info').inner_text()
        assert await page.locator('#alueOhje').is_visible()
        assert not (await page.locator('#btnAlko').inner_text()).strip()
        assert not (await page.locator('#btnSRyhma').inner_text()).strip()
        assert await page.locator('#btnAlko').get_attribute('aria-label')
        assert await page.locator('tr.tuote-rivi[data-lahde=sryhma]').count()>0
        await page.locator('#btnSRyhma').click()
        await page.wait_for_timeout(400)
        assert not await page.locator('#alueOhje').is_visible()
        assert await page.locator('tr.tuote-rivi[data-lahde=sryhma]').count()==0
        city=page.locator('#kaupunkiValinta')
        await city.fill('hel')
        assert await page.get_by_role('option',name='Helsinki',exact=True).is_visible()
        await city.press('ArrowDown');await city.press('Enter')
        assert await city.input_value()=='Helsinki'
        assert 'kaupunki=Helsinki' in page.url
        assert not await page.locator('#kaupunkiLista').is_visible()
        await city.fill('tam')
        await page.get_by_role('option',name='Tampere',exact=True).click()
        assert await city.input_value()=='Tampere'
        await city.fill('espo');await city.press('Escape')
        assert not await page.locator('#kaupunkiLista').is_visible()
        await city.fill('')
        assert 'kaupunki=' not in page.url
        for width,height in [(320,640),(375,812),(560,700),(768,1024),(800,360),(1024,768),(1280,800),(1920,1080),(2560,1080)]:
            await page.set_viewport_size({'width':width,'height':height})
            await page.wait_for_timeout(180)
            result=await page.evaluate('''()=>{const els=['btnAlko','btnSRyhma','kaupunkiValinta'].map(id=>document.getElementById(id).getBoundingClientRect());return {overflow:document.documentElement.scrollWidth>innerWidth+1,outside:els.some(r=>r.left<0||r.right>innerWidth+1),overlap:els.some((a,i)=>els.some((b,j)=>i!==j&&Math.min(a.right,b.right)>Math.max(a.left,b.left)+1&&Math.min(a.bottom,b.bottom)>Math.max(a.top,b.top)+1))}}''')
            assert not any(result.values()),(width,height,result)
            if width in (375,800,1280):await page.screenshot(path=str(ROOT/f'preview-{width}.png'))
        await page.set_viewport_size({'width':1280,'height':800})
        await page.evaluate("window.vaihdaKaupunki('Helsinki')")
        await page.wait_for_timeout(450)
        astores={x['id']:x for x in metadata['alko_myymalat']}
        sstores={x['id']:x for x in metadata['s_myymalat']}
        acount=sum(any(astores[id]['city']=='Helsinki' for id in t['myymalat']) for t in alko)
        scount=sum(any(sstores[e[0]]['city']=='Helsinki' for e in t['myymalat']) for t in s)
        assert f'{acount} Alkon tuotetta.' in await page.locator('#info').inner_text()
        await page.locator('#btnSRyhma').click();await page.locator('#btnAlko').click();await page.wait_for_timeout(400)
        assert f'{scount} S-ryhmän tuotetta.' in await page.locator('#info').inner_text()
        assert await page.locator('#alueOhje').is_visible()
        await page.locator('#hakuKentta').fill('Mighty Hard Sour');await page.wait_for_timeout(550)
        row=page.locator('tr.tuote-rivi').first
        pid=await row.get_attribute('data-product-id')
        t=next(t for t in s if t['id']==pid)
        offers=[e for e in t['myymalat'] if sstores[e[0]]['city']=='Helsinki']
        cells=await row.locator('td').all_text_contents()
        assert cells[5]=='0,5' and int(cells[6])==len(offers),cells
        assert float(cells[2])==round(min(e[1]+e[2] for e in offers),2)
        await row.locator('a.tuote-linkki').click()
        assert await page.locator('#myymalaDialog').is_visible()
        assert await page.locator('.myymala-hintarivi').count()==len(offers)
        amounts=await page.locator('.myymala-hintarivi strong').all_text_contents()
        amounts=[float(x.replace(' €','')) for x in amounts]
        assert amounts==sorted(amounts) and amounts[0]==float(cells[2])
        href=await page.locator('.myymala-hintarivi a').first.get_attribute('href')
        assert 'storeId=' in href and '/tuote/' in href
        await page.set_viewport_size({'width':375,'height':812})
        await page.screenshot(path=str(ROOT/'preview-myymalat-mobile.png'))
        assert await page.locator('#myymalaDialog').evaluate('(el)=>el.scrollWidth<=el.clientWidth+1')
        await page.keyboard.press('Escape');assert not await page.locator('#myymalaDialog').is_visible()
        await page.locator('label').filter(has=page.locator('#btnPantti')).click();await page.wait_for_timeout(400)
        assert float((await page.locator('tr.tuote-rivi').first.locator('td').all_text_contents())[2])==round(min(e[1] for e in offers),2)
        await page.locator('label').filter(has=page.locator('#btnPantti')).click();await page.wait_for_timeout(400)
        key_before=await page.locator('tr[data-product-id="6430078531450"]').get_attribute('data-key')
        city_prices={}
        for offer in t['myymalat']:
            name=sstores[offer[0]]['city']
            city_prices[name]=min(city_prices.get(name,float('inf')),offer[1])
        different_city=next(name for name,price in city_prices.items() if price>t['hinta_eur']+.01)
        await page.evaluate('(city)=>window.vaihdaKaupunki(city)',different_city)
        await page.wait_for_timeout(400)
        assert await page.locator('tr[data-product-id="6430078531450"]').get_attribute('data-key')==key_before
        await page.evaluate("window.vaihdaKaupunki('Helsinki')")
        await page.wait_for_timeout(400)
        await page.locator('#hakuKentta').fill('McGuigan Black Label Moscato');await page.wait_for_timeout(550)
        assert (await page.locator('tr[data-product-id="9310415019773"]').locator('td').all_text_contents())[5]=='0,375'
        await page.locator('#hakuKentta').fill('');await page.wait_for_timeout(550)
        await page.evaluate("window.vaihdaKaupunki('')");await page.wait_for_timeout(400)
        assert 'kaupunki=' not in page.url
        await page.set_viewport_size({'width':1280,'height':800})
        await page.evaluate('window.scrollTo(0,1200)');await page.wait_for_timeout(200)
        before=await page.evaluate('window.scrollY')
        await page.evaluate("document.querySelector('#dropdownContent input[value=Viinit]').click()")
        await page.wait_for_timeout(450)
        after=await page.evaluate('window.scrollY')
        assert abs(before-after)<3,('category scroll',before,after)
        await page.evaluate("document.querySelector('#dropdownContent input[value=Viinit]').click()")
        await page.wait_for_timeout(400)
        await page.evaluate("window.vaihdaLahde('alko');window.vaihdaLahde('sryhma')")
        await page.wait_for_timeout(450)
        await page.locator('a.tuote-linkki').first.click()
        href=await page.locator('.myymala-hintarivi a').first.get_attribute('href')
        assert 'alko.fi/fi/tuotteet/' in href and 'storeId=' not in href
        if '--final' in sys.argv:
            await page.keyboard.press('Escape')
            await page.locator('#hakuKentta').fill('1664 Blanc')
            await page.wait_for_timeout(550)
            row=page.locator('tr[data-product-id="700098"]')
            product=next(t for t in alko if t['id']=='700098')
            price_with=float((await row.locator('td').all_text_contents())[2])
            await page.locator('label').filter(has=page.locator('#btnPantti')).click()
            await page.wait_for_timeout(400)
            price_without=float((await row.locator('td').all_text_contents())[2])
            assert round(price_with-price_without,2)==product['pantti_eur']==.15
            await row.locator('img.tuote-kuva').wait_for(state='visible')
            await page.wait_for_function("document.querySelector('tr[data-product-id=\"700098\"] img.tuote-kuva')?.naturalWidth>0")
        source=(ROOT/'index.html').read_text(encoding='utf8')
        sorting='function getSortedData'+source.split('function getSortedData',1)[1].split('function laskeAnnosHinta',1)[0]
        sorting_result=await page.evaluate("""source=>{
            const compare=(sort,rows,votes={})=>new Function('getFilteredData','currentSort','efHinta','laskeAnnosHinta','aanet','tuoteAvain',source+';return getSortedData().map(t=>t.id)')(()=>rows,sort,t=>t.hinta,t=>t.annos,votes,t=>t.id);
            const rows=[{id:'s',lahde:'sryhma',hinta:2,annos:1},{id:'a',lahde:'alko',hinta:2,annos:1}];
            return {ties:['hinta','annos','aanet'].map(sort=>compare(sort,[...rows])),cheaper:compare('hinta',[{...rows[0],hinta:1},rows[1]]),moreVotes:compare('aanet',[...rows],{s:1,a:0})};
        }""",sorting)
        assert all(ids==['a','s'] for ids in sorting_result['ties']),sorting_result
        assert sorting_result['cheaper']==['s','a'] and sorting_result['moreVotes']==['s','a']
        # Oman äänisivun luku testataan paikallisella vastauksella ilman tuotannon äänimuutoksia.
        vote_s=next(t for t in s if t['id']=='6430078531450')
        vote_a=next(t for t in alko if t['id']=='700098')
        def vote_key(t,price=None):
            abv='null' if t['alkoholi_prosentti'] is None else format(t['alkoholi_prosentti'],'.15g')
            return t['nimi'].strip()+'||'+abv+'||'+format(t['hinta_eur'] if price is None else price,'.15g')
        skey=vote_key(vote_s);akey=vote_key(vote_a,vote_a['hinta_eur']+1)
        response=json.dumps({'aanet':{skey:1,akey:1},'omat':[skey,akey],'max':3})
        await page.route('**/api/votes**',lambda route:route.fulfill(status=200,content_type='application/json',body=response))
        await page.evaluate("localStorage.setItem('aaniClientId','00000000-0000-4000-8000-000000000001')")
        await page.goto('http://127.0.0.1:8766/omat-aanet/',wait_until='domcontentloaded')
        await page.wait_for_selector('.aani-kortti')
        assert await page.locator('.aani-kortti').count()==2
        assert await page.locator('.aani-kortti .kauppa-logo').count()==2
        assert 'Mighty Hard Sour' in await page.locator('.aani-kortti').first.inner_text()
        assert '1664 Blanc' in await page.locator('.aani-kortti').nth(1).inner_text()
        await page.locator('.aani-kortti .nimi a').first.click()
        await page.wait_for_selector('#myymalaDialog[open]')
        assert 'Mighty Hard Sour' in await page.locator('#myymalaDialogOtsikko').inner_text()
        assert await page.locator('.myymala-hintarivi').count()==vote_s['myymälät_maara']
        assert await page.locator('#btnAlko').get_attribute('aria-pressed')=='true'
        assert await page.locator('#btnSRyhma').get_attribute('aria-pressed')=='true'
        await page.evaluate("localStorage.removeItem('aaniClientId')")
        await page.goto('http://127.0.0.1:8766/omat-aanet/',wait_until='domcontentloaded')
        await page.wait_for_selector('.tyhja a')
        assert await page.locator('.tyhja a').get_attribute('href')=='../'
        assert not errors,errors
        print(f'OK: {len(alko)} Alko, {len(s)} S; kaupunkirajaus, myymälämäärät, hinnat, valintalista, kategoriavieritys; 9 näyttökokoa.',flush=True)
        await browser.close()

if __name__=='__main__':
    asyncio.run(main())
