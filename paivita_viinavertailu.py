"""Publish derived price data for the comparison pages."""

import json
import re
from base64 import b64encode
from datetime import datetime
from html import escape
from itertools import groupby
from math import isfinite
from pathlib import Path
from urllib.parse import urlsplit
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


def punaviinirivit(hinnasto):
    ehdokkaat = []
    for tuote in hinnasto:
        if (tuote['tyyppi'] or '').split(',', 1)[0].strip() != 'punaviinit':
            continue
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
        raise ValueError('Alkon punaviinien aineisto on puutteellinen.')

    rivit = []
    for hinta, nimi, linkki, litrat in sorted(ehdokkaat)[:10]:
        koko = f'{litrat:g}'.replace('.', ',')
        hinnat = f'<td>{hinta:.2f} €</td><td>{hinta / litrat:.2f} €</td>'.replace('.', ',')
        rivit.append(f'                <tr><td><a href="{escape(linkki)}">{escape(nimi)}</a></td>'
                     f'<td>{koko} l</td>{hinnat}</tr>')
    return rivit


def oluthinnat(alko, sryhma, kryhma):
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
                _, tiedot['hinta_eur'], tiedot['pantti_eur'] = min(tuote['myymalat'], key=lambda rivi: rivi[1] + rivi[2])
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
        ehdokkaat.append((hinta, nimi, linkki, litrat, kauppa, vahvuus))
    if len(ehdokkaat) < 10:
        raise ValueError('Oluiden vertailuaineisto on puutteellinen.')
    rivit = []
    for hinta, nimi, linkki, litrat, kauppa, vahvuus in sorted(ehdokkaat)[:10]:
        koko = f'{litrat:g}'.replace('.', ',')
        pitoisuus = f'{vahvuus:g}'.replace('.', ',')
        hinnat = f'<td>{hinta:.2f} €</td><td>{hinta / litrat:.2f} €</td>'.replace('.', ',')
        rivit.append(f'                <tr><td><a href="{escape(linkki)}">{escape(nimi)}</a>'
                     f'<br><small>{kauppa} · {pitoisuus} %</small></td><td>{koko} l</td>{hinnat}</tr>')
    return rivit


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
    viini_sivu, viini_html = otos_html('alkon-viinit', '10 halvinta punaviinipakkausta', punaviinirivit(hinnasto), keratty)
    for kansio, aineisto in [('alkon-hinnasto', hinnasto), ('halvin-viina', viinat)]:
        payload = {'keratty': raportti['keratty'], 'tuotteet': aineisto}
        kirjoita(ROOT / kansio / 'hinnat.json', json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    marketit = [
        json.loads((ROOT / f'{lahde}_tuotteet.json').read_text(encoding='utf-8'))
        for lahde in ('s_ryhma', 'k_ryhma')
    ]
    valikoima = json.loads((ROOT / 'valikoima_tiedot.json').read_text(encoding='utf-8'))
    olutdata = {'keratty': valikoima['aineisto_paivitetty'], 'tuotteet': oluthinnat(tuotteet, *marketit)}
    olut_paivays = datetime.fromisoformat(olutdata['keratty'])
    if olut_paivays.tzinfo:
        olut_paivays = olut_paivays.astimezone(ZoneInfo('Europe/Helsinki'))
    olut_sivu, olut_html = otos_html('oluen-hinnat', '10 halvinta olutpakkausta (yli 0,5 %)',
                                    olutotos(olutdata['tuotteet']), olut_paivays, 'julkaistuista')
    kirjoita(ROOT / 'oluen-hinnat' / 'hinnat.json', json.dumps(olutdata, ensure_ascii=False, separators=(',', ':')) + '\n')
    kirjoita(olut_sivu, olut_html)
    kirjoita(viina_sivu, viina_html)
    kirjoita(viini_sivu, viini_html)
    kirjoita(ROOT / 'alko_vertailu.json', json.dumps(pakkaa_alko(tuotteet), ensure_ascii=False, separators=(',', ':')) + '\n')
    for lahde, marketin_tuotteet in zip(('s_ryhma', 'k_ryhma'), marketit):
        pakattu = pakkaa_marketit(marketin_tuotteet)
        kirjoita(ROOT / f'{lahde}_vertailu.json', json.dumps(pakattu, ensure_ascii=False, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    paivita()
