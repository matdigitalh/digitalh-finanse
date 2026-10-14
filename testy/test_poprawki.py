"""Poprawki z testu 14.10 na zmyślonych danych: zwrot zakupu, tolerancja groszowa, korekta ręczna,
konta reklamowe (Google po numerze, Meta przez plik faktury), dokumenty z folderu Faktury."""
import unittest

from finanse import baza, konfig, odbudowa, zapytania, zmiany
from finanse.importy.faktury_dysk import WZOR, konto
from testy.pomoc import ONLINE, Srodowisko, faktura, operacja, zapisz_fakturownie, zapisz_ing, zapisz_rejestr


def dane(srod):
    zapisz_fakturownie(srod.dane, 'fakturownia_sprzedaz_2026-10-13.csv', [
        faktura(1, 'FV2026/05/14', 'Opłacona', '2026-05-10', '2026-05-24', 'KAPPA SP. Z O.O.', '555', [('Usługa', 924)]),   # 1 136,52
        faktura(2, 'FV2026/08/17', 'Opłacona', '2026-08-10', '2026-08-24', 'LAMBDA SA', '666', [('Usługa', 7600)]),         # 9 348,00
    ])
    zapisz_ing(srod.dane, 'ing_historia_2026-01-01_2026-10-13.csv', [
        operacja('2026-10-13', '-1,00', '0', 'ING BANK ŚLĄSKI', 'OPŁATA', ref='X0'),
        operacja('2026-10-02', '-1879,88', '0', 'GOOGLE *ADS1234567890 DUBLIN', 'Płatność kartą', rachunek=ONLINE, ref='G1'),
        operacja('2026-09-30', '-440,00', '0', 'FACEBK *WNGQGHVA', 'Płatność kartą', rachunek=ONLINE, ref='M1'),
        operacja('2026-09-21', '6999,02', '0', 'DALPO POZNAŃ SP. Z O.O.', 'Zwrot - nadpłata', ref='Z1'),
        operacja('2026-08-25', '8241,00', '0', 'LAMBDA SA', 'FV2026/08/17 minus korekta FK2026/08/1', ref='W2'),
        operacja('2026-08-06', '-6999,02', '0', 'sklep.dalpo.pl Poznan', 'Płatność kartą', rachunek=ONLINE, ref='K1'),
        operacja('2026-05-20', '1136,00', '0', 'KAPPA SP. Z O.O.', 'FV2026/05/14', ref='W1'),
    ])
    zapisz_rejestr(srod.dane, 'biuro_rejestr_zakupow_2026-01_2026-08.xlsx',
                   [['1/K', 'FV 1/08/2026', '2026-08-31', '2026-08-31', 'Biuro (00001)', None, None, 100, 23, 123]], [])
    folder = srod.katalog / 'Finanse' / 'Faktury' / 'Wrzesien 2026' / 'Zweryfikowane'
    folder.mkdir(parents=True)
    for nazwa in ('GoogleAds-5550002222_1879.88PLN_2026-09-30_konto-123-456-7890.pdf',
                  'Meta-12345678901234567_440.00PLN_2026-09-29_konto-ALFA.pdf'):
        (folder / nazwa).write_bytes(b'')


def wpl(con, ref):
    return con.execute('SELECT w.* FROM wplaty w JOIN operacje o ON o.id = w.operacja_id WHERE o.nr_ref = ?', (ref,)).fetchone()


def wyd(con, ref):
    return con.execute('SELECT w.* FROM wydatki w JOIN operacje o ON o.id = w.operacja_id WHERE o.nr_ref = ?', (ref,)).fetchone()


class TestNazwyPlikow(unittest.TestCase):
    def test_wzor_nazwy(self):
        d = WZOR.match('GoogleAds-5550001111_975.52PLN_2026-09-30_konto-123-456-7890').groupdict()
        self.assertEqual((d['wystawca'], d['kwota'], d['waluta'], d['data']), ('GoogleAds', '975.52', 'PLN', '2026-09-30'))
        self.assertEqual(konto(d['wystawca'], d['nr'], d['tag']), 'Google Ads 123-456-7890')
        d = WZOR.match('GreenCaffeNero_22.90PLN_2026-08-13_paragon').groupdict()
        self.assertEqual((d['wystawca'], d['nr'], d['tag']), ('GreenCaffeNero', None, 'paragon'))
        self.assertEqual(konto('Meta', 'FBADS-720-106419003', ''), 'Meta FBADS-720')


class TestPoprawki(unittest.TestCase):
    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane(self.srod)
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def przelicz(self):
        self.con.close()
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    def test_zwrot_zakupu_wychodzi_z_wyniku_i_list(self):
        self.assertEqual(wpl(self.con, 'Z1')['stan'], 'zwrot_zakupu')
        self.assertEqual(wyd(self.con, 'K1')['rodzaj'], 'zwrocony')

    def test_niedoplata_do_zlotowki(self):
        s = self.con.execute("SELECT stan, pozostalo, uwaga FROM faktury_stan WHERE numer = 'FV2026/05/14'").fetchone()
        self.assertEqual((s['stan'], s['pozostalo']), ('opłacona', 0))
        self.assertIn('0,52', s['uwaga'])

    def test_korekta_z_tytulu_i_korekta_reczna(self):
        k = [x for x in zapytania.do_weryfikacji(self.con) if x['rodzaj'] == 'korekta_w_tytule']
        self.assertEqual((k[0]['korekta'], k[0]['kwota']), ('FK2026/08/1', 110700))
        zmiany.zapisz('korekta', zmiany.sprawdz('korekta', {'numer': 'FK2026/08/1', 'faktura': 'FV2026/08/17', 'kwota': '110700'}))
        self.przelicz()
        s = self.con.execute("SELECT stan, korekty FROM faktury_stan WHERE numer = 'FV2026/08/17'").fetchone()
        self.assertEqual((s['stan'], s['korekty']), ('opłacona', -110700))
        self.assertEqual(self.con.execute('SELECT netto FROM korekty_reczne').fetchone()[0], -90000)

    def test_konta_reklamowe(self):
        self.assertEqual(wyd(self.con, 'G1')['konto'], 'Google Ads 123-456-7890')
        self.assertEqual(wyd(self.con, 'M1')['konto'], 'Meta ALFA')   # FACEBK przez plik faktury: kwota i data ±5 dni
        zmiany.zapisz('konto_reklamowe', {'konto': 'Google Ads 123-456-7890', 'klient': 'Klient Alfa'})
        self.przelicz()
        self.assertEqual((wyd(self.con, 'G1')['rodzaj'], wyd(self.con, 'G1')['klient']), ('przenoszony', 'Klient Alfa'))

    def test_dokument_z_folderu_po_koncu_rejestru(self):
        d = self.con.execute("SELECT d.metoda FROM wydatki_dok d JOIN operacje o ON o.id = d.operacja_id WHERE o.nr_ref = 'G1'").fetchone()
        self.assertEqual(d[0], 'plik w folderze Faktury')
        self.assertEqual(wyd(self.con, 'G1')['dokument'], 'dokument')


if __name__ == '__main__':
    unittest.main()
