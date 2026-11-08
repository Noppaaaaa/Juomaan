from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from unittest import TestCase
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
DOMAIN = 'https://juomaan.fi'


class Sivu(HTMLParser):
    def __init__(self, polku):
        super().__init__()
        self.linkit = []
        self.ankkurit = set()
        self.canonical = []
        self.noindex = False
        self.feed(polku.read_text(encoding='utf-8'))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ankkurit.add(attrs['id'])
        if tag == 'a' and 'href' in attrs:
            self.linkit.append(attrs['href'])
        if tag == 'link' and attrs.get('rel') == 'canonical':
            self.canonical.append(attrs.get('href'))
        if tag == 'meta' and attrs.get('name') in ('robots', 'googlebot'):
            self.noindex |= 'noindex' in (attrs.get('content') or '').lower()


class SeoTest(TestCase):
    def test_kartan_sivut_ja_linkit(self):
        kartta = ET.parse(ROOT / 'sitemap.xml')
        rivit = kartta.findall('{*}url')
        osoitteet = {rivi.findtext('{*}loc') for rivi in rivit}
        self.assertEqual(len(rivit), len(osoitteet), 'Kartassa on sama URL useasti.')
        self.assertIn(DOMAIN + '/', osoitteet)
        self.assertIn(f'Sitemap: {DOMAIN}/sitemap.xml', (ROOT / 'robots.txt').read_text().splitlines())

        sivut = {}
        for rivi in rivit:
            osoite = rivi.findtext('{*}loc')
            uri = urlsplit(osoite)
            self.assertEqual(osoite, DOMAIN + uri.path)
            self.assertTrue(uri.path.endswith('/'), osoite)
            self.assertLessEqual(date.fromisoformat(rivi.findtext('{*}lastmod')), date.today())
            sivu = Sivu(ROOT / uri.path.lstrip('/') / 'index.html')
            self.assertEqual(sivu.canonical, [osoite])
            self.assertFalse(sivu.noindex, osoite)
            sivut[osoite] = sivu

        tarkistettavat = [DOMAIN + '/']
        loydetyt = set()
        while tarkistettavat:
            osoite = tarkistettavat.pop()
            if osoite in loydetyt:
                continue
            loydetyt.add(osoite)
            for href in sivut[osoite].linkit:
                kohde = urlsplit(urljoin(osoite, href))
                if kohde.netloc != urlsplit(DOMAIN).netloc:
                    continue
                polku = ROOT / kohde.path.lstrip('/')
                if kohde.path.endswith('/'):
                    polku /= 'index.html'
                self.assertTrue(polku.is_file(), f'{osoite}: {href}')
                kohdeosoite = DOMAIN + kohde.path
                if kohde.fragment:
                    sivu = sivut.get(kohdeosoite) or Sivu(polku)
                    self.assertIn(kohde.fragment, sivu.ankkurit, f'{osoite}: {href}')
                if kohdeosoite in sivut:
                    tarkistettavat.append(kohdeosoite)
        self.assertEqual(loydetyt, osoitteet, 'Kaikkia kartan sivuja ei löydy etusivulta.')
