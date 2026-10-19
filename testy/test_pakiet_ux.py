"""Pakiet UX: cash flow jak w Budget Studio (granulacja dzień, tydzień, miesiąc; tydzień od wtorku do poniedziałku
jak w BS), saldo narastające, SUM, MAX, MIN, historia z banku, kafle pulpitu i filtr arkusza na listach. Zmyślone dane."""
import http.client
import json
import threading
import unittest
from datetime import date
from http.server import ThreadingHTTPServer

from finanse import baza, cashflow, konfig, odbudowa, zapytania_budzet
from testy.pomoc import Srodowisko
from testy.test_budzet import dane


class TestOkresyDat(unittest.TestCase):
    def test_tydzien_od_wtorku_do_poniedzialku_jak_w_bs(self):
        o = cashflow.okresy_dat(date(2026, 10, 13), date(2026, 10, 27), 'tydzien')
        self.assertEqual([(x['od'], x['do']) for x in o], [('2026-10-13', '2026-10-19'), ('2026-10-20', '2026-10-26'),
                                                           ('2026-10-27', '2026-10-27')])
        self.assertEqual(o[0]['etykieta'], '13 paź – 19 paź')   # jak na zrzucie BS z 19.10.2026
        self.assertEqual(date(2026, 10, 13).weekday(), 1)       # wtorek

    def test_tydzien_przyciety_do_poczatku_zakresu(self):
        o = cashflow.okresy_dat(date(2026, 4, 18), date(2026, 4, 28), 'tydzien')
        self.assertEqual(o[0]['etykieta'], '18 kwi – 20 kwi')   # zrzut BS z 14.10: pierwszy tydzień przycięty
        self.assertEqual(o[1]['etykieta'], '21 kwi – 27 kwi')

    def test_tydzien_od_poniedzialku_jako_parametr(self):
        o = cashflow.okresy_dat(date(2026, 10, 12), date(2026, 10, 25), 'tydzien', pierwszy=0)
        self.assertEqual([(x['od'], x['do']) for x in o], [('2026-10-12', '2026-10-18'), ('2026-10-19', '2026-10-25')])

    def test_miesiac_i_dzien(self):
        o = cashflow.okresy_dat(date(2026, 11, 15), date(2027, 2, 3), 'miesiac')
        self.assertEqual([x['etykieta'] for x in o], ["listopad '26", 'grudzień', "styczeń '27", 'luty'])
        self.assertEqual((o[0]['od'], o[0]['do'], o[-1]['do']), ('2026-11-15', '2026-11-30', '2027-02-03'))
        self.assertEqual(len(cashflow.okresy_dat(date(2026, 2, 1), date(2026, 3, 1), 'dzien')), 29)

    def test_walidacja(self):
        for g, od, do in (('kwartal', date(2026, 1, 1), date(2026, 2, 1)), ('dzien', date(2026, 2, 1), date(2026, 1, 1)),
                          ('dzien', date(2026, 1, 1), date(2032, 1, 1))):
            with self.assertRaises(ValueError):
                cashflow.okresy_dat(od, do, g)


class TestCashflowOkresy(unittest.TestCase):
    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane(self.srod)
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def test_granulacje_daja_te_same_sumy(self):
        wyniki = {g: cashflow.okresy(self.con, g, od='2026-09-01', do='2027-01-31', scenariusz='pelny') for g in cashflow.GRANULACJE}
        sumy = {g: (sum(o['wplywy'] for o in w['okresy']), sum(o['obciazenia'] for o in w['okresy']), w['sum'], w['min']['saldo'] <= w['sum'])
                for g, w in wyniki.items()}
        self.assertEqual(len(set(sumy.values())), 1, sumy)
        self.assertEqual(len(wyniki['miesiac']['okresy']), 5)

    def test_saldo_narastajace_min_max(self):
        w = cashflow.okresy(self.con, 'tydzien', od='2026-09-01', do='2026-12-31', scenariusz='pelny')
        narast = w['saldo_start']
        for o in w['okresy']:
            self.assertEqual(o['saldo'], o['wplywy'] + o['obciazenia'])
            narast += o['saldo']
            self.assertEqual(o['narastajaco'], narast)
        salda = [o['narastajaco'] for o in w['okresy']]
        self.assertEqual(w['min']['saldo'], min(salda))
        self.assertEqual(w['max']['saldo'], max(salda))
        self.assertEqual(w['okresy'][w['min']['okres']]['narastajaco'], min(salda))
        self.assertEqual(w['sum'], salda[-1])
        self.assertEqual(sum(o['pozycji'] for o in w['okresy']), len(w['pozycje']))

    def test_historia_z_banku_zgadza_sie_z_saldem_ing(self):
        w = cashflow.okresy(self.con, 'miesiac', od='2026-09-01', do='2026-10-13')
        self.assertEqual(w['zrodlo_salda'], 'bank')
        self.assertEqual(w['saldo_start'], 5162500 - 123000)          # saldo przed pierwszą operacją września
        self.assertEqual(w['sum'], 5000000)                           # saldo ING na dzień stanu
        self.assertTrue(all(z['typ'] == 'bank' for z in w['pozycje']))
        self.assertTrue(w['okresy'][-1]['biezacy'])

    def test_saldo_startowe_reczne_i_rodzaj(self):
        a = cashflow.okresy(self.con, 'tydzien', scenariusz='pelny')
        b = cashflow.okresy(self.con, 'tydzien', scenariusz='pelny', saldo_start='0')
        self.assertEqual(b['zrodlo_salda'], 'ręcznie')
        self.assertEqual(a['sum'] - b['sum'], a['saldo_start'])
        w = cashflow.okresy(self.con, 'tydzien', scenariusz='pelny', rodzaj='1')
        self.assertTrue(w['pozycje'] and all(z['kwota'] > 0 for z in w['pozycje']))
        self.assertTrue(all(o['obciazenia'] == 0 for o in w['okresy']))

    def test_domyslnie_od_dnia_stanu_i_scenariusze(self):
        o = cashflow.okresy(self.con)
        self.assertEqual((o['od'], o['granulacja']), ('2026-10-13', 'tydzien'))
        self.assertTrue(o['okresy'][0]['biezacy'])
        p = cashflow.okresy(self.con, scenariusz='pelny')
        self.assertGreater(len(p['pozycje']), len(o['pozycje']))   # pełny ma zaległości (za 7 dni)
        with self.assertRaises(ValueError):
            cashflow.okresy(self.con, scenariusz='czarny')

    def test_planowane_i_rzeczywiste_osobno(self):
        w = cashflow.okresy(self.con, 'miesiac', od='2026-10-14', do='2026-12-31', scenariusz='pelny')
        for o in w['okresy']:
            self.assertLessEqual(o['wplywy_plan'], o['wplywy'])
            self.assertGreaterEqual(o['obciazenia_plan'], o['obciazenia'])
        self.assertIn('faktura', {z['typ'] for z in w['pozycje']})

    def test_arkusz_tylko_jego_pozycje(self):
        aid = self.con.execute("SELECT id FROM bud_arkusz WHERE nazwa = 'Obsługa stała Alfa'").fetchone()[0]
        w = cashflow.okresy(self.con, 'miesiac', od='2026-10-14', do='2026-12-31', scenariusz='pelny', arkusz=aid)
        self.assertEqual(w['saldo_start'], 0)
        self.assertTrue(w['pozycje'] and all(z['arkusz_id'] == aid for z in w['pozycje']))

    def test_kafle_pulpitu_zgodne_z_listami(self):
        k = zapytania_budzet.kafle(self.con)['listy']
        self.assertEqual(set(k), set(zapytania_budzet.LISTY) - {'wszystkie'})
        for nazwa, x in k.items():
            for rodzaj, klucz in (('1', 'wplywy'), ('-1', 'obciazenia')):
                lista = zapytania_budzet.lista(self.con, nazwa, rodzaj)
                self.assertEqual((x[klucz]['ile'], x[klucz]['kwota']), (lista['razem'], lista['suma']), (nazwa, klucz))
        self.assertEqual(k['po_terminie']['wplywy']['ile'], 2)

    def test_komorki_arkusza_do_kolorow_bs(self):
        aid = self.con.execute("SELECT id FROM bud_arkusz WHERE nazwa = 'Obsługa stała Alfa'").fetchone()[0]
        w = zapytania_budzet.arkusz(self.con, aid)['wiersze']
        komorki = [k for x in w for k in x['komorki'].values()]
        self.assertTrue(all({'rzeczywiste', 'nieaktualne'} <= set(k) for k in komorki))
        self.assertTrue(any(k['rzeczywiste'] == 0 for k in komorki))   # same plany: niebieskie tło jak w BS

    def test_lista_arkusza(self):
        aid = self.con.execute("SELECT id FROM bud_arkusz WHERE nazwa = 'Obsługa stała Alfa'").fetchone()[0]
        w = zapytania_budzet.lista(self.con, 'wszystkie', arkusz=aid)
        self.assertTrue(w['razem'] > 0 and all(x['arkusz_id'] == aid for x in w['wiersze']))
        self.assertEqual(zapytania_budzet.lista(self.con, 'wszystkie', arkusz='nie-ma')['razem'], 0)


class TestCashflowPrzezSerwer(unittest.TestCase):
    def test_get_okresy_i_bledy(self):
        from finanse import serwer
        with Srodowisko() as srod:
            dane(srod)
            odbudowa.odbuduj()
            stary = konfig.PORT
            h = ThreadingHTTPServer((konfig.HOST, 0), serwer.Obsluga)
            konfig.PORT = h.server_address[1]
            threading.Thread(target=h.serve_forever, daemon=True).start()
            try:
                def get(sciezka):
                    c = http.client.HTTPConnection('127.0.0.1', konfig.PORT, timeout=10)
                    c.request('GET', sciezka, headers={'Host': f'127.0.0.1:{konfig.PORT}'})
                    r = c.getresponse()
                    return r.status, r.getheader('Content-Type'), r.read()
                s, _, b = get('/api/cashflow/okresy?granulacja=miesiac&od=2026-10-01&do=2026-12-31')
                self.assertEqual((s, len(json.loads(b)['okresy'])), (200, 3))
                self.assertEqual(get('/api/cashflow/okresy?granulacja=rok')[0], 400)
                self.assertEqual(get('/api/cashflow/okresy?od=2026-13-01')[0], 400)
                self.assertEqual(get('/api/budzet/kafle')[0], 200)
                s, typ, _ = get('/fonty/RobotoFlex.woff2')
                self.assertEqual((s, typ), (200, 'font/woff2'))
            finally:
                h.shutdown()
                h.server_close()
                konfig.PORT = stary


if __name__ == '__main__':
    unittest.main()
