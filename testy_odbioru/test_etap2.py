"""Odbiór etapu 2 na prawdziwych plikach: dopasowanie wpłat i należności.

Wartości oczekiwane w Finanse/Aplikacja/odbior.json (klucz „etap2”), poza repo. Bez wpisów Mata
(katalog zmian podmieniony na pusty), żeby test sprawdzał sam automat.
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


def _oczekiwane():
    try:
        return json.loads(ODBIOR.read_text(encoding='utf-8')).get('etap2')
    except (OSError, ValueError):
        return None


@unittest.skipUnless(DANE.exists() and _oczekiwane(), 'brak danych albo odbior.json (etap2) na tym komputerze')
class OdbiorEtap2(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = _oczekiwane()
        cls.tmp = tempfile.TemporaryDirectory()
        # dane z prawdziwego folderu, wpisy Mata z pustego: link do Raporty w tymczasowym katalogu Finanse
        (Path(cls.tmp.name) / 'Finanse').mkdir()
        os.symlink(FINANSE / 'Raporty', Path(cls.tmp.name) / 'Finanse' / 'Raporty')
        os.environ['FINANSE_KATALOG'] = str(Path(cls.tmp.name) / 'Finanse')
        os.environ['FINANSE_BAZA'] = str(Path(cls.tmp.name) / 'finanse.sqlite')
        cls.raport = odbudowa.odbuduj()
        cls.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        if zapytania.dzien_stanu(cls.con) != cls.o['dzien_stanu']:
            cls.con.close()
            raise unittest.SkipTest('eksport ING z innego dnia niż w odbior.json')

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()
        os.environ.pop('FINANSE_BAZA', None)
        os.environ.pop('FINANSE_KATALOG', None)

    def test_bez_bledow(self):
        self.assertEqual(self.raport['bledy'], [])

    def test_soufflet_jeden_przelew_za_piec_faktur(self):
        numery = sorted(r[0] for r in self.con.execute(
            "SELECT d.numer FROM dopasowania d JOIN operacje o ON o.id = d.operacja_id"
            " WHERE o.data_ksiegowania = '2026-07-28' AND o.kwota = ?", (self.o['soufflet_wplata_2026_07_28_gr'],)))
        self.assertEqual(numery, sorted(self.o['soufflet_faktury']))

    def test_exal_zaplacone_1_wrzesnia(self):
        for n in self.o['exal_zaplacone_2026_09_01']:
            s = self.con.execute('SELECT stan, ostatnia_wplata FROM faktury_stan WHERE numer = ?', (n,)).fetchone()
            self.assertEqual(tuple(s), ('opłacona', '2026-09-01'), n)

    def test_naleznosci_po_terminie(self):
        p = zapytania.podsumowanie_naleznosci(self.con)
        self.assertEqual(p['po_terminie'], self.o['po_terminie_gr'])
        bez = self.con.execute("SELECT SUM(s.pozostalo) FROM faktury_stan s JOIN faktury f USING(numer)"
                               " WHERE s.dni_po_terminie > 0 AND s.pozostalo > 0 AND f.status != 'Opłacona'").fetchone()[0]
        self.assertEqual(bez, self.o['po_terminie_bez_odhaczonych_w_fakturowni_gr'])
        pierwszy = p['nabywcy_po_terminie'][0]
        self.assertIn(self.o['najwiekszy_dluznik'], pierwszy['nabywca'].upper())
        self.assertEqual((pierwszy['kwota'], pierwszy['faktur'], pierwszy['najstarsza']),
                         (self.o['najwiekszy_dluznik_gr'], self.o['najwiekszy_dluznik_faktur'], self.o['najwiekszy_dluznik_dni']))


if __name__ == '__main__':
    unittest.main()
