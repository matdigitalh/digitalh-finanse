"""Etap 3 na zmyślonych danych: klient faktury, rodzaj kosztu, wydatki a rejestr zakupów, reguły Mata."""
import csv
import unittest

from finanse import baza, konfig, odbudowa, zapytania, zmiany
from finanse.klienci import klucz_kontrahenta, krotka_nazwa
from testy.pomoc import Srodowisko, faktura, operacja, zapisz_fakturownie, zapisz_ing, zapisz_rejestr

BS_NAGLOWEK = ['ID', 'Rodzaj', 'Status aktualności', 'Etap płatności', 'Podstawa płatności', 'Numer wewnętrzny',
               'Numer dokumentu', 'Kontrahent', 'Tytuł', 'Netto (wartość)', 'Brutto (wartość)', 'VAT', 'Stawka VAT',
               'Miesiąc budżetowy', 'Dzień wystawienia', 'Dzień płatności', 'Dzień płatności - realny',
               'Przesunięcie płatności', 'Miesiąc księgowania', 'Metoda płatności', 'Księgowane', 'W cash flow',
               'Komentarz', 'Komentarz w arkuszu', 'Arkusz', 'Folder', 'Kategoria', 'Sekcja', 'Przedmiot transakcji',
               'Data utworzenia', 'Data modyfikacji']


def bs_wiersz(id_, rodzaj, numer, kontrahent, brutto, dzien, arkusz, folder):
    w = dict.fromkeys(BS_NAGLOWEK, '')
    w.update({'ID': id_, 'Rodzaj': rodzaj, 'Status aktualności': 'Aktualne', 'Numer dokumentu': numer, 'Kontrahent': kontrahent,
              'Netto (wartość)': brutto, 'Brutto (wartość)': brutto, 'Miesiąc budżetowy': dzien[:8] + '01',
              'Dzień płatności': dzien, 'Arkusz': arkusz, 'Folder': folder, 'Kategoria': 'x'})
    return w


def dane_testowe(dane):
    zapisz_fakturownie(dane, 'fakturownia_sprzedaz_2026-10-13.csv', [
        faktura(1, 'FV2026/09/1', 'Wystawiona', '2026-09-01', '2026-09-15', 'XY SP. Z O.O.', '111', [('Usługa', 1000)]),
        faktura(2, 'FV2026/09/2', 'Wystawiona', '2026-09-02', '2026-09-16', 'XY SP. Z O.O.', '111', [('Usługa', 500)]),
        faktura(3, 'FV2026/09/3', 'Wystawiona', '2026-09-03', '2026-09-17', '"OMEGA" SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ',
                '222', [('Usługa', 2000)]),
    ])
    zapisz_ing(dane, 'ing_historia_2026-01-01_2026-10-13.csv', [
        operacja('2026-10-10', '-1658,04', '0', 'OMEGA SP. Z O.O.', 'Zwrot nadpłaty do faktury FV2026/09/3', ref='Z1'),
        operacja('2026-10-05', '2460,00', '0', 'OMEGA SP. Z O.O.', 'FV2026/09/3', ref='W1'),
        operacja('2026-10-04', '1658,04', '0', 'OMEGA SP. Z O.O.', 'FV2026/09/3 ponownie', ref='W2'),
        operacja('2026-09-30', '-30,00', '0', 'ING BANK ŚLĄSKI S.A. UL.SOKOLSKA 34', 'OPŁATA ZA PROWADZENIE RACHUNKU', ref='B1'),
        operacja('2026-09-25', '-1500,00', '0', 'URZĄD SKARBOWY', '26M08 VAT-7', ref='T1'),
        operacja('2026-09-20', '-800,00', '0', 'ZUS', 'DRA 08/2026', ref='T2'),
        operacja('2026-09-10', '-5000,00', '0', 'KOWALSKA ANNA UL. TESTOWA', 'WYNAGRODZENIE ZA 08.2026', ref='P1'),
        operacja('2026-09-05', '-1230,00', '0', 'DRUKARNIA TESTOWA SP. Z O.O.', '5555555555-20260901-ABCDEF000001-11', ref='K1'),
        operacja('2026-09-04', '-615,00', '0', 'STUDIO GRAFIKI', 'FS 12/09/2026', ref='K2'),
        operacja('2026-08-29', '-41,00', '0', 'FIGMA SAN FRANCISCO 94102', 'Płatność kartą', rachunek='11105000000000000000005271', ref='C1'),
        operacja('2026-08-15', '-60,00', '0', 'GOOGLE *ADS111 DUBLIN', 'Płatność kartą', rachunek='11105000000000000000005271', ref='G1'),
        operacja('2026-08-08', '-40,00', '0', 'GOOGLE *ADS222 DUBLIN', 'Płatność kartą', rachunek='11105000000000000000005271', ref='G2'),
        operacja('2026-08-02', '-99,00', '0', 'NIEZNANY SKLEP', 'Płatność kartą', ref='N1'),
    ])
    zapisz_rejestr(dane, 'biuro_rejestr_zakupow_2026-01_2026-09.xlsx',
                   [['1/K', 'FV 1/09/2026', '2026-09-01', '2026-09-30', 'DRUKARNIA TESTOWA SP. Z O.O. (00001)', None, None, 1000, 230, 1230],
                    ['2/K', 'FS 12/09/2026', '2026-09-02', '2026-09-30', 'Studio Grafiki (00002)', None, None, 500, 115, 615],
                    ['3/K', 'FV 9/2026', '2026-09-03', '2026-09-30', 'Biuro Bez Płatności (00003)', None, None, 100, 23, 123]],
                   [['1/Z', 'INV-1', '2026-08-30', '2026-09-30', 'Figma Inc. (00004)', 40],
                    ['2/Z', '5550001', '2026-08-31', '2026-09-30', 'Google Ireland Ltd. (00005)', 98]])
    p = dane / 'Budget Studio' / 'budget_studio_2026-10-13.csv'
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=BS_NAGLOWEK, delimiter='\t')
        w.writeheader()
        w.writerows([
            bs_wiersz('1', '1', 'FV2026/09/1', 'XY', '1230,00', '2026-09-15', 'Obsługa stała Klient Alfa', 'Klient Alfa'),
            bs_wiersz('2', '-1', 'FV 1/09/2026', 'Drukarnia Testowa', '-1230,00', '2026-09-05', 'Obsługa stała Klient Alfa', 'Klient Alfa'),
            bs_wiersz('3', '-1', '', 'Figma', '-41,00', '2026-08-29', 'Subskrypcje i narzędzia', 'DigitalH'),
            bs_wiersz('4', '-1', '', 'Inny Dostawca', '-615,00', '2026-09-04', 'Pracownicy i podwykonawcy', 'DigitalH'),
        ])


def wyd(con, ref):
    return con.execute('SELECT w.* FROM wydatki w JOIN operacje o ON o.id = w.operacja_id WHERE o.nr_ref = ?', (ref,)).fetchone()


def klucz(con, ref):
    return con.execute('SELECT klucz FROM operacje WHERE nr_ref = ?', (ref,)).fetchone()[0]


class TestNazwy(unittest.TestCase):
    def test_klucz_kontrahenta(self):
        self.assertEqual(klucz_kontrahenta('GOOGLE *ADS6485927858 DUBLIN'), 'ads google')
        self.assertEqual(klucz_kontrahenta('HEROLD MATEUSZ UL. BEATY'), klucz_kontrahenta('Mateusz Herold'))
        self.assertEqual(klucz_kontrahenta('Drukomat.pl Pila 64-920 616'), 'drukomat pila')

    def test_krotka_nazwa(self):
        self.assertEqual(krotka_nazwa('"OMEGA" SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ'), 'Omega')
        self.assertEqual(krotka_nazwa('Testowa Medica Prosta Spółka Akcyjna'), 'Testowa Medica')


class TestKlienci(unittest.TestCase):
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

    def klient_fv(self, numer):
        return tuple(self.con.execute('SELECT klient, zrodlo FROM faktury_klient WHERE numer = ?', (numer,)).fetchone())

    def test_bez_bledow(self):
        self.assertEqual([b for b in self.raport['bledy'] if 'wyniki' not in b], [])

    def test_klient_faktury(self):
        self.assertEqual(self.klient_fv('FV2026/09/1'), ('Klient Alfa', 'Budget Studio'))
        self.assertEqual(self.klient_fv('FV2026/09/2'), ('Klient Alfa', 'ten sam nabywca'))
        self.assertEqual(self.klient_fv('FV2026/09/3'), ('Omega', 'nazwa nabywcy'))

    def test_reguly_wbudowane(self):
        self.assertEqual(wyd(self.con, 'T1')['rodzaj'], 'vat')
        self.assertEqual(wyd(self.con, 'T2')['rodzaj'], 'praca')
        self.assertEqual(wyd(self.con, 'P1')['rodzaj'], 'praca')
        self.assertEqual(wyd(self.con, 'B1')['rodzaj'], 'staly')
        self.assertEqual(wyd(self.con, 'Z1')['rodzaj'], 'zwrot')
        self.assertEqual(wyd(self.con, 'T1')['dokument'], 'nie wymaga')

    def test_podpowiedzi_z_budget_studio_po_kwocie_i_dacie(self):
        self.assertEqual((wyd(self.con, 'K1')['rodzaj'], wyd(self.con, 'K1')['klient']), ('przenoszony', 'Klient Alfa'))
        self.assertEqual(wyd(self.con, 'C1')['rodzaj'], 'staly')
        # inna nazwa w BS, ale ta sama kwota i dzień
        self.assertEqual((wyd(self.con, 'K2')['rodzaj'], wyd(self.con, 'K2')['zrodlo']), ('praca', 'Budget Studio (ta płatność)'))
        self.assertEqual(wyd(self.con, 'N1')['rodzaj'], 'nieprzypisany')

    def test_wydatki_a_rejestr(self):
        metody = {r[0]: r[1] for r in self.con.execute(
            'SELECT o.nr_ref, d.metoda FROM wydatki_dok d JOIN operacje o ON o.id = d.operacja_id')}
        self.assertEqual(metody['K1'], 'numer KSeF (data i kwota)')
        self.assertEqual(metody['K2'], 'numer dokumentu w tytule')
        self.assertEqual(metody['C1'], 'kwota po kursie i nazwa')
        self.assertEqual((metody['G1'], metody['G2']), ('suma płatności kartą w miesiącu',) * 2)
        self.assertEqual(wyd(self.con, 'K1')['netto_dok'], 100000)
        stany = dict(self.con.execute('SELECT nr_ewid, stan FROM zakupy_stan').fetchall())
        self.assertEqual(stany['3/K'], 'bez płatności w banku')
        self.assertEqual(stany['2/Z'], 'opłacony')
        self.assertEqual(wyd(self.con, 'N1')['dokument'], 'bez dokumentu')

    def test_zwrot_nadplaty_zamyka_nadplate(self):
        # wpłaty rozliczane od najstarszej: nadpłata wychodzi na późniejszej (W1) i znika po zwrocie z 10.10
        self.assertEqual(self.con.execute('SELECT SUM(nadplata) FROM wplaty').fetchone()[0], 0)
        uwagi = [r[0] for r in self.con.execute("SELECT w.uwaga FROM wplaty w JOIN operacje o ON o.id = w.operacja_id WHERE o.nr_ref = 'W1'")]
        self.assertIn('oddana', uwagi[0])

    def test_budzet_klienta(self):
        d = {k['klient']: k for k in zapytania.klienci_lista(self.con)['klienci']}
        self.assertEqual(d['Klient Alfa']['przychod'], 150000)
        self.assertEqual(d['Klient Alfa']['koszty'], 100000)       # netto z dokumentu, nie brutto z banku
        self.assertEqual(d['Klient Alfa']['marza'], 50000)

    def test_reguly_mata_wygrywaja_i_cofniecie(self):
        zmiany.zapisz('klient_nip', {'nabywca': '222', 'klient': 'Grupa Omega'})
        w = zmiany.zapisz('koszt_regula', {'kontrahent': klucz_kontrahenta('NIEZNANY SKLEP'), 'rodzaj': 'przenoszony', 'klient': 'Klient Alfa'})
        zmiany.zapisz('koszt_operacja', {'operacja': klucz(self.con, 'K1'), 'rodzaj': 'staly', 'klient': ''})
        self.przelicz()
        self.assertEqual(self.klient_fv('FV2026/09/3'), ('Grupa Omega', 'reguła Mata'))
        self.assertEqual((wyd(self.con, 'N1')['rodzaj'], wyd(self.con, 'N1')['klient']), ('przenoszony', 'Klient Alfa'))
        self.assertEqual(wyd(self.con, 'K1')['rodzaj'], 'staly')
        self.assertEqual(len(zapytania.reguly(self.con)), 3)
        zmiany.zapisz('klient_faktura', {'faktura': 'FV2026/09/2', 'klient': 'Klient Beta'})
        self.przelicz()
        self.assertEqual(self.klient_fv('FV2026/09/2'), ('Klient Beta', 'decyzja Mata (ta faktura)'))
        self.assertEqual(self.klient_fv('FV2026/09/1'), ('Klient Alfa', 'Budget Studio'))
        zmiany.zapisz('cofnij', {'wpis': w['id']})
        self.przelicz()
        self.assertEqual(wyd(self.con, 'N1')['rodzaj'], 'nieprzypisany')

    def test_walidacja(self):
        with self.assertRaises(ValueError):
            zmiany.sprawdz('koszt_regula', {'kontrahent': 'x', 'rodzaj': 'prezent', 'klient': ''})
        with self.assertRaises(ValueError):
            zmiany.sprawdz('klient_nip', {'nabywca': '1', 'klient': ''})


if __name__ == '__main__':
    unittest.main()
