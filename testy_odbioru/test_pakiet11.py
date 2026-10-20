"""Odbiór pakietu 11 na prawdziwych plikach (tylko odczyt: Dane podpięte dowiązaniami, baza i pliki apki w katalogu
tymczasowym, nic nie trafia do Finanse/Aplikacja).

Sprawdza:
  - rentowność budżetu: wynik każdego folderu = suma jego arkuszy w każdym miesiącu, razem = suma folderów, a razem
    budżetu = niezależna suma z bazy (płatności z Księgowane, aktualne, bez arkusza systemowego),
  - ostrzeżenia ustawień wierszy: liczą się bez błędu, każde wskazuje istniejący wiersz, worek z jedną płatnością
    miesięcznie sprawdzony wprost w bazie,
  - karta klienta: otwiera się dla każdego klienta, wynik budżetu klienta = wiersz jego folderu w tabeli przestawnej,
  - alerty: bez umów w rejestrze każdy folder klienta z planami wpływów od bieżącego miesiąca ma alert „brak umowy”,
  - licznik planów nieaktualnych na pulpicie = lista planów z tym filtrem.
Wypisuje tylko liczby pozycji, bez kwot."""
import os
import shutil
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from finanse import baza, ekrany, karta_klienta, konfig, odbudowa, ostrzezenia_wierszy, przestawna, zapytania_listy

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
DANE = FINANSE / 'Raporty' / 'Dane'
EKSPORTY = sorted((DANE / 'Budget Studio').glob('budget_studio_*.csv'))


@unittest.skipUnless(EKSPORTY and (FINANSE / 'Aplikacja' / 'arkusze_bs.json').exists(), 'brak eksportu BS')
class OdbiorPakiet11(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        fin = Path(cls.tmp.name) / 'Finanse'
        (fin / 'Raporty' / 'Dane').mkdir(parents=True)
        for p in DANE.iterdir():
            if p.is_dir():
                os.symlink(p, fin / 'Raporty' / 'Dane' / p.name)
        (fin / 'Aplikacja').mkdir()
        shutil.copy(FINANSE / 'Aplikacja' / 'arkusze_bs.json', fin / 'Aplikacja' / 'arkusze_bs.json')
        cls.stare = {k: os.environ.get(k) for k in ('FINANSE_KATALOG', 'FINANSE_BAZA')}
        os.environ['FINANSE_KATALOG'] = str(fin)
        os.environ['FINANSE_BAZA'] = str(Path(cls.tmp.name) / 'finanse.sqlite')
        cls.raport = odbudowa.odbuduj()
        cls.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        cls.dzis = cls.con.execute("SELECT wartosc FROM meta WHERE klucz = 'dzien_stanu'").fetchone()[0]
        cls.rok = cls.dzis[:4]

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()
        for k, v in cls.stare.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_rentownosc_folder_to_suma_arkuszy(self):
        d = przestawna.policz(self.con, self.rok, ['folder', 'kategoria', 'arkusz'])
        for f in d['wiersze']:
            arkusze = [a for k in f['dzieci'] for a in k['dzieci']]
            self.assertEqual(f['wynik'], sum(a['wynik'] for a in arkusze), f['nazwa'])
            for m in d['miesiace']:
                self.assertEqual((f['miesiace'].get(m) or {}).get('wynik', 0),
                                 sum((a['miesiace'].get(m) or {}).get('wynik', 0) for a in arkusze), (f['nazwa'], m))
        self.assertEqual(d['razem']['wynik'], sum(f['wynik'] for f in d['wiersze']))
        r = self.con.execute("SELECT COALESCE(SUM(CASE WHEN p.rodzaj = 1 THEN p.netto END), 0), COALESCE(SUM(CASE WHEN p.rodzaj = -1 THEN p.netto END), 0)"
                             ' FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz'
                             " WHERE p.aktualna = 1 AND COALESCE(p.ksiegowane, 1) = 1 AND COALESCE(a.zrodlo, '') != 'system'"
                             ' AND substr(p.miesiac, 1, 4) = ?', (self.rok,)).fetchone()
        self.assertEqual((d['razem']['wplywy'], d['razem']['obciazenia']), tuple(r))
        print(f"\n  rentowność {self.rok}: {len(d['wiersze'])} folderów, {sum(len(k['dzieci']) for f in d['wiersze'] for k in f['dzieci'])} arkuszy, "
              'wynik folderu = suma arkuszy w każdym miesiącu')

    def test_ostrzezenia_wierszy(self):
        o = ostrzezenia_wierszy.policz(self.con)
        wiersze = {r[0] for r in self.con.execute('SELECT id FROM bud_wiersz')}
        self.assertTrue(all(x['wiersz'] in wiersze for x in o['ostrzezenia']))
        for x in (x for x in o['ostrzezenia'] if x['rodzaj'] == 'worek_stala'):
            ile = Counter(r[0] for r in self.con.execute(
                "SELECT miesiac FROM bud_platnosc WHERE wiersz = ? AND typ != 'plan' AND aktualna = 1", (x['wiersz'],)))
            self.assertGreaterEqual(len(ile), 3)
            self.assertEqual(max(ile.values()), 1)
        print(f"\n  ostrzeżenia ustawień wierszy: {o['ile']} w {o['wierszy']} wierszach, {dict(Counter(x['rodzaj'] for x in o['ostrzezenia']))}")

    def test_karta_kazdego_klienta_i_alerty(self):
        l = karta_klienta.lista(self.con)
        p = przestawna.policz(self.con, self.rok, ['folder'])
        po_folderze = {f['nazwa']: f for f in p['wiersze']}
        for x in l['klienci']:
            k = karta_klienta.karta(self.con, x['klient'], None)
            if k['folder'] and k['folder'] in po_folderze:
                self.assertEqual(k['budzet']['wynik'], po_folderze[k['folder']]['wynik'], x['klient'])
        umow = self.con.execute('SELECT COUNT(*) FROM umowy').fetchone()[0]
        alerty = karta_klienta.alerty(self.con, l['klienci'])
        if not umow:   # rejestr umów pusty: każdy folder klienta z planami wpływów ma alert „brak umowy”
            plany = defaultdict(int)
            for r in self.con.execute("SELECT a.folder, SUM(p.netto) FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz"
                                      " JOIN bud_arkusz a ON a.id = w.arkusz WHERE p.typ = 'plan' AND p.rodzaj = 1 AND p.aktualna = 1"
                                      " AND p.netto > 0 AND p.miesiac BETWEEN ? AND ? AND COALESCE(a.zrodlo, '') != 'system'"
                                      " AND COALESCE(p.decyzja, '') != 'anulowane' GROUP BY a.folder",
                                      (self.dzis[:7], karta_klienta._miesiac_plus(self.dzis[:7], 11))):
                plany[r[0]] += r[1]
            oczekiwane = {karta_klienta._klucz(f) for f, kw in plany.items() if kw} - karta_klienta._foldery_bez_umowy()
            self.assertEqual({karta_klienta._klucz(a['klient']) for a in alerty if a['rodzaj'] == 'brak umowy'}, oczekiwane)
        print(f"\n  klienci: {len(l['klienci'])} kart otwartych, stany {l['liczniki']}, alertów umów: {len(alerty)}")

    def test_licznik_planow_nieaktualnych(self):
        n = ekrany.nieaktualne_plany(self.con)
        lista = zapytania_listy.lista(self.con, 'platnosci', {'typ': 'plan', 'aktualnosc': 'Nieaktualna', 'ile': '1'})
        self.assertEqual(n['ile'], lista['razem'])
        print(f"\n  plany nieaktualne: {n['ile']} (pulpit = lista)")


if __name__ == '__main__':
    unittest.main()
