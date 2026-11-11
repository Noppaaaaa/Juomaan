"""Run with /Users/aaro/juomaan-paivitys-venv/bin/python test_hinnastoreitit.py."""
import functools
import http.server
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent
server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root)))
threading.Thread(target=server.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{server.server_port}'
routes = {
    'alkon-hinnasto': ('', ''), 'alkon-viinit': ('viini', ''),
    'halvin-viina': ('', ''), 'oluen-hinnat': ('olut', ''),
    'halvimmat-lonkerot': ('lonkero', ''), 'halvimmat-seltzerit': ('seltzer', ''),
    'halvimmat-siiderit': ('siideri', ''), 's-ryhman-halvin-alkoholi': ('', ''),
    'prisman-halvin-alkoholi': ('', ''), 'k-ryhman-halvin-alkoholi': ('', ''),
    'punaviinit-alle-10-euroa': ('punaviini', '9,99'),
    'valkoviinit-alle-10-euroa': ('valkoviini', '9,99'),
    'kuohuviinit-alle-12-euroa': ('kuohuviini', '11,99'),
    'kuohuviinit-alle-15-euroa': ('kuohuviini', '14,99'),
    'kuohuviinit-alle-20-euroa': ('kuohuviini', '19,99'),
    'halvin-punaviini': ('punaviini', ''),
}
try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        for route, (query, price) in routes.items():
            page.goto(f'{base}/{route}/', wait_until='networkidle', timeout=60000)
            assert page.url.startswith(base + '/?'), (route, page.url)
            assert page.locator('#hakuKentta').input_value() == query, route
            assert page.locator('#hintarajaArvo').input_value() == price, route
            assert page.locator('tbody tr').count() > 0, route
            if route == 'punaviinit-alle-10-euroa':
                rows = page.locator('tbody tr').all()
                for row in rows:
                    cells = row.locator('td')
                    if cells.count() >= 3:
                        assert float(cells.nth(2).inner_text().replace(',', '.')) < 10
            if route == 'prisman-halvin-alkoholi':
                assert page.locator('#prismaRajaus').is_visible()
                page.locator('#prismaRajaus').click()
                assert not page.locator('#prismaRajaus').is_visible()
        assert not errors, errors
        browser.close()
finally:
    server.shutdown()
print('16 hinnastoreittiä OK')
