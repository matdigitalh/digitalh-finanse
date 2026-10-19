"""Pakiet 4 (struktura budżetu i Biblioteka) na zmyślonych danych: słowniki z danych, łączenie duplikatów jedną serią,
blokada usuwania użytych pozycji, zmiana nazwy propagowana wszędzie, ustawienia domyślne kontrahenta wg reguły BS
(A-KOL-04, A-KOL-05), foldery i kategorie (dodaj, zmień nazwę, usuń puste albo z przeniesieniem arkuszy, kolejność)."""
import json
import unittest

from finanse import biblioteka, budzet, zapytania_budzet, zmiany
from testy.test_pakiet2 import Baza


class Pakiet4(Baza):
    def setUp(self):
        super().setUp()
        self.przelicz()   # arkusz testowy z Baza w bazie (Biblioteka czyta stan po odbudowie)

    def wiersz(self, wid, **kw):
        self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Faktura (jedna)',
                                             'stawka_vat': 23, 'dzien_wystawienia': '10.', 'dni_na_platnosc': 14, 'metoda': 'Przelew', **kw}})

    def nowy(self, wid, **pola):
        """Nowy wiersz z „Dodaj +”: tylko pole pierwszej akcji, resztę uzupełnia serwer z Biblioteki."""
        return self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'arkusz': 'a-test', **pola}, 'domyslne': True})

    def slownik(self):
        return {(r['rodzaj'], r['nazwa']): json.loads(r['dane']) for r in self.con.execute('SELECT * FROM bud_slownik')}

    def bib(self):
        return biblioteka.widok(self.con, True)

    def rek(self, rodzaj, nazwa):
        return next(x for x in self.bib()[rodzaj] if x['nazwa'] == nazwa)

    def w(self, wid):
        return dict(self.con.execute('SELECT * FROM bud_wiersz WHERE id = ?', (wid,)).fetchone())

    def ile_wpisow(self):
        return len([w for w in zmiany.wczytaj()[0] if w['typ'] == 'bud'])


class TestSlownikiZDanych(Pakiet4):
    def test_slowniki_z_danych_i_liczniki(self):
        b = self.bib()
        nazwy = {x['nazwa'] for x in b['kontrahent']}
        self.assertTrue({'', 'Alfa', 'Drukarnia', 'Urząd Skarbowy'} <= nazwy)
        sys_ = self.rek('kontrahent', '')
        self.assertTrue(sys_['systemowy'] and sys_['domyslny'])
        self.assertEqual(sys_['etykieta'], 'Bez kontrahenta')
        alfa = self.rek('kontrahent', 'Alfa')
        # wiersze Alfa z BS (Obsługa i Dodatki) i ich płatności (4 płatności BS)
        self.assertEqual((alfa['wiersze'], alfa['platnosci']), (2, 4))
        self.assertEqual(alfa['uzyc'], 6)
        # ustawienia domyślne z najczęstszego wiersza: wpływ, faktura jedna, 23 %
        self.assertEqual((alfa['ustawienia']['rodzaj'], alfa['ustawienia']['podstawa'], alfa['ustawienia']['stawka_vat']),
                         (1, 'Faktura (jedna)', 23))
        # pełna nazwa i NIP podpowiedziane z Fakturowni (ALFA SP. Z O.O.)
        self.assertEqual(alfa['podpowiedz'], {'nip': '111', 'pelna': 'ALFA SP. Z O.O.'})
        # Urząd Skarbowy używa arkusz systemowy Opłaty urzędowe
        self.assertTrue(self.rek('kontrahent', 'Urząd Skarbowy').get('arkusz_systemowy'))
        self.assertEqual({x['nazwa'] for x in b['sekcja']} >= {''}, True)
        self.assertEqual(self.rek('przedmiot', '')['etykieta'], 'Przedmiot transakcji')
        # struktura z arkuszy, pusty folder Beta też (arkusz bez płatności), folder systemowy na końcu
        foldery = [f['folder'] for f in b['struktura']]
        self.assertIn('Beta', foldery)
        self.assertEqual(foldery[-1], 'System')
        self.assertTrue(b['struktura'][-1]['systemowy'])

    def test_listy_w_arkuszu_z_biblioteki(self):
        d = zapytania_budzet.arkusz(self.con, 'a-test')
        self.assertIn('Drukarnia', d['slowniki']['kontrahent'])
        self.assertNotIn('', d['slowniki']['kontrahent'])
        self.assertEqual(d['slowniki']['domyslne'], {'kontrahent': '', 'przedmiot': ''})
        self.assertEqual(d['wzorce']['']['podstawa'], 'Faktura (jedna)')   # kontrahent domyślny: pełne ustawienia
        self.assertIn('Firma', [f['folder'] for f in d['slowniki']['struktura']])


class TestPolaczenie(Pakiet4):
    def test_polaczenie_duplikatow_jedna_seria_przepina_wiersze_i_platnosci(self):
        self.wiersz('w1', kontrahent='GoogleAds', metoda='Karta')
        self.wiersz('w2', kontrahent='Google Ads', metoda='Karta płatnicza')
        self.bud({'op': 'seria', 'operacje': [{'op': 'komorka', 'wiersz': 'w1', 'miesiac': '2026-11', 'kwota': 10000},
                                               {'op': 'komorka', 'wiersz': 'w2', 'miesiac': '2026-11', 'kwota': 20000},
                                               {'op': 'komorka', 'wiersz': 'w2', 'miesiac': '2026-12', 'kwota': 20000}]})
        # ręczna zmiana kontrahenta na jednym planie innego wiersza też ma przejść na wybrany wpis
        self.wiersz('w3', kontrahent='Drukarnia')
        self.bud({'op': 'komorka', 'wiersz': 'w3', 'miesiac': '2026-11', 'kwota': 500})
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'plan:w3:2026-11:1', 'kontrahent': 'GoogleAds'}})
        self.przelicz()
        self.assertEqual(self.rek('kontrahent', 'GoogleAds')['uzyc'], 3)   # wiersz, jego plan, plan w3
        przed = self.ile_wpisow()
        self.bud({'op': 'slownik', 'akcja': 'polacz', 'rodzaj': 'kontrahent', 'zrodla': ['GoogleAds'], 'cel': 'Google Ads',
                  'nip': '526-104-08-28', 'pelna': 'Google Ireland Ltd'})
        self.assertEqual(self.ile_wpisow(), przed + 1)   # jedna seria w pliku zmian
        self.przelicz()
        sl = self.slownik()
        self.assertNotIn(('kontrahent', 'GoogleAds'), sl)
        self.assertEqual((sl[('kontrahent', 'Google Ads')]['nip'], sl[('kontrahent', 'Google Ads')]['pelna']), ('5261040828', 'Google Ireland Ltd'))
        self.assertEqual(self.w('w1')['kontrahent'], 'Google Ads')
        kontr = {r[0] for r in self.con.execute("SELECT kontrahent FROM bud_platnosc WHERE wiersz IN ('w1', 'w2')")}
        self.assertEqual(kontr, {'Google Ads'})
        self.assertEqual(self.con.execute("SELECT kontrahent FROM bud_platnosc WHERE id = 'plan:w3:2026-11:1'").fetchone()[0], 'Google Ads')
        self.assertEqual(self.rek('kontrahent', 'Google Ads')['uzyc'], 2 + 3 + 1)
        # cofnięcie przywraca oba wpisy i wszystkie wystąpienia
        ostatni = zapytania_budzet.ostatni(self.con)
        zmiany.zapisz('cofnij', {'wpis': ostatni['wpis']})
        self.przelicz()
        self.assertEqual(self.w('w1')['kontrahent'], 'GoogleAds')
        self.assertIn(('kontrahent', 'GoogleAds'), self.slownik())

    def test_metody_polaczone_z_rachunkiem_i_systemowy_wpis_nie_znika(self):
        self.wiersz('w1', metoda='Karta')
        self.bud({'op': 'slownik', 'akcja': 'polacz', 'rodzaj': 'metoda', 'zrodla': ['Karta'], 'cel': 'Przelew',
                  'rachunek': 'główny', 'bank': 'ING'})
        self.przelicz()
        self.assertEqual(self.w('w1')['metoda'], 'Przelew')
        m = self.rek('metoda', 'Przelew')
        self.assertEqual((m['rachunek'], m['bank']), ('główny', 'ING'))
        with self.assertRaisesRegex(ValueError, 'Rachunek'):
            zmiany.sprawdz('bud', {'op': 'slownik', 'akcja': 'zmien', 'rodzaj': 'metoda', 'nazwa': 'Przelew', 'rachunek': 'skarbonka'})
        with self.assertRaisesRegex(ValueError, 'systemowy'):
            self.bud({'op': 'slownik', 'akcja': 'polacz', 'rodzaj': 'kontrahent', 'zrodla': [''], 'cel': 'Alfa'})

    def test_zmiana_nazwy_propaguje_sie_wszedzie_i_nie_dubluje(self):
        wid = self.con.execute("SELECT id FROM bud_wiersz WHERE kontrahent = 'Drukarnia'").fetchone()[0]
        self.bud({'op': 'slownik', 'akcja': 'zmien', 'rodzaj': 'kontrahent', 'nazwa': 'Drukarnia', 'nowa': 'Drukarnia Kowalski'})
        self.przelicz()
        self.assertEqual(self.w(wid)['kontrahent'], 'Drukarnia Kowalski')
        self.assertEqual({r[0] for r in self.con.execute('SELECT kontrahent FROM bud_platnosc WHERE wiersz = ?', (wid,))}, {'Drukarnia Kowalski'})
        sl = self.slownik()
        self.assertNotIn(('kontrahent', 'Drukarnia'), sl)
        self.assertEqual(sl[('kontrahent', 'Drukarnia Kowalski')]['pelna'], 'Drukarnia Kowalski')
        with self.assertRaisesRegex(ValueError, 'już jest'):
            self.bud({'op': 'slownik', 'akcja': 'zmien', 'rodzaj': 'kontrahent', 'nazwa': 'Alfa', 'nowa': 'drukarnia kowalski'})
        with self.assertRaisesRegex(ValueError, 'systemowy'):
            self.bud({'op': 'slownik', 'akcja': 'zmien', 'rodzaj': 'sekcja', 'nazwa': '', 'nowa': 'Ogólne'})
        # przedmiot i sekcja: zmiana nazwy w wierszach
        self.wiersz('w1', przedmiot='Abonmmnt', sekcja='Biuro')
        self.bud({'op': 'slownik', 'akcja': 'zmien', 'rodzaj': 'przedmiot', 'nazwa': 'Abonmmnt', 'nowa': 'Abonament'})
        self.bud({'op': 'slownik', 'akcja': 'zmien', 'rodzaj': 'sekcja', 'nazwa': 'Biuro', 'nowa': 'Biuro i administracja'})
        self.przelicz()
        self.assertEqual((self.w('w1')['przedmiot'], self.w('w1')['sekcja']), ('Abonament', 'Biuro i administracja'))


class TestUsuwanie(Pakiet4):
    def test_blokada_usuwania_uzytego_z_komunikatem(self):
        przed = self.ile_wpisow()
        with self.assertRaisesRegex(ValueError, r'Drukarnia.*wystąpie.*Połącz'):
            self.bud({'op': 'slownik', 'akcja': 'usun', 'rodzaj': 'kontrahent', 'nazwy': ['Drukarnia']})
        with self.assertRaisesRegex(ValueError, 'arkusz systemowy'):
            self.bud({'op': 'slownik', 'akcja': 'usun', 'rodzaj': 'kontrahent', 'nazwy': ['Urząd Skarbowy']})
        with self.assertRaisesRegex(ValueError, 'systemowy'):
            self.bud({'op': 'slownik', 'akcja': 'usun', 'rodzaj': 'sekcja', 'nazwy': ['']})
        self.assertEqual(self.ile_wpisow(), przed)   # nic nie trafiło do pliku zmian
        # nieużywany (dodany w Bibliotece) usuwa się, hurtowo razem z innym nieużywanym; z używanym w zaznaczeniu nic
        self.bud({'op': 'slownik', 'akcja': 'dodaj', 'rodzaj': 'kontrahent', 'nazwa': 'Orange', 'nip': '1234563218'})
        self.bud({'op': 'slownik', 'akcja': 'dodaj', 'rodzaj': 'kontrahent', 'nazwa': 'Orange Polska'})
        with self.assertRaises(ValueError):
            self.bud({'op': 'slownik', 'akcja': 'usun', 'rodzaj': 'kontrahent', 'nazwy': ['Orange', 'Drukarnia']})
        self.bud({'op': 'slownik', 'akcja': 'usun', 'rodzaj': 'kontrahent', 'nazwy': ['Orange', 'Orange Polska']})
        self.przelicz()
        self.assertFalse({('kontrahent', 'Orange'), ('kontrahent', 'Orange Polska')} & set(self.slownik()))

    def test_domyslny_nie_do_usuniecia_i_zawsze_jeden(self):
        self.bud({'op': 'slownik', 'akcja': 'dodaj', 'rodzaj': 'przedmiot', 'nazwa': 'Abonament', 'domyslny': True})
        self.przelicz()
        dom = [x['nazwa'] for x in self.bib()['przedmiot'] if x.get('domyslny')]
        self.assertEqual(dom, ['Abonament'])
        with self.assertRaisesRegex(ValueError, 'domyślny'):
            self.bud({'op': 'slownik', 'akcja': 'usun', 'rodzaj': 'przedmiot', 'nazwy': ['Abonament']})
        with self.assertRaisesRegex(ValueError, 'Jeden wpis musi być domyślny'):
            self.bud({'op': 'slownik', 'akcja': 'zmien', 'rodzaj': 'przedmiot', 'nazwa': 'Abonament', 'domyslny': False})

    def test_nazwa_i_nip_walidowane(self):
        with self.assertRaisesRegex(ValueError, 'sumę kontrolną'):
            zmiany.sprawdz('bud', {'op': 'slownik', 'akcja': 'dodaj', 'rodzaj': 'kontrahent', 'nazwa': 'X', 'nip': '1234567890'})
        self.assertEqual(biblioteka.sprawdz_nip('PL 526-104-08-28'), '5261040828')
        self.assertEqual(biblioteka.sprawdz_nip('de123456789'), 'DE123456789')
        with self.assertRaisesRegex(ValueError, 'najwyżej 60'):
            zmiany.sprawdz('bud', {'op': 'slownik', 'akcja': 'dodaj', 'rodzaj': 'metoda', 'nazwa': 'x' * 61})
        with self.assertRaisesRegex(ValueError, 'już jest'):
            self.bud({'op': 'slownik', 'akcja': 'dodaj', 'rodzaj': 'kontrahent', 'nazwa': 'alfa'})
        with self.assertRaisesRegex(ValueError, 'Umowę ustawisz w wierszu'):
            zmiany.sprawdz('bud', {'op': 'slownik', 'akcja': 'dodaj', 'rodzaj': 'kontrahent', 'nazwa': 'Y',
                                   'ustawienia': {'podstawa': 'Umowa o pracę'}})


class TestUstawieniaKontrahenta(Pakiet4):
    """A-KOL-04, A-KOL-05: kolejność działań w nowym wierszu decyduje, skąd są ustawienia."""

    USTAWIENIA = {'rodzaj': -1, 'podstawa': 'Bez faktury', 'dzien_wystawienia': '1.', 'dni_na_platnosc': 30, 'metoda': 'Karta',
                  'ksiegowane': False, 'w_cashflow': True, 'split': False, 'sekcja': 'Narzędzia'}

    def setUp(self):
        super().setUp()
        self.bud({'op': 'slownik', 'akcja': 'dodaj', 'rodzaj': 'kontrahent', 'nazwa': 'Canva', 'ustawienia': self.USTAWIENIA})

    def test_pierwsza_akcja_kontrahent_wypelnia_wiersz_jego_ustawieniami(self):
        wpis = self.nowy('n1', kontrahent='Canva')
        self.przelicz()
        w = self.w('n1')
        self.assertEqual((w['kontrahent'], w['podstawa'], w['dzien_wystawienia'], w['dni_na_platnosc'], w['metoda'], w['ksiegowane'], w['sekcja']),
                         ('Canva', 'Bez faktury', '1.', '30', 'Karta', 0, 'Narzędzia'))
        self.assertEqual(w['stawka_vat'], '')   # bez faktury: VAT „-”
        # wpis w pliku zmian jest pełny (bez flagi), więc późniejsza zmiana w Bibliotece nie zmienia historii
        self.assertNotIn('domyslne', wpis['dane'])
        self.assertEqual(wpis['dane']['obiekt']['metoda'], 'Karta')
        self.bud({'op': 'slownik', 'akcja': 'zmien', 'rodzaj': 'kontrahent', 'nazwa': 'Canva', 'ustawienia': {**self.USTAWIENIA, 'metoda': 'Przelew'}})
        self.przelicz()
        self.assertEqual(self.w('n1')['metoda'], 'Karta')

    def test_pierwsza_akcja_inna_kolumna_kontrahent_domyslny_i_jego_ustawienia(self):
        self.nowy('n2', komentarz='licencje')
        self.przelicz()
        w = self.w('n2')
        self.assertEqual((w['kontrahent'], w['podstawa'], w['stawka_vat'], w['dzien_wystawienia'], w['dni_na_platnosc'], w['metoda'], w['komentarz']),
                         ('', 'Faktura (jedna)', '23', 'Ostatni', '14', 'Konto firmowe', 'licencje'))
        # wybór kontrahenta jako druga akcja nie nadpisuje ustawień wiersza (A-KOL-04)
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'n2', 'kontrahent': 'Canva'}})
        self.przelicz()
        w = self.w('n2')
        self.assertEqual((w['kontrahent'], w['podstawa'], w['metoda']), ('Canva', 'Faktura (jedna)', 'Konto firmowe'))
        # zmiana w wierszu nie zmienia ustawień kontrahenta w Bibliotece
        self.assertEqual(self.slownik()[('kontrahent', 'Canva')]['ustawienia']['metoda'], 'Karta')

    def test_kontrahent_domyslny_z_biblioteki(self):
        self.bud({'op': 'slownik', 'akcja': 'zmien', 'rodzaj': 'kontrahent', 'nazwa': 'Canva', 'domyslny': True})
        self.bud({'op': 'slownik', 'akcja': 'dodaj', 'rodzaj': 'przedmiot', 'nazwa': 'Narzędzia', 'domyslny': True})
        self.nowy('n3', dni_na_platnosc=7)
        self.przelicz()
        w = self.w('n3')
        self.assertEqual((w['kontrahent'], w['podstawa'], w['dni_na_platnosc'], w['przedmiot']), ('Canva', 'Bez faktury', '7', 'Narzędzia'))
        self.assertFalse(self.slownik()[('kontrahent', '')]['domyslny'])

    def test_nowy_kontrahent_na_koncu_dostaje_ustawienia_wiersza(self):
        self.nowy('n4', podstawa='Faktura (w worku)')
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'n4', 'stawka_vat': 8, 'dni_na_platnosc': 21}})
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'n4', 'kontrahent': 'Hurtownia Nowa'}})   # „Dodaj” w kolumnie na końcu
        self.przelicz()
        u = self.slownik()[('kontrahent', 'Hurtownia Nowa')]
        self.assertEqual((u['pelna'], u['nip']), ('Hurtownia Nowa', ''))   # wpis uproszczony (A-KOL-03)
        self.assertEqual((u['ustawienia']['podstawa'], u['ustawienia']['stawka_vat'], u['ustawienia']['dni_na_platnosc']),
                         ('Faktura (w worku)', 8, 21))

    def test_nowy_kontrahent_jako_pierwsza_akcja_dostaje_ustawienia_domyslnego(self):
        self.nowy('n5', kontrahent='Studio Foto')
        self.przelicz()
        u = self.slownik()[('kontrahent', 'Studio Foto')]['ustawienia']
        self.assertEqual((u['podstawa'], u['stawka_vat'], u['dni_na_platnosc'], u['metoda']), ('Faktura (jedna)', 23, 14, 'Konto firmowe'))
        self.assertEqual(self.w('n5')['podstawa'], 'Faktura (jedna)')

    def test_seria_ze_slownikiem_wszystko_albo_nic(self):
        przed = self.ile_wpisow()
        with self.assertRaises(ValueError):
            self.bud({'op': 'seria', 'operacje': [
                {'op': 'slownik', 'akcja': 'dodaj', 'rodzaj': 'sekcja', 'nazwa': 'Marketing'},
                {'op': 'wiersz', 'obiekt': {'id': 'nie-ma', 'sekcja': 'Marketing'}}]})
        self.assertEqual(self.ile_wpisow(), przed)


class TestStruktura(Pakiet4):
    def s(self, **d):
        return self.bud({'op': 'struktura', **d})

    def struktura(self):
        return {f['folder']: [k['kategoria'] for k in f['kategorie']] for f in self.bib()['struktura']}

    def test_dodanie_folderu_wymaga_kategorii_i_unikalnej_nazwy(self):
        with self.assertRaisesRegex(ValueError, 'Kategoria'):
            zmiany.sprawdz('bud', {'op': 'struktura', 'akcja': 'dodaj_folder', 'folder': 'Klienci'})
        self.s(akcja='dodaj_folder', folder='Klienci', kategoria='Aktywni')
        with self.assertRaisesRegex(ValueError, 'już jest'):
            self.s(akcja='dodaj_folder', folder='klienci', kategoria='X')
        self.s(akcja='dodaj_kategorie', folder='Klienci', kategoria='Zakończeni')
        self.s(akcja='dodaj_kategorie', folder='Firma', kategoria='Aktywni')   # ta sama nazwa w innym folderze wolno
        with self.assertRaisesRegex(ValueError, 'już jest w folderze'):
            self.s(akcja='dodaj_kategorie', folder='Klienci', kategoria='aktywni')
        with self.assertRaisesRegex(ValueError, 'System'):
            self.s(akcja='dodaj_folder', folder='system', kategoria='X')
        self.przelicz()
        st = self.struktura()
        self.assertEqual(st['Klienci'], ['Aktywni', 'Zakończeni'])
        # pusty folder istnieje w Bibliotece, ale nie ma go w drzewie budżetu (A-BUD-05)
        self.assertNotIn('Klienci', [f['folder'] for f in zapytania_budzet.drzewo(self.con)['foldery']])
        # arkusz w folderze o nazwie różniącej się tylko wielkością liter: odrzucony
        with self.assertRaisesRegex(ValueError, 'wielkością liter'):
            self.bud({'op': 'arkusz', 'obiekt': {'id': 'a-x', 'nazwa': 'X', 'folder': 'KLIENCI', 'kategoria': 'Aktywni', 'od': '2026-01', 'do': '2026-12'}})
        self.bud({'op': 'arkusz', 'obiekt': {'id': 'a-x', 'nazwa': 'X', 'folder': 'Klienci', 'kategoria': 'Aktywni', 'od': '2026-01', 'do': '2026-12'}})
        self.przelicz()
        self.assertIn('Klienci', [f['folder'] for f in zapytania_budzet.drzewo(self.con)['foldery']])

    def test_zmiana_nazwy_folderu_i_kategorii_przenosi_arkusze(self):
        self.s(akcja='zmien_folder', folder='Firma', nazwa='DigitalH')
        self.s(akcja='zmien_kategorie', folder='DigitalH', kategoria='Koszty', nazwa='Koszty stałe')
        self.przelicz()
        a = self.con.execute("SELECT folder, kategoria FROM bud_arkusz WHERE id = 'a-test'").fetchone()
        self.assertEqual(tuple(a), ('DigitalH', 'Koszty stałe'))
        self.assertNotIn('Firma', self.struktura())
        with self.assertRaisesRegex(ValueError, 'już jest'):
            self.s(akcja='zmien_folder', folder='DigitalH', nazwa='alfa')

    def test_usuwanie_tylko_pustych_albo_z_przeniesieniem(self):
        with self.assertRaisesRegex(ValueError, r'ma arkusze \(1\)'):
            self.s(akcja='usun_folder', folder='Firma')
        with self.assertRaisesRegex(ValueError, 'ostatnia kategoria'):
            self.s(akcja='usun_kategorie', folder='Firma', kategoria='Koszty')
        self.s(akcja='dodaj_kategorie', folder='Firma', kategoria='Inne')
        with self.assertRaisesRegex(ValueError, r'ma arkusze \(1\)'):
            self.s(akcja='usun_kategorie', folder='Firma', kategoria='Koszty')
        # z przeniesieniem arkuszy do innej kategorii: jedna zmiana, arkusz w nowym miejscu
        self.s(akcja='usun_kategorie', folder='Firma', kategoria='Koszty', do_folderu='Firma', do_kategorii='Inne')
        self.przelicz()
        self.assertEqual(self.struktura()['Firma'], ['Inne'])
        self.assertEqual(self.con.execute("SELECT kategoria FROM bud_arkusz WHERE id = 'a-test'").fetchone()[0], 'Inne')
        # folder z arkuszami do innego folderu: kategorie przechodzą razem z arkuszami, folder znika
        self.s(akcja='usun_folder', folder='Firma', do_folderu='Beta')
        self.przelicz()
        st = self.struktura()
        self.assertNotIn('Firma', st)
        self.assertEqual(st['Beta'], ['Projekty dodatkowe', 'Inne'])
        self.assertEqual(tuple(self.con.execute("SELECT folder, kategoria FROM bud_arkusz WHERE id = 'a-test'").fetchone()), ('Beta', 'Inne'))
        # pusty folder z pustymi kategoriami usuwa się razem z nimi
        self.s(akcja='dodaj_folder', folder='Pusty', kategoria='K1')
        self.s(akcja='dodaj_kategorie', folder='Pusty', kategoria='K2')
        self.s(akcja='usun_folder', folder='Pusty')
        self.przelicz()
        self.assertNotIn('Pusty', self.struktura())

    def test_kolejnosc_folderow_i_kategorii_w_drzewie(self):
        foldery = [f['folder'] for f in self.bib()['struktura'] if not f['systemowy']]
        nowa = list(reversed(foldery))
        self.s(akcja='kolejnosc', foldery=nowa)
        self.s(akcja='dodaj_kategorie', folder='Alfa', kategoria='Projekty')
        self.s(akcja='kolejnosc', folder='Alfa', kategorie=['Projekty', 'Obsługa stała'])
        with self.assertRaisesRegex(ValueError, 'nie zgadza się'):
            self.s(akcja='kolejnosc', foldery=nowa[:-1])
        self.przelicz()
        self.assertEqual([f['folder'] for f in self.bib()['struktura'] if not f['systemowy']], nowa)
        drzewo = [f['folder'] for f in zapytania_budzet.drzewo(self.con)['foldery']]
        self.assertEqual([f for f in drzewo if f in nowa], [f for f in nowa if f in drzewo])
        self.assertEqual(self.struktura()['Alfa'], ['Projekty', 'Obsługa stała'])

    def test_struktura_przezywa_nowy_eksport_i_cofniecie(self):
        self.s(akcja='dodaj_folder', folder='Klienci', kategoria='Aktywni')
        ostatni = budzet.model_bazowy(zmiany.wczytaj()[0], odswiez=False)[0]
        self.assertNotIn('Klienci', {a['folder'] for a in ostatni['arkusze']})   # wpis, nie zmiana pliku importu
        self.przelicz()
        o = zapytania_budzet.ostatni(self.con)
        zmiany.zapisz('cofnij', {'wpis': o['wpis']})
        self.przelicz()
        self.assertNotIn('Klienci', self.struktura())


if __name__ == '__main__':
    unittest.main()
