"""Analiza wydatków na zmyślonych danych: kategorie wbudowane, pierwszeństwo decyzji Mata, cel i cofnij, koszty stałe,
kafle bez podwójnego liczenia, ostrzeżenie o kategorii niezgodnej z rodzajem, kategoria nie zmienia rodzaju ani wyniku."""
import io
import unittest

import openpyxl

from finanse import baza, eksport, konfig, odbudowa, wydatki, wynik, zmiany
from finanse.wydatki import kategoria_wbudowana, klucz_grupy
from testy.pomoc import ONLINE, Srodowisko, operacja, zapisz_ing

KARTA = 'Płatność kartą'


def karta(data, kwota, kontrahent, ref):
    return operacja(data, kwota, '0', kontrahent, KARTA, rachunek=ONLINE, ref=ref, opis=KARTA)


def dane_testowe(dane):
    zapisz_ing(dane, 'ing_historia_2025-09-01_2026-10-15.csv', [
        operacja('2026-10-15', '-100,00', '0', 'URZĄD SKARBOWY', '/OKR/26K03/CIT-8', ref='T4'),
        operacja('2026-09-25', '-1500,00', '0', 'URZĄD SKARBOWY', '/OKR/26M08/VAT-7', ref='T1'),
        operacja('2026-09-20', '-300,00', '0', 'URZĄD SKARBOWY', '/OKR/26M08/PIT-4', ref='T2'),
        operacja('2026-09-15', '-800,00', '0', 'ZUS', 'DRA 08/2026', ref='Z3'),
        operacja('2026-07-15', '-800,00', '0', 'ZUS', 'DRA 06/2026', ref='Z2'),
        operacja('2026-06-15', '-800,00', '0', 'ZUS', 'DRA 05/2026', ref='Z1'),
        operacja('2026-09-15', '-60,00', '0', 'PKO EMERYTURA SFIO', 'SKŁADKI PPK', ref='E1'),
        operacja('2026-09-10', '-5000,00', '0', 'KOWALSKA ANNA UL. TESTOWA', 'WYNAGRODZENIE ZA 08.2026', ref='P1'),
        operacja('2026-09-08', '-2000,00', '0', 'NOWAK PIOTR', 'DYWIDENDA ZA 2025', ref='D1'),
        operacja('2026-09-05', '-200,00', '0', 'KLIENT ZWROT SP. Z O.O.', 'Zwrot nadpłaty do faktury FV1', ref='ZW1'),
        operacja('2026-09-04', '-1230,00', '0', 'Drukomat.pl Pila 64-920', 'Faktura 1/09', ref='DR1'),
        karta('2026-09-29', '-50,00', 'FIGMA SAN FRANCISCO 94102', 'F4'),
        karta('2026-08-29', '-41,00', 'FIGMA SAN FRANCISCO 94102', 'F3'),
        karta('2026-07-29', '-41,00', 'FIGMA SAN FRANCISCO 94102', 'F2'),
        karta('2026-06-29', '-41,00', 'FIGMA SAN FRANCISCO 94102', 'F1'),
        karta('2026-09-12', '-310,00', 'nazwa.pl Krakow 30-727', 'N2'),
        karta('2025-09-10', '-300,00', 'nazwa.pl Krakow 30-727', 'N1'),
        karta('2026-08-15', '-60,00', 'GOOGLE *ADS1112223333 DUBLIN', 'G1'),
        karta('2026-08-10', '-25,00', 'BOLT.EU/S/2610160930 Warsaw', 'B1'),
        karta('2026-08-11', '-30,00', 'BOLT.EU/S/9999999999 Warsaw', 'B2'),
        karta('2026-08-02', '-99,00', 'NIEZNANY SKLEP', 'X1'),
    ])


def wyd(con, ref):
    return con.execute('SELECT w.* FROM wydatki w JOIN operacje o ON o.id = w.operacja_id WHERE o.nr_ref = ?', (ref,)).fetchone()


def klucz_op(con, ref):
    return con.execute('SELECT klucz FROM operacje WHERE nr_ref = ?', (ref,)).fetchone()[0]


class TestRegulyWbudowane(unittest.TestCase):
    def k(self, **o):
        return kategoria_wbudowana(o)[0]

    def test_po_rodzaju_i_nazwie(self):
        self.assertEqual(self.k(rodzaj='vat', kontrahent='Urząd Skarbowy'), 'vat')
        self.assertEqual(self.k(rodzaj='dywidenda', kontrahent='X'), 'podzial_zysku')
        self.assertEqual(self.k(rodzaj='zwrot', kontrahent='X'), 'zwroty')
        self.assertEqual(self.k(rodzaj='zwrocony', kontrahent='Allegro'), 'zwroty')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='ZUS'), 'zus')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='Zakład Ubezpieczeń Społecznych'), 'zus')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='Urząd Skarbowy', tytul='/OKR/26M09/PIT-4'), 'pit4')
        self.assertEqual(self.k(rodzaj='podatki', kontrahent='Urząd Skarbowy', tytul='CIT-8'), 'cit')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='PKO EMERYTURA- SFIO'), 'ppk')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='KOWALSKA ANNA', tytul='WYNAGRODZENIE ZA 08.2026'), 'pensje')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='Jan Nowak', tytul='Faktura 3/2026'), 'pensje')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='Mateusz Herold', tytul='Zwrot za wyjazdy służbowe w maju'), 'podroze')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='MedicCentre Sp.z.o.o'), 'benefity')
        for n in ('Google Workspace_digit Warsaw', 'FIGMA SAN FRANCISCO', 'BUDGET STUDIO WARSZAWA', 'ANTHROPIC* CLAUDE SUB', 'OPENAI *CHATGPT',
                  'CLICKUP 888', 'IPR* VXTGK TORONTO', 'Microsoft-G186021732 msbill.info', 'nazwa.pl Krakow', 'fakturownia.pl Warszawa'):
            self.assertEqual(self.k(rodzaj='staly', kontrahent=n, karta=True), 'narzedzia', n)
        self.assertEqual(self.k(rodzaj='staly', kontrahent='BRIXEN-FK Magdalena'), 'ksiegowosc')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='Kancelaria Radcy Prawnego'), 'ksiegowosc')
        self.assertEqual(self.k(rodzaj='nieprzypisany', kontrahent='BOLT.EU/S/261 Warsaw', karta=True), 'podroze')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='Booking.com Hotel Amsterdam', karta=True), 'podroze')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='MEDIAEXPERT PL ZLOTOW', karta=True), 'sprzet')
        self.assertEqual(self.k(rodzaj='staly', kontrahent='Allegro Poznan', karta=True), 'sprzet')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='RISTORANTE SEMOLINO', karta=True), 'reprezentacja')
        self.assertEqual(self.k(rodzaj='staly', kontrahent='JUST JOIN IT Sp. z o. o.'), 'rekrutacja')

    def test_koszty_klientow_i_reklama(self):
        self.assertEqual(self.k(rodzaj='przenoszony', kontrahent='GOOGLE *ADS1112223333 DUBLIN', karta=True), 'klienci_media')
        self.assertEqual(self.k(rodzaj='przenoszony', kontrahent='FACEBK *W9NGQGHVA2'), 'klienci_media')
        self.assertEqual(self.k(rodzaj='przenoszony', kontrahent='Drukomat.pl Pila'), 'klienci_druk')
        self.assertEqual(self.k(rodzaj='przenoszony', kontrahent='Studio Grafiki'), 'klienci_podwykonawcy')
        self.assertEqual(self.k(rodzaj='staly', kontrahent='FACEBK *ABC'), 'reklama')
        self.assertEqual(self.k(rodzaj='nieprzypisany', kontrahent='FACEBK *ABC', konto='Meta DigitalH'), 'reklama')
        self.assertEqual(self.k(rodzaj='nieprzypisany', kontrahent='FACEBK *ABC', konto='Meta ROPA'), 'klienci_media')

    def test_domyslne_dla_rodzaju(self):
        self.assertEqual(self.k(rodzaj='nieprzypisany', kontrahent='NIEZNANY SKLEP', karta=True), 'nieprzypisane')
        self.assertEqual(self.k(rodzaj='staly', kontrahent='NIEZNANY SKLEP', karta=True), 'inne')
        self.assertEqual(self.k(rodzaj='praca', kontrahent='NIEZNANY SKLEP SP. Z O.O.', karta=True), 'inne')
        self.assertEqual(self.k(rodzaj='podatki', kontrahent='Gmina Testowa'), 'cit')

    def test_grupa_kontrahenta_kart(self):
        self.assertEqual(klucz_grupy('FACEBK *W9NGQGHVA2 fb.me/ads', 'facebk wngqghva'), 'facebk')
        self.assertEqual(klucz_grupy('FACEBK *ACY5FFMVA2 fb.me/ads', 'acyffmva facebk'), 'facebk')
        self.assertEqual(klucz_grupy('IPR* VXTGK TORONTO', 'ipr'), 'iproyal')
        self.assertEqual(klucz_grupy('Zakład Ubezpieczeń Społecznych (ZUS)', 'ubezpieczen zaklad'), 'zus')
        self.assertEqual(klucz_grupy('FIGMA SAN FRANCISCO', 'figma san'), 'figma san')

    def test_zgodnosc(self):
        self.assertFalse(wydatki.zgodna('narzedzia', 'praca'))
        self.assertTrue(wydatki.zgodna('narzedzia', 'staly'))
        self.assertTrue(wydatki.zgodna('inne', 'praca'))
        self.assertFalse(wydatki.zgodna('pensje', 'nieprzypisany'))


class TestWydatki(unittest.TestCase):
    def setUp(self):
        self.env = Srodowisko().__enter__()
        dane_testowe(self.env.dane)
        self.przebuduj()

    def tearDown(self):
        self.con.close()
        self.env.__exit__()

    def przebuduj(self):
        if getattr(self, 'con', None):
            self.con.close()
        self.raport = odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    def wpis(self, typ, dane):
        return zmiany.zapisz(typ, zmiany.sprawdz(typ, dane))['id']

    def test_kategorie_po_odbudowie(self):
        self.assertEqual([b for b in self.raport['bledy'] if not b.startswith('Brak plików')], [])
        oczekiwane = {'T1': 'vat', 'T2': 'pit4', 'T4': 'cit', 'Z1': 'zus', 'E1': 'ppk', 'P1': 'pensje', 'D1': 'podzial_zysku', 'ZW1': 'zwroty',
                      'F1': 'narzedzia', 'N1': 'narzedzia', 'B1': 'podroze', 'X1': 'nieprzypisane', 'G1': 'klienci_media'}
        for ref, kat in oczekiwane.items():
            w = wyd(self.con, ref)
            self.assertEqual(w['kategoria'], kat, ref)
            self.assertTrue(w['kategoria_zrodlo'].startswith('reguła wbudowana'), ref)
        self.assertEqual(wyd(self.con, 'B1')['kontrahent_grupa'], wyd(self.con, 'B2')['kontrahent_grupa'])   # Bolt: jeden kontrahent

    def test_pierwszenstwo_decyzji_mata_i_rodzaj_bez_zmian(self):
        rodzaje = {r['operacja_id']: r['rodzaj'] for r in self.con.execute('SELECT operacja_id, rodzaj FROM wydatki')}
        wynik_przed = wynik.wynik_zarzadczy(self.con, '2026')
        grupa = wyd(self.con, 'F1')['kontrahent_grupa']
        self.wpis('kategoria_regula', {'kontrahent': grupa, 'kategoria': 'inne'})
        self.wpis('kategoria_operacja', {'operacja': klucz_op(self.con, 'F2'), 'kategoria': 'sprzet'})
        self.przebuduj()
        self.assertEqual(wyd(self.con, 'F1')['kategoria'], 'inne')
        self.assertEqual(wyd(self.con, 'F1')['kategoria_zrodlo'], 'reguła Mata (kontrahent)')
        self.assertEqual(wyd(self.con, 'F2')['kategoria'], 'sprzet')   # płatność wygrywa z regułą kontrahenta
        self.assertEqual(wyd(self.con, 'F2')['kategoria_zrodlo'], 'decyzja Mata (ta płatność)')
        self.assertEqual({r['operacja_id']: r['rodzaj'] for r in self.con.execute('SELECT operacja_id, rodzaj FROM wydatki')}, rodzaje)
        self.assertEqual(wynik.wynik_zarzadczy(self.con, '2026'), wynik_przed)

    def test_cel_czesciowy_i_cofnij(self):
        g = wyd(self.con, 'F1')['kontrahent_grupa']
        self.wpis('cel_wydatku', {'kontrahent': g, 'obszar': 'Zespół', 'kto': 'Anna', 'uzasadnienie': 'projekty graficzne'})
        w2 = self.wpis('cel_wydatku', {'kontrahent': g, 'ocena': 'do_wypowiedzenia'})
        self.przebuduj()
        c = dict(self.con.execute('SELECT * FROM wydatki_cel WHERE kontrahent = ?', (g,)).fetchone())
        self.assertEqual((c['obszar'], c['kto'], c['uzasadnienie'], c['ocena']), ('Zespół', 'Anna', 'projekty graficzne', 'do_wypowiedzenia'))
        self.assertRegex(c['data_oceny'], r'^\d{4}-\d{2}-\d{2}$')
        self.wpis('cofnij', {'wpis': w2})
        self.przebuduj()
        c = dict(self.con.execute('SELECT * FROM wydatki_cel WHERE kontrahent = ?', (g,)).fetchone())
        self.assertEqual((c['obszar'], c['ocena'], c['data_oceny']), ('Zespół', '', ''))

    def test_walidacja(self):
        with self.assertRaises(ValueError):
            zmiany.sprawdz('kategoria_regula', {'kontrahent': 'figma san', 'kategoria': 'nieznana'})
        with self.assertRaises(ValueError):
            zmiany.sprawdz('cel_wydatku', {'kontrahent': 'figma san', 'ocena': 'super'})
        with self.assertRaises(ValueError):
            zmiany.sprawdz('cel_wydatku', {'kontrahent': 'figma san'})   # brak zmian
        with self.assertRaises(ValueError):
            zmiany.sprawdz('cel_wydatku', {'kontrahent': 'figma san', 'staly': 'tak'})
        with self.assertRaises(ValueError):
            wydatki.sprawdz_odwolania(self.con, 'cel_wydatku', {'kontrahent': 'nie ma takiego', 'kto': 'x'})
        with self.assertRaises(ValueError):
            wydatki.sprawdz_odwolania(self.con, 'cel_wydatku', {'kontrahent': 'figma san', 'obszar': 'Szkolenia'})
        self.wpis('ustawienie', {'klucz': 'obszary_wydatkow', 'wartosc': ['Szkolenia']})
        self.przebuduj()
        wydatki.sprawdz_odwolania(self.con, 'cel_wydatku', {'kontrahent': 'figma san', 'obszar': 'Szkolenia'})
        self.assertIn('Szkolenia', wydatki.obszary(self.con))

    def test_koszty_stale(self):
        s = wydatki.koszty_stale(self.con)
        self.assertEqual(s['okno'], ['2026-06', '2026-07', '2026-08', '2026-09'])
        po = {x['klucz']: x for x in s['pozycje']}
        figma = po[wyd(self.con, 'F1')['kontrahent_grupa']]
        self.assertEqual(figma['miesiecznie'], (4100 + 4100 + 5000 + 1) // 3)   # średnia z lipca, sierpnia, września
        self.assertEqual(figma['rocznie'], figma['miesiecznie'] * 12)
        self.assertEqual((figma['ostatnia_data'], figma['ostatnia_kwota']), ('2026-09-29', 5000))
        self.assertEqual(figma['zmiana_ceny']['poprzednia'], 4100)
        self.assertIn('zus', po)   # 3 z 4 miesięcy
        nazwa = po[wyd(self.con, 'N1')['kontrahent_grupa']]   # opłata roczna ±10% rok wcześniej
        self.assertEqual((nazwa['sposob'], nazwa['rocznie'], nazwa['miesiecznie']), ('opłata roczna', 31000, 2583))
        self.assertNotIn(wyd(self.con, 'X1')['kontrahent_grupa'], po)   # jednorazowy
        self.assertFalse(any(x['kategoria'] == 'vat' for x in s['pozycje']))   # VAT nie jest kosztem stałym
        self.assertEqual(s['razem']['miesiecznie'], sum(x['miesiecznie'] for x in s['pozycje']))
        # decyzja Mata: figma niestała, sklep stały
        self.wpis('cel_wydatku', {'kontrahent': figma['klucz'], 'staly': False})
        self.wpis('cel_wydatku', {'kontrahent': wyd(self.con, 'X1')['kontrahent_grupa'], 'staly': True, 'obszar': 'Rozwój', 'kto': 'Anna'})
        self.przebuduj()
        s = wydatki.koszty_stale(self.con)
        po = {x['klucz']: x for x in s['pozycje']}
        self.assertNotIn(figma['klucz'], po)
        sklep = po[wyd(self.con, 'X1')['kontrahent_grupa']]
        self.assertEqual((sklep['miesiecznie'], sklep['sposob']), (9900, 'decyzja Mata (wykrywanie: nie)'))
        self.assertIn({'nazwa': 'Rozwój', 'miesiecznie': 9900, 'rocznie': 9900 * 12, 'ile': 1}, s['wg_obszaru'])
        self.assertIn('Anna', [x['nazwa'] for x in s['wg_osoby']])

    def test_kafle_bez_podwojnego_liczenia(self):
        a = wydatki.analiza(self.con, '2026-01-01', '2026-10-15')
        k = a['kafle']
        self.assertEqual(k['koszt_pracy']['suma'], 500000 + 3 * 80000 + 30000 + 6000)   # pensje, ZUS, PIT-4, PPK
        self.assertEqual(k['podatki']['suma'], 150000 + 10000)   # VAT i CIT, bez PIT-4 i ZUS
        self.assertEqual(a['razem'], sum(x['suma'] for x in a['kategorie']))
        self.assertEqual(a['razem'], -self.con.execute("SELECT SUM(o.kwota) FROM wydatki w JOIN operacje o ON o.id = w.operacja_id"
                                                        " WHERE o.data_ksiegowania >= '2026-01-01'").fetchone()[0])
        self.assertEqual(a['niepelne'], ['2026-10'])
        narz = next(x for x in a['kategorie'] if x['klucz'] == 'narzedzia')
        self.assertEqual(k['narzedzia']['srednia'], (sum(narz['miesiace'].get(m, 0) for m in a['pelne']) + 4) // 9)
        self.assertAlmostEqual(sum(x['udzial'] for x in a['kategorie']), 100, delta=0.5)

    def test_ostrzezenie_kategoria_niezgodna_z_rodzajem(self):
        g = wyd(self.con, 'P1')['kontrahent_grupa']
        self.assertEqual(wyd(self.con, 'P1')['rodzaj'], 'praca')
        self.wpis('kategoria_regula', {'kontrahent': g, 'kategoria': 'narzedzia'})
        self.przebuduj()
        self.assertEqual(wyd(self.con, 'P1')['rodzaj'], 'praca')   # rodzaj bez zmian, tylko ostrzeżenie
        d = wydatki.do_decyzji(self.con)
        x = next(y for y in d['niezgodne'] if y['klucz'] == g)
        self.assertTrue(x['od_mata'])
        self.assertEqual((x['kategoria'], x['rodzaj'], x['typ']), ('narzedzia', 'praca', 'niezgodna'))
        self.assertEqual(d['niezgodne'][0]['klucz'], g)   # decyzje Mata na górze
        self.assertIn(wyd(self.con, 'X1')['kontrahent_grupa'], [y['klucz'] for y in d['nieprzypisane']])
        bolt = next(y for y in d['niezgodne'] if y['klucz'] == 'bolt')
        self.assertEqual((bolt['typ'], bolt['rodzaj_podpowiedz'], bolt['ile']), ('bez_rodzaju', 'praca', 2))

    def test_karta_kontrahenta_i_eksport(self):
        g = wyd(self.con, 'F1')['kontrahent_grupa']
        k = wydatki.kontrahent(self.con, g, '2026-01-01', '2026-10-15')
        self.assertEqual((k['ile'], k['suma'], k['kategoria']), (4, 17300, 'narzedzia'))
        self.assertEqual(k['platnosci'][0]['data'], '2026-09-29')
        self.assertIn('reguła wbudowana', k['platnosci'][0]['kategoria_zrodlo'])
        with self.assertRaises(ValueError):
            wydatki.kontrahent(self.con, 'nie ma', None, None)
        nazwa, tresc, typ = eksport.plik(self.con, 'wydatki/analiza', {'format': 'xlsx', 'od': '2026-01-01', 'do': '2026-10-15'})
        wb = openpyxl.load_workbook(io.BytesIO(tresc))
        self.assertEqual(wb.sheetnames[:3], ['Kategorie', 'Kontrahenci', 'Koszty stałe'])
        suma = sum(r[1] for r in wb['Kategorie'].iter_rows(min_row=2, values_only=True) if r[1] is not None)
        self.assertAlmostEqual(suma, wydatki.analiza(self.con, '2026-01-01', '2026-10-15')['razem'] / 100, places=2)
        nazwa, tresc, typ = eksport.plik(self.con, 'wydatki/stale', {'format': 'csv'})
        self.assertTrue(nazwa.endswith('.csv'))
        self.assertIn('Kontrahent', tresc.decode('utf-8-sig').splitlines()[0])

    def test_schemat_i_odcisk(self):
        kolumny = {r[1] for r in self.con.execute('PRAGMA table_info(wydatki)')}
        self.assertTrue({'kategoria', 'kategoria_zrodlo', 'kategoria_wpis', 'kontrahent_grupa'} <= kolumny)
        self.assertIn('wydatki_cel', baza.SCHEMAT)
        import inspect
        self.assertIn('wydatki.__file__', inspect.getsource(odbudowa.odcisk_kodu))


if __name__ == '__main__':
    unittest.main()
