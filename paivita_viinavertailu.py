"""Publish derived price data for the comparison pages."""

import json
import re
import subprocess
import xml.etree.ElementTree as ET
from base64 import b64encode
from datetime import datetime
from html import escape
from itertools import groupby
from math import isfinite
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
HINTAKENTAT = ('nimi', 'tyyppi', 'linkki', 'tilavuus_litraa', 'alkoholi_prosentti', 'hinta_eur', 'pantti_eur')
BUDJETTIVIINIT = (
    ('kuohuviinit-alle-15-euroa', 'kuohuviinit', 15),
    ('kuohuviinit-alle-12-euroa', 'kuohuviinit', 12),
    ('kuohuviinit-alle-20-euroa', 'kuohuviinit', 20),
    ('punaviinit-alle-10-euroa', 'punaviinit', 10),
    ('valkoviinit-alle-10-euroa', 'valkoviinit', 10),
)


def kirjoita(polku, sisalto):
    tmp = polku.with_suffix('.tmp')
    tmp.write_text(sisalto, encoding='utf-8')
    tmp.replace(polku)


def pakkaa_alko(tuotteet):
    myymalat = sorted({tunniste for tuote in tuotteet for tunniste in tuote['myymalat']})
    bitit = {tunniste: 1 << i for i, tunniste in enumerate(myymalat)}
    for tuote in tuotteet:
        tunnisteet = tuote['myymalat']
        if tunnisteet == sorted(set(tunnisteet)):
            maski = sum(bitit[tunniste] for tunniste in tunnisteet)
            tuote['myymalat'] = b64encode(maski.to_bytes((maski.bit_length() + 7) // 8, 'little')).decode('ascii')
    return {'myymalat': myymalat, 'tuotteet': tuotteet}


def pakkaa_marketit(tuotteet):
    myymalat = sorted({rivi[0] for tuote in tuotteet for rivi in tuote['myymalat']})
    tunnisteet = {tunniste: i for i, tunniste in enumerate(myymalat)}

    # Keep the original order, including ties between offers.
    for tuote in tuotteet:
        tuote['myymalat'] = [
            [hinta, pantti, *[tunnisteet[tunniste] for tunniste, _, _ in ryhma]]
            for (hinta, pantti), ryhma in groupby(tuote['myymalat'], key=lambda rivi: rivi[1:])
        ]
    return {'myymalat': myymalat, 'tuotteet': tuotteet}


def otos_html(kansio, kuvaus, rivit, keratty, lahde='kerätyistä'):
    sivu = ROOT / kansio / 'index.html'
    html = sivu.read_text(encoding='utf-8')
    html, caption_count = re.subn(
        r'(<caption id="otoksen-paivays">)[^<]*(</caption>)',
        rf'\g<1>{kuvaus} {keratty.day}.{keratty.month}.{keratty.year} {lahde} hinnoista.\g<2>',
        html,
    )
    html, row_count = re.subn(
        r'(<tbody id="rivit">).*?(</tbody>)',
        lambda m: m[1] + '\n' + '\n'.join(rivit) + '\n            ' + m[2],
        html,
        flags=re.S,
    )
    if (caption_count, row_count) != (1, 1):
        raise ValueError(f'{kansio}: otokselle tarvitaan yksi otsikko ja yksi taulukko.')
    return sivu, html


def pakkausrivit(tuotteet, litrahinta=False, alle=None, annoshinta=False):
    ehdokkaat = []
    for tuote in tuotteet:
        nimi = (tuote['nimi'] or '').strip()
        linkki = tuote['linkki'] or ''
        litrat = tuote['tilavuus_litraa']
        perushinta = tuote['hinta_eur']
        if not (nimi and re.match(r'https://(?:www\.)?alko\.fi/', linkki, re.I)
                and all(isinstance(arvo, (int, float)) and isfinite(arvo) and arvo > 0
                        for arvo in (litrat, perushinta))):
            continue
        hinta = round(perushinta + (tuote['pantti_eur'] or 0), 2)
        vahvuus = tuote['alkoholi_prosentti'] if annoshinta else None
        if annoshinta and not (isinstance(vahvuus, (int, float)) and isfinite(vahvuus) and vahvuus > 0):
            continue
        if alle is None or hinta < alle:
            vertailuhinta = hinta * 1.5 / (litrat * vahvuus) if annoshinta else hinta
            ehdokkaat.append((vertailuhinta, nimi, linkki, litrat, hinta))
    if alle is None and len(ehdokkaat) < 10:
        raise ValueError('Alkon pakkaushintojen aineisto on puutteellinen.')

    rivit = []
    for vertailuhinta, nimi, linkki, litrat, hinta in sorted(ehdokkaat)[:10]:
        koko = f'{litrat:g}'.replace('.', ',')
        hinnat = f'<td>{hinta:.2f} €</td>'
        if annoshinta:
            hinnat += f'<td>{vertailuhinta:.2f} €</td>'
        elif litrahinta:
            hinnat += f'<td>{hinta / litrat:.2f} €</td>'
        hinnat = hinnat.replace('.', ',')
        rivit.append(f'                <tr><td><a href="{escape(linkki)}">{escape(nimi)}</a></td>'
                     f'<td>{koko} l</td>{hinnat}</tr>')
    return rivit


def juomaryhma(tuote):
    tyyppi = (tuote['tyyppi'] or '').split(',', 1)[0].strip().casefold()
    nimi = (tuote['nimi'] or '').casefold()
    if tyyppi in ('oluet', 'alkoholittomat oluet'):
        return 'oluen-hinnat'
    if 'seltzer' in nimi or 'zeltzer' in nimi:
        return 'halvimmat-seltzerit'
    if tyyppi in ('siiderit', 'alkoholittomat siiderit'):
        return 'halvimmat-siiderit'
    if tyyppi in ('long drink', 'maustettu long drink') or re.search(r'lonkero|long[ -]drink', nimi):
        return 'halvimmat-lonkerot'
    return None


def markettihinnat(alko, sryhma, kryhma, valikoima):
    myymalat = {
        'sryhma': {str(t['id']): t for t in valikoima['s_myymalat']},
        'kryhma': {str(t['id']): t for t in valikoima['k_myymalat']},
    }
    prismat = {avain for avain, myymala in myymalat['sryhma'].items()
               if re.match(r'prisma\b', myymala['name'], re.IGNORECASE)}
    ketjut = {'sryhma': 's-ryhman-halvin-alkoholi', 'kryhma': 'k-ryhman-halvin-alkoholi'}
    ryhmat = {}
    for lahde, tuotteet in [('alko', alko), ('sryhma', sryhma), ('kryhma', kryhma)]:
        for tuote in tuotteet:
            ryhma = juomaryhma(tuote)
            tiedot = {kentta: tuote.get(kentta) for kentta in HINTAKENTAT}
            if lahde == 'alko':
                if ryhma:
                    ryhmat.setdefault(ryhma, []).append({**tiedot, 'lahde': lahde})
                continue
            if not tuote['myymalat']:
                continue
            avaimet = myymalat[lahde]
            halvin = halvin_markettituote(tiedot, tuote['myymalat'], avaimet, lahde)
            if ryhma:
                ryhmat.setdefault(ryhma, []).append(halvin)
            if (tiedot['alkoholi_prosentti'] or 0) <= 0.5:
                continue
            ryhmat.setdefault(ketjut[lahde], []).append(halvin)
            if lahde == 'sryhma':
                hintarivit = [rivi for rivi in tuote['myymalat'] if str(rivi[0]) in prismat]
                if hintarivit:
                    ryhmat.setdefault('prisman-halvin-alkoholi', []).append(
                        halvin_markettituote(tiedot, hintarivit, avaimet, lahde))
    return ryhmat


def halvin_markettituote(tiedot, hintarivit, myymalat, lahde):
    tunniste, hinta, pantti = min(hintarivit, key=lambda rivi: rivi[1] + rivi[2])
    myymala = myymalat[str(tunniste)]
    nimi, arvo = ('storeId', myymala['id']) if lahde == 'sryhma' else ('kauppa', myymala['slug'])
    osoite = urlsplit(tiedot['linkki'])
    parametrit = dict(parse_qsl(osoite.query, keep_blank_values=True))
    parametrit[nimi] = arvo
    return {**tiedot, 'hinta_eur': hinta, 'pantti_eur': pantti,
            'linkki': osoite._replace(query=urlencode(parametrit)).geturl(), 'myymala': myymala['name'],
            'lahde': lahde}


def markettiotos(tuotteet, annoshinta):
    kaupat = {'alko': ('Alko', 'alko.fi'), 'sryhma': ('S-ryhmä', 's-kaupat.fi'), 'kryhma': ('K-ryhmä', 'k-ruoka.fi')}
    ehdokkaat = []
    for tuote in tuotteet:
        kauppa, domain = kaupat[tuote['lahde']]
        linkki = tuote['linkki'] or ''
        osoite = urlsplit(linkki)
        nimi = (tuote['nimi'] or '').strip()
        litrat = tuote['tilavuus_litraa']
        vahvuus = tuote['alkoholi_prosentti']
        perushinta = tuote['hinta_eur']
        if not (nimi and osoite.scheme == 'https' and osoite.hostname in (domain, 'www.' + domain)
                and all(isinstance(arvo, (int, float)) and isfinite(arvo) and arvo > 0
                        for arvo in (litrat, vahvuus, perushinta)) and vahvuus > 0.5):
            continue
        hinta = round(perushinta + (tuote['pantti_eur'] or 0), 2)
        ehdokkaat.append((hinta, nimi, linkki, litrat, tuote.get('myymala') or kauppa, vahvuus))
    rivit = []
    if annoshinta:
        ehdokkaat.sort(key=lambda rivi: (rivi[0] / (rivi[3] * rivi[5] / 1.5), rivi[1].casefold()))
    else:
        ehdokkaat.sort()
    for hinta, nimi, linkki, litrat, kauppa, vahvuus in ehdokkaat[:10]:
        koko = f'{litrat:g}'.replace('.', ',')
        pitoisuus = f'{vahvuus:g}'.replace('.', ',')
        vertailuhinta = hinta / (litrat * vahvuus / 1.5) if annoshinta else hinta / litrat
        hinnat = f'<td>{hinta:.2f} €</td><td>{vertailuhinta:.2f} €</td>'.replace('.', ',')
        rivit.append(f'                <tr><td><a href="{escape(linkki)}">{escape(nimi)}</a>'
                     f'<br><small>{escape(kauppa)} · {pitoisuus} %</small></td><td>{koko} l</td>{hinnat}</tr>')
    return rivit


def lue_json(polku, oletus=None):
    return json.loads(polku.read_text(encoding='utf-8')) if polku.exists() else oletus


def viiniluokka(tuote):
    return (tuote['tyyppi'] or '').split(',', 1)[0].strip()


def budjettiviinit(tuotteet, viinityyppi, raja):
    return [t for t in tuotteet if viiniluokka(t) == viinityyppi
            and t['hinta_eur'] is not None and round(t['hinta_eur'] + (t['pantti_eur'] or 0), 2) < raja]


def viinit(tuotteet):
    luokat = {'punaviinit', 'valkoviinit', 'roseeviinit', 'kuohuviinit'}
    return [tuote for tuote in tuotteet if (tuote['tyyppi'] or '').split(',', 1)[0].strip() in luokat]


def paivita_sivustokartta(muuttuneet, paivitysaika):
    if not muuttuneet:
        return
    if not paivitysaika.tzinfo:
        paivitysaika = paivitysaika.replace(tzinfo=ZoneInfo('Europe/Helsinki'))
    polku = ROOT / 'sitemap.xml'
    ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', ns)
    kartta = ET.fromstring(polku.read_text(encoding='utf-8'))
    for sivu in kartta.findall(f'{{{ns}}}url'):
        osoite = sivu.findtext(f'{{{ns}}}loc')
        if osoite not in muuttuneet:
            continue
        lastmod = sivu.find(f'{{{ns}}}lastmod')
        if lastmod is None:
            lastmod = ET.SubElement(sivu, f'{{{ns}}}lastmod')
        edellinen = datetime.fromisoformat(lastmod.text) if lastmod.text else None
        if edellinen and not edellinen.tzinfo:
            edellinen = edellinen.replace(tzinfo=ZoneInfo('Europe/Helsinki'))
        if not edellinen or paivitysaika > edellinen:
            lastmod.text = paivitysaika.isoformat(timespec='seconds')
    ET.indent(kartta, space='  ')
    kirjoita(polku, '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(kartta, encoding='unicode') + '\n')


def paivita():
    tuotteet = json.loads((ROOT / 'alko_tuotteet.json').read_text(encoding='utf-8'))
    raportti = json.loads((ROOT / 'alko_keruu.json').read_text(encoding='utf-8'))
    keratty = datetime.fromisoformat(raportti['keratty']).astimezone(ZoneInfo('Europe/Helsinki'))
    hinnasto = [{kentta: tuote.get(kentta) for kentta in HINTAKENTAT} for tuote in tuotteet]
    viinat = [tuote for tuote in hinnasto if 'vodkat ja viinat' in
              [osa.strip() for osa in (tuote['tyyppi'] or '').split(',')]]
    ehdokkaat = []
    for tuote in viinat:
        linkki = tuote['linkki']
        nimi = tuote['nimi'].strip()
        litrat = tuote['tilavuus_litraa']
        vahvuus = tuote['alkoholi_prosentti']
        if not (nimi and all(isinstance(arvo, (int, float)) and isfinite(arvo) and arvo > 0
                             for arvo in (litrat, vahvuus, tuote['hinta_eur']))
                and re.match(r'https://(?:www\.)?alko\.fi/', linkki, re.I)):
            continue
        hinta = round(tuote['hinta_eur'] + tuote['pantti_eur'], 2)
        annoshinta = hinta * 1.5 / (litrat * vahvuus)
        ehdokkaat.append((annoshinta, nimi, linkki, litrat, vahvuus, hinta))
    if len(ehdokkaat) < 10:
        raise ValueError('Alkon viinavertailun aineisto on puutteellinen.')

    rivit = []
    for annoshinta, nimi, linkki, litrat, vahvuus, hinta in sorted(ehdokkaat)[:10]:
        koko = f'{litrat:g}'.replace('.', ',')
        pitoisuus = f'{vahvuus:g}'.replace('.', ',')
        rivit.append(
            f'                <tr><td><a href="{escape(linkki)}">{escape(nimi)}</a></td>'
            f'<td>{koko} l</td><td>{pitoisuus} %</td>'
            + f'<td>{hinta:.2f} €</td><td>{annoshinta:.2f} €</td></tr>'.replace('.', ',')
        )

    viina_sivu, viina_html = otos_html('halvin-viina', '10 edullisinta annoshintaa', rivit, keratty)
    punaviinit = [tuote for tuote in hinnasto if (tuote['tyyppi'] or '').split(',', 1)[0].strip() == 'punaviinit']
    viini_sivu, viini_html = otos_html('alkon-viinit', '10 halvinta punaviinipakkausta',
                                      pakkausrivit(punaviinit, litrahinta=True), keratty)
    hinnasto_sivu, hinnasto_html = otos_html('alkon-hinnasto', '10 halvinta pakkausta',
                                            pakkausrivit(hinnasto), keratty)
    lisaviiniotokset = [
        otos_html('halvin-punaviini', '10 edullisinta punaviiniannosta',
                  pakkausrivit(punaviinit, annoshinta=True), keratty)
    ]
    for kansio, viinityyppi, raja in BUDJETTIVIINIT:
        ehdokkaat = [t for t in hinnasto if viiniluokka(t) == viinityyppi]
        rivit = pakkausrivit(ehdokkaat, litrahinta=True, alle=raja)
        kuvaus = f'{len(rivit)} edullisinta pakkausta alle {raja} €' if rivit else f'Ei pakkauksia alle {raja} €'
        lisaviiniotokset.append(otos_html(kansio, kuvaus, rivit, keratty))
    marketit = [
        json.loads((ROOT / f'{lahde}_tuotteet.json').read_text(encoding='utf-8'))
        for lahde in ('s_ryhma', 'k_ryhma')
    ]
    valikoima = json.loads((ROOT / 'valikoima_tiedot.json').read_text(encoding='utf-8'))
    paivitetty = valikoima['aineisto_paivitetty']
    markettipaiva = datetime.fromisoformat(paivitetty)
    if markettipaiva.tzinfo:
        markettipaiva = markettipaiva.astimezone(ZoneInfo('Europe/Helsinki'))
    ryhmat = markettihinnat(tuotteet, *marketit, valikoima)
    markkinasivut = {}
    otokset = []
    for kansio, juoma in (
        ('oluen-hinnat', 'olutpakkausta'),
        ('halvimmat-lonkerot', 'lonkeropakkausta'),
        ('halvimmat-seltzerit', 'seltzerpakkausta'),
        ('halvimmat-siiderit', 'siideripakkausta'),
        ('s-ryhman-halvin-alkoholi', 'alkoholiannoshintaa'),
        ('prisman-halvin-alkoholi', 'alkoholiannoshintaa'),
        ('k-ryhman-halvin-alkoholi', 'alkoholiannoshintaa'),
    ):
        aineisto = ryhmat.get(kansio, [])
        rivit = markettiotos(aineisto, annoshinta=kansio.endswith('-halvin-alkoholi'))
        if kansio == 'oluen-hinnat' and len(rivit) < 10:
            raise ValueError('Oluiden vertailuaineisto on puutteellinen.')
        kuvaus = f'{len(rivit)} halvinta {juoma} (yli 0,5 %)' if rivit else 'Ei hintatietoja (yli 0,5 %)'
        otokset.append(otos_html(kansio, kuvaus, rivit, markettipaiva, 'julkaistuista'))
        markkinasivut[kansio] = {'keratty': paivitetty, 'tuotteet': aineisto}
    muuttuneet = set()
    domain = 'https://juomaan.fi/'
    edellinen_valikoima = json.loads(subprocess.check_output(
        ['git', 'show', 'HEAD:valikoima_tiedot.json'], cwd=ROOT
    ))
    etusivun_aluekentat = (
        'kaupungit', 'alko_myymalat', 's_myymalat', 'k_myymalat',
        'alko_puuttuvat_myymalat', 's_puuttuvat_myymalat', 'k_puuttuvat_myymalat',
    )
    if any(valikoima.get(kentta) != edellinen_valikoima.get(kentta) for kentta in etusivun_aluekentat):
        muuttuneet.add(domain)
    hintasivut = {
        'alkon-hinnasto': {'keratty': raportti['keratty'], 'tuotteet': hinnasto},
        'halvin-viina': {'keratty': raportti['keratty'], 'tuotteet': viinat},
        **markkinasivut,
    }
    for kansio, payload in hintasivut.items():
        polku = ROOT / kansio / 'hinnat.json'
        vanhat = lue_json(polku, {}).get('tuotteet', [])
        if vanhat != payload['tuotteet']:
            muuttuneet.add(domain + kansio + '/')
            if kansio == 'alkon-hinnasto':
                if viinit(vanhat) != viinit(hinnasto):
                    muuttuneet.add(domain + 'alkon-viinit/')
                if [t for t in vanhat if viiniluokka(t) == 'punaviinit'] != punaviinit:
                    muuttuneet.add(domain + 'halvin-punaviini/')
                for sivu, viinityyppi, raja in BUDJETTIVIINIT:
                    if budjettiviinit(vanhat, viinityyppi, raja) != budjettiviinit(hinnasto, viinityyppi, raja):
                        muuttuneet.add(domain + sivu + '/')
        kirjoita(polku, json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')

    for sivu, html in [*otokset, *lisaviiniotokset]:
        kirjoita(sivu, html)
    kirjoita(viina_sivu, viina_html)
    kirjoita(viini_sivu, viini_html)
    kirjoita(hinnasto_sivu, hinnasto_html)
    etusivun_aineistot = {
        'alko': pakkaa_alko(tuotteet),
        's_ryhma': pakkaa_marketit(marketit[0]),
        'k_ryhma': pakkaa_marketit(marketit[1]),
    }
    for lahde, aineisto in etusivun_aineistot.items():
        polku = ROOT / f'{lahde}_vertailu.json'
        teksti = json.dumps(aineisto, ensure_ascii=False, separators=(',', ':')) + '\n'
        if not polku.exists() or polku.read_text(encoding='utf-8') != teksti:
            muuttuneet.add(domain)
        kirjoita(polku, teksti)
    paivita_sivustokartta(muuttuneet, markettipaiva)


if __name__ == '__main__':
    paivita()
