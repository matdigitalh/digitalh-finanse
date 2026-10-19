"""Odbiór pakietu 7 na prawdziwych plikach: każda lista sortuje się po każdej kolumnie z białej listy (po stronie serwera)
bez błędu i w dobrej kolejności, podsumowanie wszystkich wyników zgadza się z sumą wierszy, liczniki widoków startowych
w menu są równe kaflom pulpitu. Baza w katalogu tymczasowym, nic nie trafia do repo ani do pliku zmian."""
import os
import tempfile
import unittest
from pathlib import Path

from finanse import baza, filtry, konfig, odbudowa, zapytania, zapytania_budzet, zapytania_listy

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
DANE = FINANSE / 'Raporty' / 'Dane'


@unittest.skipUnless(DANE.exists(), 'brak danych na tym komputerze')
class OdbiorPakiet7(unittest.TestCase):
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

    def test_sortowanie_kazdej_listy_po_kazdej_kolumnie(self):
        listy = {'platnosci': zapytania_listy.KOL_PLATNOSCI, 'bank': zapytania.KOL_OPERACJI, 'faktury': zapytania.KOL_FAKTUR,
                 'naleznosci': zapytania.KOL_NALEZNOSCI, 'zakupy': zapytania.KOL_ZAKUPOW, 'wplaty': zapytania.KOL_WPLAT,
                 'wydatki': zapytania.KOL_WYDATKOW}
        liczbowe = {'platnosci': {'netto': lambda x: x['netto'] * x['rodzaj'], 'realny': lambda x: x['realny_ef']},
                    'bank': {'kwota': lambda x: x['kwota'], 'data_ksiegowania': lambda x: x['data_ksiegowania']},
                    'faktury': {'brutto': lambda x: x['brutto'], 'termin': lambda x: x['termin']},
                    'zakupy': {'netto': lambda x: x['netto'], 'data': lambda x: x['data']},
                    'wydatki': {'kwota': lambda x: x['kwota']}}
        for ekran, kolumny in listy.items():
            for klucz in kolumny:
                for kier in ('rosnaco', 'malejaco'):
                    w = zapytania_listy.lista(self.con, ekran, {'sortuj': klucz, 'kolejnosc': kier, 'ile': '500'})
                    f = liczbowe.get(ekran, {}).get(klucz)
                    if f:
                        wart = [f(x) for x in w['wiersze'] if f(x) not in (None, '')]
                        self.assertEqual(wart, sorted(wart, reverse=kier == 'malejaco'), (ekran, klucz, kier))

    def test_podsumowanie_rowne_sumie_wierszy(self):
        w = zapytania_listy.lista(self.con, 'platnosci', {'wszystkie': '1'})
        s = filtry.podsumuj([{'rodzaj': x['rodzaj'], 'netto': x['netto'] * x['rodzaj'], 'vat': (x['vat'] or 0) * x['rodzaj'],
                              'brutto': x['brutto'] * x['rodzaj']} for x in w['wiersze']])
        self.assertEqual(len(w['wiersze']), w['razem'])
        self.assertEqual(w['podsumowanie']['razem'], s['razem'])
        self.assertEqual(w['podsumowanie']['wplywy']['ile'], s['wplywy']['ile'])

    def test_liczniki_menu_rowne_kaflom(self):
        kafle = zapytania_budzet.kafle(self.con)['listy']
        menu = {x['id']: x['ile'] for x in zapytania_listy.menu(self.con)['ekrany']['platnosci']}
        zmienione = {v['id'] for v in zapytania_listy.widoki(self.con, 'platnosci') if v['zmieniony']}   # widok zmieniony przez Mata liczy co innego
        for nazwa, k in kafle.items():
            if nazwa in menu and nazwa not in zmienione:
                self.assertEqual(menu[nazwa], k['wplywy']['ile'] + k['obciazenia']['ile'], nazwa)
