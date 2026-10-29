import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import esto


class EstonKasittely(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.root = patch.object(esto, 'ROOT', root)
        self.marker = patch.object(esto, 'MARKER', root / 'odotus.json')
        self.root.start(); self.marker.start()
        self.addCleanup(self.root.stop); self.addCleanup(self.marker.stop)

    def test_estot_ja_odotusaika(self):
        with self.assertRaisesRegex(esto.Rajoitus, 'HTTP 429'):
            esto.rajoita(429, '7200')
        first = datetime.fromisoformat(json.loads(esto.MARKER.read_text())['odota_saakka'])
        self.assertGreaterEqual(first, datetime.now(timezone.utc) + timedelta(minutes=119))
        with self.assertRaisesRegex(esto.Rajoitus, 'HTTP 403'):
            esto.rajoita(403, 'bad-value')
        self.assertEqual(first, datetime.fromisoformat(json.loads(esto.MARKER.read_text())['odota_saakka']))

    def test_suojaussivu_200_ja_normaali_tuotesivu(self):
        esto.tarkista_sivu(200, '<title>Oluet</title>', {})
        self.assertFalse(esto.MARKER.exists())
        with self.assertRaisesRegex(esto.Rajoitus, 'HTTP 200: kaupan suojaustarkistus'):
            esto.tarkista_sivu(200, '<title>Just a moment...</title>', {})

    def test_header_suojaustarkistus(self):
        with self.assertRaises(esto.Rajoitus):
            esto.tarkista_sivu(200, '', {'Cf-Mitigated': 'challenge'})


if __name__ == '__main__':
    unittest.main()
