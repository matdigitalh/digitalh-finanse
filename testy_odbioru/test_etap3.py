"""Odbiór etapu 3 na prawdziwych plikach: klienci faktur, rodzaje kosztów, wydatki a rejestr zakupów.
Wartości oczekiwane w Finanse/Aplikacja/odbior.json (klucz „etap3”), poza repo; bez wpisów Mata."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from finanse import baza, konfig, odbudowa, zapytania

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
ODBIOR = FINANSE / 'Aplikacja' / 'odbior.json'


def _oczekiwane():
    try:
        return json.loads(ODBIOR.read_text(encoding='utf-8')).get('etap3')
    except (OSError, ValueError):
        return None


@unittest.skipUnless((FINANSE / 'Raporty' / 'Dane').exists() and _oczekiwane(), 'brak danych albo odbior.json (etap3)')
class OdbiorEtap3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = _oczekiwane()
        cls.tmp = tempfile.TemporaryDirectory()
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

    def test_faktura_biura_zaplacona_po_ksef(self):
        r = self.con.execute("SELECT o.data_ksiegowania FROM zakupy z JOIN zakupy_stan s USING(nr_ewid) JOIN operacje o"
                             " ON o.id = s.operacja_id WHERE z.podmiot LIKE '%BRIXEN%' AND z.nr_dok = ?", (self.o['brixen_dok'],)).fetchone()
        self.assertEqual(r[0], self.o['brixen_zaplacony'])

    def test_nabywca_platacy_za_dwoch_klientow(self):
        r = dict(self.con.execute("SELECT fk.klient, COUNT(*) FROM faktury f JOIN faktury_klient fk USING(numer)"
                                  " WHERE f.nabywca LIKE 'NG %' GROUP BY 1").fetchall())
        self.assertEqual(r, self.o['ng_klienci'])

    def test_zwrot_nadplaty_nie_jest_kosztem(self):
        r = self.con.execute("SELECT w.rodzaj FROM wydatki w JOIN operacje o ON o.id = w.operacja_id"
                             " WHERE o.kwota = ? AND o.tytul LIKE 'Zwrot nadp%'", (-self.o['ropa_zwrot_gr'],)).fetchone()
        self.assertEqual(r[0], 'zwrot')

    def test_dokumenty_znalezione_w_banku(self):
        n = self.con.execute("SELECT COUNT(*) FROM zakupy_stan WHERE stan = 'opłacony'").fetchone()[0]
        self.assertGreaterEqual(n, self.o['dokumentow_min_oplaconych'])


if __name__ == '__main__':
    unittest.main()
