"""Pakiet 8 (VAT, podatki, wynagrodzenia) na zmyślonych danych: arkusz systemowy „Opłaty urzędowe”, prognoza VAT
z przenoszeniem nadpłaty, kwota od biura zamraża okres, CIT narastająco, wiersze podatkowe z BS jako kwoty od biura,
kalendarz PIT-4 i ZUS, prognoza salda rachunku VAT, przelewy z banku przypisane do okresów, blokady w serwerze."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from finanse import baza, budzet, cashflow, konfig, odbudowa, podatki, zapytania_budzet, zmiany
from testy.pomoc import VAT, Srodowisko, operacja, zapisz_ing
from testy.test_budzet import dane

DZIS = '2026-10-13'   # dzień stanu w danych testowych (ostatnia operacja ING)


def bs_pusty():
    return {'od_biura': {}, 'prognoza': {}}


class TestRdzen(unittest.TestCase):
    """Reguły bez bazy: okresy, przenoszenie nadpłaty, zamrożenie, CIT narastająco, przelewy z banku."""

    def test_okresy_i_terminy(self):
        self.assertEqual(podatki.okresy('2026-02', '2026-07', 3), [('2026-01', '2026-03'), ('2026-04', '2026-06'), ('2026-07', '2026-09')])
        self.assertEqual(podatki.okresy('2026-11', '2027-01', 1), [('2026-11', '2026-11'), ('2026-12', '2026-12'), ('2027-01', '2027-01')])
        self.assertEqual(podatki._dzien_po('2026-10', 25), '2026-11-25')
        self.assertEqual(podatki._dzien_po('2026-12', 20), '2027-01-20')
        self.assertEqual(podatki.nazwa_okresu('2026-07', '2026-09'), 'III kwartał 2026')

    def test_nadplata_przechodzi_dalej_i_zwrot_na_koncu(self):
        ust = dict(podatki.USTAWIENIA_DOMYSLNE)
        okr = podatki.okresy('2026-10', '2026-12', 1)
        lista, zwrot = podatki.licz_vat(okr, {'2026-10': -50000, '2026-11': 30000, '2026-12': -10000}, ust, bs_pusty(), {})
        self.assertEqual([x['plan'] for x in lista], [0, 0, 0])            # 300 zł z października zjada listopad
        self.assertEqual([x['saldo_po'] for x in lista], [-50000, -20000, -30000])
        self.assertEqual((zwrot['plan'], zwrot['termin'], zwrot['wystawienie']), (-30000, '2027-06-14', '2027-04-30'))
        # bez przenoszenia: nadpłata każdego okresu to zwrot 60 dni po terminie
        ust['vat_przenoszenie'] = 'nie'
        lista, zwrot = podatki.licz_vat(okr, {'2026-10': -50000, '2026-11': 30000}, ust, bs_pusty(), {})
        self.assertEqual([x['plan'] for x in lista], [-50000, 30000, 0])
        self.assertEqual(lista[0]['termin'], '2027-01-24')
        self.assertIsNone(zwrot)

    def test_kwota_od_biura_zamraza_i_zasila_saldo(self):
        ust = dict(podatki.USTAWIENIA_DOMYSLNE)
        okr = podatki.okresy('2026-10', '2026-12', 1)
        vat_m = {'2026-10': 99999, '2026-11': 40000, '2026-12': 10000}
        r = {('vat', '2026-10'): {'kwota': 25000, 'kierunek': 'przeniesienie'}}   # biuro: nadwyżka 250 zł do przeniesienia
        lista, _ = podatki.licz_vat(okr, vat_m, ust, bs_pusty(), r)
        self.assertEqual([(x['typ'], x['plan']) for x in lista], [('rzeczywista', 0), ('plan', 15000), ('plan', 10000)])
        # eksport BS daje kwotę od biura, wpis w apce ją nadpisuje, „usun” odmraża także kwotę z BS
        bs = {'od_biura': {('vat', '2026-10'): {'kwota': 70000, 'kierunek': 'zaplata', 'zrodlo': 'Budget Studio'}}, 'prognoza': {}}
        self.assertEqual(podatki.licz_vat(okr, vat_m, ust, bs, {})[0][0]['plan'], 70000)
        self.assertEqual(podatki.licz_vat(okr, vat_m, ust, bs, {('vat', '2026-10'): {'kwota': 80000, 'kierunek': 'zaplata'}})[0][0]['plan'], 80000)
        self.assertEqual(podatki.licz_vat(okr, vat_m, ust, bs, {('vat', '2026-10'): {'odmrozony': True}})[0][0]['plan'], 99999)
        # saldo startowe z ustawień (nadwyżka sprzed pierwszego okresu)
        ust['vat_saldo_startowe'] = 50000
        self.assertEqual(podatki.licz_vat(okr, vat_m, ust, bs_pusty(), {})[0][0]['plan'], 49999)

    def test_cit_narastajaco_kwartalnie_i_zwrot_roczny(self):
        ust = dict(podatki.USTAWIENIA_DOMYSLNE)   # kwartał, 19%, grosze
        okr = {'2026': podatki.okresy('2026-01', '2026-12', 3)}
        netto_m = {'2026-02': 10000000, '2026-05': 5000000, '2026-08': -8000000, '2026-11': 1000000}
        bs = {'od_biura': {('cit', '2026-01'): {'kwota': 2000000, 'kierunek': 'zaplata', 'zrodlo': 'Budget Studio'}}, 'prognoza': {}}
        kw, lata = podatki.licz_cit(okr, netto_m, ust, bs, {})
        # I kw. od biura 20 000 zł; H1: 150 000 × 19% = 28 500 − 20 000 = 8 500; III kw.: 70 000 × 19% = 13 300 < 28 500: 0
        self.assertEqual([x['plan'] for x in kw], [2000000, 850000, 0, 0])
        self.assertEqual(kw[1]['termin'], '2026-07-20')
        y = lata[0]
        self.assertEqual((y['podatek_roku'], y['zaliczki'], y['plan']), (1520000, 2850000, -1330000))   # 80 000 × 19%, zwrot
        self.assertEqual(y['termin'], '2027-06-14')
        # pełne złote i brak stawki
        self.assertEqual(podatki._podatek(123456, 19, 'zl'), 23500)   # 1 234,56 × 19% = 234,57 → 235 zł
        ust['cit_stawka'] = None
        kw, lata = podatki.licz_cit(okr, netto_m, ust, bs_pusty(), {})
        self.assertEqual({x['plan'] for x in kw} | {lata[0]['plan']}, {0})

    def test_okres_przelewu_z_tytulu(self):
        self.assertEqual(podatki.okres_przelewu('vat', '/TI/N1/OKR/26M08/SFP/VAT-7', '2026-09-25'), '2026-08')
        # tytuł z miesiącem płatności to pomyłka: przelew 25.06 z „26M06” to VAT za maj
        self.assertEqual(podatki.okres_przelewu('vat', '/TI/N1/OKR/26M06/SFP/VAT-7', '2026-06-25'), '2026-05')
        self.assertEqual(podatki.okres_przelewu('cit', '/TI/N1/OKR/26K01/SFP/CIT-8', '2026-04-22'), '2026-01')
        self.assertEqual(podatki.okres_przelewu('vat', 'VAT za wrzesien', '2026-10-24'), '2026-09')
        self.assertEqual(podatki.okres_przelewu('zus', 'DRA 01/08', '2026-09-14'), '2026-08')
        self.assertEqual(podatki.rodzaj_przelewu('Urząd Skarbowy', '/OKR/25M12/SFP/PIT-4 //R/TXT/VAT-7'), 'pit4')
        self.assertEqual(podatki.rodzaj_przelewu('URZĄD SKARBOWY', 'Zwrot z podatku CIT za rok 2025'), 'cit')
        self.assertIsNone(podatki.rodzaj_przelewu('Drukarnia', 'VAT'))

    def test_walidacja_wpisow(self):
        self.assertEqual(zmiany.sprawdz('danina', {'danina': 'vat', 'okres': '2026-09', 'kwota': 631200}),
                         {'danina': 'vat', 'okres': '2026-09', 'kwota': 631200, 'kierunek': 'zaplata'})
        for zle in ({'danina': 'pit', 'okres': '2026-09', 'kwota': 1}, {'danina': 'vat', 'okres': '2026-9', 'kwota': 1},
                    {'danina': 'cit', 'okres': '2026-07', 'kwota': 1, 'kierunek': 'przeniesienie'},
                    {'danina': 'vat', 'okres': '2026-09'}, {'danina': 'vat', 'okres': '2026-09', 'kwota': -5},
                    {'danina': 'vat', 'okres': '2026-09', 'kwota': 1, 'obcy': 1}):
            with self.assertRaises(ValueError, msg=zle):
                zmiany.sprawdz('danina', zle)
        u = zmiany.sprawdz('ustawienie', {'klucz': 'podatki', 'wartosc': {'cit_stawka': 9, 'cit_okres': 'miesiac'}})
        self.assertEqual(u['wartosc'], {'cit_stawka': 9, 'cit_okres': 'miesiac'})
        for zle in ({'cit_stawka': 15}, {'vat_dzien': 31}, {'zwrot_termin': '06-31'}, {'nieznane': 1}, {}):
            with self.assertRaises(ValueError, msg=zle):
                zmiany.sprawdz('ustawienie', {'klucz': 'podatki', 'wartosc': zle})
        with self.assertRaisesRegex(ValueError, 'arkusz systemowy'):
            podatki.sprawdz_bud({'op': 'komorka', 'wiersz': 'sys:vat:2026', 'miesiac': '2026-10', 'kwota': 1})
        with self.assertRaisesRegex(ValueError, 'arkusz systemowy'):
            podatki.sprawdz_bud({'op': 'seria', 'operacje': [{'op': 'platnosc', 'obiekt': {'id': 'sys:vat:2026-10', 'realny': '2026-11-20'}}]})
        with self.assertRaisesRegex(ValueError, 'inną podstawę'):
            podatki.sprawdz_bud({'op': 'wiersz', 'obiekt': {'id': 'w', 'podstawa': 'Podatek VAT'}})
        with self.assertRaisesRegex(ValueError, 'najwcześniej 2026-10-01'):
            podatki.sprawdz_wpis({'danina': 'vat', 'okres': '2026-09', 'realny': '2026-09-30'}, [], DZIS)
        with self.assertRaisesRegex(ValueError, 'kwartału'):
            podatki.sprawdz_wpis({'danina': 'cit', 'okres': '2026-08', 'kwota': 1, 'kierunek': 'zaplata'}, [], DZIS)


class Baza(unittest.TestCase):
    """Budżet z danych testowych (eksport BS z VAT za sierpień jako kwotą od biura) i arkusz dodany w apce."""

    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane(self.srod)
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        self.bud({'op': 'arkusz', 'obiekt': {'id': 'a-test', 'nazwa': 'Testowy', 'folder': 'Firma', 'kategoria': 'Koszty',
                                             'od': '2026-01', 'do': '2026-12'}})

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def bud(self, d):
        czyste = zmiany.sprawdz('bud', d)
        podatki.sprawdz_bud(czyste)
        budzet.sprawdz_wpis(czyste, zmiany.wczytaj()[0], dzis=DZIS)
        return zmiany.zapisz('bud', czyste)

    def danina(self, d):
        czyste = zmiany.sprawdz('danina', d)
        podatki.sprawdz_wpis(czyste, zmiany.wczytaj()[0], DZIS)
        return zmiany.zapisz('danina', czyste)

    def przelicz(self):
        self.con.close()
        raport = odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        return raport

    def wiersz(self, wid, rodzaj, kwoty: dict, stawka=23, **kw):
        self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'arkusz': 'a-test', 'rodzaj': rodzaj, 'podstawa': kw.pop('podstawa', 'Faktura (jedna)'),
                                             'kontrahent': kw.pop('kontrahent', 'Klient'), 'stawka_vat': stawka,
                                             'dzien_wystawienia': '10.', 'dni_na_platnosc': 14, **kw}})
        for m, k in kwoty.items():
            self.bud({'op': 'komorka', 'wiersz': wid, 'miesiac': m, 'kwota': k})

    def platnosc(self, pid):
        r = self.con.execute('SELECT * FROM bud_platnosc WHERE id = ?', (pid,)).fetchone()
        return dict(r) if r else None

    def okres(self, danina, okres):
        return next(x for x in podatki.widok(self.con)[danina] if x['okres'] == okres)


class TestArkuszSystemowy(Baza):
    def test_1_vat_1840_zl_z_terminem_25_11_w_cash_flow(self):
        self.wiersz('w-s', 1, {'2026-10': 1000000})    # faktura sprzedaży 10 000 zł netto, 23%
        self.wiersz('w-k', -1, {'2026-10': 200000})    # koszt 2 000 zł netto, 23%
        self.przelicz()
        p = self.platnosc('sys:vat:2026-10')
        self.assertEqual((p['netto'], p['brutto'], p['rodzaj'], p['typ'], p['wystawienie'], p['termin'], p['realny']),
                         (184000, 184000, -1, 'plan', '2026-11-25', '2026-11-25', '2026-11-25'))
        a = self.con.execute("SELECT a.folder, a.nazwa FROM bud_arkusz a JOIN bud_wiersz w ON w.arkusz = a.id WHERE w.id = ?",
                             (p['wiersz'],)).fetchone()
        self.assertEqual(tuple(a), ('System', 'Opłaty urzędowe 2026'))
        pozycje = [z for t in cashflow.prognoza(self.con)['tygodnie'] for z in t['pozycje'] if z['data'] == '2026-11-25']
        self.assertIn(-184000, [z['kwota'] for z in pozycje])
        # podatki nie wchodzą do rentowności arkuszy (Księgowane = nie), a zero nie robi zaległości
        self.assertEqual(p['ksiegowane'], 0)
        self.assertIsNone(self.platnosc('sys:vat:2026-11'))

    def test_2_nadplata_z_pazdziernika_pomniejsza_listopad(self):
        self.wiersz('w-k', -1, {'2026-10': 1000000})   # naliczony 2 300 zł w październiku, sprzedaży brak
        self.wiersz('w-s', 1, {'2026-11': 2000000})    # należny 4 600 zł w listopadzie
        self.przelicz()
        self.assertIsNone(self.platnosc('sys:vat:2026-10'))
        self.assertEqual(self.platnosc('sys:vat:2026-11')['netto'], 460000 - 230000)
        x = self.okres('vat', '2026-11')
        self.assertEqual((x['model'], x['przeniesienie']), (460000, -230000))

    def test_3_kwota_od_biura_nie_zmienia_sie_po_nowym_planie(self):
        self.wiersz('w-s', 1, {'2026-10': 1000000})
        self.danina({'danina': 'vat', 'okres': '2026-10', 'kwota': 150000, 'komentarz': 'JPK od biura'})
        self.przelicz()
        self.assertEqual((self.platnosc('sys:vat:2026-10')['netto'], self.platnosc('sys:vat:2026-10')['typ']), (150000, 'rzeczywista'))
        self.wiersz('w-s2', 1, {'2026-10': 500000})
        self.przelicz()
        p = self.platnosc('sys:vat:2026-10')
        self.assertEqual((p['netto'], p['typ'], p['komentarz']), (150000, 'rzeczywista', 'JPK od biura'))
        x = self.okres('vat', '2026-10')
        self.assertEqual((x['prognoza'], x['od_biura']['kwota'], x['roznica']), (345000, 150000, 195000))
        # dzień realny zmienia się bez odmrażania; „usun” wraca do prognozy
        self.danina({'danina': 'vat', 'okres': '2026-10', 'realny': '2026-11-20'})
        self.przelicz()
        self.assertEqual((self.platnosc('sys:vat:2026-10')['realny'], self.platnosc('sys:vat:2026-10')['netto']), ('2026-11-20', 150000))
        self.danina({'danina': 'vat', 'okres': '2026-10', 'usun': True})
        self.przelicz()
        self.assertEqual((self.platnosc('sys:vat:2026-10')['netto'], self.platnosc('sys:vat:2026-10')['typ']), (345000, 'plan'))

    def test_4_faktura_0_procent_nie_zmienia_vat(self):
        self.wiersz('w-s', 1, {'2026-10': 1000000})
        self.przelicz()
        przed = self.platnosc('sys:vat:2026-10')['netto']
        self.wiersz('w-g', -1, {'2026-10': 853010}, stawka=0, kontrahent='Google Ads')   # import usług: 0%
        self.przelicz()
        self.assertEqual(self.platnosc('sys:vat:2026-10')['netto'], przed)

    def test_5_ksiegowane_off_poza_vat_i_cit(self):
        self.wiersz('w-s', 1, {'2026-10': 1000000})
        self.przelicz()
        przed = (self.platnosc('sys:vat:2026-10')['netto'], self.okres('cit', '2026-10')['podstawa'])
        self.wiersz('w-d', -1, {'2026-10': 5000000}, ksiegowane=False, kontrahent='Wspólnik')
        self.wiersz('w-b', 1, {'2026-10': 7000000}, ksiegowane=False, podstawa='Bez faktury', stawka=None, kontrahent='Pożyczka')
        self.przelicz()
        self.assertEqual((self.platnosc('sys:vat:2026-10')['netto'], self.okres('cit', '2026-10')['podstawa']), przed)

    def test_6_saldo_rachunku_vat_rosnie_o_mpp_i_maleje_o_przelew_vat(self):
        # tylko VAT z rachunku VAT (ustawienie), żeby zaliczka CIT z danych testowych nie mieszała w saldzie
        zmiany.zapisz('ustawienie', zmiany.sprawdz('ustawienie', {'klucz': 'podatki', 'wartosc': {'rachunek_vat_na': 'vat'}}))
        zapisz_ing(self.srod.dane, 'ing_historia_vat_2026-10-13.csv', [
            operacja('2026-10-13', '100,00', '3000,00', 'DIGITALH SP. Z O.O.', '/VAT/100,00/IDC/1/INV/FV1', rachunek=VAT, ref='MPP1')])
        self.wiersz('w-s', 1, {'2026-10': 1000000}, split=True, kontrahent='Klient MPP')   # 2 300 zł VAT na rachunek VAT
        self.przelicz()
        rv = podatki.widok(self.con)['rachunek_vat']
        self.assertEqual(rv['saldo_start'], 300000)
        z = [(x['data'], x['rodzaj'], x['kwota'], x['z_glownego'], x['saldo']) for x in rv['zdarzenia']]
        # wpływ MPP w dniu realnym planu (10.10 + 14 dni), przelew VAT 25.11: 2 300 zł z rachunku VAT
        self.assertIn(('2026-10-24', 'plan MPP', 230000, 0, 530000), z)
        self.assertIn(('2026-11-25', 'VAT', -230000, 0, 300000), z)
        self.assertEqual(rv['vat_najblizszy']['saldo_przed'], 530000)
        # przelew VAT większy niż saldo: resztę dokłada rachunek główny
        self.wiersz('w-s2', 1, {'2026-10': 3000000}, kontrahent='Klient bez MPP')   # bez MPP w historii: VAT idzie na główny
        self.przelicz()
        v = podatki.widok(self.con)['rachunek_vat']['vat_najblizszy']
        self.assertEqual((v['kwota'], v['z_rachunku_vat'], v['z_glownego']), (-920000, -530000, -390000))


class TestDaneZBudgetStudio(Baza):
    def test_wiersze_podatkowe_bs_to_kwoty_od_biura_i_przelewy_z_banku(self):
        # eksport BS: VAT za sierpień 2 × 500 zł (to samo ID) jako opłacony; w banku 600 + 400 z „/OKR/26M08/”
        self.assertIsNone(self.con.execute("SELECT 1 FROM bud_arkusz WHERE nazwa = 'Opłaty 2026'").fetchone())
        self.assertIsNone(self.con.execute("SELECT 1 FROM bud_wiersz WHERE podstawa = 'Podatek VAT' AND arkusz NOT LIKE 'sys:%'").fetchone())
        x = self.okres('vat', '2026-08')
        self.assertEqual((x['od_biura']['kwota'], x['od_biura']['zrodlo'], x['plan'], x['zaplacono'], x['status']),
                         (100000, 'Budget Studio', 100000, 100000, 'zapłacone'))
        self.assertEqual([p['kwota'] for p in x['przelewy']], [60000, 40000])
        self.assertEqual(zapytania_budzet.platnosc(self.con, 'sys:vat:2026-08')['platnosc']['etap'], 'Opłacona')
        # wiersze, arkusze i płatności budżetu w raporcie bez arkusza systemowego (jak w eksporcie BS)
        self.assertEqual(self.przelicz()['budzet'], {'arkuszy': 4, 'wierszy': 4, 'platnosci': 7})
        w = podatki.widok(self.con)
        self.assertEqual(w['zastapione_arkusze_bs'], ['Opłaty 2026'])
        self.assertEqual(w['horyzont'], ['2026-01', '2027-09'])
        self.assertEqual(w['kontrola']['okresow'], 8)   # styczeń do sierpnia: termin minął (wrzesień płatny 25.10)

    def test_cit_z_budzetu_i_pit_zus_z_umow(self):
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-u', 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Umowa o pracę',
                                             'kontrahent': 'Jan Testowy', 'dzien_wystawienia': 'Ostatni', 'dni_na_platnosc': 7,
                                             'proporcje': {'osoba': 590000, 'us': 60000, 'zus': 350000}}})
        self.bud({'op': 'komorka', 'wiersz': 'w-u', 'miesiac': '2026-11', 'kwota': 1500000})
        self.przelicz()
        w = podatki.widok(self.con)
        # wynagrodzenie za listopad wypłacone 7.12: PIT-4 i ZUS za grudzień (miesiąc wypłaty), płatne 20. i 15. stycznia
        lis = next(x for x in w['wynagrodzenia'] if x['okres'] == '2026-12')
        self.assertEqual((lis['pit4_plan'], lis['zus_plan'], lis['pit4_termin'], lis['zus_termin']), (90000, 525000, '2027-01-20', '2027-01-15'))
        # CIT: eksport BS bez miesiąca księgowania, więc miesiąc z dnia wystawienia: lipiec 500, wrzesień 1 000 − 500,
        # październik 1 000, listopad 1 000; umowa 15 000 zł w listopadzie daje stratę: zaliczka IV kw. 0, III kw. wraca po roku
        iii, iv = self.okres('cit', '2026-07'), self.okres('cit', '2026-10')
        self.assertEqual((iii['podstawa'], iii['plan']), (100000, 19000))
        self.assertEqual((iv['podstawa'], iv['plan']), (200000 - 1500000, 0))
        rok = next(y for y in w['cit_roczny'] if y['okres'] == '2026')
        self.assertEqual((rok['podatek_roku'], rok['zaliczki'], rok['plan']), (0, 19000, -19000))
        self.assertEqual(self.platnosc('sys:cit-rok:2026')['rodzaj'], 1)

    def test_ustawienia_z_wpisu(self):
        zmiany.zapisz('ustawienie', zmiany.sprawdz('ustawienie', {'klucz': 'podatki', 'wartosc': {'cit_okres': 'miesiac', 'cit_stawka': 9}}))
        self.przelicz()
        w = podatki.widok(self.con)
        self.assertEqual((w['ustawienia']['cit_okres'], w['ustawienia']['cit_stawka']), ('miesiac', 9))
        self.assertEqual(self.okres('cit', '2026-07')['plan'], 4500)   # lipiec: 500 zł × 9%
        self.assertEqual(self.okres('cit', '2026-07')['termin'], '2026-08-20')
        self.assertEqual(self.okres('cit', '2026-09')['plan'], 4500)   # narastająco 1 000 zł × 9% − 45 zł z lipca


class TestSerwer(unittest.TestCase):
    def test_bud_na_arkuszu_systemowym_odrzucony_danina_zapisana(self):
        from finanse import serwer
        with Srodowisko() as srod:
            dane(srod)
            zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
            odbudowa.odbuduj()
            stary = konfig.PORT
            h = ThreadingHTTPServer((konfig.HOST, 0), serwer.Obsluga)
            konfig.PORT = h.server_address[1]
            threading.Thread(target=h.serve_forever, daemon=True).start()
            try:
                def wyslij(typ, d, metoda='POST', sciezka='/api/zmiana'):
                    c = http.client.HTTPConnection('127.0.0.1', konfig.PORT, timeout=10)
                    c.request(metoda, sciezka, body=json.dumps({'typ': typ, 'dane': d}) if metoda == 'POST' else None,
                              headers={'Host': f'127.0.0.1:{konfig.PORT}', 'X-Finanse': '1', 'Content-Type': 'application/json'})
                    r = c.getresponse()
                    return r.status, json.loads(r.read() or b'{}')
                kod, w = wyslij('bud', {'op': 'platnosc', 'obiekt': {'id': 'sys:vat:2026-08', 'realny': '2026-09-20'}})
                self.assertEqual(kod, 400)
                self.assertIn('arkusz systemowy', w['blad'])
                kod, w = wyslij('danina', {'danina': 'vat', 'okres': '2026-09', 'realny': '2026-09-15'})
                self.assertEqual(kod, 400)
                kod, w = wyslij('danina', {'danina': 'vat', 'okres': '2026-09', 'kwota': 12300, 'kierunek': 'zaplata'})
                self.assertEqual(kod, 200, w)
                kod, w = wyslij(None, None, 'GET', '/api/podatki')
                x = next(x for x in w['vat'] if x['okres'] == '2026-09')
                self.assertEqual((x['plan'], x['od_biura']['zrodlo'], x['status']), (12300, 'biuro (wpis w apce)', 'kwota od biura'))
            finally:
                h.shutdown()
                h.server_close()
                konfig.PORT = stary


if __name__ == '__main__':
    unittest.main()
