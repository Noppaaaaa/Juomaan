"""Yhdistää myymäläaineistot kaupunkihakuun; yksi tuote, alueen alin hinta ja myymälämäärä."""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from aineiston_keräys_S import lue_tilavuus, lue_alkoholi

ROOT = Path(__file__).resolve().parent

def lue(name):
    return json.loads((ROOT/name).read_text(encoding='utf8'))

def tallenna(name, data):
    path = ROOT/name
    tmp = path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    tmp.replace(path)

def main():
    source_files=list(ROOT.glob('s_ryhma_tuotteet_*.json'))
    expected={t['id'] for t in lue('s_ryhma_myymalat_verkkokauppa.json') if t.get('brand') in {'abc','alepa','herkku','prisma','s-market','sale'}}
    found={f.stem.rsplit('_',1)[1] for f in source_files}
    if not expected or not expected.issubset(found):
        raise RuntimeError(f'S-ryhmän myymäläkeruu on kesken: {len(expected-found)} myymäläaineistoa puuttuu. Nykyisiä valikoimia ei korvattu.')
    sstores = {s['id']:s for s in lue('s_ryhma_myymalat.json')}
    astores = {s['id']:s for s in lue('alko_myymalat.json')}
    details = lue('s_ryhma_tuotetiedot.json')
    alko = lue('alko_tuotteet.json')
    for product in alko:
        counts = Counter(astores[s]['city'] for s in set(product['myymalat']) if s in astores)
        product['kaupungit'] = {city:{'myymälät_maara':count} for city,count in counts.items()}
        assert sum(counts.values())==product['myymälät_maara']
    products, collected, corrected = {}, set(), set()
    for file in source_files:
        sid = file.stem.rsplit('_',1)[1]
        if sid not in sstores:
            raise ValueError(f'Tuntematon myymälä {sid}')
        collected.add(sid)
        city = sstores[sid]['city']
        seen = set()
        for source in json.loads(file.read_text(encoding='utf8')):
            if not source.get('linkki') or source.get('hinta_eur',0)<=0:
                continue
            ean = source['linkki'].rstrip('/').rsplit('/',1)[1]
            if ean in seen:
                continue
            seen.add(ean)
            detail = details[ean]
            pricing = detail.get('pricing') or {}
            price = pricing.get('currentPrice') or detail.get('price') or 0
            deposit = pricing.get('depositPrice') or detail.get('depositPrice') or 0
            comparison = pricing.get('comparisonPrice') or detail.get('comparisonPrice') or 0
            unit = pricing.get('comparisonUnit') or detail.get('comparisonUnit')
            volume = lue_tilavuus(detail.get('name') or source['nimi'],max(0,price-deposit),comparison if unit=='LTR' else 0)
            assert 0 < volume <= 100, f'Pakkauskoko puuttuu: {ean}'
            if abs(volume-source['tilavuus_litraa'])>.002:
                corrected.add(ean)
            if ean not in products:
                product = {k:source[k] for k in ['nimi','tyyppi','linkki','kuva_url']}
                product.update(id=ean,lahde='sryhma',tilavuus_litraa=volume,
                    alkoholi_prosentti=source.get('alkoholi_prosentti') or lue_alkoholi(detail.get('name') or '') or None,
                    myymälät_maara=0,kaupungit={},myymalat=[])
                products[ean]=product
            product=products[ean]
            if not product['kuva_url'].startswith('https://') and detail.get('kuva_url'):
                product['kuva_url']=detail['kuva_url']
            if source['kuva_url'].startswith('https://'):
                product['kuva_url']=source['kuva_url']
            offer={'hinta_eur':source['hinta_eur'],'pantti_eur':source['pantti_eur']}
            if 'hinta_eur' not in product or sum(offer.values()) < product['hinta_eur']+product['pantti_eur']:
                product.update(offer)
            local = product['kaupungit'].setdefault(city,dict(offer,**{'myymälät_maara':0}))
            if sum(offer.values()) < local['hinta_eur']+local['pantti_eur']:
                local.update(offer)
            local['myymälät_maara']+=1
            product['myymälät_maara']+=1
            product['myymalat'].append([sid,source['hinta_eur'],source['pantti_eur']])
    result=list(products.values())
    assert all(sum(c['myymälät_maara'] for c in t['kaupungit'].values())==t['myymälät_maara'] for t in result)
    assert all(t['linkki'] and t['kuva_url'] for t in result)
    for product in alko+result:
        product.pop('kaupungit',None)
        assert product['myymälät_maara']==len(product['myymalat'])
    tallenna('alko_tuotteet.json',alko)
    tallenna('s_ryhma_tuotteet.json',result)
    tallenna('valikoima_tiedot.json',{
        'koottu':datetime.now(timezone.utc).isoformat(),
        'kaupungit':sorted({s['city'] for s in [*sstores.values(),*astores.values()] if s.get('city')}),
        's_myymalat':list(sstores.values()),'alko_myymalat':list(astores.values()),
        's_myymaloita':len(sstores),'s_kerattyja_myymaloita':len(collected),
        's_juomia':len(result),'s_korjattuja_pakkauskokoja':len(corrected),
        's_puuttuvat_myymalat':[s for sid,s in sstores.items() if sid not in collected],
        'alko_myymaloita':len(astores),'alko_juomia':len(alko)
    })
    print(f'Alko {len(alko)}, S {len(result)}, S-pakkauskokoja korjattu {len(corrected)}, S-myymälöitä {len(collected)}/{len(sstores)}')

if __name__=='__main__':
    main()
