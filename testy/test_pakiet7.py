"""Pakiet 7: listy płatności jak w Budget Studio. Filtry dat w trybach BS (A-FIL-01 do 07) liczone od dnia stanu,
sortowanie po stronie serwera po każdej kolumnie z białej listy (APK-BRAK-09), podsumowanie zaznaczenia, zapisane widoki
(zdarzenie „widok”), akcje grupowe jako jedna seria (wszystko albo nic) i Do weryfikacji. Zmyślone dane."""
import http.client
import json
import threading
import unittest
from datetime import date
from http.server import ThreadingHTTPServer

from finanse import baza, filtry, konfig, odbudowa, zapytania, zapytania_listy, zmiany
from testy.pomoc import Srodowisko
from testy.test_budzet import dane

D = date.fromisoformat


class TestZakresDat(unittest.TestCase):
    def test_przyklady_z_bazy_wiedzy_bs(self):
        # Miesiąc, N = 3, K = -1 przy dniu stanu 1.12.2025: poprzedni, bieżący i następny miesiąc
        self.assertEqual(filtry.zakres('ruchomy:miesiac:3:-1', D('2025-12-01')), (D('2025-11-01'), D('2026-01-31')))
        # Dzień realnej płatności, dziś, N = 14: „do zapłacenia, 2 tygodnie”
        self.assertEqual(filtry.zakres('ruchomy:dzien:14:0', D('2026-10-13')), (D('2026-10-13'), D('2026-10-26')))
        # Miesiąc księgowania, N = 1, K = -1: poprzedni miesiąc
        self.assertEqual(filtry.zakres('ruchomy:miesiac:1:-1', D('2026-10-13'), miesieczny=True), (D('2026-09-01'), D('2026-09-30')))
        # Data dodania, dziś, N = 7, K = -7: ostatni tydzień wprowadzeń
        self.assertEqual(filtry.zakres('ruchomy:dzien:7:-7', D('2026-10-13')), (D('2026-10-06'), D('2026-10-12')))

    def test_biezacy_okres_i_od_dzis_do_konca(self):
        wt = D('2026-10-13')   # wtorek
        self.assertEqual(filtry.zakres('biezacy:tydzien', wt, pierwszy_dzien_tyg=1), (D('2026-10-13'), D('2026-10-19')))   # tydzień BS: od wtorku do poniedziałku
        self.assertEqual(filtry.zakres('biezacy:tydzien', wt, pierwszy_dzien_tyg=0), (D('2026-10-12'), D('2026-10-18')))
        self.assertEqual(filtry.zakres('biezacy:miesiac', wt), (D('2026-10-01'), D('2026-10-31')))
        self.assertEqual(filtry.zakres('biezacy:rok', wt), (D('2026-01-01'), D('2026-12-31')))
        self.assertEqual(filtry.zakres('biezacy:kwartal', wt, miesieczny=True), (D('2026-10-01'), D('2026-12-31')))
        self.assertEqual(filtry.zakres('dokonca:miesiac', wt), (D('2026-10-13'), D('2026-10-31')))   # „od dziś do końca miesiąca”
        self.assertEqual(filtry.zakres('biezacy:miesiac', D('2024-02-10')), (D('2024-02-01'), D('2024-02-29')))

    def test_zakres_statyczny_otwarty_i_miesiace(self):
        self.assertEqual(filtry.zakres('zakres:2026-01-01:2026-01-15', D('2026-10-13')), (D('2026-01-01'), D('2026-01-15')))
        self.assertEqual(filtry.zakres('zakres::2026-01-15', D('2026-10-13')), (None, D('2026-01-15')))
        self.assertEqual(filtry.zakres('zakres:2026-01:2026-03', D('2026-10-13'), miesieczny=True), (D('2026-01-01'), D('2026-03-31')))
        self.assertIsNone(filtry.zakres('wszystko', D('2026-10-13')))
        self.assertIsNone(filtry.zakres('', D('2026-10-13')))

    def test_kotwica_dnia_tygodnia_kwartal_rok(self):
        self.assertEqual(filtry.zakres('ruchomy:dzien_tyg:7:0:0', D('2026-10-14')), (D('2026-10-12'), D('2026-10-18')))   # od poniedziałku
        self.assertEqual(filtry.zakres('ruchomy:kwartal:1:-1', D('2026-10-13')), (D('2026-07-01'), D('2026-09-30')))
        self.assertEqual(filtry.zakres('ruchomy:rok:2:0', D('2026-10-13')), (D('2026-01-01'), D('2027-12-31')))

    def test_daty_wzgledne_przeliczane_przy_otwarciu(self):
        p = filtry.podglad('ruchomy:dzien:14:0', D('2026-10-13'))
        self.assertEqual((p['dzis'], p['jutro'], p['za_miesiac']),
                         (['2026-10-13', '2026-10-26'], ['2026-10-14', '2026-10-27'], ['2026-11-13', '2026-11-26']))
        self.assertEqual(filtry.podglad('biezacy:miesiac', D('2026-01-31'))['za_miesiac'], ['2026-02-01', '2026-02-28'])

    def test_bledne_tryby_odrzucone(self):
        for spec, m in (('biezacy:kwartal', False), ('biezacy:tydzien', True), ('dokonca:tydzien', True), ('ruchomy:dzien:14:0', True),
                        ('ruchomy:dzien:0:0', False), ('ruchomy:dzien:x:0', False), ('ruchomy:dzien_tyg:7:0', False),
                        ('zakres:2026-02-01:2026-01-01', False), ('zakres:2026-13-01:', False), ('jutro', False), ('ruchomy:tydzien:1:0', False)):
            with self.assertRaises(ValueError, msg=spec):
                filtry.zakres(spec, D('2026-10-13'), miesieczny=m)

    def test_warunek_sql(self):
        sql, p = filtry.warunek('p.wystawienie', 'zakres:2026-01-01:2026-01-31', D('2026-10-13'))
        self.assertEqual((sql, p), ('(substr(p.wystawienie, 1, 10) >= ? AND substr(p.wystawienie, 1, 10) <= ?)', ['2026-01-01', '2026-01-31']))
        sql, p = filtry.warunek('p.ksiegowanie', 'ruchomy:miesiac:1:-1', D('2026-10-13'), miesieczny=True)
        self.assertEqual(p, ['2026-09', '2026-09'])
        self.assertEqual(filtry.warunek('x', 'wszystko', D('2026-10-13')), (None, []))


class TestSortowanieIPodsumowanie(unittest.TestCase):
    def test_alfabet_polski(self):
        slowa = ['Żaba', 'zebra', 'Ąbc', 'abc', 'Łódź', 'lis', 'źle', 'Ćma', 'cma']
        self.assertEqual(sorted(slowa, key=filtry.klucz_pl), ['abc', 'Ąbc', 'cma', 'Ćma', 'lis', 'Łódź', 'zebra', 'źle', 'Żaba'])
        self.assertEqual(filtry.porownaj_pl('a', 'A'), 0)

    def test_porzadek_z_bialej_listy(self):
        kol = {'kwota': ('kwota', False), 'nazwa': ('nazwa', True)}
        self.assertEqual(filtry.porzadek('; DROP TABLE x', 'rosnaco', kol, 'data DESC', 'id'), 'data DESC, id')
        self.assertIn('kwota) ASC', filtry.porzadek('kwota', 'rosnaco', kol, 'data DESC'))
        self.assertIn('COLLATE PL DESC', filtry.porzadek('nazwa', 'malejaco', kol, 'data DESC'))

    def test_podsumowanie_trzech_wierszy(self):
        w = [{'rodzaj': 1, 'netto': 100000, 'vat': 23000, 'brutto': 123000}, {'rodzaj': -1, 'netto': -50000, 'vat': -4000, 'brutto': -54000},
             {'rodzaj': 1, 'netto': 1999, 'vat': 0, 'brutto': 1999}]
        s = filtry.podsumuj(w)
        self.assertEqual(s['wplywy'], {'ile': 2, 'netto': 101999, 'vat': 23000, 'brutto': 124999})
        self.assertEqual(s['obciazenia'], {'ile': 1, 'netto': -50000, 'vat': -4000, 'brutto': -54000})
        self.assertEqual((s['ile'], s['razem']), (3, {'netto': 51999, 'vat': 19000, 'brutto': 70999}))


# Kolumny liczbowe i dat do sprawdzenia porządku: klucz sortowania → wartość z wiersza
WARTOSCI = {
    'platnosci': {'netto': lambda x: x['netto'] * x['rodzaj'], 'brutto': lambda x: x['brutto'] * x['rodzaj'],
                  'vat': lambda x: (x['vat'] or 0) * x['rodzaj'], 'stawka': lambda x: x['stawka'], 'wystawienie': lambda x: x['wystawienie'],
                  'termin': lambda x: x['termin_efektywny'], 'realny': lambda x: x['realny_ef'], 'miesiac': lambda x: x['miesiac'],
                  'ksiegowanie': lambda x: x['ksiegowanie_mies'], 'rodzaj': lambda x: x['rodzaj']},
    'bank': {'data_ksiegowania': lambda x: x['data_ksiegowania'], 'data_transakcji': lambda x: x['data_transakcji'],
             'kwota': lambda x: x['kwota'], 'saldo_po': lambda x: x['saldo_po']},
    'faktury': {'netto': lambda x: x['netto'], 'vat': lambda x: x['vat'], 'brutto': lambda x: x['brutto'], 'termin': lambda x: x['termin'],
                'data_wystawienia': lambda x: x['data_wystawienia'], 'data_sprzedazy': lambda x: x['data_sprzedazy'],
                'pozostalo': lambda x: x['pozostalo']},
    'naleznosci': {'termin': lambda x: x['termin'], 'naleznosc': lambda x: x['naleznosc'], 'pozostalo': lambda x: x['pozostalo'],
                   'dni_po_terminie': lambda x: x['dni_po_terminie'], 'data_wystawienia': lambda x: x['data_wystawienia']},
    'wydatki': {'data_ksiegowania': lambda x: x['data_ksiegowania'], 'kwota': lambda x: x['kwota']},
}
BIALE_LISTY = {'platnosci': zapytania_listy.KOL_PLATNOSCI, 'bank': zapytania.KOL_OPERACJI, 'faktury': zapytania.KOL_FAKTUR,
               'naleznosci': zapytania.KOL_NALEZNOSCI, 'zakupy': zapytania.KOL_ZAKUPOW, 'wplaty': zapytania.KOL_WPLAT,
               'wydatki': zapytania.KOL_WYDATKOW}


class TestListy(unittest.TestCase):
    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane(self.srod)
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def przelicz(self):
        self.con.close()
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    def lista(self, ekran, **q):
        return zapytania_listy.lista(self.con, ekran, {k: str(v) for k, v in q.items()})

    def test_sortowanie_po_kazdej_kolumnie_po_stronie_serwera(self):
        for ekran, kolumny in BIALE_LISTY.items():
            for klucz in kolumny:
                for kier in ('rosnaco', 'malejaco'):
                    w = self.lista(ekran, sortuj=klucz, kolejnosc=kier)['wiersze']
                    f = WARTOSCI.get(ekran, {}).get(klucz)
                    if not f:
                        continue
                    wart = [f(x) for x in w]
                    pelne = [v for v in wart if v not in (None, '')]
                    self.assertEqual(pelne, sorted(pelne, reverse=kier == 'malejaco'), (ekran, klucz, kier))
                    self.assertEqual(wart[:len(pelne)], pelne, f'puste na końcu: {ekran} {klucz}')
        self.assertGreater(self.lista('platnosci')['razem'], 3)

    def test_sortowanie_tekstu_po_polsku_i_ciagle_miedzy_stronami(self):
        w = self.lista('platnosci', sortuj='kontrahent', kolejnosc='rosnaco')['wiersze']
        nazwy = [x['w_kontrahent'] for x in w]
        self.assertEqual(nazwy, sorted(nazwy, key=filtry.klucz_pl))
        calosc = [x['id'] for x in self.lista('platnosci', sortuj='netto', kolejnosc='malejaco', ile=100)['wiersze']]
        strony = [x['id'] for s in (1, 2, 3, 4) for x in self.lista('platnosci', sortuj='netto', kolejnosc='malejaco', ile=2, strona=s)['wiersze']]
        self.assertEqual(strony, calosc)

    def test_filtry_dat_na_liscie_od_dnia_stanu(self):
        self.assertEqual(zapytania.dzis(self.con), D('2026-10-13'))
        w = self.lista('platnosci', d_wystawienie='zakres:2026-09-01:2026-10-31')['wiersze']
        self.assertTrue(w and all('2026-09-01' <= x['wystawienie'] <= '2026-10-31' for x in w))
        w = self.lista('platnosci', d_miesiac='ruchomy:miesiac:1:-1')['wiersze']   # miesiąc budżetowy: poprzedni wobec dnia stanu
        self.assertTrue(w and all(x['miesiac'] == '2026-09' for x in w))
        w = self.lista('platnosci', d_realny='ruchomy:dzien:60:0')['wiersze']
        self.assertTrue(all('2026-10-13' <= x['realny_ef'] <= '2026-12-11' for x in w))
        w = self.lista('bank', d_ksiegowania='zakres:2026-09-01:2026-09-30')['wiersze']
        self.assertEqual(sorted(x['data_ksiegowania'] for x in w), ['2026-09-05', '2026-09-10', '2026-09-25', '2026-09-25'])
        self.assertEqual(self.lista('faktury', d_termin='zakres:2026-10-01:2026-10-31')['razem'], 1)
        with self.assertRaises(ValueError):
            self.lista('platnosci', d_wystawienie='ruchomy:dzien:x:0')
        self.assertEqual(self.lista('platnosci', d_nieznany='biezacy:miesiac')['razem'], self.lista('platnosci')['razem'])   # nieznany typ daty pominięty

    def test_filtry_cech_wielokrotny_wybor(self):
        wszystkie = self.lista('platnosci')
        vat = self.lista('platnosci', podstawa='Podatek VAT')
        self.assertTrue(vat['razem'] and all(x['podstawa_platnosci'] == 'Podatek VAT' for x in vat['wiersze']))
        oba = self.lista('platnosci', podstawa='Podatek VAT|Faktura (jedna)')
        self.assertEqual(oba['razem'], wszystkie['razem'])
        self.assertTrue(all(x['etap'] in ('Opłacona', 'Po terminie') for x in self.lista('platnosci', etap='Opłacona|Po terminie')['wiersze']))
        self.assertTrue(all(x['typ'] == 'plan' for x in self.lista('platnosci', typ='plan')['wiersze']))
        self.assertTrue(all(x['typ'] != 'plan' for x in self.lista('platnosci', typ='rzeczywista')['wiersze']))
        self.assertTrue(all(x['w_kontrahent'] == 'Drukarnia' for x in self.lista('platnosci', kontrahent='Drukarnia')['wiersze']))
        aid = self.con.execute("SELECT id FROM bud_arkusz WHERE nazwa = 'Opłaty 2026'").fetchone()[0]
        self.assertTrue(all(x['arkusz_id'] == aid for x in self.lista('platnosci', arkusz=aid)['wiersze']))
        o = zapytania_listy.opcje_platnosci(self.con)
        self.assertIn('Drukarnia', o['kontrahent'])
        self.assertEqual(self.lista('platnosci', rodzaj='-1', aktualnosc='Aktualna')['razem'],
                         sum(1 for x in wszystkie['wiersze'] if x['rodzaj'] == -1 and x['aktualnosc'] == 'Aktualna'))

    def test_podsumowanie_zaznaczenia_rowne_sumom(self):
        for ekran, kwoty in (('platnosci', lambda x: {'rodzaj': x['rodzaj'], 'netto': x['netto'] * x['rodzaj'],
                                                         'vat': (x['vat'] or 0) * x['rodzaj'], 'brutto': x['brutto'] * x['rodzaj']}),
                             ('bank', lambda x: {'rodzaj': 1 if x['kwota'] > 0 else -1, 'brutto': x['kwota']})):
            w = self.lista(ekran, wszystkie=1)
            self.assertEqual(len(w['wiersze']), w['razem'])
            s = filtry.podsumuj([kwoty(x) for x in w['wiersze']])
            for g in ('wplywy', 'obciazenia'):
                self.assertEqual((w['podsumowanie'][g]['ile'], w['podsumowanie'][g]['brutto']), (s[g]['ile'], s[g]['brutto']), (ekran, g))
            self.assertEqual(w['podsumowanie']['razem']['brutto'], s['razem']['brutto'])
        trzy = self.lista('platnosci', sortuj='netto', kolejnosc='malejaco')['wiersze'][:3]   # zaznaczenie 3 wierszy
        s = filtry.podsumuj([{'rodzaj': x['rodzaj'], 'netto': x['netto'] * x['rodzaj'], 'brutto': x['brutto'] * x['rodzaj']} for x in trzy])
        self.assertEqual(s['razem']['netto'], sum(x['netto'] * x['rodzaj'] for x in trzy))
        self.assertEqual(s['wplywy']['ile'] + s['obciazenia']['ile'], 3)

    def test_widoki_startowe_zapisane_zmienione_usuniete(self):
        start = [v['id'] for v in zapytania_listy.widoki(self.con, 'platnosci')]
        self.assertEqual(start[:7], ['wszystkie', 'nieoplacone', 'niewystawione', 'po_terminie', 'do_wystawienia', 'do_zaplacenia', 'zaplacone'])
        self.assertIn('najwieksze_koszty', start)
        w1 = zmiany.zapisz('widok', zmiany.sprawdz('widok', {'ekran': 'platnosci', 'id': 'w-moje', 'nazwa': 'Moje obciążenia na 2 tygodnie',
                                                                'parametry': {'rodzaj': '-1', 'd_realny': 'ruchomy:dzien:14:0'},
                                                                'kolumny': ['rodzaj', 'kontrahent', 'brutto']}))
        zmiany.zapisz('widok', zmiany.sprawdz('widok', {'ekran': 'platnosci', 'id': 'zaplacone', 'nazwa': 'Zapłacone (miesiąc)',
                                                        'parametry': {'lista': 'zaplacone', 'd_realny': 'biezacy:miesiac'}}))
        zmiany.zapisz('widok', zmiany.sprawdz('widok', {'ekran': 'platnosci', 'id': 'niewystawione', 'usun': True}))
        zmiany.zapisz('widok', zmiany.sprawdz('widok', {'ekran': 'platnosci', 'id': 'wszystkie', 'usun': True}))   # domyślny zostaje
        self.przelicz()
        v = {x['id']: x for x in zapytania_listy.widoki(self.con, 'platnosci')}
        self.assertEqual(v['w-moje']['kolumny'], ['rodzaj', 'kontrahent', 'brutto'])
        self.assertEqual(v['zaplacone']['nazwa'], 'Zapłacone (miesiąc)')
        self.assertTrue(v['zaplacone']['zmieniony'])
        self.assertNotIn('niewystawione', v)
        self.assertIn('wszystkie', v)
        menu = zapytania_listy.menu(self.con)['ekrany']['platnosci']
        for poz in menu:   # licznik w menu = liczba pozycji listy w tym widoku
            self.assertEqual(poz['ile'], self.lista('platnosci', **v[poz['id']]['parametry'])['razem'], poz['id'])
        zmiany.zapisz('cofnij', {'wpis': w1['id']})
        self.przelicz()
        self.assertNotIn('w-moje', [x['id'] for x in zapytania_listy.widoki(self.con, 'platnosci')])
        for zly in ({'ekran': 'nie-ma', 'id': 'a', 'nazwa': 'x'}, {'ekran': 'bank', 'id': 'a b', 'nazwa': 'x'},
                    {'ekran': 'bank', 'id': 'a', 'nazwa': ''}, {'ekran': 'bank', 'id': 'a', 'nazwa': 'x', 'parametry': {'strona': '2'}},
                    {'ekran': 'bank', 'id': 'a', 'nazwa': 'x', 'kolumny': ['<b>']}):
            with self.assertRaises(ValueError, msg=zly):
                zmiany.sprawdz('widok', zly)

    def test_seria_wszystko_albo_nic_i_cofniecie_calej(self):
        with self.assertRaises(ValueError):   # drugi wpis zły: odrzucona cała seria
            zmiany.sprawdz('seria', {'wpisy': [{'typ': 'do_weryfikacji', 'dane': {'obiekt': 'faktura', 'ref': 'FV2026/09/1'}},
                                               {'typ': 'do_weryfikacji', 'dane': {'obiekt': 'cokolwiek', 'ref': 'x'}}]})
        with self.assertRaises(ValueError):   # budżet ma własną serię, cel i widok nie są akcjami listy
            zmiany.sprawdz('seria', {'wpisy': [{'typ': 'bud', 'dane': {'op': 'seria', 'operacje': []}}]})
        klucz = self.con.execute('SELECT klucz FROM operacje WHERE kwota = -61500').fetchone()[0]
        seria = zmiany.zapisz('seria', zmiany.sprawdz('seria', {'wpisy': [
            {'typ': 'do_weryfikacji', 'dane': {'obiekt': 'faktura', 'ref': 'FV2026/09/1', 'powod': 'zapytać klienta'}},
            {'typ': 'do_weryfikacji', 'dane': {'obiekt': 'operacja', 'ref': klucz}}]}))
        self.przelicz()
        ozn = [x for x in zapytania.do_weryfikacji(self.con) if x['rodzaj'] == 'oznaczone']
        self.assertEqual(sorted(x['obiekt'] for x in ozn), ['faktura', 'operacja'])
        self.assertEqual(next(x for x in ozn if x['obiekt'] == 'operacja')['kwota'], -61500)
        self.assertEqual(zapytania.podsumowanie_naleznosci(self.con)['do_weryfikacji'], len(zapytania.do_weryfikacji(self.con)))
        lista = zapytania_listy.do_weryfikacji(self.con, {'grupa': 'oznaczone', 'sortuj': 'kwota', 'kolejnosc': 'rosnaco'})
        self.assertEqual([x['kwota'] for x in lista['wiersze']], [-61500, 123000])
        zmiany.zapisz('do_weryfikacji', zmiany.sprawdz('do_weryfikacji', {'obiekt': 'faktura', 'ref': 'FV2026/09/1', 'usun': True}))
        self.przelicz()
        self.assertEqual([x['obiekt'] for x in zapytania.do_weryfikacji(self.con) if x['rodzaj'] == 'oznaczone'], ['operacja'])
        zmiany.zapisz('cofnij', {'wpis': seria['id']})   # cofnięcie serii cofa każdy jej wpis
        self.przelicz()
        self.assertEqual([x for x in zapytania.do_weryfikacji(self.con) if x['rodzaj'] == 'oznaczone'], [])

    def test_oplacona_poza_bankiem_z_data(self):
        zmiany.zapisz('seria', zmiany.sprawdz('seria', {'wpisy': [
            {'typ': 'poza_bankiem', 'dane': {'faktura': 'FV2026/09/1', 'powod': 'opłacona poza bankiem: kompensata', 'data': '2026-10-02'}}]}))
        self.przelicz()
        s = self.con.execute("SELECT stan, pozostalo, ostatnia_wplata FROM faktury_stan WHERE numer = 'FV2026/09/1'").fetchone()
        self.assertEqual(tuple(s), ('opłacona poza bankiem', 0, '2026-10-02'))
        with self.assertRaises(ValueError):
            zmiany.sprawdz('poza_bankiem', {'faktura': 'FV2026/09/1', 'powod': 'x', 'data': '2026-02-30'})


class TestListyPrzezSerwer(unittest.TestCase):
    def test_get_listy_i_akcje_grupowe_jedna_seria(self):
        from finanse import serwer
        with Srodowisko() as srod:
            dane(srod)
            odbudowa.odbuduj()
            stary = konfig.PORT
            h = ThreadingHTTPServer((konfig.HOST, 0), serwer.Obsluga)
            konfig.PORT = h.server_address[1]
            threading.Thread(target=h.serve_forever, daemon=True).start()
            plik = konfig.katalog_zmian() / 'Mac-testowy.jsonl'
            linie = lambda: len(plik.read_text(encoding='utf-8').splitlines()) if plik.exists() else 0
            try:
                def zapytanie(metoda, sciezka, cialo=None):
                    c = http.client.HTTPConnection('127.0.0.1', konfig.PORT, timeout=20)
                    c.request(metoda, sciezka, body=json.dumps(cialo) if cialo is not None else None,
                              headers={'Host': f'127.0.0.1:{konfig.PORT}', 'X-Finanse': '1', 'Content-Type': 'application/json'})
                    r = c.getresponse()
                    return r.status, json.loads(r.read() or b'{}')
                s, d = zapytanie('GET', '/api/lista/platnosci?sortuj=netto&kolejnosc=rosnaco&opcje=1')
                self.assertEqual(s, 200)
                netto = [x['netto'] * x['rodzaj'] for x in d['wiersze']]
                self.assertEqual(netto, sorted(netto))
                self.assertIn('podstawa', d['opcje'])
                for e in ('bank', 'faktury', 'naleznosci', 'zakupy', 'wplaty', 'do-weryfikacji', 'wydatki'):
                    self.assertEqual(zapytanie('GET', f'/api/lista/{e}?sortuj=kwota&kolejnosc=rosnaco')[0], 200, e)
                self.assertEqual(zapytanie('GET', '/api/lista/platnosci?d_realny=ruchomy:dzien:0:0')[0], 400)
                self.assertEqual(zapytanie('GET', '/api/lista/nie-ma')[0], 400)
                self.assertEqual(zapytanie('GET', '/api/widoki?ekran=bank')[1][1]['id'], 'wplywy')
                self.assertEqual(zapytanie('GET', '/api/zakres?spec=ruchomy:miesiac:3:-1&miesieczny=1')[1]['dzis'], ['2026-09-01', '2026-11-30'])
                m = zapytanie('GET', '/api/listy/menu')[1]
                self.assertEqual(m['ekrany']['bank'][0]['ile'], 5)
                # seria z pozycją, której nie ma: nic nie trafia do pliku
                przed = linie()
                s, d = zapytanie('POST', '/api/zmiana', {'typ': 'seria', 'dane': {'wpisy': [
                    {'typ': 'do_weryfikacji', 'dane': {'obiekt': 'faktura', 'ref': 'FV2026/09/1'}},
                    {'typ': 'do_weryfikacji', 'dane': {'obiekt': 'faktura', 'ref': 'FV-NIE-MA'}}]}})
                self.assertEqual(s, 400)
                self.assertIn('wpis 2 z 2', d['blad'])
                self.assertEqual(linie(), przed)
                # zmiana dnia realnego trzech planów = jeden wpis (seria budżetu)
                zapytanie('POST', '/api/zmiana', {'typ': 'ustawienie', 'dane': {'klucz': 'planowanie', 'wartosc': 'tak'}})
                plany = [x['id'] for x in zapytanie('GET', '/api/lista/platnosci?typ=plan&sortuj=termin&kolejnosc=rosnaco')[1]['wiersze']
                         if x['etap'] != 'Opłacona'][:3]
                self.assertEqual(len(plany), 3)
                przed = linie()
                s, d = zapytanie('POST', '/api/zmiana', {'typ': 'bud', 'dane': {'op': 'seria', 'operacje': [
                    {'op': 'platnosc', 'obiekt': {'id': p, 'realny': '2026-11-20'}} for p in plany]}})
                self.assertEqual((s, linie()), (200, przed + 1))
                w = zapytanie('GET', '/api/lista/platnosci?d_realny=zakres:2026-11-20:2026-11-20')[1]['wiersze']
                self.assertEqual(sorted(x['id'] for x in w), sorted(plany))
                # opłacona poza bankiem z datą: jedna seria decyzji budżetu
                s, _ = zapytanie('POST', '/api/zmiana', {'typ': 'bud', 'dane': {'op': 'seria', 'operacje': [
                    {'op': 'decyzja_planu', 'platnosc': p, 'decyzja': 'zaplacone', 'data': '2026-10-10'} for p in plany[:2]]}})
                self.assertEqual(s, 200)
                w = zapytanie('GET', '/api/lista/platnosci?etap=Op%C5%82acona&typ=plan')[1]['wiersze']
                self.assertTrue({p for p in plany[:2]} <= {x['id'] for x in w})
            finally:
                h.shutdown()
                h.server_close()
                konfig.PORT = stary


if __name__ == '__main__':
    unittest.main()
