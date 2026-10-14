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
        self.assertEqual(r['wymagana'], r['srednie_koszty'] * 3)
        self.assertIn(r['status'], ('dobrze', 'uwaga', 'zle'))
        self.assertGreaterEqual(r['srednie_koszty'], r['srednie_stale'])   # stałe to część wszystkich

    def test_walidacja_celow(self):
        for zle in ({'klucz': 'cel_zysk', 'wartosc': '1'}, {'klucz': 'cel_marza_proc', 'wartosc': 'dużo'},
                    {'klucz': 'cel_marza_proc', 'wartosc': '150'}):
            with self.assertRaises(ValueError):
                zmiany.sprawdz('cel', zle)
        self.assertEqual(zmiany.sprawdz('cel', {'klucz': 'cel_obrot_rok', 'wartosc': '120000000'})['wartosc'], 120000000)


if __name__ == '__main__':
    unittest.main()
