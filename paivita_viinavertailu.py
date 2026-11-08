"""Publish derived price data for the comparison pages."""

import json
import re
from base64 import b64encode
from datetime import datetime
from html import escape
from itertools import groupby
from math import isfinite
from pathlib import Path
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


def pakkaa_marketit(lahde):
    tuotteet = json.loads((ROOT / f'{lahde}_tuotteet.json').read_text(encoding='utf-8'))
    myymalat = sorted({rivi[0] for tuote in tuotteet for rivi in tuote['myymalat']})
    tunnisteet = {tunniste: i for i, tunniste in enumerate(myymalat)}

    # Keep the original order, including ties between offers.
    for tuote in tuotteet:
        tuote['myymalat'] = [
            [hinta, pantti, *[tunnisteet[tunniste] for tunniste, _, _ in ryhma]]
            for (hinta, pantti), ryhma in groupby(tuote['myymalat'], key=lambda rivi: rivi[1:])
        ]
    return {'myymalat': myymalat, 'tuotteet': tuotteet}


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

    sivu = ROOT / 'halvin-viina' / 'index.html'
    html = sivu.read_text(encoding='utf-8')
    html, caption_count = re.subn(
        r'(<caption id="otoksen-paivays">)[^<]*(</caption>)',
        rf'\g<1>10 edullisinta annoshintaa {keratty.day}.{keratty.month}.{keratty.year} kerätyistä hinnoista.\g<2>',
        html,
    )
    html, row_count = re.subn(
        r'(<tbody id="rivit">).*?(</tbody>)',
        lambda m: m[1] + '\n' + '\n'.join(rivit) + '\n            ' + m[2],
        html,
        flags=re.S,
    )
    if (caption_count, row_count) != (1, 1):
        raise ValueError('Viinavertailun otokselle tarvitaan yksi otsikko ja yksi taulukko.')
    for kansio, aineisto in [('alkon-hinnasto', hinnasto), ('halvin-viina', viinat)]:
        payload = {'keratty': raportti['keratty'], 'tuotteet': aineisto}
        kirjoita(ROOT / kansio / 'hinnat.json', json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n')
    kirjoita(sivu, html)
    kirjoita(ROOT / 'alko_vertailu.json', json.dumps(pakkaa_alko(tuotteet), ensure_ascii=False, separators=(',', ':')) + '\n')
    for lahde in ('s_ryhma', 'k_ryhma'):
        pakattu = pakkaa_marketit(lahde)
        kirjoita(ROOT / f'{lahde}_vertailu.json', json.dumps(pakattu, ensure_ascii=False, separators=(',', ':')) + '\n')


if __name__ == '__main__':
    paivita()
