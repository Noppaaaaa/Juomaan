import unittest
from paivita_alko_tuotetiedot import etsi_tuotetiedot, on_tuote_404


class AlkoTuotetiedot(unittest.TestCase):
    def test_rsc_http_200_not_found(self):
        self.assertTrue(on_tuote_404('1:{"notFound":[["404: This page could not be found."]]}'))
        self.assertFalse(on_tuote_404('1:{"productId":904254,"valueInCents":599}'))

    def test_numeraalinen_tuotetunnus_taytyy_merkkijonotunnukseen(self):
        text='1:{"productId":904254,"valueInCents":1299,"deposit":"$undefined"}'
        self.assertEqual(etsi_tuotetiedot(text,'904254'),{'deposit':0,'total':12.99})


if __name__=='__main__':
    unittest.main()
