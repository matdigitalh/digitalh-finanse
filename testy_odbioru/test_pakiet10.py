"""Odbiór pakietu 10 na prawdziwych plikach (tylko odczyt, baza w katalogu tymczasowym, nic nie trafia do Dane/):
  - eksport płatności budżetu ma ten sam układ kolumn co najnowszy budget_studio_*.csv, a płatności z importu BS mają
    w eksporcie te same kwoty, daty i opisy co w pliku BS (porównanie 1:1 po ID),
  - suma eksportu = stopka listy przy tych samych filtrach,
  - każdy plik w Dane/ jest rozpoznany po zawartości jako swoje źródło, PDF dostaje ostrzeżenie,
  - ponowny import tego samego pliku ING (podgląd, bez zapisu) pokazuje „Bez zmian” = liczba wierszy,
  - w Historii importów liczniki każdego pliku sumują się do liczby jego wierszy.
Wypisuje tylko liczby zgodności, bez kwot i nazw."""
import csv
import io
import os
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from finanse import baza, budzet, eksport, konfig, odbudowa, plan, zapytania_budzet
from finanse.importy import dziennik, podsumowanie, reczny, rozpoznanie
from finanse.importy.wspolne import pliki

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
DANE = FINANSE / 'Raporty' / 'Dane'
EKSPORTY_BS = pliki(DANE, 'Budget Studio/budget_studio_*.csv') if DANE.exists() else []
PORÓWNYWANE = ['Rodzaj', 'Podstawa płatności', 'Numer wewnętrzny', 'Numer dokumentu', 'Tytuł', 'Netto (wartość)', 'Brutto (wartość)',
               'VAT', 'Miesiąc budżetowy', 'Dzień wystawienia', 'Dzień płatności', 'Dzień płatności - realny', 'Przesunięcie płatności',
               'Miesiąc księgowania', 'Metoda płatności', 'Księgowane', 'W cash flow', 'Komentarz', 'Komentarz w arkuszu', 'Arkusz',
               'Folder', 'Kategoria', 'Sekcja', 'Przedmiot transakcji', 'Data utworzenia', 'Data modyfikacji']


@unittest.skipUnless(EKSPORTY_BS, 'brak danych na tym komputerze')
class OdbiorPakiet10(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ['FINANSE_BAZA'] = str(Path(cls.tmp.name) / 'finanse.sqlite')
        os.environ.pop('FINANSE_KATALOG', None)
        odbudowa.odbuduj()
        cls.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()
        os.environ.pop('FINANSE_BAZA', None)

    def test_uklad_kolumn_jak_w_pliku_bs(self):
        with open(EKSPORTY_BS[0], encoding='utf-8-sig', newline='') as f:
            self.assertEqual(next(csv.reader(f, delimiter='\t')), eksport.KOLUMNY_BS)

    def test_platnosci_z_bs_jeden_do_jednego(self):
        uzyty = zapytania_budzet.drzewo(self.con)['import']['plik']
        with open(DANE / 'Budget Studio' / uzyty, encoding='utf-8-sig', newline='') as f:
            # VAT i podatek dochodowy z BS zastępuje arkusz systemowy Opłaty urzędowe (pakiet 8; zgodność z BS: test_pakiet8)
            bs = [x for x in csv.DictReader(f, delimiter='\t') if x['Rodzaj'] in ('1', '-1')
                  and budzet._podstawa(x['Podstawa płatności']) not in plan.PODATKI]
        _, tresc, _ = eksport.plik(self.con, 'budzet/lista', {'format': 'csv'})
        nasze = list(csv.DictReader(io.StringIO(tresc.decode('utf-8')), delimiter='\t'))
        po_id = defaultdict(list)
        for x in nasze:
            po_id[x['ID']].append(x)
        brak, zgodne, rozne = 0, 0, defaultdict(int)
        for x in bs:
            kand = po_id.get(x['ID'], [])
            if not kand:
                brak += 1
                continue
            najlepszy = max(kand, key=lambda y: sum(y[k].strip() == x[k].strip() for k in PORÓWNYWANE))
            kand.remove(najlepszy)
            roznice = [k for k in PORÓWNYWANE if najlepszy[k].strip() != x[k].strip()]
            zgodne += not roznice
            for k in roznice:
                rozne[k] += 1
        print(f'\n  eksport płatności vs plik BS: {zgodne} z {len(bs)} wierszy zgodnych we wszystkich {len(PORÓWNYWANE)} kolumnach,'
              f' brak w eksporcie: {brak}, różnice wg kolumn: {dict(rozne) or "brak"}')
        self.assertEqual(brak, 0, 'każda płatność z pliku BS jest w eksporcie')
        for k in ('Rodzaj', 'Netto (wartość)', 'Brutto (wartość)', 'VAT', 'Miesiąc budżetowy', 'Arkusz', 'Folder', 'Kategoria'):
            self.assertEqual(rozne.get(k, 0), 0, k)

    def test_suma_eksportu_jak_stopka_listy(self):
        for filtry in ({}, {'lista': 'po_terminie'}, {'lista': 'do_zaplacenia'}, {'rodzaj': '1'}):
            lista = zapytania_budzet.lista(self.con, filtry.get('lista', 'wszystkie'), filtry.get('rodzaj'))
            _, tresc, _ = eksport.plik(self.con, 'budzet/lista', {**filtry, 'format': 'csv'})
            w = list(csv.DictReader(io.StringIO(tresc.decode('utf-8')), delimiter='\t'))
            self.assertEqual(len(w), lista['razem'], filtry)
            from decimal import Decimal
            self.assertEqual(sum(int(Decimal((x['Brutto (wartość)'] or '0').replace(',', '.')) * 100) for x in w), lista['suma'], filtry)

    def test_rozpoznanie_plikow_z_dane(self):
        oczekiwane = {}
        for rodzaj, wzorzec, _, _ in odbudowa.ZRODLA:
            for p in DANE.glob(wzorzec):
                oczekiwane[p] = rodzaj
        self.assertTrue(oczekiwane)
        for p, rodzaj in oczekiwane.items():
            r = rozpoznanie.rozpoznaj(p.read_bytes(), 'dowolna nazwa')
            self.assertEqual(r['rodzaj'], rodzaj, p.name)
            if rodzaj == 'Wyniki biura':
                self.assertTrue(p.stem.endswith(r['okres']), p.name)
        for p in DANE.rglob('*.pdf'):
            self.assertIn('PDF', rozpoznanie.rozpoznaj(p.read_bytes(), p.name)['powod'])

    def test_ponowny_import_pliku_ing_bez_zmian(self):
        przed = sorted(DANE.rglob('*'))
        wpisy = len(dziennik.wczytaj())
        for p in pliki(DANE, 'ING/ing_historia_*.csv'):
            r = reczny.przyjmij(p.read_bytes(), p.name, zapisz=False)
            self.assertEqual(r['duplikat'], f'ING/{p.name}')
            self.assertEqual(r['liczniki']['bez_zmian'], r['wierszy'] - r['liczniki']['pominiete'])
            self.assertEqual((r['liczniki']['dodane'], r['liczniki']['zaktualizowane']), (0, 0))
            print(f"\n  ponowny import {p.name}: bez zmian {r['liczniki']['bez_zmian']} z {r['wierszy']} wierszy,"
                  f" pominięte {r['liczniki']['pominiete']}")
        self.assertEqual(sorted(DANE.rglob('*')), przed, 'podgląd niczego nie zapisał w Dane/')
        self.assertEqual(len(dziennik.wczytaj()), wpisy)

    def test_historia_liczniki_sumuja_sie_do_wierszy(self):
        h = podsumowanie.historia(self.con)['importy']
        self.assertTrue(h)
        for x in h:
            if x['id'].startswith('plik:'):
                self.assertEqual(x['dodane'] + x['zaktualizowane'] + x['bez_zmian'] + x['pominiete'], x['wierszy'], x['plik'])
                self.assertNotEqual(x['stan'], 'błąd odczytu', x['plik'])


if __name__ == '__main__':
    unittest.main()
