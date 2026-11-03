import unittest
from paivita_alko_tuotetiedot import etsi_tuotetiedot, on_tuote_404, tuotesivu_polku


class AlkoTuotetiedot(unittest.TestCase):
    def test_rsc_http_200_not_found(self):
        self.assertTrue(on_tuote_404('1:{"notFound":[["404: This page could not be found."]]}'))
        self.assertFalse(on_tuote_404('1:{"productId":904254,"valueInCents":599}'))

    def test_numeraalinen_tuotetunnus_taytyy_merkkijonotunnukseen(self):
        text='1:{"productId":904254,"valueInCents":1299,"deposit":"$undefined"}'
        self.assertEqual(etsi_tuotetiedot(text,'904254'),{'deposit':0,'total':12.99})

    def test_alkon_uusi_tuotesivu_vaatii_kuvasta_saatavan_slugin(self):
        path=tuotesivu_polku('904254','https://images.alko.fi/images/t_img_160x192/cdn/904254/acquesi-asti-spumante-rose-demi-sec.jpg')
        self.assertEqual(path,'/fi/tuotteet/904254/acquesi-asti-spumante-rose-demi-sec')

    def test_validi_tuotetieto_loytyy_vaikka_rsc_sisaltaa_yleisen_404_mallin(self):
        text='1:{"productId":904254,"valueInCents":1359,"deposit":0.1}\\n2:{"notFound":[["404: This page could not be found."]]}'
        self.assertIsNotNone(etsi_tuotetiedot(text,'904254'))


if __name__=='__main__':
    unittest.main()
