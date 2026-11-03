import unittest
from paivita_alko_tuotetiedot import etsi_tuotetiedot


class AlkoTuotetiedot(unittest.TestCase):
    def test_numeraalinen_tuotetunnus_taytyy_merkkijonotunnukseen(self):
        text='1:{"productId":904254,"valueInCents":1299,"deposit":"$undefined"}'
        self.assertEqual(etsi_tuotetiedot(text,'904254'),{'deposit':0,'total':12.99})


if __name__=='__main__':
    unittest.main()
