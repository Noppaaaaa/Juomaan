"""Publish derived price data for the comparison pages."""

import json
import re
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


def pakkausrivit(tuotteet, litrahinta=False):
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
        ehdokkaat.append((hinta, nimi, linkki, litrat))
    if len(ehdokkaat) < 10:
        raise ValueError('Alkon pakkaushintojen aineisto on puutteellinen.')

    rivit = []
    for hinta, nimi, linkki, litrat in sorted(ehdokkaat)[:10]:
        koko = f'{litrat:g}'.replace('.', ',')
        hinnat = f'<td>{hinta:.2f} €</td>'
        if litrahinta:
            hinnat += f'<td>{hinta / litrat:.2f} €</td>'
        hinnat = hinnat.replace('.', ',')
        rivit.append(f'                <tr><td><a href="{escape(linkki)}">{escape(nimi)}</a></td>'
                     f'<td>{koko} l</td>{hinnat}</tr>')
    return rivit


def oluthinnat(alko, sryhma, kryhma, valikoima):
    myymalat = {
        'sryhma': {str(t['id']): t for t in valikoima['s_myymalat']},
        'kryhma': {str(t['id']): t for t in valikoima['k_myymalat']},
    }
    oluet = []
    for lahde, tuotteet in [('alko', alko), ('sryhma', sryhma), ('kryhma', kryhma)]:
        for tuote in tuotteet:
            tyyppi = (tuote['tyyppi'] or '').split(',', 1)[0].strip().casefold()
            if tyyppi not in ('oluet', 'alkoholittomat oluet'):
                continue
            tiedot = {kentta: tuote.get(kentta) for kentta in HINTAKENTAT}
            if lahde != 'alko':
                if not tuote['myymalat']:
                    continue
                tunniste, tiedot['hinta_eur'], tiedot['pantti_eur'] = min(
                    tuote['myymalat'], key=lambda rivi: rivi[1] + rivi[2])
                myymala = myymalat[lahde][str(tunniste)]
                nimi, arvo = ('storeId', myymala['id']) if lahde == 'sryhma' else ('kauppa', myymala['slug'])
                osoite = urlsplit(tiedot['linkki'])
                parametrit = dict(parse_qsl(osoite.query, keep_blank_values=True))
                parametrit[nimi] = arvo
                tiedot['linkki'] = osoite._replace(query=urlencode(parametrit)).geturl()
                tiedot['myymala'] = myymala['name']
            oluet.append({**tiedot, 'lahde': lahde})
    return oluet


def olutotos(oluet):
    kaupat = {'alko': ('Alko', 'alko.fi'), 'sryhma': ('S-ryhmä', 's-kaupat.fi'), 'kryhma': ('K-ryhmä', 'k-ruoka.fi')}
    ehdokkaat = []
    for tuote in oluet:
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
    if len(ehdokkaat) < 10:
        raise ValueError('Oluiden vertailuaineisto on puutteellinen.')
    rivit = []
    for hinta, nimi, linkki, litrat, kauppa, vahvuus in sorted(ehdokkaat)[:10]:
        koko = f'{litrat:g}'.replace('.', ',')
        pitoisuus = f'{vahvuus:g}'.replace('.', ',')
        hinnat = f'<td>{hinta:.2f} €</td><td>{hinta / litrat:.2f} €</td>'.replace('.', ',')
        rivit.append(f'                <tr><td><a href="{escape(linkki)}">{escape(nimi)}</a>'
                     f'<br><small>{escape(kauppa)} · {pitoisuus} %</small></td><td>{koko} l</td>{hinnat}</tr>')
    return rivit


def lue_json(polku, oletus=None):
    return json.loads(polku.read_text(encoding='utf-8')) if polku.exists() else oletus


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
    marketit = [
        json.loads((ROOT / f'{lahde}_tuotteet.json').read_text(encoding='utf-8'))
        for lahde in ('s_ryhma', 'k_ryhma')
    ]
    valikoima = json.loads((ROOT / 'valikoima_tiedot.json').read_text(encoding='utf-8'))
    olutdata = {'keratty': valikoima['aineisto_paivitetty'], 'tuotteet': oluthinnat(tuotteet, *marketit, valikoima)}
    olut_paivays = datetime.fromisoformat(olutdata['keratty'])
    if olut_paivays.tzinfo:
        olut_paivays = olut_paivays.astimezone(ZoneInfo('Europe/Helsinki'))
    olut_sivu, olut_html = otos_html('oluen-hinnat', '10 halvinta olutpakkausta (yli 0,5 %)',
                                    olutotos(olutdata['tuotteet']), olut_paivays, 'julkaistuista')
    muuttuneet = set()
    domain = 'https://juomaan.fi/'
    hintasivut = {
        'alkon-hinnasto': {'keratty': raportti['keratty'], 'tuotteet': hinnasto},
        'halvin-viina': {'keratty': raportti['keratty'], 'tuotteet': viinat},
        'oluen-hinnat': olutdata,
    }
    for kansio, payload in hintasivut.items():
        polku = ROOT / kansio / 'hinnat.json'
        vanhat = lue_json(polku, {}).get('tuotteet', [])
        if vanhat != payload['tuotteet']:
            muuttuneet.add(domain + kansio + '/')
            if kansio == 'alkon-hinnasto' and viinit(vanhat) != viinit(hinnasto):
                muuttuneet.add(domain + 'alkon-viinit/')
        kirjoita(polku, json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')

    kirjoita(olut_sivu, olut_html)
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
    paivita_sivustokartta(muuttuneet, olut_paivays)


if __name__ == '__main__':
    paivita()
