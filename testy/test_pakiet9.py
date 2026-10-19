"""Pakiet 9 (cash flow jak w BS, umowy w cash flow) na zmyślonych danych: domyślnie tylko płatności budżetu (bez szacunku
kosztów i należności spoza budżetu), oś po dniu realnej płatności, etap i aktualność jak w BS, pozycje „z umowy” dla umowy
na czas nieokreślony, brak ich po końcu umowy na czas określony (plany zostają z ostrzeżeniem), scenariusz „klienci
odchodzą” z wypowiedzeniem na koniec miesiąca, zgodność sum z eksportem BS, cash flow arkusza bez PIT i ZUS, lista
płatności wycinka, rejestr umów powiązany z folderem i arkuszami, zapisane widoki cash flow."""
import csv
import unittest

from finanse import baza, budzet, cashflow, konfig, odbudowa, podatki, umowy, zapytania_budzet, zapytania_listy, zmiany
from testy.pomoc import Srodowisko
from testy.test_budzet import KOLUMNY, bs, dane

DZIS = '2026-10-13'   # dzień stanu w danych testowych (ostatnia operacja ING)


class Baza(unittest.TestCase):
    """Dane z test_budzet (Alfa z eksportu BS) + dwóch klientów dodanych w apce: Gamma (plany do listopada, umowa na czas
    nieokreślony) i Delta (plany do grudnia, umowa na czas określony do końca roku, wpisana starym sposobem: sam klient)."""

    def setUp(self):
        self.srod = Srodowisko().__enter__()
        dane(self.srod)
        # rzeczywista z BS „Niewymagana” (nieopłacona przed terminem, jak przyszły ZUS z umowy): BS liczy ją w cash flow
        p = self.srod.dane / 'Budget Studio' / 'budget_studio_2026-10-13.csv'
        with open(p, 'a', encoding='utf-8', newline='') as f:
            csv.DictWriter(f, fieldnames=KOLUMNY, delimiter='\t').writerow(
                bs('7', '-1', 'Niewymagana', 'Bez faktury', 'ZUS', '-300,00', '2026-10', '2026-11-15', 'Obsługa stała Alfa', 'Alfa',
                   'Obsługa stała', nr='DRA 10', realny='2026-11-15'))
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        for aid, folder in (('a-gamma', 'Gamma'), ('a-delta', 'Delta')):
            self.bud({'op': 'arkusz', 'obiekt': {'id': aid, 'nazwa': f'Obsługa {folder}', 'folder': folder, 'kategoria': 'Obsługa stała',
                                                 'od': '2026-01', 'do': '2027-12'}})
        self.wiersz('w-g', 'a-gamma', 1, {'2026-10': 100000, '2026-11': 100000}, kontrahent='Gamma', dni_na_platnosc=14)
        self.wiersz('w-d', 'a-delta', 1, {'2026-10': 200000, '2026-11': 200000, '2026-12': 200000}, kontrahent='Delta',
                    dzien_wystawienia='Ostatni', dni_na_platnosc=7)
        self.przelicz()
        self.umowa({'id': 'u-g', 'klient': 'Gamma', 'folder': 'Gamma', 'rodzaj': 'nieokreslony', 'wypowiedzenie_mies': 3,
                    'koniec_miesiaca': True, 'wartosc_mies': 100000})
        self.umowa({'id': 'u-d', 'klient': 'DELTA sp. z o.o.', 'rodzaj': 'okreslony', 'do': '2026-12-31', 'wypowiedzenie_mies': 1,
                    'wartosc_mies': 200000})
        self.przelicz()

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def bud(self, d):
        czyste = zmiany.sprawdz('bud', d)
        podatki.sprawdz_bud(czyste)
        budzet.sprawdz_wpis(czyste, zmiany.wczytaj()[0], dzis=DZIS)
        return zmiany.zapisz('bud', czyste)

    def umowa(self, d):
        czyste = zmiany.sprawdz('umowa', d)
        umowy.sprawdz_odwolania(self.con, czyste)
        return zmiany.zapisz('umowa', czyste)

    def wiersz(self, wid, aid, rodzaj, kwoty: dict, **kw):
        self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'arkusz': aid, 'rodzaj': rodzaj, 'podstawa': kw.pop('podstawa', 'Faktura (jedna)'),
                                             'kontrahent': kw.pop('kontrahent', 'Klient'), 'stawka_vat': kw.pop('stawka_vat', 23),
                                             'dzien_wystawienia': kw.pop('dzien_wystawienia', '10.'), **kw}})
        for m, k in kwoty.items():
            self.bud({'op': 'komorka', 'wiersz': wid, 'miesiac': m, 'kwota': k})

    def przelicz(self):
        self.con.close()
        raport = odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        return raport

    def cf(self, **kw):
        kw.setdefault('granulacja', 'miesiac')
        kw.setdefault('od', DZIS)
        kw.setdefault('do', '2027-06-30')
        return cashflow.okresy(self.con, **kw)


class TestTrybDomyslny(Baza):
    def test_domyslnie_tylko_plany_i_rzeczywiste_bez_szacunku(self):
        """Decyzja 8: po dniu stanu wyłącznie płatności budżetu (plany, rzeczywiste nieopłacone, z umowy); szacunek kosztów
        i należności spoza budżetu tylko po włączeniu w panelu."""
        w = self.cf()
        typy = {z['typ'] for z in w['pozycje']}
        self.assertTrue(typy <= {'plan', 'rzeczywista', 'umowa', 'bank'}, typy)
        self.assertNotIn('szacunek', typy)
        self.assertEqual(w['parametry']['pochodzenie'], list(cashflow.POCHODZENIE_DOMYSLNE))
        # po dniu stanu nic z banku, przed nim tylko bank
        self.assertTrue(all(z['typ'] != 'bank' for z in w['pozycje'] if z['data'] > DZIS))
        # faktura połączona z planem (FV2026/09/1) nie dochodzi drugi raz, gdy włączymy należności spoza budżetu
        z_fv = self.cf(pochodzenie='plan|rzeczywista|umowa|bank|faktura')
        self.assertNotIn('FV2026/09/1', [z['nr_dok'] for z in z_fv['pozycje'] if z['typ'] == 'faktura'])

    def test_os_po_dniu_realnym(self):
        """A-CF-02: plan stoi na dniu realnej płatności; przesunięcie dnia realnego przesuwa go w cash flow, termin zostaje."""
        pid = 'plan:w-g:2026-11:1'
        z = next(z for z in self.cf()['pozycje'] if z['id'] == pid)
        self.assertEqual((z['data'], z['termin'], z['kwota'], z['przesuniecie']), ('2026-11-24', '2026-11-24', 123000, 0))
        self.bud({'op': 'platnosc', 'obiekt': {'id': pid, 'realny': '2026-12-01'}})
        self.przelicz()
        w = self.cf()
        z = next(z for z in w['pozycje'] if z['id'] == pid)
        self.assertEqual((z['data'], z['termin'], z['przesuniecie']), ('2026-12-01', '2026-11-24', 7))
        self.assertEqual(w['okresy'][z['okres']]['etykieta'], 'grudzień')

    def test_niewymagana_z_bs_w_cash_flow(self):
        """Uwaga z pakietu 8: rzeczywista „Niewymagana” w BS (np. przyszły ZUS) nie jest opłacona i jest w cash flow."""
        z = next(z for z in self.cf()['pozycje'] if z.get('nr_dok') == 'DRA 10')
        self.assertEqual((z['typ'], z['etap_cf'], z['data'], z['kwota']), ('rzeczywista', 'Niewymagana', '2026-11-15', -30000))

    def test_zaleglosci_jak_w_bs_i_filtr_aktualnosci(self):
        """Plan z minionym dniem realnym (nieaktualny) nie wchodzi do prognozy od dziś (licznik), w scenariuszu pełnym za 7 dni;
        filtr statusu aktualności jak w BS."""
        w = self.cf()
        self.assertEqual(w['poza_prognoza']['ile'], 2)   # plany Alfa z lipca i września (minął dzień realny)
        p = self.cf(scenariusz='pelny', aktualnosc='Nieaktualna')
        # zaległości za 7 dni; plan Gammy z października jest nieaktualny (minął dzień wystawienia 10.10), ale dzień realny
        # 24.10 jeszcze przed nami, więc stoi na swoim dniu, jak w BS
        self.assertEqual({(z['data'], z['zaleglosc']) for z in p['pozycje']}, {('2026-10-20', True), ('2026-10-24', False)})
        a = self.cf(aktualnosc='Aktualna')
        self.assertTrue(a['pozycje'] and all(z['aktualnosc'] == 'Aktualna' for z in a['pozycje']))

    def test_etap_oplacona_w_trybie_historii_z_budzetu(self):
        """Historia z budżetu jak w BS: z etapem „Opłacona” widać opłacone płatności (dzień przelewu), bez niego tylko nieopłacone."""
        bez = self.cf(od='2026-09-01', do='2026-09-30', historia='budzet')
        z = self.cf(od='2026-09-01', do='2026-09-30', historia='budzet', etap='Planowana|Niewymagana|Po terminie|Opłacona')
        self.assertNotIn('bank', {x['typ'] for x in z['pozycje']})
        oplacone = [x for x in z['pozycje'] if x['etap_cf'] == 'Opłacona']
        self.assertTrue(oplacone)
        self.assertFalse([x for x in bez['pozycje'] if x['etap_cf'] == 'Opłacona'])
        with self.assertRaises(ValueError):
            self.cf(etap='Zapłacone')

    def test_szacunek_tylko_po_wlaczeniu(self):
        w = self.cf(pochodzenie='plan|rzeczywista|umowa|bank|szacunek')
        self.assertIn('pochodzenie', w['parametry'])
        self.assertIn('szacunek', w['parametry']['pochodzenie'])
        with self.assertRaises(ValueError):
            self.cf(pochodzenie='plan|zgadywanie')

    def test_granulacje_te_same_sumy_i_zakres_ruchomy(self):
        wyniki = {g: cashflow.okresy(self.con, g, d_realny='ruchomy:miesiac:6:0') for g in cashflow.GRANULACJE}
        sumy = {(sum(o['wplywy'] for o in w['okresy']), sum(o['obciazenia'] for o in w['okresy']), w['sum']) for w in wyniki.values()}
        self.assertEqual(len(sumy), 1)
        self.assertEqual((wyniki['miesiac']['od'], wyniki['miesiac']['do']), ('2026-10-01', '2027-03-31'))
        w = cashflow.okresy(self.con, 'miesiac', d_realny='wszystko')
        self.assertEqual(w['od'], '2026-09-05')   # pierwsza operacja z banku


class TestUmowyWCashFlow(Baza):
    def test_z_umowy_dla_nieokreslonej(self):
        """Decyzja 9: Gamma ma plany do listopada; od grudnia pozycja „z umowy”: netto z umowy + VAT 23% z wiersza, termin
        ostatni dzień miesiąca + 14 dni z wiersza klienta."""
        poz = [z for z in self.cf()['pozycje'] if z['typ'] == 'umowa']
        self.assertEqual({z['umowa'] for z in poz}, {'u-g'})   # Delta: czas określony, plany do końca umowy
        pierwsza = min(poz, key=lambda z: z['data'])
        self.assertEqual((pierwsza['miesiac'], pierwsza['netto'], pierwsza['vat'], pierwsza['kwota'], pierwsza['wystawienie'], pierwsza['data']),
                         ('2026-12', 100000, 23000, 123000, '2026-12-31', '2027-01-14'))
        self.assertEqual([z['miesiac'] for z in sorted(poz, key=lambda z: z['data'])], ['2026-12', '2027-01', '2027-02', '2027-03',
                                                                                      '2027-04', '2027-05'])
        o = self.cf(pochodzenie='plan|rzeczywista|bank')   # wyłączone w panelu
        self.assertFalse([z for z in o['pozycje'] if z['typ'] == 'umowa'])
        okres = next(x for x in self.cf()['okresy'] if x['od'] <= '2027-01-14' <= x['do'])
        self.assertEqual(okres['wplywy_umowa'], 123000)

    def test_okreslona_bez_pozycji_po_koncu_i_ostrzezenie(self):
        """Decyzja 10: plan Delty po końcu umowy zostaje w cash flow, z ostrzeżeniem; pozycji „z umowy” po końcu brak,
        chyba że umowa przedłuża się sama."""
        self.bud({'op': 'komorka', 'wiersz': 'w-d', 'miesiac': '2027-01', 'kwota': 200000})
        self.przelicz()
        w = self.cf()
        po = [z for z in w['pozycje'] if z['po_koncu_umowy']]
        self.assertEqual([(z['id'], z['miesiac']) for z in po], [('plan:w-d:2027-01:1', '2027-01')])
        self.assertEqual((w['plany_po_koncu_umowy']['ile'], w['plany_po_koncu_umowy']['klienci']), (1, ['Delta']))
        self.assertFalse([z for z in w['pozycje'] if z.get('umowa') == 'u-d'])
        u = umowy.dla_arkusza(self.con, 'a-delta')
        self.assertEqual((u['umowa'], u['plany_po_koncu']['ile'], u['koniec_umowy']), ('u-d', 1, '2026-12-31'))
        self.assertEqual(zapytania_budzet.arkusz(self.con, 'a-delta')['umowa']['plany_po_koncu']['ile'], 1)
        # z automatycznym przedłużeniem: od lutego (po ostatnim planie) pozycje z umowy, bez ostrzeżenia
        self.umowa({'id': 'u-d', 'klient': 'DELTA sp. z o.o.', 'rodzaj': 'okreslony', 'do': '2026-12-31', 'przedluzenie': True,
                    'wypowiedzenie_mies': 1, 'wartosc_mies': 200000})
        self.przelicz()
        w = self.cf()
        self.assertFalse([z for z in w['pozycje'] if z['po_koncu_umowy']])
        self.assertEqual(min(z['miesiac'] for z in w['pozycje'] if z.get('umowa') == 'u-d'), '2027-02')

    def test_scenariusz_klienci_odchodza(self):
        """BL-01, decyzja 11: Gamma (3 mies. na koniec miesiąca) wypowiada w dniu stanu 13.10 → odchodzi 31.01.2027;
        od lutego brak jej wpływów (plany i z umowy). Delta (do 31.12, 1 mies.) odchodzi z końcem umowy."""
        baza_ = self.cf()
        w = self.cf(odejscia='wszyscy')
        g = next(x for x in w['odejscia'] if x['folder'] == 'Gamma')
        self.assertEqual((g['odejscie'], g['od_miesiaca']), ('2027-01-31', '2027-02'))
        gamma = [z['miesiac'] for z in w['pozycje'] if z['folder'] == 'Gamma' and z['znak'] > 0]
        self.assertEqual(max(gamma), '2027-01')
        self.assertGreater(g['wplywy_wypadle'], 0)
        self.assertEqual(w['bez_odejsc']['sum'], baza_['sum'])
        self.assertEqual(baza_['sum'] - w['sum'], sum(x['wplywy_wypadle'] for x in w['odejscia']))
        self.assertLessEqual(w['min']['saldo'], baza_['min']['saldo'])
        d = next(x for x in w['odejscia'] if x['folder'] == 'Delta')
        self.assertEqual(d['odejscie'], '2026-11-30')   # wypowiedzenie dziś: miesiąc na koniec miesiąca, przed końcem umowy
        # tylko wybrany klient
        tylko = self.cf(odejscia='Delta')
        self.assertEqual([x['folder'] for x in tylko['odejscia']], ['Delta'])
        self.assertIn('2027-03', [z['miesiac'] for z in tylko['pozycje'] if z['folder'] == 'Gamma'])

    def test_terminy_umowy_obie_strony(self):
        u = umowy.termin({'rodzaj': 'nieokreslony', 'wypowiedzenie_mies': 3, 'wypowiedzenie_mies_my': 1, 'koniec_miesiaca': True},
                         umowy.date(2026, 10, 13))
        self.assertEqual(u['odejscie_przy_wypowiedzeniu_dzis'], {'klient': '2027-01-31', 'my': '2026-11-30'})
        self.assertEqual(u['ostatni_dzien_wypowiedzenia'], {'klient': None, 'my': None})
        u = umowy.termin({'rodzaj': 'okreslony', 'do': '2026-11-30', 'przedluzenie': True, 'wypowiedzenie_mies': 1}, umowy.date(2026, 10, 13))
        self.assertEqual(u['ostatni_dzien_wypowiedzenia']['klient'], '2026-10-31')   # na koniec miesiąca
        self.assertEqual(u['odejscie_przy_wypowiedzeniu_dzis']['klient'], '2026-11-30')
        u = umowy.termin({'rodzaj': 'okreslony', 'do': '2026-11-30', 'przedluzenie': True, 'wypowiedzenie_mies': 3}, umowy.date(2026, 10, 13))
        self.assertEqual(u['odejscie_przy_wypowiedzeniu_dzis']['klient'], '2027-01-31')   # spóźnione: umowa się przedłuża

    def test_rejestr_powiazany_z_folderem(self):
        d = umowy.lista(self.con)
        u = {x['id']: x for x in d['umowy']}
        self.assertEqual((u['u-g']['folder'], u['u-g']['folder_zrodlo']), ('Gamma', 'wpis'))
        self.assertEqual((u['u-d']['folder'], u['u-d']['folder_zrodlo']), ('Delta', 'dopasowanie po nazwie klienta'))
        self.assertEqual(u['u-d']['arkusze_ids'], ['a-delta'])
        k = {x['folder']: x for x in d['klienci']}
        self.assertTrue(k['Alfa']['brak_umowy'])
        self.assertFalse(k['Gamma']['brak_umowy'])
        self.assertEqual(umowy.dla_arkusza(self.con, self.con.execute("SELECT id FROM bud_arkusz WHERE folder = 'Alfa'").fetchone()[0])['brak_umowy'], True)
        with self.assertRaisesRegex(ValueError, 'nie ma folderu'):
            umowy.sprawdz_odwolania(self.con, zmiany.sprawdz('umowa', {'id': 'x', 'klient': 'X', 'folder': 'Nie ma', 'rodzaj': 'nieokreslony'}))
        with self.assertRaisesRegex(ValueError, 'nie ma arkusza'):
            umowy.sprawdz_odwolania(self.con, zmiany.sprawdz('umowa', {'id': 'x', 'klient': 'X', 'arkusze': ['zly'], 'rodzaj': 'nieokreslony'}))
        with self.assertRaises(ValueError):
            zmiany.sprawdz('umowa', {'id': 'x', 'klient': 'X', 'rodzaj': 'nieokreslony', 'arkusze': 'a-gamma'})
        # wybrane arkusze zamiast wszystkich z folderu
        self.umowa({'id': 'u-g', 'klient': 'Gamma', 'folder': 'Gamma', 'arkusze': ['a-gamma'], 'rodzaj': 'nieokreslony',
                    'wypowiedzenie_mies': 3, 'wartosc_mies': 100000})
        self.przelicz()
        self.assertEqual(next(x for x in umowy.lista(self.con)['umowy'] if x['id'] == 'u-g')['arkusze_zrodlo'], 'wpis')


class TestZgodnoscZBs(Baza):
    def test_sumy_miesieczne_jak_w_eksporcie_bs(self):
        """Historia z budżetu i etap bez opłaconych = cash flow BS: suma brutto płatności nieopłaconych z „W cash flow” wg
        miesiąca dnia realnej płatności, miesiąc po miesiącu (bez danin, które liczy arkusz systemowy, i dodatków apki)."""
        p = self.srod.dane / 'Budget Studio' / 'budget_studio_2026-10-13.csv'
        oczek = {}
        with open(p, encoding='utf-8') as f:
            for x in csv.DictReader(f, delimiter='\t'):
                if x['Etap płatności'] == 'Opłacona' or x['W cash flow'] != 'Tak' or x['Podstawa płatności'].startswith('Podatek'):
                    continue
                m = (x['Dzień płatności - realny'] or x['Dzień płatności'])[:7]
                oczek[m] = oczek.get(m, 0) + int(round(float(x['Brutto (wartość)'].replace(',', '.')) * 100))
        w = cashflow.okresy(self.con, 'miesiac', od='2026-01-01', do='2026-12-31', historia='budzet', pochodzenie='plan|rzeczywista')
        nasze = {}
        for z in w['pozycje']:
            if not z['danina'] and z['arkusz'] == 'Obsługa stała Alfa':
                nasze[z['data'][:7]] = nasze.get(z['data'][:7], 0) + z['kwota']
        self.assertEqual(nasze, oczek)


class TestArkuszILista(Baza):
    def test_cash_flow_arkusza_bez_pit_i_zus(self):
        """A-CF-15: cash flow arkusza ma tylko jego płatności, bez PIT i ZUS z umów i bez danin; w całości są."""
        self.wiersz('w-p', 'a-gamma', -1, {'2026-11': 1500000}, podstawa='Umowa o pracę', kontrahent='Jan',
                    proporcje={'osoba': 59, 'us': 6, 'zus': 35}, stawka_vat=None)
        self.przelicz()
        ark = self.cf(arkusz='a-gamma')
        self.assertEqual(ark['saldo_start'], 0)
        self.assertEqual({z['skladowa'] for z in ark['pozycje'] if z['podstawa'] == 'Umowa o pracę'}, {'osoba'})
        self.assertFalse([z for z in ark['pozycje'] if z['danina'] or z['typ'] == 'bank'])
        calosc = self.cf()
        self.assertEqual({z['skladowa'] for z in calosc['pozycje'] if z['podstawa'] == 'Umowa o pracę'}, {'osoba', 'us', 'zus'})
        self.assertTrue([z for z in calosc['pozycje'] if z['danina']])

    def test_lista_wycinka_sort_i_podsumowanie(self):
        q = {'granulacja': 'miesiac', 'od': DZIS, 'do': '2027-06-30', 'w_od': '2026-11-01', 'w_do': '2026-12-31', 'sortuj': 'brutto',
             'kolejnosc': 'malejaco'}
        d = zapytania_listy.lista(self.con, 'cashflow', q)
        self.assertTrue(d['razem'] and all('2026-11-01' <= z['data'] <= '2026-12-31' for z in d['wiersze']))
        self.assertEqual([z['kwota'] for z in d['wiersze']], sorted([z['kwota'] for z in d['wiersze']], reverse=True))
        w = self.cf()
        wycinek = [z for z in w['pozycje'] if '2026-11-01' <= z['data'] <= '2026-12-31']
        self.assertEqual(d['podsumowanie']['razem']['brutto'], sum(z['kwota'] for z in wycinek))
        self.assertEqual(d['razem'], len(wycinek))
        s = zapytania_listy.lista(self.con, 'cashflow', {**q, 'q': 'gamma', 'sortuj': 'kontrahent'})
        self.assertTrue(s['wiersze'] and all('gamma' in f"{z['kontrahent']} {z['arkusz']}".lower() for z in s['wiersze']))

    def test_zapisane_widoki_cash_flow(self):
        v = zapytania_listy.widoki(self.con, 'cashflow')
        self.assertEqual([x['id'] for x in v][:2], ['13tyg', '2tyg'])
        self.assertTrue(v[0]['domyslny'])
        wpis = zmiany.sprawdz('widok', {'ekran': 'cashflow', 'id': 'w-moj', 'nazwa': 'Moje 8 tygodni',
                                         'parametry': {'granulacja': 'tydzien', 'd_realny': 'ruchomy:dzien:56:0', 'odejscia': 'wszyscy'},
                                         'kolumny': ['rodzaj', 'kontrahent', 'brutto']})
        zmiany.zapisz('widok', wpis)
        self.przelicz()
        v = zapytania_listy.widoki(self.con, 'cashflow')
        self.assertEqual(v[-1]['nazwa'], 'Moje 8 tygodni')
        w = cashflow.okresy(self.con, **v[-1]['parametry'])
        self.assertEqual((w['od'], w['do']), (DZIS, '2026-12-07'))


if __name__ == '__main__':
    unittest.main()
