"""Odbiór pakietu 8 na prawdziwych plikach (tylko odczyt: Dane podpięte dowiązaniami, baza i pliki apki w katalogu
tymczasowym, nic nie trafia do Finanse/Aplikacja).

Sprawdza arkusz systemowy „Opłaty urzędowe” wobec eksportu Budget Studio i banku:
  - VAT: okres z planem w BS ma prognozę apki równą prognozie BS co do grosza, okres opłacony w BS ma kwotę od biura,
  - CIT: kwota od biura z BS przejęta; zgodność prognoz z BS wypisana (BS nie przelicza planu po terminie),
  - historia VAT: prognoza z budżetu kontra przelewy do urzędu z ING (wypisane liczby okresów, bez kwot).
Wartości oczekiwane biorą się z tego samego eksportu BS i wyciągów, więc żadna kwota nie jest zapisana w repo."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from finanse import baza, budzet, konfig, odbudowa, podatki

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
DANE = FINANSE / 'Raporty' / 'Dane'
EKSPORTY = sorted((DANE / 'Budget Studio').glob('budget_studio_*.csv'))


@unittest.skipUnless(EKSPORTY and (FINANSE / 'Aplikacja' / 'arkusze_bs.json').exists(), 'brak eksportu BS')
class OdbiorPodatki(unittest.TestCase):
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
        cls.w = podatki.widok(cls.con)
        cls.import_bs = budzet.wczytaj_model()

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()
        for k, v in cls.stare.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_bez_bledow_i_wiersze_podatkowe_bs_zastapione(self):
        self.assertEqual(self.raport['bledy'], [])
        self.assertTrue(self.w['horyzont'])
        n = self.con.execute("SELECT COUNT(*) FROM bud_wiersz WHERE podstawa IN ('Podatek VAT', 'Podatek dochodowy') AND arkusz NOT LIKE 'sys:%'").fetchone()[0]
        self.assertEqual(n, 0)

    def test_vat_jak_w_budget_studio(self):
        prognozy = [x for x in self.w['vat'] if x['prognoza_bs'] is not None]
        biuro = [x for x in self.w['vat'] if x['od_biura'] and x['od_biura']['zrodlo'] == 'Budget Studio']
        rozne = [x['okres'] for x in prognozy if x['plan'] != x['prognoza_bs']]
        print(f'\n  VAT: {len(prognozy) - len(rozne)} z {len(prognozy)} prognoz równych BS co do grosza, '
              f'{len(biuro)} okresów z kwotą od biura z BS')
        self.assertEqual(rozne, [])
        z = self.w['vat_zwrot']
        if z and z['prognoza_bs'] is not None:
            self.assertEqual(z['plan'], z['prognoza_bs'])

    def test_cit_kwoty_od_biura_i_prognozy(self):
        rzeczywiste = {(p['miesiac']) for p in self.import_bs['platnosci']
                       for w in self.import_bs['wiersze'] if w['id'] == p['wiersz'] and w['podstawa'] == 'Podatek dochodowy'
                       and w['rodzaj'] == -1 and p['typ'] != 'plan'}
        for x in self.w['cit']:
            if x['okres'] in rzeczywiste:
                self.assertIsNotNone(x['od_biura'], x['okres'])
        okresy = [x for x in self.w['cit'] + self.w['cit_roczny'] if x['prognoza_bs'] is not None and not x['od_biura']]
        rowne = sum(1 for x in okresy if x['plan'] == x['prognoza_bs'])
        po_terminie = sum(1 for x in okresy if x['plan'] != x['prognoza_bs'] and (x.get('termin') or '') < self.w['dzien_stanu'])
        print(f'\n  CIT ({self.w["ustawienia"]["cit_okres"]}, {self.w["ustawienia"]["cit_stawka"]}%): {rowne} z {len(okresy)} prognoz '
              f'równych BS, różne po terminie (BS ich nie przelicza): {po_terminie}')

    def test_historia_vat_kontra_bank(self):
        h = [x for x in self.w['vat'] if x['termin'] <= self.w['dzien_stanu']]
        zgodne = sum(1 for x in h if abs(x['prognoza'] - x['zaplacono']) <= 100)
        bliskie = sum(1 for x in h if 100 < abs(x['prognoza'] - x['zaplacono']) <= x['zaplacono'] * 5 // 100)
        biuro_bank = sum(1 for x in h if x['od_biura'] and abs(x['od_biura']['kwota'] - x['zaplacono']) <= 100)
        print(f'\n  VAT {len(h)} okresów z minionym terminem: prognoza z budżetu = przelew w {zgodne}, do 5% w {bliskie}, '
              f'dalej w {len(h) - zgodne - bliskie}; kwota od biura = przelew w {biuro_bank}')
        self.assertTrue(all(x['zaplacono'] > 0 for x in h if x['plan'] > 0), [x['okres'] for x in h if not x['zaplacono']])


if __name__ == '__main__':
    unittest.main()
