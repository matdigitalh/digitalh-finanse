"""Rejestr umów: terminy dla trzech rodzajów umów, alert, walidacja, zapis przez plik zmian z cofnięciem."""
import unittest
from datetime import date

from finanse import baza, konfig, odbudowa, umowy, zmiany
from testy.pomoc import Srodowisko, operacja, zapisz_ing

DZIS = date(2026, 10, 15)


class TestTerminy(unittest.TestCase):
    def test_okreslony_z_przedluzeniem(self):
        t = umowy.termin({'rodzaj': 'okreslony', 'do': '2026-12-31', 'przedluzenie': True, 'wypowiedzenie_mies': 1, 'alert_dni': 60}, DZIS)
        self.assertEqual((t['data'], t['stan']), ('2026-11-30', 'alert'))     # 46 dni, alert 60

    def test_okreslony_bez_przedluzenia(self):
        t = umowy.termin({'rodzaj': 'okreslony', 'do': '2027-06-30', 'wypowiedzenie_mies': 3}, DZIS)
        self.assertEqual((t['data'], t['stan']), ('2027-06-30', 'ok'))
        self.assertIn('wygasa', t['co'])

    def test_minal(self):
        t = umowy.termin({'rodzaj': 'okreslony', 'do': '2026-10-01', 'przedluzenie': True, 'wypowiedzenie_mies': 1}, DZIS)
        self.assertEqual(t['stan'], 'minął')

    def test_nieokreslony_na_koniec_miesiaca(self):
        t = umowy.termin({'rodzaj': 'nieokreslony', 'wypowiedzenie_mies': 3, 'koniec_miesiaca': True}, DZIS)
        self.assertEqual((t['koniec'], t['stan']), ('2027-01-31', 'bez terminu'))
        t = umowy.termin({'rodzaj': 'nieokreslony', 'wypowiedzenie_mies': 1, 'koniec_miesiaca': False}, DZIS)
        self.assertEqual(t['koniec'], '2026-11-15')

    def test_walidacja(self):
        for zle in ({'id': 'u1', 'klient': '', 'rodzaj': 'okreslony'}, {'id': 'u1', 'klient': 'A', 'rodzaj': 'okreslony'},
                    {'id': 'u1', 'klient': 'A', 'rodzaj': 'na zawsze'}, {'id': 'u1', 'klient': 'A', 'rodzaj': 'nieokreslony', 'wypowiedzenie_mies': 'trzy'}):
            with self.assertRaises(ValueError):
                zmiany.sprawdz('umowa', zle)


class TestRejestr(unittest.TestCase):
    def test_zapis_zmiana_usuniecie(self):
        with Srodowisko() as srod:
            zapisz_ing(srod.dane, 'ing_historia_2026-10-01_2026-10-13.csv', [operacja('2026-10-13', '1,00', '1,00', 'X', 'x', ref='R')])
            zmiany.zapisz('umowa', zmiany.sprawdz('umowa', {'id': 'u1', 'klient': 'Alfa', 'rodzaj': 'nieokreslony', 'wypowiedzenie_mies': '1',
                                                             'wartosc_mies': '500000'}))
            zmiany.zapisz('umowa', zmiany.sprawdz('umowa', {'id': 'u1', 'klient': 'Alfa', 'rodzaj': 'okreslony', 'do': '2026-12-31',
                                                             'przedluzenie': True, 'wypowiedzenie_mies': '1', 'wartosc_mies': '600000'}))
            wpis = zmiany.zapisz('umowa', {'id': 'u2', 'klient': 'Beta', 'rodzaj': 'nieokreslony'})
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
            d = umowy.lista(con, DZIS)
            self.assertEqual(d['wartosc_mies'], 600000)
            self.assertEqual([u['klient'] for u in d['umowy']], ['Alfa', 'Beta'])   # alert przed „bez terminu”
            con.close()
            zmiany.zapisz('cofnij', {'wpis': wpis['id']})
            zmiany.zapisz('umowa', {'id': 'u1', 'usun': True})
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
            self.assertEqual(umowy.lista(con, DZIS)['umowy'], [])
            con.close()


if __name__ == '__main__':
    unittest.main()
