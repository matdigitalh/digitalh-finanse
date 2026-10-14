"""Etap 4 na zmyślonych danych: miesiąc kosztów pracy, wynik zarządczy, VAT i podział zysku poza wynikiem."""
import unittest

from finanse import baza, konfig, odbudowa, wynik
from finanse.wynik import okres_pracy
from testy.pomoc import Srodowisko
from testy.test_klienci import dane_testowe


class TestOkresPracy(unittest.TestCase):
    def test_okres_z_tytulu(self):
        self.assertEqual(okres_pracy('WYNAGRODZENIE ZA 07.2026 ZARZĄD', '2026-08-06'), '2026-07')
        self.assertEqual(okres_pracy('DRA 01/07', '2026-08-17'), '2026-07')
        self.assertEqual(okres_pracy('DRA 01/12', '2026-01-15'), '2025-12')
        self.assertEqual(okres_pracy('/TI/N123/OKR/26M08/SFP/PIT-4 /TXT/PIT-4', '2026-09-21'), '2026-08')
        self.assertEqual(okres_pracy('SKŁADKI PPK 2026 07 FIRMA', '2026-08-17'), '2026-07')

    def test_bez_okresu(self):
        self.assertEqual(okres_pracy('Rach. umowa o dzieło', '2026-08-11'), '2026-07')
        self.assertEqual(okres_pracy('Rach. umowa o dzieło', '2026-08-28'), '2026-08')
        self.assertEqual(okres_pracy('przelew', '2026-01-10'), '2025-12')


class TestWynik(unittest.TestCase):
    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane_testowe(self.srod.dane)
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        self.w = wynik.wynik_zarzadczy(self.con, '2026')
        self.wiersz = {x['klucz']: x for x in self.w['wiersze']}

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def test_obrot_i_koszty_klienta(self):
        self.assertEqual(self.wiersz['obrot']['miesiace']['2026-09'], 350000)            # 1000 + 500 + 2000 netto
        self.assertEqual(self.wiersz['przenoszony']['miesiace']['2026-09'], -100000)     # netto z dokumentu, miesiąc dokumentu

    def test_praca_w_miesiacu_ktorego_dotyczy(self):
        self.assertEqual(self.wiersz['praca']['miesiace']['2026-08'], -500000 - 80000)  # wynagrodzenie ZA 08 i ZUS z 20.09

    def test_vat_dywidenda_zwrot_poza_wynikiem(self):
        m = '2026-09'
        w = self.wiersz
        oczekiwany = (w['obrot']['miesiace'][m] + w['przenoszony']['miesiace'][m] + w['praca']['miesiace'][m]
                      + w['staly']['miesiace'][m] + w['nieprzypisany']['miesiace'][m])
        self.assertEqual(w['wynik']['miesiace'][m], oczekiwany)
        self.assertEqual(w['vat']['miesiace']['2026-09'], -150000)
        self.assertEqual(w['zwrot']['razem'], -165804)

    def test_obroty_klientow_i_vat(self):
        k = {x['klient']: x for x in wynik.obroty_klientow(self.con, '2026')['klienci']}
        self.assertEqual((k['Klient Alfa']['obrot'], k['Klient Alfa']['koszty']), (150000, 100000))
        v = {x['miesiac']: x for x in wynik.vat(self.con, '2026')['miesiace']}
        self.assertEqual(v['2026-09']['nalezny'], 80500)
        self.assertEqual(v['2026-09']['naliczony'], 23000 + 11500 + 2300)


if __name__ == '__main__':
    unittest.main()
