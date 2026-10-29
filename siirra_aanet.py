"""Siirtää vanhat äänet uusille product_key-arvoille aineiston päivityksen jälkeen.

Yhdistää vanhat äänet uusiin tuotteisiin prioriteetillä:
1. Sama nimi + sama kauppa (s, alko, k)
2. Sama kuva + sama kauppa
3. Sama nimi + toinen kauppa (prioriteetillä s, alko, k)
4. Sama kuva + toinen kauppa

Kauppa-avaimet: sryhma (S-ryhmä), alko (Alko), kryhma (K-ryhmä)

Käyttö: python3 siirra_aanet.py [--api-token TOKEN] [--api-key KEY] [--zone-id ZONE]
Tai aseta ympäristömuuttujat: CF_API_TOKEN, CF_API_KEY, CF_ZONE_ID
"""
import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Kauppa-avaimet product_key-formaatissa: "nimi||alkoholi_prosentti||hinta_eur"
# lahde-kenttä tuotteessa: 'sryhma', 'alko', 'kryhma'
STORE_PRIORITY = ['sryhma', 'alko', 'kryhma']


def lue_tuotteet():
    """Lue kaikki tuotteet JSON-tiedostoista ja palauta listana."""
    products = []
    # Alko
    alko_path = ROOT / 'alko_tuotteet.json'
    if alko_path.exists():
        for p in json.loads(alko_path.read_text(encoding='utf-8')):
            p['lahde'] = 'alko'
            products.append(p)
    # S-ryhmä
    s_path = ROOT / 's_ryhma_tuotteet.json'
    if s_path.exists():
        for p in json.loads(s_path.read_text(encoding='utf-8')):
            p['lahde'] = 'sryhma'
            products.append(p)
    # K-ryhmä (jos on)
    k_path = ROOT / 'k_ryhma_tuotteet.json'
    if k_path.exists():
        for p in json.loads(k_path.read_text(encoding='utf-8')):
            p['lahde'] = 'kryhma'
            products.append(p)
    return products


def muodosta_key(nimi, alkoholi, hinta):
    """Muodosta product_key annetuista kentistä."""
    return f"{nimi}||{alkoholi}||{hinta}"


def normalisoi_nimi(nimi):
    """Normalisoi tuotteen nimi vertailua varten."""
    if not nimi:
        return ''
    return nimi.strip().lower().replace('  ', ' ')


def sama_nimi(n1, n2):
    """Tarkista nimien samankaltaisuus."""
    return normalisoi_nimi(n1) == normalisoi_nimi(n2)


def sama_kuva(url1, url2):
    """Tarkista kuvien samankaltaisuus."""
    if not url1 or not url2:
        return False
    # Verrataan URL-osoitteiden basename-osaa tai koko URLia
    def base(u):
        try:
            return u.split('?')[0].split('/')[-1].lower()
        except Exception:
            return u.lower()
    return base(url1) == base(url2) or base(url1) in base(url2) or base(url2) in base(url1)


def etsi_uusi_key(vanha_key, tuotteet, vanha_lahde):
    """Etsi uusi product_key vanhalle äänelle.

    Prioriteetti:
    1. Sama nimi + sama kauppa
    2. Sama kuva + sama kauppa
    3. Sama nimi + toinen kauppa (prioriteetillä s, alko, k)
    4. Sama kuva + toinen kauppa
    """
    # Hae vanhan äänen tiedot
    parts = vanha_key.split('||')
    if len(parts) < 3:
        return None
    old_name = parts[0]
    old_alc = parts[1] if len(parts) > 1 else ''
    old_price = parts[2] if len(parts) > 2 else ''

    # 1. Etsi sama nimi + sama kauppa
    for p in tuotteet:
        if p.get('lahde') != vanha_lahde:
            continue
        if sama_nimi(old_name, p.get('nimi', '')):
            alkoholi = p.get('alkoholi_prosentti', '')
            hinta = p.get('hinta_eur', '')
            if alkoholi is None:
                alkoholi = ''
            if hinta is None:
                hinta = ''
            return muodosta_key(p['nimi'], alkoholi, hinta)

    # 2. Etsi sama kuva + sama kauppa
    vanha_kuva = ''
    for p in tuotteet:
        if p.get('lahde') != vanha_lahde:
            continue
        if vanha_kuva and sama_kuva(vanha_kuva, p.get('kuva_url', '')):
            alkoholi = p.get('alkoholi_prosentti', '')
            hinta = p.get('hinta_eur', '')
            if alkoholi is None:
                alkoholi = ''
            if hinta is None:
                hinta = ''
            return muodosta_key(p['nimi'], alkoholi, hinta)

    # 3. Etsi sama nimi + toinen kauppa (prioriteetillä s, alko, k)
    for store in STORE_PRIORITY:
        if store == vanha_lahde:
            continue
        for p in tuotteet:
            if p.get('lahde') != store:
                continue
            if sama_nimi(old_name, p.get('nimi', '')):
                alkoholi = p.get('alkoholi_prosentti', '')
                hinta = p.get('hinta_eur', '')
                if alkoholi is None:
                    alkoholi = ''
                if hinta is None:
                    hinta = ''
                return muodosta_key(p['nimi'], alkoholi, hinta)

    # 4. Etsi sama kuva + toinen kauppa
    for store in STORE_PRIORITY:
        if store == vanha_lahde:
            continue
        for p in tuotteet:
            if p.get('lahde') != store:
                continue
            if vanha_kuva and sama_kuva(vanha_kuva, p.get('kuva_url', '')):
                alkoholi = p.get('alkoholi_prosentti', '')
                hinta = p.get('hinta_eur', '')
                if alkoholi is None:
                    alkoholi = ''
                if hinta is None:
                    hinta = ''
                return muodosta_key(p['nimi'], alkoholi, hinta)

    return None


def hae_aanet_from_api():
    """Hae nykyiset äänet /api/votes GET-päätepisteestä."""
    from urllib import request, error
    url = 'https://juomaan.fi/api/votes'
    req = request.Request(url)
    try:
        with request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data.get('aanet', {})
    except error.HTTPError as e:
        print(f'Virhe äänten haussa: HTTP {e.code}')
        return {}
    except Exception as e:
        print(f'Virhe äänten haussa: {e}')
        return {}


def paivitys_aanet_api(mapping):
    """Siirrä äänet API:n kautta."""
    url = 'https://juomaan.fi/api/votes'
    payload = json.dumps({'migrate': mapping}).encode('utf-8')
    req = request.Request(url, data=payload, method='POST')
    req.add_header('Content-Type', 'application/json')
    try:
        with request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            print(f'API-vastaus: {data}')
            return data
    except error.HTTPError as e:
        print(f'Virhe päivityksessä: HTTP {e.code}')
        try:
            print(e.read().decode('utf-8'))
        except Exception:
            pass
        return None
    except Exception as e:
        print(f'Virhe päivityksessä: {e}')
        return None


def main():
    parser = argparse.ArgumentParser(description='Siirrä vanhat äänet uusiin product_key-arvoihin')
    parser.add_argument('--dry-run', action='store_true', help='Näytä muutokset mutta älä suorita')
    args = parser.parse_args()

    # Lue tuotteet
    print('Luetaan tuotteet...')
    tuotteet = lue_tuotteet()
    print(f'Löytyi {len(tuotteet)} tuotetta.')

    # Hae nykyiset äänet
    print('Haetaan nykyiset äänet...')
    aanet = hae_aanet_from_api()
    print(f'Löytyi {len(aanet)} eri product_key-ääntä.')

    if not aanet:
        print('Ei ääniä siirrettäväksi.')
        return

    # Rakenna mapping
    mapping = {}
    unmatched = []
    for vanha_key in aanet.keys():
        # Päättely: mikä kauppa äänellä on? Tarkastetaan tuotteen nimi.
        vanha_lahde = 'sryhma'  # oletus
        parts = vanha_key.split('||')
        if len(parts) >= 3:
            vanha_nimi = parts[0]
            # Arvataan kauppa nimen perusteella (ei täydellinen, mutta riittävä)
            # Tarkempi tapa: etsi tuote nimellä ja katse sen lahde
            for p in tuotteet:
                if sama_nimi(vanha_nimi, p.get('nimi', '')):
                    vanha_lahde = p.get('lahde', 'sryhma')
                    break

        uusi_key = etsi_uusi_key(vanha_key, tuotteet, vanha_lahde)
        if uusi_key and uusi_key != vanha_key:
            mapping[vanha_key] = uusi_key
            print(f'  {vanha_key[:60]}... -> {uusi_key[:60]}...')
        elif uusi_key:
            pass  # Sama key, ei tarvii päivitystä
        else:
            unmatched.append(vanha_key)
            print(f'  Ei vastaavaa tuotetta: {vanha_key[:60]}...')

    print(f'\nSiirrettävää: {len(mapping)} ääntä')
    print(f'Löytämättä: {len(unmatched)} ääntä')

    if not mapping:
        print('Ei muutoksia.')
        return

    if args.dry_run:
        print('\nDry-run: ei siirretty mitään.')
        print('Siirrettävä mapping:')
        print(json.dumps(mapping, ensure_ascii=False, indent=2)[:1000])
        return

    # Siirrä äänet API:n kautta
    print('\nSiirretään äänet...')
    result = paivitys_aanet_api(mapping)
    if result:
        print(f'Valmis: {result.get("moved", 0)} ääntä siirretty {result.get("keys", 0)} tuotteelle.')
    else:
        print('Virhe siirrossa. Tarkista että worker on päivitetty.')


if __name__ == '__main__':
    main()
