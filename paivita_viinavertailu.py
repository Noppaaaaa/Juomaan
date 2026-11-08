"""Generate the dated first rows of the spirits comparison from Alko's catalogue."""

import json
import re
from datetime import datetime
from html import escape
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent


def paivita():
    tuotteet = json.loads((ROOT / 'alko_tuotteet.json').read_text(encoding='utf-8'))
    raportti = json.loads((ROOT / 'alko_keruu.json').read_text(encoding='utf-8'))
    keratty = datetime.fromisoformat(raportti['keratty']).astimezone(ZoneInfo('Europe/Helsinki'))
    ehdokkaat = []
    for tuote in tuotteet:
        if 'vodkat ja viinat' not in (osa.strip() for osa in tuote['tyyppi'].split(',')):
            continue
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
    tmp = sivu.with_suffix('.tmp')
    tmp.write_text(html, encoding='utf-8')
    tmp.replace(sivu)


if __name__ == '__main__':
    paivita()
