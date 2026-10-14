import shutil
import unittest

from finanse import baza, konfig, odbudowa, zapytania
from testy.pomoc import (GLOWNY, ONLINE, VAT, Srodowisko, faktura, operacja, uwaga, zapisz_fakturownie, zapisz_ing,
                         zapisz_rejestr)


def wrzesien_pazdziernik(dane):
    """Dwa nakładające się eksporty ING; ostatni dzień wspólny. Najnowsze na górze, jak w banku."""
    zapisz_ing(dane, 'ing_historia_2026-09-01_2026-09-30.csv', [
        operacja('2026-09-30', '-1000,00', '9000,00', 'FIRMA TESTOWA A', 'FV 1/2026', ref='R3'),
        operacja('2026-09-15', '10000,00', '10000,00', 'KLIENT ZMYŚLONY SP. Z O.O.', 'FV2026/09/1', ref='R1'),
    ])
    zapisz_ing(dane, 'ing_historia_2026-09-15_2026-10-13.csv', [
        operacja('2026-10-13', '-50,00', '8450,00', '', 'opłata', ref=''),
        operacja('2026-10-12', '-500,00', '8500,00', 'DIGITALH SPÓŁKA Z OGRANICZONĄ', 'Przelew własny', ref='R4'),
        operacja('2026-10-12', '500,00', '700,00', 'DIGITALH SPÓŁKA Z OGRANICZONĄ', 'Przelew własny', rachunek=ONLINE, ref='R4b'),
        operacja('2026-10-10', '-230,00', '8770,00', 'DOSTAWCA', '/VAT/230,00/IDC/123/INV/X', ref='R5'),
        operacja('2026-10-10', '230,00', '230,00', 'DOSTAWCA', '/VAT/230,00/IDC/123/INV/X', rachunek=VAT, ref='R5'),
        operacja('2026-09-30', '-1000,00', '9000,00', 'FIRMA TESTOWA A', 'FV 1/2026', ref='R3'),
        operacja('2026-09-15', '10000,00', '10000,00', 'KLIENT ZMYŚLONY SP. Z O.O.', 'FV2026/09/1', ref='R1'),
    ])


class TestING(unittest.TestCase):
    def test_nakladajace_sie_eksporty_i_podzielona_platnosc(self):
        with Srodowisko() as s:
            wrzesien_pazdziernik(s.dane)
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy())
            # 7 unikalnych operacji: dwie z września się powtarzają, VAT z tym samym numerem na dwóch rachunkach zostaje
            self.assertEqual(con.execute('SELECT COUNT(*) FROM operacje').fetchone()[0], 7)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM operacje WHERE nr_ref='R5'").fetchone()[0], 2)
            log = {r['plik']: r for r in con.execute('SELECT * FROM import_log')}
            self.assertEqual(log['ing_historia_2026-09-01_2026-09-30.csv']['pominietych'], 2)
            salda = zapytania.salda(con)
            self.assertEqual(salda['główny']['saldo_po'], 845000)   # pierwszy wiersz rachunku w najnowszym pliku
            self.assertEqual(salda['online']['saldo_po'], 70000)
            self.assertEqual(salda['VAT']['saldo_po'], 23000)
            self.assertEqual(zapytania.stan(con)['gotowka'], 915000)

    def test_ruch_wewnetrzny(self):
        with Srodowisko() as s:
            wrzesien_pazdziernik(s.dane)
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy())
            wewn = {(r['nr_ref'], r['rachunek']) for r in con.execute('SELECT * FROM operacje WHERE wewnetrzna=1')}
            self.assertEqual(wewn, {('R4', 'główny'), ('R4b', 'online'), ('R5', 'VAT')})
            bez = zapytania.operacje(con, wewnetrzne='bez')
            self.assertEqual(bez['wplywy'], 1000000)
            self.assertEqual(bez['obciazenia'], -128000)

    def test_dwukrotna_odbudowa_i_kopia_pliku_nic_nie_zmieniaja(self):
        with Srodowisko() as s:
            wrzesien_pazdziernik(s.dane)
            odbudowa.odbuduj()
            pierwszy = odcisk_liczb()
            shutil.copy(s.dane / 'ING' / 'ing_historia_2026-09-15_2026-10-13.csv',
                        s.dane / 'ING' / 'ing_historia_2026-09-15_2026-10-13 kopia.csv')
            odbudowa.odbuduj()
            self.assertEqual(odcisk_liczb(), pierwszy)
            odbudowa.odbuduj()
            self.assertEqual(odcisk_liczb(), pierwszy)

    def test_zly_plik_nie_blokuje_reszty(self):
        with Srodowisko() as s:
            wrzesien_pazdziernik(s.dane)
            (s.dane / 'ING' / 'ing_historia_2026-10-14_2026-10-14.csv').write_text('to nie jest eksport', encoding='utf-8')
            raport = odbudowa.odbuduj()
            self.assertTrue(any('brak kolumn' in b for b in raport['bledy']))
            con = baza.polacz(konfig.plik_bazy())
            self.assertEqual(con.execute('SELECT COUNT(*) FROM operacje').fetchone()[0], 7)

    def test_uprawnienia_bazy(self):
        with Srodowisko() as s:
            wrzesien_pazdziernik(s.dane)
            odbudowa.odbuduj()
            self.assertEqual(konfig.plik_bazy().stat().st_mode & 0o777, 0o600)
            self.assertEqual(konfig.plik_bazy().parent.stat().st_mode & 0o777, 0o700)


def odcisk_liczb():
    con = baza.polacz(konfig.plik_bazy())
    try:
        return tuple(con.execute('SELECT COUNT(*), SUM(kwota), SUM(wewnetrzna) FROM operacje').fetchone()) + \
            tuple(con.execute('SELECT COUNT(*), COALESCE(SUM(brutto),0) FROM faktury').fetchone())
    finally:
        con.close()


class TestFakturownia(unittest.TestCase):
    def test_pozycje_w_blokach_i_uwagi(self):
        with Srodowisko() as s:
            zapisz_fakturownie(s.dane, 'fakturownia_sprzedaz_2026-10-01.csv', [faktura(1, 'FV2026/09/9', 'Opłacona', '2026-09-01', '2026-09-08', 'Stary', '1', [('X', 1.0)])])
            zapisz_fakturownie(s.dane, 'fakturownia_sprzedaz_2026-10-13.csv', [
                faktura(1, 'FV2026/10/1', 'Wystawiona', '2026-10-01', '2026-10-15', 'Klient Zmyślony', '123-456-78-90',
                        [('Obsługa', 1000.0), ('Media', 500.0)], ksef='1234567890-20261001-ABCDEF-12'),
                uwaga(1, 'FV2026/10/1', 'Koszty reklamowe refaktura'),
                faktura(2, 'FV2026/10/2', 'Opłacona', '2026-10-02', '2026-10-09', 'Inny Klient', '999', [('SEO', 200.0)], oplacono='246.0'),
            ])
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy())
            # tylko najnowszy eksport
            self.assertEqual([r[0] for r in con.execute('SELECT numer FROM faktury ORDER BY numer')], ['FV2026/10/1', 'FV2026/10/2'])
            f = dict(con.execute("SELECT * FROM faktury WHERE numer='FV2026/10/1'").fetchone())
            self.assertEqual((f['netto'], f['vat'], f['brutto']), (150000, 34500, 184500))
            self.assertEqual(f['nip'], '1234567890')
            self.assertEqual(f['uwagi'], 'Koszty reklamowe refaktura')
            self.assertEqual(f['korekta'], 0)
            poz = con.execute("SELECT nazwa, netto FROM faktury_pozycje WHERE numer='FV2026/10/1' ORDER BY lp").fetchall()
            self.assertEqual([tuple(p) for p in poz], [('Obsługa', 100000), ('Media', 50000)])
            log = con.execute("SELECT uwagi FROM import_log WHERE rodzaj='Fakturownia'").fetchone()[0]
            self.assertNotIn('różną od netto', log)

    def test_korekta(self):
        with Srodowisko() as s:
            zapisz_fakturownie(s.dane, 'fakturownia_sprzedaz_2026-10-13.csv', [
                faktura(1, 'FV2026/10/3', 'Wystawiona', '2026-10-03', '2026-10-10', 'K', '1', [('Obsługa', -500.0)], oryginal='FV2026/07/3')])
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy())
            f = con.execute('SELECT korekta, oryginal, brutto FROM faktury').fetchone()
            self.assertEqual(tuple(f), (1, 'FV2026/07/3', -61500))


class TestRejestr(unittest.TestCase):
    def test_sufiks_sumy_i_nakladanie(self):
        from datetime import datetime
        with Srodowisko() as s:
            d = datetime(2026, 9, 1)
            zapisz_rejestr(s.dane, 'biuro_rejestr_zakupow_2026-01_2026-09.xlsx',
                           [['ZR/1', 'A/1', d, d, 'DOSTAWCA SP. Z O.O. (00024)', 0, 0, 100.0, 23.0, 123.0],
                            ['ZR/2', 'A/2', d, d, 'DRUKARNIA (00007)', 10, 0.8, 0, 0, 10.8]],
                           [['DW/1', 'FB-1', d, d, 'META PLATFORMS IRLANDIA LIMITED (00018)', 55.5]])
            zapisz_rejestr(s.dane, 'biuro_rejestr_zakupow_2026-09_2026-10.xlsx',
                           [['ZR/2', 'A/2', d, d, 'DRUKARNIA (00007)', 10, 0.8, 0, 0, 10.8]], [])
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy())
            rows = {r['nr_ewid']: dict(r) for r in con.execute('SELECT * FROM zakupy')}
            self.assertEqual(set(rows), {'ZR/1', 'ZR/2', 'DW/1'})
            self.assertEqual(rows['ZR/1']['podmiot'], 'DOSTAWCA SP. Z O.O.')
            self.assertEqual(rows['ZR/1']['podmiot_kod'], '00024')
            self.assertEqual((rows['ZR/2']['netto'], rows['ZR/2']['vat'], rows['ZR/2']['brutto']), (1000, 80, 1080))
            self.assertEqual((rows['DW/1']['netto'], rows['DW/1']['brutto']), (5550, None))


if __name__ == '__main__':
    unittest.main()
