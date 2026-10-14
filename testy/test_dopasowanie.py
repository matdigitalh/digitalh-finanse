"""Etap 2 na zmyślonych danych: dopasowanie wpłat do faktur, należności, decyzje Mata."""
import json
import unittest

from finanse import baza, konfig, odbudowa, zapytania, zmiany
from finanse.dopasowanie import numery_w_tytule, rdzen_ksef
from testy.pomoc import Srodowisko, faktura, operacja, zapisz_fakturownie, zapisz_ing

KSEF_5 = '1112223344-20260905-AAAA11110000-01'
KSEF_6 = '1112223344-20260905-BBBB22220000-02'


def dane_testowe(dane):
    a, b, g, d = 'ALFA SP. Z O.O.', 'BETA SPÓŁKA AKCYJNA', 'GAMMA SPÓŁKA Z O.O.', 'DELTA SP. Z O.O.'
    zapisz_fakturownie(dane, 'fakturownia_sprzedaz_2026-10-13.csv', [
        faktura(1, 'FV2026/09/1', 'Opłacona', '2026-09-01', '2026-09-15', a, '111', [('Usługa', 1000)]),
        faktura(2, 'FV2026/09/2', 'Wystawiona', '2026-09-02', '2026-09-16', a, '111', [('Usługa', 500)]),
        faktura(3, 'FV2026/09/3', 'Wystawiona', '2026-09-03', '2026-09-17', a, '111', [('Usługa', 500)]),
        faktura(4, 'FV2026/09/4', 'Wystawiona', '2026-09-04', '2026-09-18', a, '111', [('Usługa', 2000)]),
        faktura(5, 'FV2026/09/5', 'Wystawiona', '2026-09-05', '2026-09-19', b, '222', [('Usługa', 1000)], ksef=KSEF_5),
        faktura(6, 'FV2026/09/6', 'Wystawiona', '2026-09-05', '2026-09-19', b, '222', [('Usługa', 500)], ksef=KSEF_6),
        faktura(7, 'FV2026/09/7', 'Wystawiona', '2026-09-07', '2026-09-21', b, '222', [('Usługa', 1000)]),
        faktura(8, 'FV2026/09/8', 'Wystawiona', '2026-09-08', '2026-09-22', b, '222', [('Usługa', 500)]),
        faktura(9, 'FV2026/08/1', 'Opłacona', '2026-08-01', '2026-08-15', g, '333', [('Usługa', 1000)]),
        faktura(10, 'FV2026/08/2', 'Wystawiona', '2026-08-02', '2026-08-16', g, '333', [('Usługa', 2000)]),
        faktura(11, 'FV2026/09/9', 'Wystawiona', '2026-09-09', '2026-09-23', g, '333', [('Rabat', -200)], oryginal='FV2026/08/2'),
        faktura(12, 'FV2026/09/10', 'Wystawiona', '2026-09-10', '2026-09-24', d, '444', [('Usługa', 1000)]),
        faktura(13, 'FV2026/09/11', 'Wystawiona', '2026-09-11', '2026-09-25', d, '444', [('Usługa', 500)]),
    ])
    zapisz_ing(dane, 'ing_historia_2026-01-01_2026-10-13.csv', [
        operacja('2026-10-13', '1230,00', '0', 'DELTA SP. Z O.O. UL. TESTOWA 1', 'FV2026/09/1', ref='D1'),
        operacja('2026-10-10', '2214,00', '0', 'GAMMA SPÓŁKA Z O.O.', 'FV2026/08/2', ref='G1'),
        operacja('2026-10-05', '1845,00', '0', 'BETA SPÓŁKA AKCYJNA', 'zapłata za wrzesień', ref='B2'),
        operacja('2026-10-03', '1845,00', '0', 'BETA SPÓŁKA AKCYJNA', f'{KSEF_5} -20260905-BBBB22220000-02', ref='B1'),
        operacja('2026-10-02', '1230,00', '0', 'ALFA SP. Z O.O.', '/VAT/230,00/IDC/111/INV/FV20 26_09_1/TXT/FV2026_09_1', ref='A3'),
        operacja('2026-10-02', '1230,00', '0', 'ALFA SP. Z O.O.', 'fv2026/09/2 i 3', ref='A4'),
        operacja('2026-10-01', '2460,00', '0', 'ALFA SP. Z O.O.', 'Zapłata za fakturę:F V2026/09/4', ref='A1'),
        operacja('2026-10-01', '615,00', '0', 'ALFA SP. Z O.O.', 'FV2026/09/2', ref='A2'),
        operacja('2026-09-20', '50,00', '0', 'SKLEP INTERNETOWY', 'przelew', ref='S1'),
        operacja('2026-09-19', '30,00', '0', 'CASHBACK-KONTA-KORPOR.(KOSZTY)', 'Nagroda 15% z kartą Mastercard', ref='C1'),
        operacja('2026-09-18', '615,00', '0', 'DELTA SP. Z O.O.', 'fv2024/09/11', ref='L1'),
        operacja('2026-01-10', '999,00', '0', 'ALFA SP. Z O.O.', '/FV/2025/12/5', ref='A0'),
    ])


def klucz(con, ref):
    return con.execute('SELECT klucz FROM operacje WHERE nr_ref = ?', (ref,)).fetchone()[0]


def wplata(con, ref):
    return con.execute('SELECT w.* FROM wplaty w JOIN operacje o ON o.id = w.operacja_id WHERE o.nr_ref = ?', (ref,)).fetchone()


def faktura_stan(con, numer):
    return con.execute('SELECT * FROM faktury_stan WHERE numer = ?', (numer,)).fetchone()


def dopasowane(con, ref):
    return {r['numer']: (r['kwota'], r['pewnosc']) for r in con.execute(
        'SELECT d.* FROM dopasowania d JOIN operacje o ON o.id = d.operacja_id WHERE o.nr_ref = ?', (ref,))}


class TestRozpoznawanieNumerow(unittest.TestCase):
    def test_zapisy_z_banku(self):
        self.assertEqual(numery_w_tytule('/INV/FV20 26_09_13/TXT/FV2026_09_13'), [(2026, 9, 13)])
        self.assertEqual(numery_w_tytule('Zapłata za fakturę:F V2026/09/1'), [(2026, 9, 1)])
        self.assertEqual(numery_w_tytule('fv2026/03/18 i 19'), [(2026, 3, 18), (2026, 3, 19)])
        self.assertEqual(numery_w_tytule('FV2026/03/27 ; FV2026/04/3 ; FV2026/0'), [(2026, 3, 27), (2026, 4, 3)])
        self.assertEqual(numery_w_tytule('/NIP/123/FV/2025/12/21'), [(2025, 12, 21)])
        self.assertEqual(numery_w_tytule('/VAT/1127,00/IDC/123/INV/202 5/12/16/T'), [(2025, 12, 16)])
        self.assertEqual(numery_w_tytule('FV2026/09/8 kwota 1820,40'), [(2026, 9, 8)])
        self.assertEqual(numery_w_tytule('Perfecta - zajęcie komornicze 2'), [])

    def test_rdzen_ksef_bez_nip_i_sumy(self):
        self.assertEqual(rdzen_ksef(KSEF_5), '20260905-AAAA11110000')


class TestDopasowanie(unittest.TestCase):
    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane_testowe(self.srod.dane)
        self.raport = odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def przelicz(self):
        self.con.close()
        self.raport = odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    def test_bez_bledow(self):
        self.assertEqual([b for b in self.raport['bledy'] if not b.startswith('Brak plików Biuro')], [])

    def test_numer_w_tytule_rozne_zapisy(self):
        self.assertEqual(dopasowane(self.con, 'A1'), {'FV2026/09/4': (246000, 'pewne')})
        self.assertEqual(dopasowane(self.con, 'A3'), {'FV2026/09/1': (123000, 'pewne')})
        for n in ('FV2026/09/1', 'FV2026/09/2', 'FV2026/09/3', 'FV2026/09/4'):
            self.assertEqual(faktura_stan(self.con, n)['stan'], 'opłacona', n)

    def test_podwojna_wplata_to_nadplata(self):
        # 09/2 zapłacona 01.10 osobno i 02.10 razem z 09/3: druga wpłata za 09/2 to nadpłata 615 zł
        self.assertEqual(wplata(self.con, 'A4')['nadplata'], 61500)
        typy = [x['rodzaj'] for x in zapytania.do_weryfikacji(self.con)]
        self.assertIn('nadplata', typy)

    def test_ksef_w_skrocie_za_dwie_faktury(self):
        self.assertEqual(dopasowane(self.con, 'B1'), {'FV2026/09/5': (123000, 'pewne'), 'FV2026/09/6': (61500, 'pewne')})

    def test_suma_faktur_nabywcy_do_potwierdzenia(self):
        self.assertEqual(dopasowane(self.con, 'B2'), {'FV2026/09/7': (123000, 'prawdopodobne'), 'FV2026/09/8': (61500, 'prawdopodobne')})

    def test_korekta_pomniejsza_naleznosc(self):
        s = faktura_stan(self.con, 'FV2026/08/2')
        self.assertEqual((s['naleznosc'], s['korekty'], s['stan']), (221400, -24600, 'opłacona'))
        self.assertIsNone(faktura_stan(self.con, 'FV2026/09/9'))   # korekta nie jest osobną należnością

    def test_wiekowanie_na_dzien_stanu(self):
        s = faktura_stan(self.con, 'FV2026/08/1')   # termin 15.08, dzień stanu 13.10
        self.assertEqual((s['stan'], s['dni_po_terminie'], s['przedzial'], s['pozostalo']), ('nieopłacona', 59, '31–60 dni', 123000))
        typy = {x['rodzaj']: x for x in zapytania.do_weryfikacji(self.con)}
        self.assertEqual(typy['fakturownia_oplacona']['numer'], 'FV2026/08/1')   # w Fakturowni odhaczona, w banku nie

    def test_cudzy_oplacony_numer_w_tytule(self):
        w = wplata(self.con, 'D1')
        self.assertIn('innego nabywcy', w['uwaga'])
        self.assertEqual(dopasowane(self.con, 'D1'), {'FV2026/09/10': (123000, 'prawdopodobne')})

    def test_sprzed_eksportu_i_nieznana(self):
        self.assertEqual(wplata(self.con, 'A0')['stan'], 'sprzed_eksportu')
        self.assertEqual(wplata(self.con, 'S1')['stan'], 'nieznana')

    def test_literowka_w_roku(self):
        # „fv2024/09/11”: takiej faktury nie ma, ten sam miesiąc i numer z 2026 na tę samą kwotę
        self.assertEqual(dopasowane(self.con, 'L1'), {'FV2026/09/11': (61500, 'prawdopodobne')})

    def test_wplywy_bez_faktury_regula_wbudowana(self):
        w = wplata(self.con, 'C1')
        self.assertEqual(w['stan'], 'bez_faktury')
        self.assertIn('reguła wbudowana', w['uwaga'])

    def test_podpowiedz_nigdy_pusta(self):
        self.assertTrue(wplata(self.con, 'S1')['podpowiedz'])

    def test_podsumowanie(self):
        p = zapytania.podsumowanie_naleznosci(self.con)
        self.assertEqual(p['dzien_stanu'], '2026-10-13')
        self.assertEqual(p['razem'], 123000)
        self.assertEqual(p['do_polaczenia'], 1)

    def test_decyzje_mata_i_cofniecie(self):
        k_d, k_s, k_b = klucz(self.con, 'D1'), klucz(self.con, 'S1'), klucz(self.con, 'B2')
        zmiany.zapisz('zatwierdz', {'operacja': k_b, 'faktura': 'FV2026/09/7'})
        zmiany.zapisz('zatwierdz', {'operacja': k_b, 'faktura': 'FV2026/09/8'})
        zmiany.zapisz('odrzuc', {'operacja': k_d, 'faktura': 'FV2026/09/10'})
        wpis = zmiany.zapisz('bez_faktury', {'operacja': k_s, 'powod': 'zwrot płatności kartą'})
        zmiany.zapisz('poza_bankiem', {'faktura': 'FV2026/08/1', 'powod': 'kompensata'})
        self.przelicz()
        self.assertEqual(wplata(self.con, 'B2')['pewnosc'], 'pewne')
        self.assertEqual(dopasowane(self.con, 'D1'), {})
        self.assertEqual(faktura_stan(self.con, 'FV2026/09/10')['stan'], 'nieopłacona')
        self.assertEqual(wplata(self.con, 'S1')['stan'], 'bez_faktury')
        self.assertEqual(faktura_stan(self.con, 'FV2026/08/1')['stan'], 'opłacona poza bankiem')
        # ręczne połączenie wygrywa z odrzuceniem automatu; cofnięcie przywraca wpłatę do połączenia
        zmiany.zapisz('polacz', {'operacja': k_d, 'faktury': ['FV2026/09/10']})
        zmiany.zapisz('cofnij', {'wpis': wpis['id']})
        self.przelicz()
        self.assertEqual(dopasowane(self.con, 'D1'), {'FV2026/09/10': (123000, 'pewne')})
        self.assertEqual(wplata(self.con, 'S1')['stan'], 'nieznana')

    def test_walidacja_wpisow(self):
        with self.assertRaises(ValueError):
            zmiany.sprawdz('usun_wszystko', {})
        with self.assertRaises(ValueError):
            zmiany.sprawdz('polacz', {'operacja': 'x', 'faktury': []})
        self.assertEqual(zmiany.sprawdz('bez_faktury', {'operacja': 'x', 'powod': 'zwrot', 'inne': 1}),
                         {'operacja': 'x', 'powod': 'zwrot'})

    def test_dwukrotna_odbudowa_te_same_wyniki(self):
        przed = [tuple(r) for r in self.con.execute('SELECT * FROM faktury_stan ORDER BY numer')]
        self.przelicz()
        self.assertEqual([tuple(r) for r in self.con.execute('SELECT * FROM faktury_stan ORDER BY numer')], przed)


class TestZapisPrzezSerwer(unittest.TestCase):
    """POST /api/zmiana: walidacja, odwołania do istniejących danych, zapis w pliku tego Maca."""

    def test_zapis(self):
        import http.client
        import threading
        from http.server import ThreadingHTTPServer
        from finanse import serwer
        with Srodowisko() as srod:
            dane_testowe(srod.dane)
            odbudowa.odbuduj()
            stary = konfig.PORT
            http_srv = ThreadingHTTPServer((konfig.HOST, 0), serwer.Obsluga)
            konfig.PORT = http_srv.server_address[1]
            threading.Thread(target=http_srv.serve_forever, daemon=True).start()
            try:
                def wyslij(cialo, x_finanse=True):
                    c = http.client.HTTPConnection('127.0.0.1', konfig.PORT, timeout=10)
                    h = {'Host': f'127.0.0.1:{konfig.PORT}', 'Content-Type': 'application/json'}
                    if x_finanse:
                        h['X-Finanse'] = '1'
                    c.request('POST', '/api/zmiana', body=json.dumps(cialo), headers=h)
                    r = c.getresponse()
                    tresc = r.read()
                    return r.status, json.loads(tresc) if r.getheader('Content-Type', '').startswith('application/json') else {}
                con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
                k = klucz(con, 'S1')
                con.close()
                self.assertEqual(wyslij({'typ': 'bez_faktury', 'dane': {'operacja': k, 'powod': 'zwrot'}}, x_finanse=False)[0], 403)
                self.assertEqual(wyslij({'typ': 'skasuj', 'dane': {}})[0], 400)
                self.assertEqual(wyslij({'typ': 'bez_faktury', 'dane': {'operacja': 'zmyślona', 'powod': ''}})[0], 400)
                self.assertEqual(wyslij({'typ': 'polacz', 'dane': {'operacja': k, 'faktury': ['FV1999/1/1']}})[0], 400)
                status, odp = wyslij({'typ': 'bez_faktury', 'dane': {'operacja': k, 'powod': 'zwrot'}})
                self.assertEqual(status, 200, odp)
                linie = (konfig.katalog_zmian() / 'Mac-testowy.jsonl').read_text(encoding='utf-8').splitlines()
                self.assertEqual(len(linie), 1)
                con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
                self.assertEqual(wplata(con, 'S1')['stan'], 'bez_faktury')
                con.close()
            finally:
                http_srv.shutdown()
                http_srv.server_close()
                konfig.PORT = stary


if __name__ == '__main__':
    unittest.main()
