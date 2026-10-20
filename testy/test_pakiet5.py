"""Pakiet 5 (rzeczywiste vs planowane i łączenie) na zmyślonych danych: rzeczywista zastępuje plan w komórce (różnica
kwot, kontrahent i komentarz z dokumentu, blokada podstawy, odłączenie przywraca plan), podział jednej faktury na dwa
arkusze, worek przyjmuje wiele rzeczywistych (150 → 163), blokady BS (inny rodzaj, pusta komórka, Do rozliczenia ≠ 0,
dokument już w budżecie), podpowiedź planu z pewnością i jeden plan na podpowiedź, zamiana planu na rzeczywistą,
płatność dodana ręcznie z walidacjami BS, etap „Niewymagana” ≠ opłacona, lista płac i ostrzeżenia kosztu pracy."""
import csv
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from finanse import baza, budzet, cashflow, konfig, laczenie, odbudowa, serwer, zapytania, zapytania_budzet, zmiany
from testy.pomoc import Srodowisko, faktura, operacja, zapisz_fakturownie, zapisz_ing
from testy.test_budzet import KOLUMNY, bs, dane

DZIS = '2026-10-13'


def dane5(srod):
    """Dane z test_budzet plus faktury z października, płatności kartą, wynagrodzenie i wiersze BS z etapem „Niewymagana”."""
    dane(srod)
    zapisz_fakturownie(srod.dane, 'fakturownia_sprzedaz_2026-10-13.csv', [
        faktura(1, 'FV2026/09/1', 'Wystawiona', '2026-09-30', '2026-10-07', 'ALFA SP. Z O.O.', '111', [('Obsługa', 1000)]),
        faktura(2, 'FV2026/08/1', 'Wystawiona', '2026-08-31', '2026-09-07', 'ALFA SP. Z O.O.', '111', [('Obsługa', 1000)]),
        faktura(3, 'FV2026/10/5', 'Wystawiona', '2026-10-05', '2026-10-19', 'ALFA SP. Z O.O.', '111', [('Obsługa październik', 4500)]),
        faktura(4, 'FV2026/10/6', 'Wystawiona', '2026-10-06', '2026-10-20', 'GAMMA S.A.', '222', [('Kampania', 8530.10)]),
        faktura(5, 'FV2026/09/7', 'Wystawiona', '2026-09-15', '2026-09-29', 'DELTA SP. Z O.O.', '333', [('Projekt', 777)]),
    ])
    zapisz_ing(srod.dane, 'ing_historia_2026-01-01_2026-10-13.csv', [
        operacja('2026-10-13', '-10,00', '50000,00', 'ING BANK', 'OPŁATA', ref='X'),
        operacja('2026-10-08', '-80,00', '50010,00', 'OPENAI SAN FRANCISCO 94158 840   2210036864', 'Płatność kartą 07.10.2026',
                 opis='Płatność kartą', ref='C1'),
        operacja('2026-10-06', '-6716,06', '50090,00', 'JÓZEFIAK PAULINA PLAC GRUNWALDZKI', 'WYNAGRODZENIE ZA 09.2026', ref='P1'),
        operacja('2026-09-25', '-600,00', '56806,06', 'URZĄD SKARBOWY', '/OKR/26M08/SFP/VAT-7', ref='V1'),
        operacja('2026-09-25', '-400,00', '57406,06', 'URZĄD SKARBOWY', '/OKR/26M08/SFP/VAT-7 dopłata', ref='V2'),
        operacja('2026-09-10', '-615,00', '57806,06', 'DRUKARNIA SP. Z O.O.', 'FS 1/09', ref='K1'),
        operacja('2026-09-05', '1230,00', '58421,06', 'ALFA SP. Z O.O.', 'FV2026/08/1', ref='W1'),
    ])
    p = srod.dane / 'Budget Studio' / 'budget_studio_2026-10-13.csv'
    with open(p, encoding='utf-8', newline='') as f:
        wiersze = list(csv.DictReader(f, delimiter='\t'))
    wiersze += [
        # wynagrodzenie z BS: ZUS za wrzesień płatny w listopadzie, w BS „Niewymagana” (rzeczywista NIEopłacona)
        bs('8', '-1', 'Niewymagana', 'Umowa o pracę - ZUS', 'Paulina', '-4279,15', '2026-09', '2026-11-15', 'Pracownicy', 'Firma', 'Koszty stałe'),
        # koszt z BS „Niewymagana” z przyszłym terminem: też nieopłacony
        bs('9', '-1', 'Niewymagana', 'Faktura ', 'Drukarnia', '-300,00', '2026-10', '2026-11-20', 'Pracownicy', 'Firma', 'Koszty stałe',
           'Druk', nr='FS 9/10', brutto='-369,00'),
        # BS „Opłacona” z minionym terminem, bez przelewu: opłacona tylko wg BS
        bs('10', '-1', 'Opłacona', 'Faktura ', 'Kurier', '-50,00', '2026-08', '2026-08-20', 'Pracownicy', 'Firma', 'Koszty stałe',
           'Kurier', nr='K 1/08', brutto='-61,50'),
        # wynagrodzenie z BS „Opłacona” z przyszłym terminem (PIT za wrzesień płatny 20.11): nie zamyka się z BS (decyzja 12)
        bs('11', '-1', 'Opłacona', 'Umowa o pracę - PIT', 'Paulina', '-780,03', '2026-09', '2026-11-20', 'Pracownicy', 'Firma', 'Koszty stałe'),
    ]
    with open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=KOLUMNY, delimiter='\t')
        w.writeheader()
        w.writerows(wiersze)


class Baza5(unittest.TestCase):
    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane5(self.srod)
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        zmiany.zapisz('ustawienie', zmiany.sprawdz('ustawienie', {'klucz': 'laczenie_od', 'wartosc': '2026-10-01'}))
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        self.bud({'op': 'seria', 'operacje': [
            {'op': 'arkusz', 'obiekt': {'id': 'a-test', 'nazwa': 'Testowy', 'folder': 'Firma', 'kategoria': 'Koszty', 'od': '2026-01', 'do': '2026-12'}},
            {'op': 'arkusz', 'obiekt': {'id': 'a-dwa', 'nazwa': 'Drugi', 'folder': 'Gamma', 'kategoria': 'Kampanie', 'od': '2026-01', 'do': '2026-12'}}]})

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def bud(self, d, przelicz=True):
        """Jak serwer: walidacja pól, odwołania i próba na modelu (z dokumentami z bazy), dopiero potem zapis."""
        czyste = zmiany.sprawdz('bud', d)
        serwer._sprawdz_odwolania(self.con, 'bud', czyste)
        w = zmiany.zapisz('bud', czyste)
        if przelicz:
            self.przelicz()
        return w

    def blad(self, d) -> str:
        with self.assertRaises(ValueError) as e:
            czyste = zmiany.sprawdz('bud', d)
            serwer._sprawdz_odwolania(self.con, 'bud', czyste)
        return str(e.exception)

    def przelicz(self):
        self.con.close()
        r = odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        return r

    def wiersz(self, wid, arkusz='a-test', **kw):
        self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'arkusz': arkusz, 'rodzaj': -1, 'podstawa': 'Faktura (jedna)', 'kontrahent': f'Firma {wid}',
                                             'stawka_vat': 23, 'dzien_wystawienia': '10.', 'dni_na_platnosc': 14, 'metoda': 'Przelew', **kw}},
                 przelicz=False)

    def komorka(self, wid, m, kwota):
        self.bud({'op': 'komorka', 'wiersz': wid, 'miesiac': m, 'kwota': kwota})

    def platnosci(self, wid, m=None):
        sql = 'SELECT p.*, s.etap FROM bud_platnosc p LEFT JOIN bud_stan s ON s.platnosc = p.id WHERE p.wiersz = ?'
        return [dict(r) for r in self.con.execute(sql + (' AND p.miesiac = ?' if m else '') + ' ORDER BY p.id', (wid, m) if m else (wid,))]

    def wartosc(self, aid, wid, m):
        w = next(x for x in zapytania_budzet.arkusz(self.con, aid)['wiersze'] if x['id'] == wid)
        return w['komorki'].get(m, {}).get('netto')

    def reczna(self, rid, netto, rodzaj=-1, podstawa='Bez faktury', **kw):
        return {'op': 'rzeczywista', 'obiekt': {'id': rid, 'rodzaj': rodzaj, 'podstawa': podstawa, 'kontrahent': 'Parking Centrum',
                                                 'wystawienie': '2026-10-05', 'netto': netto, **kw}}


class TestRzeczywistaZastepujePlan(Baza5):
    def test_faktura_4500_na_plan_4000_i_odlaczenie(self):
        """Kryterium odbioru: różnica 500 zł, komórka = 4 500, plan znika, kontrahent i komentarz z faktury, wiersz ma
        zablokowaną podstawę; odłączenie przywraca plan 4 000."""
        self.wiersz('w-alfa', rodzaj=1, kontrahent='Alfa', komentarz='Obsługa', dzien_wystawienia='5.')
        self.komorka('w-alfa', '2026-10', 400000)
        karta = laczenie.karta(self.con, 'faktura:FV2026/10/5')
        pod = next(c for c in karta['podpowiedzi'] if c['wiersz'] == 'w-alfa')
        self.assertEqual((pod['miesiac'], pod['plan'], pod['roznica']), ('2026-10', 400000, -50000))   # różnica 500 zł
        self.assertIn('kontrahent jak w wierszu', pod['uzasadnienie'])
        self.bud({'op': 'polacz', 'dokument': 'faktura:FV2026/10/5', 'czesci': [{'wiersz': 'w-alfa', 'miesiac': '2026-10', 'kwota': 450000}]})
        ps = self.platnosci('w-alfa', '2026-10')
        self.assertEqual(len(ps), 1)
        p = ps[0]
        self.assertEqual((p['typ'], p['netto'], p['vat'], p['brutto'], p['kontrahent'], p['komentarz'], p['nr_dok'], p['dokument']),
                         ('rzeczywista', 450000, 103500, 553500, 'Alfa', '', 'FV2026/10/5', 'faktura:FV2026/10/5'))
        self.assertEqual(self.wartosc('a-test', 'w-alfa', '2026-10'), 450000)
        self.assertEqual(p['etap'], 'Wystawiona')   # z Fakturowni i banku, nie z kliknięcia
        self.assertNotIn('faktura:FV2026/10/5', [r['ref'] for r in laczenie.lista(self.con, {})['wiersze']])
        self.assertIn('podstawy nie zmienisz', self.blad({'op': 'wiersz', 'obiekt': {'id': 'w-alfa', 'podstawa': 'Bez faktury'}}))
        self.assertIn('kwoty nie zmienisz', self.blad({'op': 'komorka', 'wiersz': 'w-alfa', 'miesiac': '2026-10', 'kwota': 500000}))
        # plan zrealizowany nie przyjmie kolejnej rzeczywistej
        self.assertIn('plan jest zrealizowany', self.blad({'op': 'polacz', 'dokument': 'faktura:FV2026/10/6', 'czesci': [
            {'wiersz': 'w-alfa', 'miesiac': '2026-10', 'kwota': 853010}]}))
        self.bud({'op': 'odlacz', 'dokument': 'faktura:FV2026/10/5'})
        ps = self.platnosci('w-alfa', '2026-10')
        self.assertEqual([(p['typ'], p['netto'], p['kontrahent'], p['komentarz']) for p in ps], [('plan', 400000, 'Alfa', 'Obsługa')])
        self.assertIn('faktura:FV2026/10/5', [r['ref'] for r in laczenie.lista(self.con, {})['wiersze']])

    def test_zostaw_reszte_planu(self):
        self.wiersz('w-alfa', rodzaj=1, kontrahent='Alfa')
        self.komorka('w-alfa', '2026-10', 600000)
        self.bud({'op': 'polacz', 'dokument': 'faktura:FV2026/10/5', 'reszta': 'zostaw',
                  'czesci': [{'wiersz': 'w-alfa', 'miesiac': '2026-10', 'kwota': 450000}]})
        ps = self.platnosci('w-alfa', '2026-10')
        self.assertEqual(sorted((p['typ'], p['netto']) for p in ps), [('plan', 150000), ('rzeczywista', 450000)])
        self.assertEqual(self.wartosc('a-test', 'w-alfa', '2026-10'), 600000)

    def test_podzial_faktury_na_dwa_arkusze(self):
        """Faktura 8 530,10 netto: 3 201,32 do jednego arkusza, 5 328,78 do drugiego; VAT dzielony proporcjonalnie."""
        self.wiersz('w-a', rodzaj=1, kontrahent='Gamma')
        self.wiersz('w-b', arkusz='a-dwa', rodzaj=1, kontrahent='Gamma', podstawa='Faktura (w worku)')
        self.komorka('w-a', '2026-10', 300000)
        self.komorka('w-b', '2026-10', 500000)
        self.assertIn('Do rozliczenia zostało 100,00 zł', self.blad({'op': 'polacz', 'dokument': 'faktura:FV2026/10/6', 'czesci': [
            {'wiersz': 'w-a', 'miesiac': '2026-10', 'kwota': 320132}, {'wiersz': 'w-b', 'miesiac': '2026-10', 'kwota': 522878}]}))
        self.bud({'op': 'polacz', 'dokument': 'faktura:FV2026/10/6', 'czesci': [
            {'wiersz': 'w-a', 'miesiac': '2026-10', 'kwota': 320132}, {'wiersz': 'w-b', 'miesiac': '2026-10', 'kwota': 532878}]})
        rz = [dict(r) for r in self.con.execute("SELECT p.netto, p.vat, w.arkusz FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz"
                                                " WHERE p.dokument = 'faktura:FV2026/10/6' ORDER BY p.id")]
        self.assertEqual([(x['netto'], x['arkusz']) for x in rz], [(320132, 'a-test'), (532878, 'a-dwa')])
        self.assertEqual(sum(x['netto'] for x in rz), 853010)
        self.assertEqual(sum(x['vat'] for x in rz), 196192)   # VAT dokumentu co do grosza
        self.assertEqual(rz[0]['vat'], 73630)                 # 196 192 × 320 132 / 853 010, połówki w górę

    def test_worek_150_i_rzeczywiste_20_23_potem_120(self):
        self.wiersz('w-park', podstawa='Bez faktury (w worku)', kontrahent='Parking Centrum')
        self.komorka('w-park', '2026-10', 15000)
        self.bud({'op': 'seria', 'operacje': [self.reczna('r1', 2000), self.reczna('r2', 2300)]})
        self.bud({'op': 'seria', 'operacje': [
            {'op': 'polacz', 'dokument': 'reczna:r1', 'czesci': [{'wiersz': 'w-park', 'miesiac': '2026-10', 'kwota': 2000}]},
            {'op': 'polacz', 'dokument': 'reczna:r2', 'czesci': [{'wiersz': 'w-park', 'miesiac': '2026-10', 'kwota': 2300}]}]})
        self.assertEqual(self.wartosc('a-test', 'w-park', '2026-10'), -15000)
        plany = [p for p in self.platnosci('w-park', '2026-10') if p['typ'] == 'plan']
        self.assertEqual(sum(p['netto'] for p in plany), 10700)   # niezrealizowane plany tygodniowe
        self.bud(self.reczna('r3', 12000))
        self.bud({'op': 'polacz', 'dokument': 'reczna:r3', 'czesci': [{'wiersz': 'w-park', 'miesiac': '2026-10', 'kwota': 12000}]})
        self.assertEqual(self.wartosc('a-test', 'w-park', '2026-10'), -16300)
        # zmniejszenie worka poniżej sumy rzeczywistych zablokowane, zamknięcie worka (usuń resztę)
        self.assertIn('nie może być mniejsza', self.blad({'op': 'komorka', 'wiersz': 'w-park', 'miesiac': '2026-10', 'kwota': 10000}))

    def test_worek_zamkniety_reszta_usun_i_otwarcie_wieksza_kwota(self):
        self.wiersz('w-park', podstawa='Bez faktury (w worku)', kontrahent='Parking Centrum')
        self.komorka('w-park', '2026-10', 15000)
        self.bud(self.reczna('r1', 2000))
        self.bud({'op': 'polacz', 'dokument': 'reczna:r1', 'reszta': 'usun', 'czesci': [{'wiersz': 'w-park', 'miesiac': '2026-10', 'kwota': 2000}]})
        self.assertEqual([p['typ'] for p in self.platnosci('w-park', '2026-10')], ['rzeczywista'])
        self.komorka('w-park', '2026-10', 20000)   # A-KOM-05: zwiększenie kwoty otwiera worek
        self.assertEqual(sum(p['netto'] for p in self.platnosci('w-park', '2026-10') if p['typ'] == 'plan'), 18000)


class TestBlokady(Baza5):
    def test_inny_rodzaj_pusta_komorka_podstawa_i_dokument_w_budzecie(self):
        self.wiersz('w-koszt', kontrahent='Alfa')
        self.komorka('w-koszt', '2026-10', 450000)
        self.assertIn('Nie połączysz wpływu z wierszem obciążeń', self.blad({'op': 'polacz', 'dokument': 'faktura:FV2026/10/5', 'czesci': [
            {'wiersz': 'w-koszt', 'miesiac': '2026-10', 'kwota': 450000}]}))
        self.wiersz('w-pusty', rodzaj=1, kontrahent='Alfa')
        self.assertIn('jest pusta', self.blad({'op': 'polacz', 'dokument': 'faktura:FV2026/10/5', 'czesci': [
            {'wiersz': 'w-pusty', 'miesiac': '2026-10', 'kwota': 450000}]}))
        self.wiersz('w-bez', rodzaj=1, kontrahent='Alfa', podstawa='Bez faktury')
        self.komorka('w-bez', '2026-10', 450000)
        self.assertIn('Podstawa się nie zgadza', self.blad({'op': 'polacz', 'dokument': 'faktura:FV2026/10/5', 'czesci': [
            {'wiersz': 'w-bez', 'miesiac': '2026-10', 'kwota': 450000}]}))
        # faktura z BS (numer w eksporcie): już w budżecie, drugi raz jej nie połączysz
        self.assertEqual(self.con.execute("SELECT stan FROM bud_laczenie WHERE ref = 'faktura:FV2026/08/1'").fetchone()[0], 'w_budzecie')
        self.assertIn('już w budżecie', self.blad({'op': 'polacz', 'dokument': 'faktura:FV2026/08/1', 'czesci': [
            {'wiersz': 'w-bez', 'miesiac': '2026-10', 'kwota': 100000}]}))
        self.assertIn('nie ma takiego dokumentu', self.blad({'op': 'polacz', 'dokument': 'faktura:NIE-MA', 'czesci': [
            {'wiersz': 'w-bez', 'miesiac': '2026-10', 'kwota': 1}]}))

    def test_przelew_bez_dokumentu_do_wiersza_z_faktura_vat_ze_stawki(self):
        self.wiersz('w-ai', kontrahent='OpenAI', podstawa='Faktura (w worku)', stawka_vat=23)
        self.komorka('w-ai', '2026-10', 10000)
        ref = next(r['ref'] for r in laczenie.lista(self.con, {})['wiersze'] if r['typ'] == 'operacja' and r['kwota'] == 8000)
        self.bud({'op': 'polacz', 'dokument': ref, 'czesci': [{'wiersz': 'w-ai', 'miesiac': '2026-10', 'kwota': 8000}]})
        p = next(p for p in self.platnosci('w-ai', '2026-10') if p['typ'] != 'plan')
        self.assertEqual((p['brutto'], p['netto'], p['vat'], p['etap']), (8000, 6504, 1496, 'Opłacona'))   # opłacona z banku

    def test_poczekalnia_od_dnia_startu_lacenia(self):
        stany = dict(self.con.execute("SELECT ref, stan FROM bud_laczenie WHERE typ = 'faktura'").fetchall())
        self.assertEqual(stany['faktura:FV2026/10/5'], 'do_polaczenia')
        self.assertEqual(stany['faktura:FV2026/09/1'], 'sprzed')   # wystawiona przed startem łączenia w apce (Budget Studio)
        self.assertEqual(stany['faktura:FV2026/08/1'], 'w_budzecie')
        # wynagrodzenie z reguły wbudowanej nie czeka w „Do połączenia” (idzie listą płac)
        self.assertFalse(self.con.execute("SELECT 1 FROM bud_laczenie WHERE kontrahent LIKE '%JÓZEFIAK%'").fetchone())


class TestPodpowiedzi(Baza5):
    def test_jedna_komorka_dla_jednej_podpowiedzi_i_seria_wg_podpowiedzi(self):
        self.wiersz('w-alfa', rodzaj=1, kontrahent='Alfa', dzien_wystawienia='5.')
        self.wiersz('w-gam', arkusz='a-dwa', rodzaj=1, kontrahent='Gamma')
        self.komorka('w-alfa', '2026-10', 450000)
        self.komorka('w-gam', '2026-10', 853010)
        lista = {r['ref']: r for r in laczenie.lista(self.con, {})['wiersze']}
        a, g = lista['faktura:FV2026/10/5'], lista['faktura:FV2026/10/6']
        # faktura Alfy: najlepszy plan w arkuszu klienta (folder Alfa, ten sam nabywca co poprzednia faktura w BS)
        wiersz_bs = self.con.execute("SELECT wiersz FROM bud_platnosc WHERE bs_id = '3'").fetchone()[0]
        self.assertEqual((a['pod_wiersz'], a['pod_miesiac'], a['pewnosc'], a['pod_arkusz_nazwa']), (wiersz_bs, '2026-10', 'wysoka', 'Obsługa stała Alfa'))
        self.assertIn('ten sam klient (folder Alfa)', a['uzasadnienie'])
        self.assertIn('wcześniej łączone z tym wierszem', a['uzasadnienie'])
        self.assertEqual((g['pod_wiersz'], g['pewnosc']), ('w-gam', 'wysoka'))
        self.assertIn('kwota równa planowi', g['uzasadnienie'])
        # komórka nie-worek trafia do jednej podpowiedzi: druga faktura Alfy nie dostanie tego samego planu
        k = laczenie.karta(self.con, 'faktura:FV2026/10/5')
        self.assertEqual(k['podpowiedzi'][0]['wiersz'], wiersz_bs)
        # „Połącz wg podpowiedzi” na dwóch pozycjach: jedna seria, jeden wpis w pliku zmian
        przed = len(zmiany.wczytaj()[0])
        self.bud({'op': 'seria', 'operacje': [{'op': 'polacz', 'dokument': x['ref'], 'czesci': [
            {'wiersz': x['pod_wiersz'], 'miesiac': x['pod_miesiac'], 'kwota': x['kwota']}]} for x in (a, g)]})
        self.assertEqual(len(zmiany.wczytaj()[0]), przed + 1)
        self.assertEqual(laczenie.ile_do_polaczenia(self.con), len([r for r in lista.values()]) - 2)
        # cofnięcie serii przywraca oba plany
        zmiany.zapisz('cofnij', {'wpis': zapytania_budzet.ostatni(self.con)['wpis']})
        self.przelicz()
        self.assertEqual([p['typ'] for p in self.platnosci('w-gam', '2026-10')], ['plan'])
        self.assertEqual([p['typ'] for p in self.platnosci(wiersz_bs, '2026-10')], ['plan'])


class TestZamianaIReczna(Baza5):
    def test_zmien_na_rzeczywista(self):
        self.wiersz('w-druk', kontrahent='Drukarnia', komentarz='Ulotki')
        self.komorka('w-druk', '2026-09', 50000)   # wystawienie 10.09
        self.komorka('w-druk', '2026-12', 50000)   # wystawienie 10.12: w przyszłości
        pid = 'plan:w-druk:2026-09:1'
        self.assertIn('Podaj numer faktury', self.blad({'op': 'zamien', 'plan': pid}))
        self.assertIn('dopiero od dnia jego wystawienia', self.blad({'op': 'zamien', 'plan': 'plan:w-druk:2026-12:1', 'obiekt': {'nr_dok': 'FS 1'}}))
        self.bud({'op': 'zamien', 'plan': pid, 'obiekt': {'nr_dok': 'FS 7/09', 'netto': 52000}})
        ps = self.platnosci('w-druk', '2026-09')
        self.assertEqual([(p['typ'], p['netto'], p['vat'], p['nr_dok'], p['komentarz'], p['zrodlo']) for p in ps],
                         [('rzeczywista', 52000, 11960, 'FS 7/09', 'Ulotki', 'zamiana planu')])
        self.bud({'op': 'odlacz', 'dokument': f'zamiana:{pid}'})
        self.assertEqual([(p['typ'], p['netto']) for p in self.platnosci('w-druk', '2026-09')], [('plan', 50000)])
        # worek nie
        self.wiersz('w-worek', podstawa='Faktura (w worku)', dni_na_platnosc=0)
        self.komorka('w-worek', '2026-09', 30000)
        self.assertIn('Worka nie zmienisz', self.blad({'op': 'zamien', 'plan': 'plan:w-worek:2026-09:t1', 'obiekt': {'nr_dok': 'X'}}))

    def test_reczna_walidacje_bs_i_do_polaczenia(self):
        self.assertIn('nie może być z przyszłości', self.blad(self.reczna('r1', 1000, wystawienie='2099-01-01')))
        self.assertIn('najwcześniej 45 dni przed', self.blad(self.reczna('r1', 1000, podstawa='Faktura', stawka=23, realny='2026-08-01')))
        self.assertIn('nie może być wcześniej niż dzień', self.blad(self.reczna('r1', 1000, realny='2026-10-01')))
        self.assertIn('stawkę VAT', self.blad(self.reczna('r1', 1000, podstawa='Faktura')))
        self.bud(self.reczna('r1', 10000, podstawa='Faktura', stawka=23, realny='2026-09-01', nr_dok='F 1'))
        x = next(r for r in laczenie.lista(self.con, {})['wiersze'] if r['ref'] == 'reczna:r1')
        self.assertEqual((x['netto'], x['vat'], x['brutto'], x['zrodlo_nazwa']), (10000, 2300, 12300, 'Dodana ręcznie'))
        # usunięcie tylko niepołączonej
        self.bud({'op': 'rzeczywista', 'obiekt': {'id': 'r1'}, 'usun': True})
        self.assertFalse(self.con.execute("SELECT 1 FROM bud_laczenie WHERE ref = 'reczna:r1'").fetchone())


class TestOplaconaINiewymagana(Baza5):
    def test_niewymagana_nigdy_nie_jest_oplacona(self):
        """Etap BS „Niewymagana” = rzeczywista nieopłacona przed terminem: zostaje w cash flow (ZUS za wrzesień płatny
        w listopadzie, faktura kosztowa z terminem 20.11). BS „Opłacona” bez przelewu i z minionym terminem: tylko wg BS."""
        etapy = {r['bs_id']: r['etap'] for r in self.con.execute(
            "SELECT p.bs_id, s.etap FROM bud_platnosc p JOIN bud_stan s ON s.platnosc = p.id WHERE p.bs_id IN ('8', '9', '10', '11')")}
        self.assertEqual(etapy, {'8': 'Planowana', '9': 'Planowana', '10': 'Opłacona wg BS', '11': 'Planowana'})
        ids = {r[0] for r in self.con.execute("SELECT id FROM bud_platnosc WHERE bs_id IN ('8', '9', '11')")}
        zd, _ = cashflow._zdarzenia(self.con, cashflow._d(DZIS), cashflow._d('2027-03-31'))
        self.assertLessEqual(ids, {z['zrodlo'] for z in zd})


class TestOplaconaRecznieZData(Baza5):
    def test_zaplacone_tylko_z_data_przelewu(self):
        """Decyzja 3: „Opłacona” z banku; ręcznie tylko wyjątek i zawsze z datą przelewu (zapisaną jako dzień realny)."""
        self.wiersz('w-druk', kontrahent='Drukarnia')
        self.komorka('w-druk', '2026-09', 50000)
        pid = 'plan:w-druk:2026-09:1'
        self.assertIn('tylko z datą przelewu', self.blad({'op': 'decyzja_planu', 'platnosc': pid, 'decyzja': 'zaplacone'}))
        self.bud({'op': 'decyzja_planu', 'platnosc': pid, 'decyzja': 'zaplacone', 'data': '2026-09-28'})
        p = self.platnosci('w-druk', '2026-09')[0]
        self.assertEqual((p['etap'], p['realny'], p['decyzja']), ('Opłacona', '2026-09-28', 'zapłacone (Mat)'))

    def test_reczna_z_data_poza_bankiem_jest_oplacona_po_polaczeniu(self):
        self.wiersz('w-park', podstawa='Bez faktury', kontrahent='Parking Centrum')
        self.komorka('w-park', '2026-10', 2000)
        self.bud(self.reczna('r1', 2000, oplacona='2026-10-06'))
        self.bud({'op': 'polacz', 'dokument': 'reczna:r1', 'czesci': [{'wiersz': 'w-park', 'miesiac': '2026-10', 'kwota': 2000}]})
        p = self.platnosci('w-park', '2026-10')[0]
        self.assertEqual((p['typ'], p['etap'], p['realny']), ('rzeczywista', 'Opłacona', '2026-10-06'))


class TestWorekZamkniecie(Baza5):
    def test_zamknij_i_otworz_worek(self):
        """Worek przyjmuje rzeczywiste do ręcznego zamknięcia; zamknięcie usuwa niezrealizowane plany tygodniowe (komórka =
        suma rzeczywistych), zamknięty nie przyjmie kolejnej, otwarcie przywraca plany na resztę."""
        self.wiersz('w-park', podstawa='Bez faktury (w worku)', kontrahent='Parking Centrum')
        self.komorka('w-park', '2026-10', 15000)
        self.assertIn('nie ma jeszcze żadnej płatności rzeczywistej', self.blad({'op': 'zamknij_worek', 'wiersz': 'w-park', 'miesiac': '2026-10'}))
        self.bud({'op': 'seria', 'operacje': [self.reczna('r1', 2000), self.reczna('r2', 2300)]})
        self.bud({'op': 'polacz', 'dokument': 'reczna:r1', 'czesci': [{'wiersz': 'w-park', 'miesiac': '2026-10', 'kwota': 2000}]})
        k = zapytania_budzet.komorka(self.con, 'w-park', '2026-10')
        self.assertEqual((k['worek']['zamkniety'], k['worek']['rzeczywistych'], k['worek']['plany']), (False, 1, 13000))
        self.bud({'op': 'zamknij_worek', 'wiersz': 'w-park', 'miesiac': '2026-10'})
        self.assertEqual([p['typ'] for p in self.platnosci('w-park', '2026-10')], ['rzeczywista'])
        self.assertEqual(self.wartosc('a-test', 'w-park', '2026-10'), -2000)
        self.assertTrue(zapytania_budzet.komorka(self.con, 'w-park', '2026-10')['worek']['zamkniety'])
        self.assertIn('już zamknięty', self.blad({'op': 'zamknij_worek', 'wiersz': 'w-park', 'miesiac': '2026-10'}))
        self.assertIn('jest zamknięty', self.blad({'op': 'polacz', 'dokument': 'reczna:r2', 'czesci': [
            {'wiersz': 'w-park', 'miesiac': '2026-10', 'kwota': 2300}]}))
        self.bud({'op': 'odlacz', 'dokument': 'worek:w-park:2026-10'})
        self.assertEqual(sum(p['netto'] for p in self.platnosci('w-park', '2026-10') if p['typ'] == 'plan'), 13000)
        self.assertEqual(self.wartosc('a-test', 'w-park', '2026-10'), -15000)
        # plan pojedynczy nie jest workiem
        self.wiersz('w-jeden', podstawa='Bez faktury', kontrahent='Parking Centrum')
        self.komorka('w-jeden', '2026-10', 1000)
        self.assertIn('tylko worek', self.blad({'op': 'zamknij_worek', 'wiersz': 'w-jeden', 'miesiac': '2026-10'}))


class TestNoweWiersze(Baza5):
    def test_polacz_z_budzetem_nowe_wiersze_jedna_seria(self):
        """B-LACZ-07: zaznaczone rzeczywiste jako nowe wiersze w arkuszu (1 wiersz = 1 płatność): wiersz z danymi dokumentu,
        plan 0 w miesiącu dokumentu i połączenie jedną serią; komórka = kwota dokumentu."""
        lista = {r['ref']: r for r in laczenie.lista(self.con, {})['wiersze']}
        x = lista['faktura:FV2026/10/6']
        self.assertEqual(x['termin'], '2026-10-20')   # dni na płatność z dokumentu
        przed = len(zmiany.wczytaj()[0])
        self.bud({'op': 'seria', 'operacje': [
            {'op': 'wiersz', 'obiekt': {'id': 'w-nowy', 'arkusz': 'a-dwa', 'rodzaj': 1, 'podstawa': 'Faktura (jedna)', 'kontrahent': 'Gamma',
                                        'dzien_wystawienia': '6.', 'dni_na_platnosc': 14, 'stawka_vat': 23}},
            {'op': 'komorka', 'wiersz': 'w-nowy', 'miesiac': '2026-10', 'kwota': 0},
            {'op': 'polacz', 'dokument': x['ref'], 'czesci': [{'wiersz': 'w-nowy', 'miesiac': '2026-10', 'kwota': x['kwota']}]}]})
        self.assertEqual(len(zmiany.wczytaj()[0]), przed + 1)
        self.assertEqual(self.wartosc('a-dwa', 'w-nowy', '2026-10'), 853010)
        self.assertEqual([p['typ'] for p in self.platnosci('w-nowy', '2026-10')], ['rzeczywista'])

    def test_rozjazd_faktura_bez_pozycji_ma_dokument_do_polaczenia(self):
        """Rozjazd „Faktura bez pozycji w BS” (sprzed startu łączenia) prowadzi do dokumentu, który można połączyć."""
        rz = [x for x in zapytania_budzet.rozjazdy(self.con) if x['rodzaj'] == 'Faktura bez pozycji w BS']
        x = next(r for r in rz if r['ref'] == 'FV2026/09/7')
        self.assertEqual((x['dok']['ref'], x['dok']['stan']), ('faktura:FV2026/09/7', 'sprzed'))


class TestListaPlac(Baza5):
    def setUp(self):
        super().setUp()
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-up', 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Umowa o pracę',
                                             'kontrahent': 'Paulina Józefiak', 'dzien_wystawienia': 'Ostatni', 'dni_na_platnosc': 7,
                                             'proporcje': {'osoba': 735026, 'us': 78003, 'zus': 427915}}}, przelicz=False)
        self.bud({'op': 'seria', 'operacje': [{'op': 'komorka', 'wiersz': 'w-up', 'miesiac': m, 'kwota': 1240944}
                                               for m in ('2026-09', '2026-10', '2026-11', '2026-12')]})

    def test_przyszle_pit_i_zus_w_cashflow_do_wpisu_listy_plac(self):
        """Test regresji: plany wynagrodzeń (w tym PIT i ZUS) zostają w cash flow, dopóki nie ma listy płac; przelew z banku
        nie zamyka planu (tylko podpowiada); żaden import BS go nie zamyka."""
        zd, _ = cashflow._zdarzenia(self.con, cashflow._d(DZIS), cashflow._d('2027-03-31'))
        w_cf = {z['zrodlo'] for z in zd}
        for m in ('2026-10', '2026-11'):
            for s in ('osoba', 'us', 'zus'):
                self.assertIn(f'plan:w-up:{m}:{s}', w_cf)
        wrzesien = {p['skladowa']: p for p in self.platnosci('w-up', '2026-09')}
        self.assertEqual({p['typ'] for p in wrzesien.values()}, {'plan'})
        self.assertNotEqual(wrzesien['osoba']['etap'], 'Opłacona')   # wypłata w banku 6 716,06 nie zamyka planu
        self.assertIn(f"plan:w-up:2026-09:us", w_cf)
        # ostrzeżenie (a): wypłata za wrzesień minęła 7.10, lista płac niewpisana
        o = [x for x in laczenie.ostrzezenia(self.con) if x['rodzaj'] == 'lista_niewpisana']
        self.assertEqual([(x['wiersz'], x['miesiac']) for x in o], [('w-up', '2026-09')])
        self.assertIn('lista_niewpisana', {x['rodzaj'] for x in zapytania.do_weryfikacji(self.con)})
        # ręczne „zapłacone” na planie wynagrodzenia odrzucone (decyzja 12)
        self.assertIn('listą płac', self.blad({'op': 'decyzja_planu', 'platnosc': 'plan:w-up:2026-09:osoba', 'decyzja': 'zaplacone', 'data': DZIS}))

    def test_lista_plac_zamienia_plany_na_rzeczywiste_i_ostrzezenia(self):
        self.bud({'op': 'lista_plac', 'miesiac': '2026-09', 'pozycje': [{'wiersz': 'w-up', 'osoba': 800000, 'us': 90000, 'zus': 450000}]})
        ps = {p['skladowa']: p for p in self.platnosci('w-up', '2026-09')}
        self.assertEqual({s: (p['typ'], p['netto'], p['zrodlo']) for s, p in ps.items()},
                         {s: ('rzeczywista', k, 'lista płac') for s, k in (('osoba', 800000), ('us', 90000), ('zus', 450000))})
        self.assertEqual((ps['us']['termin'], ps['zus']['termin'], ps['us']['spinacz']), ('2026-11-20', '2026-11-15', ps['osoba']['id']))
        rodzaje = {x['rodzaj']: x for x in laczenie.ostrzezenia(self.con)}
        self.assertNotIn('lista_niewpisana', rodzaje)
        # (b) estymacja na październik (1 240 944) niższa niż ostatnia lista (1 340 000)
        self.assertEqual((rodzaje['estymacja_nizsza']['miesiac'], rodzaje['estymacja_nizsza']['kwota']), ('2026-10', 1240944 - 1340000))
        # (c) wypłata z listy 8 000,00, przelew 6 716,06
        c = rodzaje['lista_vs_przelew']
        self.assertEqual((c['miesiac'], c['kwota']), ('2026-09', 800000 - 671606))
        # formularz: wpisane kwoty, plan, przelewy
        f = laczenie.lista_plac(self.con, '2026-09')
        osoba = next(o for o in f['osoby'] if o['wiersz'] == 'w-up')
        self.assertEqual((osoba['wpisane'], osoba['z_listy'], [x['kwota'] for x in osoba['przelewy']]),
                         ({'osoba': 800000, 'us': 90000, 'zus': 450000}, True, [671606]))
        # poprawka listy (ten sam miesiąc) i powrót do planu („usun”)
        self.bud({'op': 'lista_plac', 'miesiac': '2026-09', 'pozycje': [{'wiersz': 'w-up', 'osoba': 671606, 'us': 78003, 'zus': 427915}]})
        self.assertNotIn('lista_vs_przelew', {x['rodzaj'] for x in laczenie.ostrzezenia(self.con)})
        self.bud({'op': 'lista_plac', 'miesiac': '2026-09', 'usun': True, 'pozycje': [{'wiersz': 'w-up'}]})
        self.assertEqual({p['typ'] for p in self.platnosci('w-up', '2026-09')}, {'plan'})

    def test_wiersz_bez_umowy_na_liscie_plac(self):
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-prezes', 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Bez faktury',
                                             'kontrahent': 'Prezes', 'dzien_wystawienia': 'Ostatni', 'dni_na_platnosc': 7}}, przelicz=False)
        self.komorka('w-prezes', '2026-09', 1200000)
        self.assertIn('nie jest wierszem wynagrodzenia', self.blad({'op': 'lista_plac', 'miesiac': '2026-09',
                                                                      'pozycje': [{'wiersz': 'w-prezes', 'osoba': 1}]}))
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-prezes', 'lista_plac': True}})
        self.bud({'op': 'lista_plac', 'miesiac': '2026-09', 'pozycje': [{'wiersz': 'w-prezes', 'osoba': 936793, 'us': 100000, 'zus': 50000}]})
        p = self.platnosci('w-prezes', '2026-09')
        self.assertEqual([(x['typ'], x['netto'], json.loads(x['skladniki'])) for x in p],
                         [('rzeczywista', 1086793, {'osoba': 936793, 'us': 100000, 'zus': 50000})])
        # komórka umowy z rzeczywistą z kopii BS nie przyjmie listy płac; zwykły dokument nie trafi do wiersza wynagrodzenia
        self.komorka('w-prezes', '2026-10', 1200000)
        self.assertIn('wiersz wynagrodzenia', self.blad({'op': 'polacz', 'dokument': next(r['ref'] for r in laczenie.lista(self.con, {})['wiersze']
                                                                                         if r['typ'] == 'operacja' and r['kwota'] == 8000),
                                                          'czesci': [{'wiersz': 'w-prezes', 'miesiac': '2026-10', 'kwota': 8000}]}))


class TestSerwer(unittest.TestCase):
    def test_api_listy_karty_ostrzezen_i_polaczenie(self):
        with Srodowisko() as srod:
            dane5(srod)
            zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
            zmiany.zapisz('ustawienie', {'klucz': 'laczenie_od', 'wartosc': '2026-10-01'})
            odbudowa.odbuduj()
            stary = konfig.PORT
            h = ThreadingHTTPServer((konfig.HOST, 0), serwer.Obsluga)
            konfig.PORT = h.server_address[1]
            threading.Thread(target=h.serve_forever, daemon=True).start()
            try:
                def wyslij(typ, d, metoda='POST', sciezka='/api/zmiana'):
                    c = http.client.HTTPConnection('127.0.0.1', konfig.PORT, timeout=20)
                    c.request(metoda, sciezka, body=json.dumps({'typ': typ, 'dane': d}) if metoda == 'POST' else None,
                              headers={'Host': f'127.0.0.1:{konfig.PORT}', 'X-Finanse': '1', 'Content-Type': 'application/json'})
                    r = c.getresponse()
                    return r.status, json.loads(r.read() or b'{}')
                kod, w = wyslij(None, None, 'GET', '/api/lista/do-polaczenia')
                self.assertEqual(kod, 200)
                self.assertIn('faktura:FV2026/10/5', [x['ref'] for x in w['wiersze']])
                kod, w = wyslij(None, None, 'GET', '/api/ostrzezenia')
                self.assertEqual((kod, sorted(w)), (200, ['do_polaczenia', 'liczba', 'ostrzezenia']))
                kod, w = wyslij(None, None, 'GET', '/api/laczenie/dokument?ref=faktura%3AFV2026%2F10%2F5')
                self.assertEqual((kod, w['dokument']['netto'], w['stan']), (200, 450000, 'do_polaczenia'))
                kod, w = wyslij(None, None, 'GET', '/api/lista-plac?miesiac=2026-09')
                self.assertEqual(kod, 200)
                kod, w = wyslij(None, None, 'GET', '/api/lista-plac?miesiac=zly')
                self.assertEqual(kod, 400)
                wyslij('bud', {'op': 'seria', 'operacje': [
                    {'op': 'arkusz', 'obiekt': {'id': 'a-t', 'nazwa': 'T', 'folder': 'Alfa', 'kategoria': 'K', 'od': '2026-01', 'do': '2026-12'}},
                    {'op': 'wiersz', 'obiekt': {'id': 'w-a', 'arkusz': 'a-t', 'rodzaj': 1, 'podstawa': 'Faktura (jedna)', 'kontrahent': 'Alfa'}},
                    {'op': 'komorka', 'wiersz': 'w-a', 'miesiac': '2026-10', 'kwota': 0}]})
                kod, w = wyslij('bud', {'op': 'polacz', 'dokument': 'faktura:FV2026/10/5', 'czesci': [{'wiersz': 'w-a', 'miesiac': '2026-10', 'kwota': 1}]})
                self.assertEqual(kod, 400)
                self.assertIn('Do rozliczenia', w['blad'])
                kod, w = wyslij('bud', {'op': 'polacz', 'dokument': 'faktura:FV2026/10/5', 'czesci': [{'wiersz': 'w-a', 'miesiac': '2026-10', 'kwota': 450000}]})
                self.assertEqual(kod, 200, w)
                kod, w = wyslij(None, None, 'GET', '/api/budzet/ostatni')
                self.assertEqual(w['ostatni']['ops'], ['polacz'])
            finally:
                h.shutdown()
                h.server_close()
                konfig.PORT = stary


if __name__ == '__main__':
    unittest.main()
