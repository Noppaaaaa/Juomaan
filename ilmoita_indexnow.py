"""Notify Bing after the updated production sitemap is available."""

import json
import subprocess
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
HOST = 'juomaan.fi'
BASE = f'https://{HOST}'
KEY_FILE = '2fd37037ba404785b169b7b8465872cb.txt'


def kartan_sivut(xml):
    return {sivu.findtext('{*}loc'): sivu.findtext('{*}lastmod')
            for sivu in ET.fromstring(xml).findall('{*}url')}


def ilmoita(edellinen):
    ennen = subprocess.check_output(['git', 'show', f'{edellinen}:sitemap.xml'], cwd=ROOT)
    nyt = (ROOT / 'sitemap.xml').read_bytes()
    vanhat, uudet = kartan_sivut(ennen), kartan_sivut(nyt)
    osoitteet = sorted(u for u in vanhat.keys() | uudet.keys()
                      if u.startswith(BASE + '/') and (u not in vanhat or u not in uudet or vanhat[u] != uudet[u]))
    if not osoitteet:
        print('IndexNow: ei muuttuneita osoitteita.')
        return

    for yritys in range(10):
        tulos = subprocess.run(['curl', '-fsS', '--compressed', '--max-time', '6', f'{BASE}/sitemap.xml'],
                               capture_output=True)
        if tulos.returncode == 0:
            try:
                if kartan_sivut(tulos.stdout) == uudet:
                    break
            except ET.ParseError:
                pass
        if yritys < 9:
            time.sleep(8)
    else:
        raise RuntimeError('Uusi sivustokartta ei ehtinyt tuotantoon.')

    key = (ROOT / KEY_FILE).read_text().strip()
    payload = {'host': HOST, 'key': key, 'keyLocation': f'{BASE}/{KEY_FILE}', 'urlList': osoitteet}
    status = subprocess.check_output([
        'curl', '-sS', '--max-time', '15', '-o', '/dev/null', '-w', '%{http_code}',
        '-H', 'Content-Type: application/json; charset=utf-8', '--data-binary', '@-',
        'https://www.bing.com/indexnow',
    ], input=json.dumps(payload), text=True)
    if status not in ('200', '202'):
        raise RuntimeError(f'IndexNow HTTP {status}')
    print(f'IndexNow: {len(osoitteet)} osoitetta, HTTP {status}.')


if __name__ == '__main__':
    ilmoita(sys.argv[1])
