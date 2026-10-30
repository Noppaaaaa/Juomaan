"""Keep legacy votes attached to their products during catalogue refreshes."""
from __future__ import annotations

import json
import re
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
VOTES_URL = 'https://juomaan.fi/api/votes'
CATALOGUES = ('alko_tuotteet.json', 's_ryhma_tuotteet.json', 'k_ryhma_tuotteet.json')


def js_number(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return str(value).lower()
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if number == number.to_integral_value():
        return str(number.quantize(Decimal(1)))
    return format(number.normalize(), 'f')


def legacy_key(product):
    return '||'.join((
        str(product.get('nimi') or ''),
        js_number(product.get('alkoholi_prosentti')),
        js_number(product.get('hinta_eur')),
    ))


def catalogue_revisions(filename):
    result = subprocess.run(
        ['git', 'log', '--format=%H', '--', filename], cwd=ROOT,
        text=True, capture_output=True, check=True,
    )
    return result.stdout.splitlines()


def read_revision(commit, filename):
    result = subprocess.run(
        ['git', 'show', f'{commit}:{filename}'], cwd=ROOT,
        text=True, capture_output=True, check=False,
    )
    if result.returncode:
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def fetch_vote_keys():
    raw = subprocess.run(
        ['curl', '--fail', '--silent', '--show-error', '--max-time', '30',
         '-H', 'Accept: application/json', '-H', 'Cache-Control: no-cache', VOTES_URL],
        check=True, capture_output=True, text=True,
    ).stdout
    data = json.loads(raw)
    votes = data.get('aanet')
    if not isinstance(votes, dict):
        raise RuntimeError('Äänten palvelu palautti odottamattoman vastauksen.')
    return [key for key in votes if not key.startswith('{"v":2,')]


def descriptor(product, source):
    product_id = product.get('id') or product.get('i')
    if not product_id:
        path = urlsplit(product.get('linkki') or '').path
        match = re.search(r'/(?:tuotteet|cdn)/(\d+)(?:/|$)', path)
        product_id = match.group(1) if match else path.rstrip('/').rsplit('/', 1)[-1]
    image_url = product.get('kuva_url') or product.get('u') or ''
    if not product_id:
        match = re.search(r'/cdn/(\d+)(?:/|$)', urlsplit(image_url).path)
        product_id = match.group(1) if match else ''
    return {
        's': source,
        'i': str(product_id or ''),
        'n': product.get('nimi') or '',
        'l': product.get('tilavuus_litraa'),
        'a': product.get('alkoholi_prosentti'),
        'u': image_url,
        'h': product.get('h'),
    }


def identity(record):
    return tuple(str(record.get(key) or '') for key in ('s', 'i', 'n', 'l', 'a', 'u', 'h'))


def main():
    active_keys = fetch_vote_keys()
    old_history_path = ROOT / 'aanet_historia.json'
    existing = json.loads(old_history_path.read_text(encoding='utf-8')) if old_history_path.exists() else {}
    history = {}
    active = set(active_keys)
    previous = {key: [descriptor(record, record.get('s', '')) for record in existing.get(key, [])]
                for key in active_keys}
    for filename, source in zip(CATALOGUES, ('alko', 'sryhma', 'kryhma')):
        needed = {
            key for key in active
            if not any(record.get('s') == source and record.get('i')
                       for record in previous[key])
        }
        for commit in catalogue_revisions(filename):
            if not needed:
                break
            for product in read_revision(commit, filename):
                key = legacy_key(product)
                if key in needed:
                    previous[key].append(descriptor(product, source))
                    needed.remove(key)
    for key in active_keys:
        unique = {identity(record): record for record in previous[key]}
        if unique:
            history[key] = list(unique.values())

    temp = old_history_path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(history, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    temp.replace(old_history_path)
    matched = sum(bool(records) for records in history.values())
    print(f'Äänihistoria päivitetty: {matched}/{len(active_keys)} vanhaa avainta tunnistettu.')


if __name__ == '__main__':
    main()
