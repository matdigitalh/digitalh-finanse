"""Odbiór etapu 1 na prawdziwych plikach z Finanse/Raporty/Dane.

Wartości oczekiwane czyta z Finanse/Aplikacja/odbior.json (poza repo, żeby kwoty nie trafiły na GitHub).

Czyta prawdziwe dane tylko do odczytu, bazę buduje w katalogu tymczasowym. Niczego nie zapisuje w repo
i nie wypisuje danych poza wynikiem asercji. Uruchamiać lokalnie: python -m unittest testy_odbioru.test_etap1
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from finanse import baza, konfig, odbudowa, zapytania

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
DANE = FINANSE / 'Raporty' / 'Dane'
ODBIOR = FINANSE / 'Aplikacja' / 'odbior.json'


@unittest.skipUnless(DANE.exists() and ODBIOR.exists(), 'brak danych albo odbior.json na tym komputerze')
class OdbiorEtap1(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['FINANSE_BAZA'] = str(Path(cls.tmp.name) / 'finanse.sqlite')
        os.environ.pop('FINANSE_KATALOG', None)
        cls.oczekiwane = json.loads(ODBIOR.read_text(encoding='utf-8'))
        cls.raport = odbudowa.odbuduj()
        cls.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()
        os.environ.pop('FINANSE_BAZA', None)

    def test_bez_bledow_importu(self):
        self.assertEqual(self.raport['bledy'], [])

    def test_saldo(self):
        s = zapytania.salda(self.con)
        o = self.oczekiwane
        if s['główny']['data_ksiegowania'] != o['saldo_data']:
            self.skipTest('eksport ING z innego dnia niż w odbior.json')
        self.assertEqual(round((s['główny']['saldo_po'] + s['online']['saldo_po']) / 100), o['saldo_glowne_online_zl'])
        self.assertEqual(round(s['VAT']['saldo_po'] / 100), o['saldo_vat_zl'])

    def test_rzis_przychod_i_polrocze(self):
        a = self.con.execute("SELECT wartosc FROM wyniki_biura WHERE okres='2026-06' AND kod='A'").fetchone()
        self.assertEqual(a[0], self.oczekiwane['rzis_2026_06_przychod_gr'])

    def test_dwukrotna_odbudowa_nie_zmienia_liczb(self):
        def liczby():
            con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
            try:
                return [tuple(con.execute(f'SELECT COUNT(*), {s} FROM {t}').fetchone())
                        for t, s in (('operacje', 'SUM(kwota)'), ('faktury', 'SUM(brutto)'), ('zakupy', 'SUM(netto)'),
                                     ('wyniki_biura', 'SUM(wartosc)'))]
            finally:
                con.close()
        przed = liczby()
        odbudowa.odbuduj()
        self.assertEqual(liczby(), przed)

    def test_suma_pozycji_rowna_netto_faktury(self):
        rozjazd = self.con.execute('SELECT COUNT(*) FROM faktury f WHERE netto != (SELECT COALESCE(SUM(netto),0)'
                                   ' FROM faktury_pozycje p WHERE p.numer=f.numer)').fetchone()[0]
        self.assertEqual(rozjazd, 0)


if __name__ == '__main__':
    unittest.main()
