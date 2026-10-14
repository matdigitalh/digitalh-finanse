"""Odbiór budżetu na prawdziwym eksporcie BS: struktura, liczba płatności, salda arkuszy równe saldom w BS (zwiad),
płatność opłacona z banku. Wartości w Finanse/Aplikacja/odbior.json (klucz „budzet”), poza repo."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from finanse import baza, konfig, odbudowa, zapytania_budzet

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
ODBIOR = FINANSE / 'Aplikacja' / 'odbior.json'


def _o():
    try:
        return json.loads(ODBIOR.read_text(encoding='utf-8')).get('budzet')
    except (OSError, ValueError):
        return None


@unittest.skipUnless(_o() and (FINANSE / 'Raporty' / 'Dane' / 'Budget Studio' / (_o() or {}).get('eksport_bs', '-')).exists(),
                     'brak eksportu BS albo odbior.json (budzet)')
class OdbiorBudzet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = _o()
        cls.tmp = tempfile.TemporaryDirectory()
        fin = Path(cls.tmp.name) / 'Finanse'
        (fin / 'Raporty' / 'Dane').mkdir(parents=True)
        for p in (FINANSE / 'Raporty' / 'Dane').iterdir():
            if p.is_dir() and p.name != 'Budget Studio':
                os.symlink(p, fin / 'Raporty' / 'Dane' / p.name)
        (fin / 'Raporty' / 'Dane' / 'Budget Studio').mkdir()
        os.symlink(FINANSE / 'Raporty' / 'Dane' / 'Budget Studio' / cls.o['eksport_bs'], fin / 'Raporty' / 'Dane' / 'Budget Studio' / cls.o['eksport_bs'])
        (fin / 'Aplikacja').mkdir()
        shutil.copy(FINANSE / 'Aplikacja' / 'arkusze_bs.json', fin / 'Aplikacja' / 'arkusze_bs.json')
        os.environ['FINANSE_KATALOG'] = str(fin)
        os.environ['FINANSE_BAZA'] = str(Path(cls.tmp.name) / 'finanse.sqlite')
        cls.raport = odbudowa.odbuduj()
        cls.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()
        os.environ.pop('FINANSE_BAZA', None)
        os.environ.pop('FINANSE_KATALOG', None)

    def test_bez_bledow_i_komplet(self):
        self.assertEqual(self.raport['bledy'], [])
        self.assertEqual((self.raport['budzet']['arkuszy'], self.raport['budzet']['platnosci']), (self.o['arkuszy'], self.o['platnosci']))

    def test_salda_jak_w_budget_studio(self):
        salda = {a['nazwa']: a['saldo'] for f in zapytania_budzet.drzewo(self.con)['foldery'] for ark in f['kategorie'].values() for a in ark}
        for nazwa, saldo in self.o['salda_arkuszy_bs_gr'].items():
            self.assertEqual(salda[nazwa], saldo, nazwa)

    def test_oplacona_z_banku(self):
        r = self.con.execute("SELECT s.etap FROM bud_powiazanie b JOIN bud_stan s ON s.platnosc = b.platnosc WHERE b.ref = ?",
                             (self.o['oplacona_z_banku']['faktura'],)).fetchone()
        self.assertEqual(r[0], 'Opłacona')

    def test_aktywne_faktury_zgodne_z_planem(self):
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM bud_rozjazd WHERE rodzaj = 'Kwota w BS inna niż na fakturze'").fetchone()[0], 0)
