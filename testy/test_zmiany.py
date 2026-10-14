import os
import unittest

from finanse import konfig, odbudowa, serwer, zmiany
from testy.pomoc import Srodowisko, operacja, zapisz_ing


class TestDwaMaki(unittest.TestCase):
    def test_kazdy_mac_pisze_do_swojego_pliku_a_stan_sklada_sie_po_czasie(self):
        with Srodowisko():
            os.environ['FINANSE_MAC'] = 'Mac-mini'
            zmiany.zapisz('regula_platnika', {'platnik': 'A', 'klient': 'X'})
            os.environ['FINANSE_MAC'] = 'MacBook'
            zmiany.zapisz('regula_platnika', {'platnik': 'A', 'klient': 'Y'})
            pliki = sorted(p.name for p in konfig.katalog_zmian().glob('*.jsonl'))
            self.assertEqual(pliki, ['Mac-mini.jsonl', 'MacBook.jsonl'])
            wpisy, ostrzezenia = zmiany.wczytaj()
            self.assertEqual([w['dane']['klient'] for w in wpisy], ['X', 'Y'])
            self.assertEqual(ostrzezenia, [])
            self.assertEqual((konfig.katalog_zmian() / 'MacBook.jsonl').stat().st_mode & 0o777, 0o600)

    def test_ucieta_linia_i_konflikt_icloud_to_ostrzezenie_nie_awaria(self):
        with Srodowisko():
            zmiany.zapisz('test', {})
            with open(konfig.katalog_zmian() / 'Mac-testowy.jsonl', 'a', encoding='utf-8') as f:
                f.write('{"czas": "2026-')
            (konfig.katalog_zmian() / 'Mac-testowy (conflicted copy).jsonl.bak').write_text('')
            wpisy, ostrzezenia = zmiany.wczytaj()
            self.assertEqual(len(wpisy), 1)
            self.assertEqual(len(ostrzezenia), 2)

    def test_wpis_z_drugiego_maca_oznacza_baze_jako_nieaktualna(self):
        with Srodowisko() as s:
            zapisz_ing(s.dane, 'ing_historia_2026-10-01_2026-10-13.csv',
                       [operacja('2026-10-13', '1,00', '1,00', 'K', 't', ref='R1')])
            odbudowa.odbuduj()
            self.assertTrue(serwer.czy_aktualna())
            os.environ['FINANSE_MAC'] = 'MacBook'
            zmiany.zapisz('umowa', {'klient': 'X'})
            self.assertFalse(serwer.czy_aktualna())
            odbudowa.odbuduj()
            self.assertTrue(serwer.czy_aktualna())

    def test_nowy_plik_w_dane_oznacza_baze_jako_nieaktualna(self):
        with Srodowisko() as s:
            zapisz_ing(s.dane, 'ing_historia_2026-10-01_2026-10-13.csv', [operacja('2026-10-13', '1,00', '1,00', 'K', 't', ref='R1')])
            odbudowa.odbuduj()
            zapisz_ing(s.dane, 'ing_historia_2026-10-01_2026-10-20.csv', [operacja('2026-10-20', '1,00', '2,00', 'K', 't', ref='R2')])
            self.assertFalse(serwer.czy_aktualna())


if __name__ == '__main__':
    unittest.main()
