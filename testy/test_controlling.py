"""Pulpit kontrolingowy na zmyślonych danych: rezerwa gotówki, cele z pliku zmian, walidacja celów."""
import unittest

from finanse import baza, controlling, konfig, odbudowa, zmiany
from testy.pomoc import Srodowisko
from testy.test_klienci import dane_testowe


class TestControlling(unittest.TestCase):
    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane_testowe(self.srod.dane)
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def test_cele_domyslne_i_z_pliku_zmian(self):
        self.assertEqual(controlling.policz(self.con)['cele'], controlling.CELE_DOMYSLNE)
        zmiany.zapisz('cel', zmiany.sprawdz('cel', {'klucz': 'cel_marza_proc', 'wartosc': '12,5'}))
        self.con.close()
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        self.assertEqual(controlling.policz(self.con)['cele']['cel_marza_proc'], 12.5)

    def test_rezerwa(self):
        r = controlling.policz(self.con)['rezerwa']
        self.assertEqual(r['okno'][-1], '2026-09')            # pełne miesiące przed miesiącem stanu (10.2026)
        self.assertGreater(r['srednie_koszty'], 0)
        self.assertEqual(r['wymagana'], r['koszt_krytyczny'] * 3)
        self.assertEqual(r['wymagana_wszystkie'], r['srednie_koszty'] * 3)
        self.assertIn(r['status'], ('dobrze', 'uwaga', 'zle'))
        self.assertGreaterEqual(r['srednie_koszty'], r['srednie_stale'])   # stałe to część wszystkich

    def test_walidacja_celow(self):
        for zle in ({'klucz': 'cel_zysk', 'wartosc': '1'}, {'klucz': 'cel_marza_proc', 'wartosc': 'dużo'},
                    {'klucz': 'cel_marza_proc', 'wartosc': '150'}):
            with self.assertRaises(ValueError):
                zmiany.sprawdz('cel', zle)
        self.assertEqual(zmiany.sprawdz('cel', {'klucz': 'cel_obrot_rok', 'wartosc': '120000000'})['wartosc'], 120000000)


class TestRezerwaKrytyczna(unittest.TestCase):
    """Rezerwa na koszty krytyczne (decyzja Mata 2026-10-20). Dane z test_klienci: wrzesień 2026 praca 6415 zł
    (ZUS, pensja, grafik), koszt klienta 1230 zł, stałe 41 zł (Figma, sierpień) i 30 zł (bank, wrzesień), nieprzypisane 199 zł."""

    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane_testowe(self.srod.dane)
        odbudowa.odbuduj()

    def tearDown(self):
        self.srod.__exit__()

    def rezerwa(self):
        odbudowa.odbuduj()
        con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        try:
            r = controlling.policz(con)['rezerwa']
        finally:
            con.close()
        return r, {p['klucz']: p for p in r['pozycje']}

    def wpis(self, dane):
        return zmiany.zapisz('rezerwa', zmiany.sprawdz('rezerwa', dane))

    def test_domyslne_pozycje(self):
        r, p = self.rezerwa()
        self.assertEqual([x['klucz'] for x in r['pozycje']], list(controlling.KLUCZE_POZYCJI))
        self.assertEqual([k for k, x in p.items() if x['wlaczona']], ['wynagrodzenia', 'ksiegowosc'])
        self.assertEqual(r['ksiegowosc'], ['brixen fk'])
        # średnia z miesięcy z danymi (sierpień i wrzesień): praca 641 500 gr / 2
        self.assertEqual(p['wynagrodzenia']['srednia'], 320750)
        self.assertEqual(p['ksiegowosc']['srednia'], 0)
        self.assertEqual(r['koszt_krytyczny'], 320750)
        self.assertEqual(r['wymagana'], 320750 * 3)
        self.assertEqual(r['nadwyzka'], r['gotowka'] - r['wymagana'])
        # wszystkie pozycje razem = średnia wszystkich kosztów (stare pole zostaje, cashflow.py czyta srednie_stale)
        self.assertEqual(sum(x['srednia'] for x in r['pozycje']), r['srednie_koszty'])
        self.assertEqual(r['srednie_stale'], r['srednie_koszty'] - p['klienci']['srednia'])
        for x in r['pozycje']:
            self.assertIsInstance(x['srednia'], int)

    def test_wylaczenie_i_wlaczenie_pozycji(self):
        self.wpis({'pozycje': {'wynagrodzenia': {'wlaczona': False}, 'narzedzia': {'wlaczona': True}}})
        r, p = self.rezerwa()
        self.assertFalse(p['wynagrodzenia']['wlaczona'])
        self.assertEqual(r['koszt_krytyczny'], p['narzedzia']['srednia'] + p['ksiegowosc']['srednia'])
        self.assertEqual(r['koszt_krytyczny'], 3550)
        self.assertEqual(r['wlaczone'], ['Księgowość', 'Narzędzia i inne stałe'])

    def test_kwota_wlasna_zastepuje_srednia(self):
        self.wpis({'pozycje': {'wynagrodzenia': {'kwota': 4500000}}})
        r, p = self.rezerwa()
        self.assertEqual((p['wynagrodzenia']['srednia'], p['wynagrodzenia']['liczona']), (320750, 4500000))
        self.assertEqual(r['koszt_krytyczny'], 4500000)
        self.wpis({'pozycje': {'wynagrodzenia': {'kwota': None}}})   # puste pole: z powrotem średnia, włączenie bez zmian
        r, p = self.rezerwa()
        self.assertEqual((p['wynagrodzenia']['liczona'], p['wynagrodzenia']['wlaczona']), (320750, True))

    def test_ksiegowosc_wyjeta_z_narzedzi(self):
        _, p = self.rezerwa()
        self.assertEqual(p['narzedzia']['srednia'], 3550)   # Figma 41 zł + bank 30 zł, przez 2 miesiące
        self.wpis({'ksiegowosc': ['Figma San ']})
        r, p = self.rezerwa()
        self.assertEqual(r['ksiegowosc'], ['figma san'])
        self.assertEqual((p['ksiegowosc']['srednia'], p['narzedzia']['srednia']), (2050, 1500))
        self.assertEqual(r['koszt_krytyczny'], 320750 + 2050)

    def test_cofniecie_wpisu(self):
        self.wpis({'pozycje': {'wynagrodzenia': {'kwota': 100}}})
        w = self.wpis({'pozycje': {'wynagrodzenia': {'kwota': 200}, 'podatki': {'wlaczona': True}}})
        _, p = self.rezerwa()
        self.assertEqual(p['wynagrodzenia']['liczona'], 200)
        zmiany.zapisz('cofnij', zmiany.sprawdz('cofnij', {'wpis': w['id']}))
        r, p = self.rezerwa()
        self.assertEqual(p['wynagrodzenia']['liczona'], 100)   # stan sprzed cofniętego wpisu, nie domyślny
        self.assertFalse(p['podatki']['wlaczona'])

    def test_walidacja(self):
        for zle in ({'pozycje': {'premie': {'wlaczona': True}}}, {'pozycje': {'wynagrodzenia': {'kwota': -1}}},
                    {'pozycje': {'wynagrodzenia': {'kwota': 12.5}}}, {'pozycje': {'wynagrodzenia': {'kwota': '100'}}},
                    {'pozycje': {'wynagrodzenia': {'wlaczona': 'tak'}}}, {'pozycje': {'wynagrodzenia': {'inne': 1}}},
                    {'pozycje': {}}, {'ksiegowosc': 'brixen fk'}, {'pozycje': {}, 'cel': 1}, {'ksiegowosc': ['']}):
            with self.assertRaises(ValueError, msg=zle):
                zmiany.sprawdz('rezerwa', zle)
        self.assertEqual(zmiany.sprawdz('rezerwa', {'pozycje': {'podatki': {'wlaczona': True, 'kwota': 0}}}),
                         {'pozycje': {'podatki': {'wlaczona': True, 'kwota': 0}}})
        from finanse import serwer   # odwołania: kontrahent księgowości musi być w wydatkach z banku
        con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        try:
            serwer._sprawdz_odwolania(con, 'rezerwa', {'pozycje': {}, 'ksiegowosc': ['figma san']})
            with self.assertRaises(ValueError):
                serwer._sprawdz_odwolania(con, 'rezerwa', {'pozycje': {}, 'ksiegowosc': ['zmyslone biuro']})
        finally:
            con.close()


if __name__ == '__main__':
    unittest.main()
