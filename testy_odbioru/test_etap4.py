"""Odbiór etapu 4 na prawdziwych plikach: wynik zarządczy kontra księgi biura, VAT.
Wartości oczekiwane w Finanse/Aplikacja/odbior.json (klucz „etap4”), poza repo; bez wpisów Mata."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from finanse import baza, konfig, odbudowa, wynik, zapytania

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
ODBIOR = FINANSE / 'Aplikacja' / 'odbior.json'


def _oczekiwane():
    try:
        return json.loads(ODBIOR.read_text(encoding='utf-8')).get('etap4')
    except (OSError, ValueError):
        return None


@unittest.skipUnless((FINANSE / 'Raporty' / 'Dane').exists() and _oczekiwane(), 'brak danych albo odbior.json (etap4)')
class OdbiorEtap4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = _oczekiwane()
        cls.tmp = tempfile.TemporaryDirectory()
        (Path(cls.tmp.name) / 'Finanse').mkdir()
        os.symlink(FINANSE / 'Raporty', Path(cls.tmp.name) / 'Finanse' / 'Raporty')
        os.environ['FINANSE_KATALOG'] = str(Path(cls.tmp.name) / 'Finanse')
        os.environ['FINANSE_BAZA'] = str(Path(cls.tmp.name) / 'finanse.sqlite')
        odbudowa.odbuduj()
        cls.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        if zapytania.dzien_stanu(cls.con) != cls.o['dzien_stanu']:
            cls.con.close()
            raise unittest.SkipTest('eksport ING z innego dnia niż w odbior.json')
        cls.w = wynik.wynik_zarzadczy(cls.con, '2026')

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()
        os.environ.pop('FINANSE_BAZA', None)
        os.environ.pop('FINANSE_KATALOG', None)

    def test_obrot_zgodny_z_ksiegami_co_do_grosza(self):
        b = self.w['porownanie_z_biurem']
        self.assertEqual(b['okres'], self.o['okres_biura'])
        self.assertEqual(b['aplikacja_obrot'], b['biuro']['A'])
        self.assertEqual(b['biuro']['A'], self.o['obrot_h1_gr'])

    def test_wynik_bez_zmian_wobec_odbioru(self):
        self.assertEqual(self.w['porownanie_z_biurem']['aplikacja_wynik'], self.o['wynik_h1_gr'])

    def test_vat_maj_czerwiec(self):
        v = {m['miesiac']: m for m in wynik.vat(self.con, '2026')['miesiace']}
        self.assertEqual((v['2026-05']['zaplacony'], v['2026-06']['zaplacony']),
                         (self.o['vat_zaplacony_maj_gr'], self.o['vat_zaplacony_czerwiec_gr']))


if __name__ == '__main__':
    unittest.main()
