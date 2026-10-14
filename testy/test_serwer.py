import http.client
import json
import socket
import threading
import unittest
from http.server import ThreadingHTTPServer

from finanse import konfig, odbudowa, serwer
from testy.pomoc import Srodowisko, operacja, zapisz_ing


class TestSerwer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srod = Srodowisko().__enter__()
        zapisz_ing(cls.srod.dane, 'ing_historia_2026-10-01_2026-10-13.csv',
                   [operacja('2026-10-13', '100,00', '100,00', 'KLIENT', 'FV2026/10/1', ref='R1')])
        odbudowa.odbuduj()
        cls.stary_port = konfig.PORT
        cls.http = ThreadingHTTPServer((konfig.HOST, 0), serwer.Obsluga)
        konfig.PORT = cls.http.server_address[1]
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        konfig.PORT = cls.stary_port
        cls.srod.__exit__()

    def zadanie(self, metoda, sciezka, host=None, naglowki=None):
        c = http.client.HTTPConnection('127.0.0.1', konfig.PORT, timeout=5)
        h = {'Host': host or f'127.0.0.1:{konfig.PORT}', **(naglowki or {})}
        c.request(metoda, sciezka, headers=h)
        r = c.getresponse()
        return r, r.read()

    def test_tylko_lokalny_adres(self):
        self.assertEqual(konfig.HOST, '127.0.0.1')
        self.assertEqual(self.http.server_address[0], '127.0.0.1')

    def test_stan_i_naglowki_bezpieczenstwa(self):
        r, tresc = self.zadanie('GET', '/api/stan')
        self.assertEqual(r.status, 200)
        dane = json.loads(tresc)
        self.assertEqual(dane['gotowka'], 10000)
        self.assertTrue(dane['aktualna'])
        self.assertIn("default-src 'self'", r.getheader('Content-Security-Policy'))
        self.assertEqual(r.getheader('Cache-Control'), 'no-store')

    def test_obcy_host_odrzucony(self):
        r, _ = self.zadanie('GET', '/api/stan', host='zly.example.com')
        self.assertEqual(r.status, 403)

    def test_zapis_bez_naglowka_odrzucony(self):
        r, _ = self.zadanie('POST', '/api/odbuduj')
        self.assertEqual(r.status, 403)
        r, tresc = self.zadanie('POST', '/api/odbuduj', naglowki={'X-Finanse': '1'})
        self.assertEqual(r.status, 200)

    def test_wyjscie_poza_katalog_web_zablokowane(self):
        r, _ = self.zadanie('GET', '/../finanse/konfig.py')
        self.assertEqual(r.status, 404)

    def test_strona_glowna(self):
        r, tresc = self.zadanie('GET', '/')
        self.assertEqual(r.status, 200)
        self.assertIn(b'Finanse DigitalH', tresc)


if __name__ == '__main__':
    unittest.main()
