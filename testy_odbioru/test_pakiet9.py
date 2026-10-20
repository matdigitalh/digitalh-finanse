"""Odbiór pakietu 9 na prawdziwych plikach (tylko odczyt: Dane podpięte dowiązaniami, baza i pliki apki w katalogu
tymczasowym, nic nie trafia do Finanse/Aplikacja).

Cash flow w trybie domyślnym (jak w BS) kontra eksport Budget Studio: płatności nieopłacone z „W cash flow = tak”, wg miesiąca
dnia realnej płatności, od dnia stanu. Każda różnica w miesiącu musi mieć przyczynę płatność po płatności:
  - opłacona w banku, w BS nadal nieopłacona (apka liczy opłacenie z banku, decyzja 3),
  - w BS opłacona, w banku do dnia stanu przelewu nie ma (eksport BS bywa nowszy niż wyciąg ING),
  - danina z arkusza systemowego Opłaty urzędowe inna niż plan VAT lub CIT w BS (pakiet 8),
  - pozycja z umowy (dodatek apki, decyzja 9).
Wypisuje liczbę miesięcy zgodnych i przyczyny z liczbą płatności, bez kwot. Wartości oczekiwane biorą się z tego samego
eksportu BS, więc żadna kwota nie jest zapisana w repo."""
import csv
import os
import shutil
import tempfile
import unittest
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from finanse import baza, cashflow, konfig, odbudowa

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
DANE = FINANSE / 'Raporty' / 'Dane'
EKSPORTY = sorted((DANE / 'Budget Studio').glob('budget_studio_*.csv'))
PODATKI = ('Podatek VAT', 'Podatek dochodowy')


def _gr(s: str) -> int:
    return int((Decimal((s or '0').replace(' ', '').replace(',', '.')) * 100).quantize(Decimal(1)))


def _skladowa(podstawa: str, skladowa=None) -> str:
    """Umowa ma w BS jedno ID na trzy wiersze (dla osoby, PIT, ZUS): płatność rozpoznajemy po ID i składowej."""
    if skladowa:
        return skladowa
    p = podstawa or ''
    return 'us' if p.endswith('- PIT') else 'zus' if p.endswith('- ZUS') else 'osoba' if ' - dla ' in p else ''


@unittest.skipUnless(EKSPORTY and (FINANSE / 'Aplikacja' / 'arkusze_bs.json').exists(), 'brak eksportu BS')
class OdbiorCashflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        fin = Path(cls.tmp.name) / 'Finanse'
        (fin / 'Raporty' / 'Dane').mkdir(parents=True)
        for p in DANE.iterdir():
            if p.is_dir():
                os.symlink(p, fin / 'Raporty' / 'Dane' / p.name)
        (fin / 'Aplikacja').mkdir()
        for n in ('arkusze_bs.json', 'ustawienia.json'):
            if (FINANSE / 'Aplikacja' / n).exists():
                shutil.copy(FINANSE / 'Aplikacja' / n, fin / 'Aplikacja' / n)
        cls.stare = {k: os.environ.get(k) for k in ('FINANSE_KATALOG', 'FINANSE_BAZA')}
        os.environ['FINANSE_KATALOG'] = str(fin)
        os.environ['FINANSE_BAZA'] = str(Path(cls.tmp.name) / 'finanse.sqlite')
        cls.raport = odbudowa.odbuduj()
        cls.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        cls.stan = cls.con.execute("SELECT wartosc FROM meta WHERE klucz = 'dzien_stanu'").fetchone()[0]

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()
        for k, v in cls.stare.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def eksport_bs(self) -> dict:
        """(ID płatności BS, składowa umowy) → (brutto, dzień realny, podstawa, etap), wiersze z „W cash flow = tak”."""
        wynik = {}
        with open(EKSPORTY[-1], encoding='utf-8') as f:
            for x in csv.DictReader(f, delimiter='\t'):
                if x['Rodzaj'] not in ('1', '-1') or x['W cash flow'] != 'Tak':
                    continue
                klucz = (x['ID'], _skladowa(x['Podstawa płatności'].strip()))
                stare = wynik.get(klucz)
                wynik[klucz] = ((stare[0] if stare else 0) + _gr(x['Brutto (wartość)']), x['Dzień płatności - realny'] or x['Dzień płatności'],
                                x['Podstawa płatności'].strip(), x['Etap płatności'])
        return wynik

    def test_tryb_domyslny_zgodny_z_cash_flow_bs(self):
        stan = self.stan
        bs = self.eksport_bs()
        koniec = max(v[1] for v in bs.values())
        d = cashflow.okresy(self.con, 'miesiac', od=stan, do=max(koniec, stan))   # tryb domyślny, bez żadnych filtrów
        self.assertEqual(d['parametry']['pochodzenie'], list(cashflow.POCHODZENIE_DOMYSLNE))
        nasze = [z for z in d['pozycje'] if z['typ'] != 'bank' and z['data'] >= stan]
        # BS: nieopłacone z dniem realnym od dnia stanu
        bs_m, bs_dan = defaultdict(int), defaultdict(int)
        for k, r, pod, etap in bs.values():
            if etap != 'Opłacona' and r >= stan:
                (bs_dan if pod in PODATKI else bs_m)[r[:7]] += k
        my_m, my_dan, z_umow = defaultdict(int), defaultdict(int), defaultdict(int)
        for z in nasze:
            (z_umow if z['typ'] == 'umowa' else my_dan if z['danina'] else my_m)[z['data'][:7]] += z['kwota']
        # płatność po płatności (ID z BS): nasz etap i dzień, także dla płatności, które apka ma za opłacone
        wszystkie = {z['id']: z for z in cashflow._budzet(self.con, stan)}
        po_bs = defaultdict(list)
        for r in self.con.execute("SELECT id, bs_id FROM bud_platnosc WHERE bs_id IS NOT NULL AND bs_id != ''"):
            if r['id'] in wszystkie:
                z = wszystkie[r['id']]
                po_bs[(r['bs_id'], _skladowa(z['podstawa_platnosci'], z['skladowa']))].append(r['id'])
        przyczyny, niewyjasnione = defaultdict(int), []
        wyjasnione_m = defaultdict(int)
        for bid, (k, r, pod, etap) in bs.items():
            if pod in PODATKI:
                continue
            moje = [wszystkie[i] for i in po_bs.get(bid, [])]
            nasza = sum(z['kwota'] for z in moje if z['etap_cf'] != 'Opłacona' and z['data'].isoformat() >= stan)
            jej = k if etap != 'Opłacona' and r >= stan else 0
            if nasza == jej:
                continue
            if jej and moje and all(z['etap_cf'] == 'Opłacona' for z in moje):
                przyczyny['opłacona w banku, w BS nadal nieopłacona'] += 1
                wyjasnione_m[r[:7]] -= jej
            elif not jej and etap == 'Opłacona' and moje and all(z['etap_cf'] != 'Opłacona' for z in moje):
                przyczyny['w BS opłacona, w banku do dnia stanu przelewu nie ma'] += 1
                for z in moje:
                    if z['data'].isoformat() >= stan:
                        wyjasnione_m[z['data'].isoformat()[:7]] += z['kwota']
            else:
                niewyjasnione.append((bid, pod, etap))
        for m in set(bs_dan) | set(my_dan):
            if bs_dan[m] != my_dan[m]:
                przyczyny['danina z arkusza systemowego inna niż plan w BS'] += 1
        for m in z_umow:
            przyczyny['pozycje z umów (dodatek apki)'] += 1
        miesiace = sorted(set(bs_m) | set(my_m) | set(bs_dan) | set(my_dan) | set(z_umow))
        zgodne = [m for m in miesiace if bs_m[m] + bs_dan[m] == my_m[m] + my_dan[m] + z_umow[m]]
        print(f"\n  cash flow od {stan}, tryb domyślny: {len(zgodne)} z {len(miesiace)} miesięcy zgodnych z BS co do grosza")
        for p, n in sorted(przyczyny.items()):
            print(f'  różnica: {p}: {n}')
        self.assertEqual(niewyjasnione, [], 'płatności z różnicą bez przyczyny')
        for m in miesiace:   # różnica w miesiącu = suma wyjaśnionych różnic płatności (daniny i umowy osobno)
            self.assertEqual(my_m[m] - bs_m[m], wyjasnione_m[m], m)

    def test_bez_szacunku_i_bez_naleznosci_spoza_budzetu(self):
        d = cashflow.okresy(self.con, 'miesiac', d_realny='ruchomy:miesiac:12:0')
        self.assertFalse({'szacunek', 'faktura'} & {z['typ'] for z in d['pozycje']})
        z = cashflow.okresy(self.con, 'miesiac', d_realny='ruchomy:miesiac:12:0', pochodzenie='plan|rzeczywista|umowa|bank|szacunek')
        self.assertGreaterEqual(len(z['pozycje']), len(d['pozycje']))

    def test_lista_rowna_wykresowi(self):
        q = {'granulacja': 'tydzien', 'd_realny': 'ruchomy:dzien:91:0', 'wszystkie': '1'}
        d = cashflow.okresy(self.con, **{k: v for k, v in q.items() if k != 'wszystkie'})
        lista = cashflow.lista(self.con, q)
        self.assertEqual(lista['razem'], len(d['pozycje']))
        self.assertEqual(lista['podsumowanie']['razem']['brutto'], sum(o['saldo'] for o in d['okresy']))


if __name__ == '__main__':
    unittest.main()
