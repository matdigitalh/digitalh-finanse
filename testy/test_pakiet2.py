"""Pakiet 2 (model planu jak w BS) na zmyślonych danych: wiersz jako generator planów, komórka z kwotą, worek,
umowy z proporcji, reguła dnia wystawienia, reguła nadpisań, blokady po pierwszej rzeczywistej, etap i aktualność,
dziedziczenie cech z budżetu."""
import json
import random
import unittest

from finanse import baza, budzet, konfig, odbudowa, plan, zapytania_budzet, zmiany
from testy.pomoc import Srodowisko
from testy.test_budzet import dane

DZIS = '2026-10-13'   # dzień stanu w danych testowych (ostatnia operacja ING)


class TestRegulyPlanu(unittest.TestCase):
    """Kryteria odbioru 1, 2, 3, 6, 7 wprost na generatorze (bez bazy)."""

    def test_1_faktura_dzien_10_14_dni(self):
        w = {'id': 'w1', 'podstawa': 'Faktura (jedna)', 'stawka_vat': 23, 'dzien_wystawienia': '10.', 'dni_na_platnosc': 14}
        ps = plan.generuj_komorke(w, '2025-11', 100000)
        self.assertEqual(len(ps), 1)
        p = ps[0]
        self.assertEqual((p['netto'], p['vat'], p['brutto']), (100000, 23000, 123000))
        self.assertEqual((p['wystawienie'], p['termin'], p['realny'], p['ksiegowanie'][:7]), ('2025-11-10', '2025-11-24', '2025-11-24', '2025-11'))

    def test_2_worek_wrzesien_2025(self):
        w = {'id': 'w2', 'podstawa': 'Faktura (w worku)', 'stawka_vat': 23, 'dni_na_platnosc': 0}
        ps = plan.generuj_komorke(w, '2025-09', 300000)
        self.assertEqual([p['netto'] for p in ps], [70000, 70000, 70000, 70000, 20000])
        self.assertEqual([p['wystawienie'] for p in ps], ['2025-09-01', '2025-09-08', '2025-09-15', '2025-09-22', '2025-09-29'])
        self.assertEqual({p['ksiegowanie'] for p in ps}, {'2025-09-01'})

    def test_worek_reszta_do_ostatniego_i_6_tygodni(self):
        # marzec 2026 zaczyna się w niedzielę: 6 części (1, 2–8, 9–15, 16–22, 23–29, 30–31)
        czesci = plan.podziel_worek(100001, '2026-03')
        self.assertEqual(len(czesci), 6)
        self.assertEqual(sum(k for _, k in czesci), 100001)
        self.assertEqual(czesci[0], ('2026-03-01', 3226))   # 1/31 z 1000,01 zł

    def test_worek_tydzien_od_wtorku_jak_w_eksporcie_bs(self):
        # parametr worek_pierwszy_dzien_tygodnia = 1: grudzień 2026 (1.12 wtorek) jak w eksporcie BS z 14.10.2026
        self.assertEqual(plan.podziel_worek(250000, '2026-12', 1),
                         [('2026-12-01', 56452), ('2026-12-08', 56452), ('2026-12-15', 56452), ('2026-12-22', 56452), ('2026-12-29', 24192)])
        self.assertEqual(plan.podziel_worek(250000, '2026-11', 1)[:2], [('2026-11-01', 16667), ('2026-11-03', 58333)])

    def test_3_umowa_o_prace_z_proporcji(self):
        prop = {'osoba': 590000, 'us': 60000, 'zus': 350000}   # 59 / 6 / 35 %
        self.assertEqual(plan.podziel_umowe(1500000, prop), {'osoba': 885000, 'us': 90000, 'zus': 525000})
        los = random.Random(7)
        for _ in range(100):
            kwota = los.randint(0, 10 ** 8)
            prop = {'osoba': los.randint(0, 10 ** 7), 'us': los.randint(0, 10 ** 6), 'zus': los.randint(0, 10 ** 7)}
            if not sum(prop.values()):
                continue
            wynik = plan.podziel_umowe(kwota, prop)
            self.assertEqual(sum(wynik.values()), kwota)
            self.assertTrue(all(v >= 0 for v in wynik.values()))

    def test_umowa_zero_dozwolone_i_terminy_skladowych(self):
        self.assertEqual(plan.podziel_umowe(1000000, {'osoba': 1, 'us': 0, 'zus': 0}), {'osoba': 1000000, 'us': 0, 'zus': 0})
        w = {'id': 'u', 'podstawa': 'Umowa o pracę', 'proporcje': {'osoba': 59, 'us': 6, 'zus': 35}, 'dzien_wystawienia': 'Ostatni',
             'dni_na_platnosc': 7, 'ksiegowane': False, 'stawka_vat': 23}
        ps = {p['skladowa']: p for p in plan.generuj_komorke(w, '2026-03', 1500000)}
        self.assertEqual((ps['osoba']['wystawienie'], ps['osoba']['termin']), ('2026-03-31', '2026-04-07'))
        self.assertEqual((ps['zus']['wystawienie'], ps['zus']['termin']), ('2026-03-31', '2026-05-15'))
        self.assertEqual((ps['us']['wystawienie'], ps['us']['termin']), ('2026-03-31', '2026-05-20'))
        self.assertTrue(all(p['ksiegowane'] and p['vat'] == 0 and p['stawka'] is None for p in ps.values()))   # umowa: K zawsze tak, VAT „-”
        self.assertEqual(ps['us']['spinacz'], ps['osoba']['id'])
        dzielo = plan.generuj_komorke({**w, 'podstawa': 'Umowa o dzieło', 'proporcje': {'osoba': 88, 'us': 12}}, '2026-03', 100000)
        self.assertEqual([p['skladowa'] for p in dzielo], ['osoba', 'us'])

    def test_skladowe_ida_za_data_osoby(self):
        w = {'id': 'u', 'podstawa': 'Umowa zlecenie', 'proporcje': {'osoba': 70, 'us': 10, 'zus': 20}, 'dzien_wystawienia': 'Ostatni',
             'dni_na_platnosc': 7}
        n = {plan.id_planu('u', '2026-03', 'osoba'): {'wystawienie': '2026-04-02'}}
        ps = {p['skladowa']: p for p in plan.generuj_komorke(w, '2026-03', 100000, n)}
        self.assertEqual((ps['osoba']['wystawienie'], ps['osoba']['termin']), ('2026-04-02', '2026-04-09'))
        self.assertEqual((ps['us']['wystawienie'], ps['us']['termin']), ('2026-04-02', '2026-05-20'))

    def test_reguly_dnia_wystawienia(self):
        self.assertEqual(plan.wystawienie_z_reguly('2025-04', '1. +2'), ('2025-06-01', '2025-06-01'))   # z dołu
        self.assertEqual(plan.wystawienie_z_reguly('2025-04', '20. -1'), ('2025-03-20', '2025-03-01'))  # z góry
        self.assertEqual(plan.wystawienie_z_reguly('2025-04', '10. +1 B'), ('2025-05-10', '2025-04-01'))
        self.assertEqual(plan.wystawienie_z_reguly('2025-04', 'Pierwszy'), ('2025-04-01', '2025-04-01'))
        self.assertEqual(plan.wystawienie_z_reguly('2025-02', '31.'), ('2025-02-28', '2025-02-01'))     # ponad koniec = ostatni
        self.assertEqual(plan.wystawienie_z_reguly('2025-04', 'Ostatni'), ('2025-04-30', '2025-04-01'))
        with self.assertRaises(ValueError):
            plan.regula('10. +13')
        with self.assertRaises(ValueError):
            plan.regula('dziesiąty')

    def test_6_dzien_20_kolejnego_miesiaca_wymusza_ksiegowanie_wg_wystawienia(self):
        r = plan.regula('20. +1 B')
        self.assertFalse(r['budzet'])
        self.assertEqual(plan.regula_tekst(r), '20. +1')
        self.assertEqual(plan.wystawienie_z_reguly('2025-04', '20. +1 B'), ('2025-05-20', '2025-05-01'))
        self.assertEqual(zmiany.sprawdz('bud', {'op': 'wiersz', 'obiekt': {'id': 'w', 'dzien_wystawienia': '20. +1 B'}})['obiekt']['dzien_wystawienia'], '20. +1')

    def test_7_aktualnosc(self):
        wczoraj, jutro = '2026-10-12', '2026-10-14'
        self.assertFalse(plan.aktualna_wg_bs('plan', False, wczoraj, '2026-10-30', '2026-10-30', DZIS))
        self.assertTrue(plan.aktualna_wg_bs('plan', False, DZIS, '2026-10-30', '2026-10-30', DZIS))
        # rzeczywista po terminie (termin minął), ale z przyszłym dniem realnej płatności: aktualna
        self.assertTrue(plan.aktualna_wg_bs('rzeczywista', False, '2026-09-01', '2026-10-01', jutro, DZIS))
        self.assertEqual(plan.etap_wg_bs('rzeczywista', False, '2026-10-01', DZIS), 'Po terminie')
        self.assertFalse(plan.aktualna_wg_bs('rzeczywista', False, '2026-09-01', '2026-10-01', wczoraj, DZIS))
        # opłacona zawsze aktualna: nie ma pary „nieaktualna + opłacona”
        self.assertTrue(plan.aktualna_wg_bs('rzeczywista', True, '2020-01-01', '2020-01-01', '2020-01-01', DZIS))
        self.assertEqual(plan.etap_wg_bs('plan', False, '2020-01-01', DZIS), 'Planowana')
        self.assertEqual(plan.etap_wg_bs('rzeczywista', False, '2026-12-01', DZIS), 'Niewymagana')

    def test_kwota_zero_to_ukryty_plan(self):
        for pod in ('Faktura (jedna)', 'Faktura (w worku)', 'Umowa o pracę'):
            ps = plan.generuj_komorke({'id': 'w', 'podstawa': pod, 'proporcje': {'osoba': 1}}, '2026-11', 0)
            self.assertEqual(len(ps), 1)
            self.assertTrue(ps[0]['ukryty'] and ps[0]['netto'] == 0)


class Baza(unittest.TestCase):
    """Zdarzenia na zmyślonym budżecie: arkusz testowy 2025-01 do 2026-12 dodany w apce."""

    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane(self.srod)
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        self.bud({'op': 'arkusz', 'obiekt': {'id': 'a-test', 'nazwa': 'Testowy', 'folder': 'Firma', 'kategoria': 'Koszty',
                                             'od': '2025-01', 'do': '2026-12'}})

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def bud(self, d):
        """Jak serwer: walidacja pól, próba na modelu z blokadami BS, dopiero potem zapis."""
        czyste = zmiany.sprawdz('bud', d)
        budzet.sprawdz_wpis(czyste, zmiany.wczytaj()[0], dzis=DZIS)
        return zmiany.zapisz('bud', czyste)

    def przelicz(self):
        self.con.close()
        raport = odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        return raport

    def plany(self, wid):
        return {r['id']: dict(r) for r in self.con.execute('SELECT * FROM bud_platnosc WHERE wiersz = ? ORDER BY id', (wid,))}

    def faktura(self, wid='w-f', **kw):
        self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Faktura (jedna)',
                                             'kontrahent': 'Drukarnia', 'stawka_vat': 23, 'dzien_wystawienia': '10.',
                                             'dni_na_platnosc': 14, 'metoda': 'Przelew', **kw}})


class TestKomorki(Baza):
    def test_1_komorka_tworzy_plan_z_ustawien_wiersza(self):
        self.faktura()
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2025-11', 'kwota': 100000})
        self.przelicz()
        ps = self.plany('w-f')
        self.assertEqual(list(ps), ['plan:w-f:2025-11:1'])
        p = ps['plan:w-f:2025-11:1']
        self.assertEqual((p['netto'], p['vat'], p['brutto'], p['wystawienie'], p['termin'], p['realny'], p['ksiegowanie'][:7]),
                         (100000, 23000, 123000, '2025-11-10', '2025-11-24', '2025-11-24', '2025-11'))
        self.assertEqual((p['kontrahent'], p['typ'], p['generowany'], p['ksiegowane'], p['w_cashflow']), ('Drukarnia', 'plan', 1, 1, 1))
        self.assertEqual(self.con.execute('SELECT kwota FROM bud_komorka WHERE wiersz = ?', ('w-f',)).fetchone()[0], 100000)
        # zmiana kwoty przelicza plan, pusta komórka = brak planów
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2025-11', 'kwota': 50000})
        self.przelicz()
        self.assertEqual(self.plany('w-f')['plan:w-f:2025-11:1']['vat'], 11500)
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2025-11', 'kwota': None})
        self.przelicz()
        self.assertEqual(self.plany('w-f'), {})

    def test_2_worek_przez_komorke(self):
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-w', 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Faktura (w worku)',
                                             'kontrahent': 'Meta', 'stawka_vat': 23, 'dni_na_platnosc': 0}})
        self.bud({'op': 'komorka', 'wiersz': 'w-w', 'miesiac': '2025-09', 'kwota': 300000})
        self.przelicz()
        self.assertEqual([p['netto'] for p in self.plany('w-w').values()], [70000, 70000, 70000, 70000, 20000])

    def test_3_umowa_o_prace_przez_komorke_i_blokada_pit_przed_wyplata(self):
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-u', 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Umowa o pracę',
                                             'kontrahent': 'Jan Testowy', 'dzien_wystawienia': 'Ostatni', 'dni_na_platnosc': 7,
                                             'proporcje': {'osoba': 2655021, 'us': 270096, 'zus': 1575007}}})
        self.bud({'op': 'komorka', 'wiersz': 'w-u', 'miesiac': '2026-11', 'kwota': 1500000})
        self.przelicz()
        ps = {p['skladowa']: p for p in self.plany('w-u').values()}
        self.assertEqual(sum(p['netto'] for p in ps.values()), 1500000)
        self.assertEqual({p['kontrahent'] for p in ps.values()}, {'Jan Testowy'})   # spinacz: kontrahent = osoba
        lista = zapytania_budzet.lista(self.con, q='Jan Testowy')
        self.assertEqual(sorted(x['podstawa_platnosci'] for x in lista['wiersze']),
                         ['Umowa o pracę - PIT', 'Umowa o pracę - ZUS', 'Umowa o pracę - dla pracownika'])
        # umowa: tylko obciążenie, kwoty od księgowej obowiązkowe
        with self.assertRaisesRegex(ValueError, 'obciążenie'):
            self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-u2', 'arkusz': 'a-test', 'rodzaj': 1, 'podstawa': 'Umowa zlecenie',
                                                 'proporcje': {'osoba': 1}}})
        with self.assertRaisesRegex(ValueError, 'księgowej'):
            self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-u2', 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Umowa zlecenie'}})

    def test_komorka_poza_zakresem_arkusza_odrzucona(self):
        self.faktura()
        with self.assertRaisesRegex(ValueError, 'poza zakresem arkusza'):
            self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2027-01', 'kwota': 100})

    def test_komorka_na_imporcie_zastepuje_plan_bs(self):
        wid = self.con.execute("SELECT wiersz FROM bud_platnosc WHERE id = 'bs:3'").fetchone()[0]
        self.bud({'op': 'komorka', 'wiersz': wid, 'miesiac': '2026-10', 'kwota': 200000})
        self.przelicz()
        ps = self.plany(wid)
        self.assertNotIn('bs:3', ps)
        self.assertEqual(ps[f'plan:{wid}:2026-10:1']['netto'], 200000)
        self.assertIn('bs:1', ps)   # rzeczywista nietknięta
        # cofnięcie przywraca plan z BS
        wpis = zmiany.wczytaj()[0][-1]['id']
        zmiany.zapisz('cofnij', {'wpis': wpis})
        self.przelicz()
        self.assertIn('bs:3', self.plany(wid))

    def test_seria_komorek_w_calosci_albo_wcale(self):
        self.faktura()
        ops = [{'op': 'komorka', 'wiersz': 'w-f', 'miesiac': f'2026-{m:02d}', 'kwota': 1000 * m} for m in range(1, 13)]
        self.bud({'op': 'seria', 'operacje': ops})
        self.przelicz()
        self.assertEqual(len(self.plany('w-f')), 12)
        with self.assertRaises(ValueError):
            self.bud({'op': 'seria', 'operacje': [{'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2025-01', 'kwota': 5},
                                                   {'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2030-01', 'kwota': 5}]})
        self.przelicz()
        self.assertEqual(len(self.plany('w-f')), 12)


class TestNadpisania(Baza):
    def test_4_zmiana_stawki_w_wierszu_nadpisuje_wszystkie_plany_nie_rzeczywiste(self):
        wid = self.con.execute("SELECT wiersz FROM bud_platnosc WHERE id = 'bs:2'").fetchone()[0]
        przed_rz = dict(self.con.execute("SELECT vat, brutto FROM bud_platnosc WHERE id = 'bs:1'").fetchone())
        self.bud({'op': 'komorka', 'wiersz': wid, 'miesiac': '2026-11', 'kwota': 100000})
        self.bud({'op': 'platnosc', 'obiekt': {'id': f'plan:{wid}:2026-11:1', 'stawka': 5}})   # ręczny wyjątek na planie z komórki
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'bs:2', 'stawka': 5}})                    # i na planie z BS
        self.przelicz()
        self.assertEqual(self.plany(wid)[f'plan:{wid}:2026-11:1']['vat'], 5000)
        self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'stawka_vat': 8}})
        self.przelicz()
        ps = self.plany(wid)
        self.assertEqual(ps[f'plan:{wid}:2026-11:1']['vat'], 8000)
        self.assertEqual(json.loads(ps[f'plan:{wid}:2026-11:1']['nadpisane'] or '{}'), {})
        self.assertEqual((ps['bs:2']['vat'], ps['bs:3']['vat']), (8000, 8000))
        self.assertEqual({k: ps['bs:1'][k] for k in ('vat', 'brutto')}, przed_rz)

    def test_zmiana_dnia_wystawienia_i_dni_w_wierszu(self):
        self.faktura()
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2026-11', 'kwota': 100000})
        pid = 'plan:w-f:2026-11:1'
        self.bud({'op': 'platnosc', 'obiekt': {'id': pid, 'termin': '2026-11-30', 'komentarz': 'ręcznie'}})
        self.przelicz()
        p = self.plany('w-f')[pid]
        self.assertEqual((p['termin'], p['realny'], p['komentarz']), ('2026-11-30', '2026-11-30', 'ręcznie'))
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-f', 'dzien_wystawienia': '5. +1', 'dni_na_platnosc': 7}})
        self.przelicz()
        p = self.plany('w-f')[pid]
        self.assertEqual((p['wystawienie'], p['termin'], p['realny'], p['ksiegowanie']), ('2026-12-05', '2026-12-12', '2026-12-12', '2026-12-01'))
        self.assertEqual(p['komentarz'], 'ręcznie')   # komentarz wiersza się nie zmienił, ręczny zostaje

    def test_zmiana_bez_zmiany_wartosci_nie_kasuje_wyjatku(self):
        self.faktura()
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2026-11', 'kwota': 100000})
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'plan:w-f:2026-11:1', 'stawka': 5}})
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-f', 'stawka_vat': 23, 'dni_na_platnosc': 14, 'kontrahent': 'Drukarnia'}})
        self.przelicz()
        self.assertEqual(self.plany('w-f')['plan:w-f:2026-11:1']['stawka'], 5)

    def test_nadpisania_dozwolone_tylko_tam_gdzie_w_bs(self):
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-w', 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Faktura (w worku)', 'stawka_vat': 23}})
        self.bud({'op': 'komorka', 'wiersz': 'w-w', 'miesiac': '2026-11', 'kwota': 300000})
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'plan:w-w:2026-11:t1', 'kontrahent': 'Biedronka'}})
        for zle, komunikat in (({'stawka': 8}, 'fakturze jednej'), ({'netto': 5}, 'w komórce'), ({'metoda': 'Karta'}, 'kontrahenta i komentarz')):
            with self.assertRaisesRegex(ValueError, komunikat):
                self.bud({'op': 'platnosc', 'obiekt': {'id': 'plan:w-w:2026-11:t2', **zle}})
        self.przelicz()
        self.assertEqual(self.plany('w-w')['plan:w-w:2026-11:t1']['kontrahent'], 'Biedronka')
        # data planu najwyżej 5 lat od dziś
        self.faktura()
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2026-11', 'kwota': 100})
        with self.assertRaisesRegex(ValueError, '5 lat'):
            self.bud({'op': 'platnosc', 'obiekt': {'id': 'plan:w-f:2026-11:1', 'termin': '2032-01-01'}})

    def test_kwota_planu_jednej_faktury_to_kwota_komorki(self):
        self.faktura()
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2026-11', 'kwota': 100000})
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'plan:w-f:2026-11:1', 'netto': 40000}})
        self.przelicz()
        self.assertEqual(self.con.execute("SELECT kwota FROM bud_komorka WHERE wiersz = 'w-f'").fetchone()[0], 40000)

    def test_decyzja_na_planie_z_komorki_zostaje_w_komorce(self):
        self.faktura()
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2026-09', 'kwota': 100000})
        self.bud({'op': 'decyzja_planu', 'platnosc': 'plan:w-f:2026-09:1', 'decyzja': 'przesun', 'termin': '2026-11-15'})
        self.przelicz()
        p = self.plany('w-f')['plan:w-f:2026-09:1']
        self.assertEqual((p['miesiac'], p['termin'], p['realny'], p['decyzja']), ('2026-09', '2026-11-15', '2026-11-15', 'przesunięte'))


class TestBlokady(Baza):
    def test_5_po_rzeczywistej_podstawa_i_rodzaj_zablokowane(self):
        wid = self.con.execute("SELECT wiersz FROM bud_platnosc WHERE id = 'bs:1'").fetchone()[0]   # bs:1 to rzeczywista
        with self.assertRaisesRegex(ValueError, 'podstawy nie zmienisz'):
            self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'podstawa': 'Bez faktury'}})
        with self.assertRaisesRegex(ValueError, 'rodzaju .* nie zmienisz'):
            self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'rodzaj': -1}})
        self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'metoda': 'Karta'}})   # reszta cech dalej edytowalna
        # bez rzeczywistych podstawa się zmienia, a plany liczą się od nowa
        self.faktura()
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2026-11', 'kwota': 100000})
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-f', 'podstawa': 'Bez faktury'}})
        self.przelicz()
        p = self.plany('w-f')['plan:w-f:2026-11:1']
        self.assertEqual((p['netto'], p['vat'], p['brutto']), (100000, 0, 100000))

    def test_komorka_z_rzeczywista_zablokowana(self):
        wid = self.con.execute("SELECT wiersz FROM bud_platnosc WHERE id = 'bs:1'").fetchone()[0]
        with self.assertRaisesRegex(ValueError, 'płatność rzeczywista'):
            self.bud({'op': 'komorka', 'wiersz': wid, 'miesiac': '2026-08', 'kwota': 5})

    def test_zmiana_podstawy_przelicza_plany_z_bs(self):
        wid = self.con.execute("SELECT wiersz FROM bud_platnosc WHERE id = 'bs:4'").fetchone()[0]   # same plany
        self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'podstawa': 'Faktura (w worku)'}})
        self.przelicz()
        ps = self.plany(wid)
        self.assertNotIn('bs:4', ps)
        self.assertEqual(sum(p['netto'] for p in ps.values()), 50000)
        self.assertEqual(len(ps), 5)   # lipiec 2026: 5 tygodni


class TestDziedziczenie(Baza):
    def test_8_zmiana_nazwy_arkusza_widoczna_na_listach_bez_przebudowy_planow(self):
        self.faktura()
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2026-11', 'kwota': 100000})
        self.przelicz()
        przed = self.plany('w-f')
        self.bud({'op': 'arkusz', 'obiekt': {'id': 'a-test', 'nazwa': 'Testowy 2026'}})
        self.przelicz()
        self.assertEqual({k: {x: v[x] for x in ('netto', 'wystawienie', 'termin')} for k, v in self.plany('w-f').items()},
                         {k: {x: v[x] for x in ('netto', 'wystawienie', 'termin')} for k, v in przed.items()})
        lista = zapytania_budzet.lista(self.con, q='Drukarnia')
        self.assertIn('Testowy 2026', {x['arkusz'] for x in lista['wiersze']})
        karta = zapytania_budzet.platnosc(self.con, 'plan:w-f:2026-11:1')
        self.assertEqual((karta['platnosc']['arkusz'], karta['platnosc']['folder']), ('Testowy 2026', 'Firma'))

    def test_ksiegowane_poza_rentownoscia_i_flagi_z_wiersza(self):
        from finanse import rentownosc
        self.faktura(ksiegowane=False, w_cashflow=False, split=True)
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2026-11', 'kwota': 100000})
        self.przelicz()
        p = self.plany('w-f')['plan:w-f:2026-11:1']
        self.assertEqual((p['ksiegowane'], p['w_cashflow']), (0, 0))
        self.assertEqual(self.con.execute("SELECT split FROM bud_wiersz WHERE id = 'w-f'").fetchone()[0], 1)
        ark = {a['id']: a for a in rentownosc.arkusze(self.con)}
        self.assertEqual(ark.get('a-test', {}).get('plan_koszt', 0), 0)

    def test_etap_i_aktualnosc_w_bazie(self):
        self.faktura()
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2026-09', 'kwota': 100})
        self.bud({'op': 'komorka', 'wiersz': 'w-f', 'miesiac': '2026-12', 'kwota': 100})
        self.przelicz()
        stan = {r['platnosc']: (r['etap_wg_bs'], r['aktualnosc']) for r in self.con.execute('SELECT * FROM bud_stan')}
        self.assertEqual(stan['plan:w-f:2026-09:1'], ('Planowana', 'Nieaktualna'))
        self.assertEqual(stan['plan:w-f:2026-12:1'], ('Planowana', 'Aktualna'))
        self.assertEqual(stan['bs:1'][0], 'Opłacona')   # rzeczywista opłacona z banku


class TestWalidacja(unittest.TestCase):
    def test_pola_wiersza_pakietu_2(self):
        d = zmiany.sprawdz('bud', {'op': 'wiersz', 'obiekt': {'id': 'w', 'podstawa': 'Umowa o pracę', 'split': True, 'kup': 50,
                                                              'proporcje': {'osoba': 100, 'us': 0, 'zus': 0}, 'dzien_wystawienia': '9 +1 b'}})
        self.assertEqual(d['obiekt']['dzien_wystawienia'], '9. +1 B')
        for zle in ({'proporcje': {'osoba': 0}}, {'proporcje': {'inna': 5}}, {'kup': 30}, {'podstawa': 'Umowa B2B'},
                    {'dzien_wystawienia': '10. +15'}):
            with self.assertRaises(ValueError, msg=str(zle)):
                zmiany.sprawdz('bud', {'op': 'wiersz', 'obiekt': {'id': 'w', **zle}})
        self.assertEqual(zmiany.sprawdz('bud', {'op': 'komorka', 'wiersz': 'w', 'miesiac': '2026-11', 'kwota': None})['kwota'], None)
        for zle in ({'op': 'komorka', 'wiersz': 'w', 'miesiac': '2026-13', 'kwota': 1}, {'op': 'komorka', 'wiersz': 'w', 'miesiac': '2026-11', 'kwota': -1},
                    {'op': 'komorka', 'miesiac': '2026-11', 'kwota': 1}, {'op': 'komorka', 'wiersz': 'w', 'miesiac': '2026-11', 'kwota': 1, 'x': 1}):
            with self.assertRaises(ValueError, msg=str(zle)):
                zmiany.sprawdz('bud', zle)


if __name__ == '__main__':
    unittest.main()
