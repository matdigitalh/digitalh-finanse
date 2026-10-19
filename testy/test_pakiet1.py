"""Pakiet 1 (błędy psujące dane) na zmyślonych danych: stałe ID mimo zmian w eksporcie BS, VAT liczony na serwerze
także w kopiach, seria zmian w całości albo wcale, biała lista pól, listy planu ze stronicowaniem, drobne poprawki."""
import csv
import json
import os
import threading
import http.client
import unittest
from datetime import date
from http.server import ThreadingHTTPServer

from finanse import baza, budzet, konfig, odbudowa, umowy, zapytania_budzet, zmiany
from testy.pomoc import Srodowisko, operacja, zapisz_ing
from testy.test_budzet import KOLUMNY, bs, dane


def zapisz_bs(srod, nazwa, wiersze):
    p = srod.dane / 'Budget Studio' / nazwa
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=KOLUMNY, delimiter='\t')
        w.writeheader()
        w.writerows(wiersze)
    return p


def wiersze_bs_z_pliku(srod, nazwa='budget_studio_2026-10-13.csv'):
    with open(srod.dane / 'Budget Studio' / nazwa, encoding='utf-8') as f:
        return list(csv.DictReader(f, delimiter='\t'))


class Baza(unittest.TestCase):
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
        raport = odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        return raport

    def bud(self, d):
        return zmiany.zapisz('bud', zmiany.sprawdz('bud', d))

    def platnosc(self, pid):
        r = self.con.execute('SELECT * FROM bud_platnosc WHERE id = ?', (pid,)).fetchone()
        return dict(r) if r else None


class TestStabilneId(Baza):
    def test_id_platnosci_bez_hasha_wiersza_i_mapa_deterministyczna(self):
        ids = {r[0] for r in self.con.execute('SELECT id FROM bud_platnosc')}
        self.assertEqual(ids, {'bs:1', 'bs:2', 'bs:3', 'bs:4', 'bs:5', 'bs:6', 'bs:6:2'})   # ID 6 dwa razy w eksporcie
        mapa = budzet.plik_mapy()
        self.assertEqual(mapa.stat().st_mode & 0o777, 0o600)
        pierwsza = mapa.read_text(encoding='utf-8')
        czas = mapa.stat().st_mtime_ns
        self.przelicz()
        self.assertEqual(mapa.read_text(encoding='utf-8'), pierwsza)
        self.assertEqual(mapa.stat().st_mtime_ns, czas)   # zapis tylko przy zmianie

    def test_zmiana_kontrahenta_i_folderu_w_bs_nie_gubi_zmiany_mata(self):
        wid = self.platnosc('bs:2')['wiersz']
        aid = self.con.execute('SELECT arkusz FROM bud_wiersz WHERE id = ?', (wid,)).fetchone()[0]
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'bs:2', 'netto': 123400}})
        self.przelicz()
        self.assertEqual(self.platnosc('bs:2')['netto'], 123400)
        # kolejny eksport: arkusz w innym folderze, płatność 2 z innym kontrahentem i komentarzem
        nowe = []
        for x in wiersze_bs_z_pliku(self.srod):
            if x['Folder'] == 'Alfa':
                x['Folder'] = 'Alfa Nowa'
            if x['ID'] == '2':
                x['Kontrahent'], x['Komentarz w arkuszu'] = 'Alfa SA', 'Obsługa, nowy opis'
            nowe.append(x)
        zapisz_bs(self.srod, 'budget_studio_2026-10-20.csv', nowe)
        raport = self.przelicz()
        p = self.platnosc('bs:2')
        self.assertEqual((p['netto'], p['wiersz']), (123400, wid))
        a = self.con.execute('SELECT id, folder FROM bud_arkusz WHERE id = ?', (aid,)).fetchone()
        self.assertEqual(tuple(a), (aid, 'Alfa Nowa'))   # to samo ID arkusza, nowa nazwa folderu
        self.assertEqual(self.con.execute('SELECT arkusz FROM bud_wiersz WHERE id = ?', (wid,)).fetchone()[0], aid)
        self.assertEqual(zapytania_budzet.osierocone_ile(self.con), 0)
        self.assertNotIn('osierocone', raport['budzet'])
        self.assertEqual(raport['budzet']['platnosci'], 7)

    def test_nowa_platnosc_trafia_do_wiersza_po_starym_kluczu(self):
        wid = self.platnosc('bs:3')['wiersz']
        nowe = wiersze_bs_z_pliku(self.srod) + [bs('9', '1', 'Planowana', 'Faktura ', 'Alfa', '1000,00', '2026-11', '2026-12-07',
                                                   'Obsługa stała Alfa', 'Alfa', 'Obsługa stała', 'Obsługa', brutto='1230,00')]
        zapisz_bs(self.srod, 'budget_studio_2026-10-20.csv', nowe)
        self.przelicz()
        self.assertEqual(self.platnosc('bs:9')['wiersz'], wid)

    def test_zdarzenie_ze_starym_id_platnosci_jest_tlumaczone(self):
        """Zgodność wstecz: wpis z ID sprzed mapy (bs:<ID>:<hash wiersza>) trafia w tę samą płatność, plik zmian nietknięty."""
        wid = self.platnosc('bs:4')['wiersz']
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        stary = f'bs:4:{wid}'
        self.bud({'op': 'decyzja_planu', 'platnosc': stary, 'decyzja': 'anuluj'})
        plik = konfig.katalog_zmian() / 'Mac-testowy.jsonl'
        przed = plik.read_text(encoding='utf-8')
        self.przelicz()
        self.assertEqual(self.platnosc('bs:4')['decyzja'], 'anulowane')
        self.assertEqual(plik.read_text(encoding='utf-8'), przed)

    def test_osierocone_zdarzenie_widoczne_nie_znika_po_cichu(self):
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'bs:999', 'netto': 100}})
        self.bud({'op': 'decyzja_planu', 'platnosc': 'bs:998', 'decyzja': 'anuluj'})
        raport = self.przelicz()
        self.assertEqual(raport['budzet']['osierocone'], 2)
        h = zapytania_budzet.historia(self.con)
        self.assertEqual({x['obiekt'] for x in h['osierocone']}, {'bs:999', 'bs:998'})
        self.assertEqual(zapytania_budzet.drzewo(self.con)['osierocone'], 2)
        self.assertIsNone(self.platnosc('bs:999'))   # nic nie powstało z niepełnych danych


class TestVat(Baza):
    def setUp(self):
        super().setUp()
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})

    def test_zaokraglenie_polowkami_w_gore(self):
        self.assertEqual(budzet.vat_od_netto(150, 23), 35)        # 34,5 gr → 35 (round() dałby 34)
        self.assertEqual(budzet.vat_od_netto(100000, '0,23'), 23000)
        self.assertEqual(budzet.vat_od_netto(100000, '0,2299'), 23000)   # stawka efektywna z BS
        self.assertEqual(budzet.vat_od_netto(100000, 23, 'Bez faktury'), 0)
        self.assertEqual(budzet.vat_od_netto(100000, 'zw'), 0)

    def test_edycja_netto_planu_23_i_kopia_przy_duplikowaniu(self):
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'bs:3', 'netto': 100000}})
        self.przelicz()
        p = self.platnosc('bs:3')
        self.assertEqual((p['netto'], p['vat'], p['brutto'], p['stawka']), (100000, 23000, 123000, 23))
        w = dict(self.con.execute('SELECT * FROM bud_wiersz WHERE id = ?', (p['wiersz'],)).fetchone())
        self.bud({'op': 'seria', 'operacje': [
            {'op': 'wiersz', 'obiekt': {'id': 'w-kopia', 'arkusz': w['arkusz'], 'rodzaj': w['rodzaj'], 'podstawa': w['podstawa'],
                                        'kontrahent': w['kontrahent'], 'stawka_vat': w['stawka_vat'], 'dni_na_platnosc': w['dni_na_platnosc']}},
            {'op': 'platnosc', 'obiekt': {'id': 'p-kopia', 'wzor': 'bs:3', 'wiersz': 'w-kopia', 'netto': 100000}}]})
        self.przelicz()
        k = self.platnosc('p-kopia')
        for pole in ('netto', 'vat', 'brutto', 'miesiac', 'termin', 'wystawienie', 'stawka'):
            self.assertEqual(k[pole], p[pole], pole)
        self.assertEqual(k['typ'], 'plan')

    def test_kopia_w_inny_miesiac_przesuwa_daty(self):
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'p-luty', 'wzor': 'bs:3', 'miesiac': '2027-02', 'netto': 50000}})
        self.przelicz()
        k = self.platnosc('p-luty')
        self.assertEqual((k['miesiac'], k['termin'], k['vat'], k['brutto']), ('2027-02', '2027-03-07', 11500, 61500))

    def test_faktura_z_kilkoma_stawkami_zachowuje_proporcje(self):
        model = {'arkusze': [{'id': 'a', 'od': '2026-01', 'do': '2026-12'}],
                 'wiersze': [{'id': 'w', 'arkusz': 'a', 'rodzaj': 1, 'podstawa': 'Faktura (jedna)', 'stawka_vat': '0,138'}],
                 'platnosci': [{'id': 'bs:1', 'wiersz': 'w', 'miesiac': '2026-05', 'netto': 100000, 'vat': 13800, 'brutto': 113800,
                                'stawka': '0,138'}]}
        budzet.zastosuj_zdarzenia(model, [{'id': 'z', 'czas': '1', 'typ': 'bud', 'dane': {'op': 'platnosc', 'obiekt': {'id': 'bs:1', 'netto': 50000}}}])
        self.assertEqual((model['platnosci'][0]['vat'], model['platnosci'][0]['brutto']), (6900, 56900))

    def test_plan_cykliczny_bez_float(self):
        aid = self.con.execute("SELECT id FROM bud_arkusz WHERE nazwa = 'Pusty arkusz'").fetchone()[0]
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-c', 'arkusz': aid, 'rodzaj': 1, 'podstawa': 'Faktura (jedna)', 'stawka_vat': 23,
                                             'plan': {'netto': 150, 'stawka_vat': 23, 'cykl': 'miesiac', 'od': '2026-10', 'do': '2026-10'}}})
        self.przelicz()
        r = self.con.execute("SELECT vat, brutto FROM bud_platnosc WHERE wiersz = 'w-c'").fetchone()
        self.assertEqual(tuple(r), (35, 185))


class TestWalidacja(unittest.TestCase):
    def test_nieznane_pole_odrzucone(self):
        with self.assertRaisesRegex(ValueError, 'nieznane pole kwota_brutto'):
            zmiany.sprawdz('bud', {'op': 'platnosc', 'obiekt': {'id': 'p', 'netto': 1, 'kwota_brutto': 2}})
        with self.assertRaisesRegex(ValueError, 'nieznane pole'):
            zmiany.sprawdz('bud', {'op': 'seria', 'operacje': [{'op': 'wiersz', 'obiekt': {'id': 'w', 'zrodlo': 'x'}}]})

    def test_typy_i_zakresy(self):
        zle = [
            {'op': 'platnosc', 'obiekt': {'id': 'p', 'netto': -1}},
            {'op': 'platnosc', 'obiekt': {'id': 'p', 'netto': 10.5}},
            {'op': 'platnosc', 'obiekt': {'id': 'p', 'stawka': 7}},
            {'op': 'platnosc', 'obiekt': {'id': 'p', 'termin': '2026-02-30'}},
            {'op': 'platnosc', 'obiekt': {'id': 'p', 'miesiac': '2026-13'}},
            {'op': 'platnosc', 'obiekt': {'id': 'p', 'komentarz': 'x' * 171}},
            {'op': 'wiersz', 'obiekt': {'id': 'w', 'rodzaj': 2}},
            {'op': 'wiersz', 'obiekt': {'id': 'w', 'dni_na_platnosc': 100}},
            {'op': 'wiersz', 'obiekt': {'id': 'w', 'podstawa': 'Faktura z księżyca'}},
            {'op': 'arkusz', 'obiekt': {'id': 'a', 'nazwa': 'x' * 81}},
            {'op': 'seria', 'operacje': []},
            {'op': 'seria', 'operacje': [{'op': 'seria', 'operacje': []}]},
        ]
        for d in zle:
            with self.subTest(d=d), self.assertRaises(ValueError):
                zmiany.sprawdz('bud', d)

    def test_zapis_bs_zamieniany_na_wartosci(self):
        d = zmiany.sprawdz('bud', {'op': 'wiersz', 'obiekt': {'id': 'w', 'stawka_vat': '0,23', 'dni_na_platnosc': 'Natychmiast',
                                                               'ksiegowane': 1, 'dzien_wystawienia': '15.'}})
        self.assertEqual((d['obiekt']['stawka_vat'], d['obiekt']['dni_na_platnosc'], d['obiekt']['ksiegowane']), (23, 0, True))
        self.assertEqual(zmiany.sprawdz('bud', {'op': 'wiersz', 'obiekt': {'id': 'w', 'dni_na_platnosc': '45 (nietypowe)'}})['obiekt']['dni_na_platnosc'], 45)


class TestSeria(Baza):
    def setUp(self):
        super().setUp()
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        self.przelicz()

    def scal_z_bledem(self):
        w = dict(self.con.execute("SELECT * FROM bud_wiersz WHERE id = (SELECT wiersz FROM bud_platnosc WHERE id = 'bs:2')").fetchone())
        return {'op': 'seria', 'operacje': [
            {'op': 'wiersz', 'obiekt': {'id': 'w-scal', 'arkusz': w['arkusz'], 'rodzaj': 1, 'podstawa': 'Faktura (jedna)'}},
            {'op': 'platnosc', 'obiekt': {'id': 'p-s1', 'wzor': 'bs:2', 'wiersz': 'w-scal', 'netto': 100000}},
            {'op': 'platnosc', 'obiekt': {'id': 'p-s2', 'wzor': 'bs:nie-ma', 'wiersz': 'w-scal', 'netto': 100000}},
            {'op': 'wiersz', 'obiekt': {'id': w['id']}, 'usun': True}]}

    def test_seria_z_bledem_w_trzeciej_operacji_odrzucona_przez_serwer(self):
        from finanse import serwer
        stary = konfig.PORT
        h = ThreadingHTTPServer((konfig.HOST, 0), serwer.Obsluga)
        konfig.PORT = h.server_address[1]
        threading.Thread(target=h.serve_forever, daemon=True).start()
        plik = konfig.katalog_zmian() / 'Mac-testowy.jsonl'
        przed, wierszy = plik.read_text(encoding='utf-8'), self.con.execute('SELECT COUNT(*) FROM bud_wiersz').fetchone()[0]
        try:
            c = http.client.HTTPConnection('127.0.0.1', konfig.PORT, timeout=10)
            c.request('POST', '/api/zmiana', body=json.dumps({'typ': 'bud', 'dane': self.scal_z_bledem()}),
                      headers={'Host': f'127.0.0.1:{konfig.PORT}', 'X-Finanse': '1', 'Content-Type': 'application/json'})
            r = c.getresponse()
            odp = json.loads(r.read())
        finally:
            h.shutdown()
            h.server_close()
            konfig.PORT = stary
        self.assertEqual(r.status, 400)
        self.assertIn('operacja 3 z 4', odp['blad'])
        self.assertEqual(plik.read_text(encoding='utf-8'), przed)   # nic w pliku zmian
        self.przelicz()
        self.assertIsNone(self.con.execute("SELECT 1 FROM bud_wiersz WHERE id = 'w-scal'").fetchone())   # nic w bazie
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM bud_wiersz').fetchone()[0], wierszy)

    def test_seria_w_pliku_ktora_przestala_pasowac_nie_jest_nakladana_czesciowo(self):
        zmiany.zapisz('bud', zmiany.sprawdz('bud', self.scal_z_bledem()))   # wpis z innego Maca, bez sprawdzenia na serwerze
        raport = self.przelicz()
        self.assertIsNone(self.con.execute("SELECT 1 FROM bud_wiersz WHERE id = 'w-scal'").fetchone())
        self.assertIsNotNone(self.platnosc('bs:2'))
        self.assertEqual(raport['budzet']['osierocone'], 1)

    def test_seria_cala_i_cofniecie_calej(self):
        d = self.scal_z_bledem()
        d['operacje'][2]['obiekt']['wzor'] = 'bs:3'
        # wiersza z płatnością rzeczywistą nie usuniesz (pakiet 3, A-OPS-09), więc seria usuwa sam plan bs:2
        d['operacje'][3] = {'op': 'platnosc', 'obiekt': {'id': 'bs:2'}, 'usun': True}
        budzet.sprawdz_wpis(d, zmiany.wczytaj()[0])   # bez wyjątku
        wpis = zmiany.zapisz('bud', zmiany.sprawdz('bud', d))
        self.przelicz()
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM bud_platnosc WHERE wiersz = 'w-scal'").fetchone()[0], 2)
        self.assertIsNone(self.platnosc('bs:2'))
        self.assertEqual(len([h for h in zapytania_budzet.historia(self.con)['zmiany'] if h['wpis'] == wpis['id']]), 4)
        zmiany.zapisz('cofnij', {'wpis': wpis['id']})
        self.przelicz()
        self.assertIsNone(self.con.execute("SELECT 1 FROM bud_wiersz WHERE id = 'w-scal'").fetchone())
        self.assertIsNotNone(self.platnosc('bs:2'))


class TestListyPlanu(unittest.TestCase):
    def test_450_platnosci_5_stron_po_100_suma_ze_wszystkich(self):
        with Srodowisko() as srod:
            zapisz_ing(srod.dane, 'ing_historia_2026-01-01_2026-10-13.csv', [operacja('2026-10-13', '-1,00', '100,00', 'ING', 'OPŁATA', ref='X')])
            wiersze = [bs(str(i), '1', 'Planowana', 'Bez faktury ', f'Klient {i % 7}', f'{i},00', '2026-11', '2026-11-20',
                          'Arkusz', 'Folder', 'Kategoria', f'opis {i % 3}') for i in range(1, 451)]
            zapisz_bs(srod, 'budget_studio_2026-10-13.csv', wiersze)
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
            try:
                suma = sum(i * 100 for i in range(1, 451))
                strony = [zapytania_budzet.lista(con, 'wszystkie', strona=n, ile=100) for n in range(1, 6)]
                self.assertEqual([len(s['wiersze']) for s in strony], [100, 100, 100, 100, 50])
                self.assertEqual({s['razem'] for s in strony}, {450})
                self.assertEqual({s['suma'] for s in strony}, {suma})
                self.assertEqual(len({w['id'] for s in strony for w in s['wiersze']}), 450)   # strony się nie nakładają
                q = zapytania_budzet.lista(con, 'wszystkie', q='Klient 3')
                self.assertEqual(q['razem'], len([i for i in range(1, 451) if i % 7 == 3]))
                self.assertEqual(zapytania_budzet.lista(con, ile=5000)['ile'], 500)
            finally:
                con.close()


class TestDrobne(unittest.TestCase):
    def test_umowy_od_dnia_stanu(self):
        with Srodowisko() as srod:
            zapisz_ing(srod.dane, 'ing_historia_2026-01-01_2026-03-31.csv', [operacja('2026-03-31', '1,00', '1,00', 'K', 't', ref='R1')])
            zmiany.zapisz('umowa', zmiany.sprawdz('umowa', {'id': 'u1', 'klient': 'Alfa', 'rodzaj': 'okreslony', 'do': '2026-04-30',
                                                             'wypowiedzenie_mies': 0, 'alert_dni': 30}))
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
            try:
                u = umowy.lista(con)
            finally:
                con.close()
            self.assertEqual(u['dzis'], '2026-03-31')
            self.assertEqual(u['umowy'][0]['dni'], 30)

    def test_czesc_roku_w_roku_przestepnym(self):
        from finanse import controlling, wynik
        with Srodowisko() as srod:
            zapisz_ing(srod.dane, 'ing_historia_2028-01-01_2028-12-31.csv', [operacja('2028-12-31', '1,00', '1,00', 'K', 't', ref='R1')])
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
            try:
                w = json.dumps(wynik.wynik_zarzadczy(con, '2028'))
                c = controlling.policz(con)
            finally:
                con.close()
        self.assertIn('"czesc_roku": 1.0', w)   # 31.12 roku przestępnego to cały rok (366/366), nie 366/365
        self.assertEqual(c['obrot']['czesc_roku'], 1.0)


if __name__ == '__main__':
    unittest.main()
