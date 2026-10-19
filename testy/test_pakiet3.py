"""Pakiet 3 (edycja arkusza jak w BS) na zmyślonych danych: akcje na wierszach liczone na serwerze (scal, podziel,
duplikuj, usuń, przenieś), zarządzanie arkuszem (nazwa, zakres, przesunięcie startu, duplikat, usunięcie), blokady
z komunikatem „co zrobić zamiast”, odstępstwa planu od wiersza (pomarańczowe pola), karta komórki i cofanie."""
import unittest

from finanse import budzet, plan, zapytania_budzet, zmiany
from testy.test_pakiet2 import Baza, DZIS


class Pakiet3(Baza):
    def wiersz(self, wid, **kw):
        self.bud({'op': 'wiersz', 'obiekt': {'id': wid, 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Faktura (jedna)',
                                             'kontrahent': f'Firma {wid}', 'stawka_vat': 23, 'dzien_wystawienia': '10.',
                                             'dni_na_platnosc': 14, 'metoda': 'Przelew', **kw}})

    def komorki(self, wid, **kwoty):
        self.bud({'op': 'seria', 'operacje': [{'op': 'komorka', 'wiersz': wid, 'miesiac': m.replace('_', '-'), 'kwota': k}
                                               for m, k in kwoty.items()]})

    def wiersz_bs(self, pid):
        return self.con.execute('SELECT wiersz FROM bud_platnosc WHERE id = ?', (pid,)).fetchone()[0]

    def arkusz_bs(self):
        return self.con.execute("SELECT id FROM bud_arkusz WHERE nazwa = 'Obsługa stała Alfa'").fetchone()[0]

    def wiersze(self, aid='a-test'):
        return {r['id']: dict(r) for r in self.con.execute('SELECT * FROM bud_wiersz WHERE arkusz = ? ORDER BY kolejnosc', (aid,))}


class TestScal(Pakiet3):
    def test_dwie_faktury_w_tym_samym_miesiacu_daja_worek_ze_wszystkimi_platnosciami(self):
        self.wiersz('w1', komentarz='pierwszy', sekcja='Biuro')
        self.wiersz('w2', komentarz='drugi', dzien_wystawienia='20.')
        self.komorki('w1', **{'2026_11': 100000})
        self.komorki('w2', **{'2026_11': 50000, '2026_12': 30000})
        self.przelicz()
        przed = sorted((p['netto'], p['vat'], p['wystawienie']) for w in ('w1', 'w2') for p in self.plany(w).values())
        self.bud({'op': 'scal', 'wiersze': ['w1', 'w2']})
        self.przelicz()
        ws = self.wiersze()
        self.assertNotIn('w2', ws)
        self.assertEqual((ws['w1']['podstawa'], ws['w1']['komentarz'], ws['w1']['sekcja']), ('Faktura (w worku)', 'pierwszy', 'Biuro'))
        ps = self.plany('w1')
        # wszystkie płatności, nie suma kwot: 2 w listopadzie (każda ze swoją datą), 1 w grudniu
        self.assertEqual(sorted((p['netto'], p['vat'], p['wystawienie']) for p in ps.values()), przed)
        self.assertEqual(sorted(p['miesiac'] for p in ps.values()), ['2026-11', '2026-11', '2026-12'])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM bud_komorka WHERE wiersz IN ('w1', 'w2')").fetchone()[0], 0)
        # zmiana kwoty w komórce worka po scaleniu liczy plany od nowa (tygodnie)
        self.komorki('w1', **{'2026_11': 150000})
        self.przelicz()
        self.assertEqual(sum(p['netto'] for p in self.plany('w1').values() if p['miesiac'] == '2026-11'), 150000)

    def test_bez_wspolnego_miesiaca_podstawa_zostaje(self):
        self.wiersz('w1')
        self.wiersz('w2')
        self.komorki('w1', **{'2026_10': 1000})
        self.komorki('w2', **{'2026_11': 2000})
        self.bud({'op': 'scal', 'wiersze': ['w1', 'w2']})
        self.przelicz()
        self.assertEqual(self.wiersze()['w1']['podstawa'], 'Faktura (jedna)')
        self.assertEqual(sum(p['netto'] for p in self.plany('w1').values()), 3000)

    def test_rozna_podstawa_albo_rodzaj_odrzucone(self):
        self.wiersz('w1')
        self.wiersz('w2', podstawa='Bez faktury')
        self.wiersz('w3', rodzaj=1)
        self.wiersz('w4', podstawa='Faktura (w worku)')
        with self.assertRaisesRegex(ValueError, 'tej samej podstawie'):
            self.bud({'op': 'scal', 'wiersze': ['w1', 'w2']})
        with self.assertRaisesRegex(ValueError, 'tego samego rodzaju'):
            self.bud({'op': 'scal', 'wiersze': ['w1', 'w3']})
        self.bud({'op': 'scal', 'wiersze': ['w1', 'w4']})   # faktura z fakturą w worku: wolno
        with self.assertRaises(ValueError):
            zmiany.sprawdz('bud', {'op': 'scal', 'wiersze': ['w1']})

    def test_rzeczywiste_przechodza_z_id_i_cofniecie_przywraca(self):
        wid = self.wiersz_bs('bs:1')   # Alfa: bs:1 rzeczywista, bs:2 i bs:3 plany
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-alfa', 'arkusz': self.arkusz_bs(), 'rodzaj': 1, 'podstawa': 'Faktura (jedna)',
                                             'kontrahent': 'Alfa'}})
        self.komorki('w-alfa', **{'2026_12': 70000})
        wpis = self.bud({'op': 'scal', 'wiersze': ['w-alfa', wid]})
        self.przelicz()
        ps = self.plany('w-alfa')
        self.assertIn('bs:1', ps)
        self.assertEqual(ps['bs:1']['typ'], 'rzeczywista')
        self.assertEqual(sum(p['netto'] for p in ps.values()), 70000 + 3 * 100000)
        self.assertIsNone(self.con.execute('SELECT 1 FROM bud_wiersz WHERE id = ?', (wid,)).fetchone())
        zmiany.zapisz('cofnij', {'wpis': wpis['id']})
        self.przelicz()
        self.assertEqual(self.wiersz_bs('bs:1'), wid)


class TestPodziel(Pakiet3):
    def test_tyle_wierszy_ile_platnosci(self):
        self.wiersz('w1', komentarz='abonament', sekcja='IT')
        self.komorki('w1', **{'2026_01': 100, '2026_02': 200, '2026_03': 300})
        self.bud({'op': 'podziel', 'wiersz': 'w1'})
        self.przelicz()
        ws = self.wiersze()
        self.assertEqual(len(ws), 3)
        for w in ws.values():
            self.assertEqual((w['komentarz'], w['sekcja'], w['podstawa'], w['dzien_wystawienia']), ('abonament', 'IT', 'Faktura (jedna)', '10.'))
            self.assertEqual(len(self.plany(w['id'])), 1)
        self.assertEqual(self.plany('w1')[next(iter(self.plany('w1')))]['netto'], 100)   # najwcześniejsza zostaje w oryginale
        self.assertEqual(sorted(p['netto'] for w in ws for p in self.plany(w).values()), [100, 200, 300])

    def test_jedna_platnosc_i_umowa_odrzucone(self):
        self.wiersz('w1')
        self.komorki('w1', **{'2026_01': 100})
        with self.assertRaisesRegex(ValueError, 'co najmniej dwiema płatnościami'):
            self.bud({'op': 'podziel', 'wiersz': 'w1'})
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-u', 'arkusz': 'a-test', 'rodzaj': -1, 'podstawa': 'Umowa o pracę',
                                             'proporcje': {'osoba': 60, 'us': 10, 'zus': 30}}})
        self.komorki('w-u', **{'2026_01': 1000, '2026_02': 1000})
        with self.assertRaisesRegex(ValueError, 'Wiersza umowy nie podzielisz'):
            self.bud({'op': 'podziel', 'wiersz': 'w-u'})


class TestDuplikujUsunPrzenies(Pakiet3):
    def test_duplikat_ma_kwoty_a_rzeczywiste_staja_sie_planami(self):
        wid = self.wiersz_bs('bs:1')
        self.bud({'op': 'duplikuj', 'wiersze': [wid], 'nowe': ['w-kopia']})
        self.przelicz()
        ps = self.plany('w-kopia')
        self.assertEqual({p['typ'] for p in ps.values()}, {'plan'})
        self.assertEqual(sorted((p['miesiac'], p['netto']) for p in ps.values()),
                         [('2026-08', 100000), ('2026-09', 100000), ('2026-10', 100000)])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM bud_komorka WHERE wiersz = 'w-kopia'").fetchone()[0], 3)

    def test_usuniecie_wiersza_i_platnosci_rzeczywistej_zablokowane(self):
        wid = self.wiersz_bs('bs:1')
        with self.assertRaisesRegex(ValueError, 'nie usuniesz.*Wyczyść kwoty'):
            self.bud({'op': 'wiersz', 'obiekt': {'id': wid}, 'usun': True})
        with self.assertRaisesRegex(ValueError, 'płatność rzeczywista'):
            self.bud({'op': 'platnosc', 'obiekt': {'id': 'bs:1'}, 'usun': True})
        self.wiersz('w1')
        self.komorki('w1', **{'2026_01': 100})
        self.bud({'op': 'seria', 'operacje': [{'op': 'wiersz', 'obiekt': {'id': 'w1'}, 'usun': True}]})
        self.przelicz()
        self.assertEqual(self.plany('w1'), {})

    def test_przeniesienie_poza_zakres_arkusza_docelowego_odrzucone(self):
        self.wiersz('w1')
        self.komorki('w1', **{'2025_03': 100})
        with self.assertRaisesRegex(ValueError, 'Najpierw wydłuż arkusz docelowy'):
            self.bud({'op': 'przenies', 'wiersze': ['w1'], 'do_arkusza': self.arkusz_bs()})
        # do nowego arkusza tworzonego w tej samej serii
        self.bud({'op': 'seria', 'operacje': [
            {'op': 'arkusz', 'obiekt': {'id': 'a-nowy', 'nazwa': 'Nowy', 'folder': 'Firma', 'kategoria': 'Koszty', 'od': '2025-01', 'do': '2025-12'}},
            {'op': 'przenies', 'wiersze': ['w1'], 'do_arkusza': 'a-nowy'}]})
        self.przelicz()
        self.assertIn('w1', self.wiersze('a-nowy'))

    def test_limit_wierszy_w_arkuszu(self):
        stary = budzet.LIMIT_WIERSZY
        budzet.LIMIT_WIERSZY = 2
        try:
            self.wiersz('w1')
            self.wiersz('w2')
            with self.assertRaisesRegex(ValueError, 'najwyżej 2 wierszy'):
                self.wiersz('w3')
        finally:
            budzet.LIMIT_WIERSZY = stary


class TestZarzadzaj(Pakiet3):
    def test_zakres_wydluzenie_dodaje_kolumny_bez_zmiany_platnosci(self):
        aid = self.arkusz_bs()
        przed = {r['id']: (r['netto'], r['termin']) for r in self.con.execute('SELECT * FROM bud_platnosc')}
        self.bud({'op': 'arkusz', 'obiekt': {'id': aid, 'do': '2027-12'}})
        self.przelicz()
        d = zapytania_budzet.arkusz(self.con, aid)
        self.assertEqual(d['miesiace'][-1], '2027-12')
        self.assertEqual({r['id']: (r['netto'], r['termin']) for r in self.con.execute('SELECT * FROM bud_platnosc')}, przed)

    def test_wyciecie_miesiaca_z_rzeczywista_odrzucone_a_z_planami_kasuje_plany(self):
        aid = self.arkusz_bs()   # 2026-07 do 2026-12, rzeczywiste w sierpniu i wrześniu, plan w lipcu (bs:4)
        with self.assertRaisesRegex(ValueError, 'sierpień 2026.*muszą zostać w zakresie'):
            self.bud({'op': 'arkusz', 'obiekt': {'id': aid, 'od': '2026-09'}})
        self.bud({'op': 'arkusz', 'obiekt': {'id': aid, 'od': '2026-08'}})
        self.przelicz()
        self.assertIsNone(self.con.execute("SELECT 1 FROM bud_platnosc WHERE id = 'bs:4'").fetchone())
        self.assertIsNotNone(self.con.execute("SELECT 1 FROM bud_platnosc WHERE id = 'bs:1'").fetchone())

    def test_zakres_ponad_20_lat_i_odwrotny_odrzucone(self):
        with self.assertRaisesRegex(ValueError, '20 lat'):
            self.bud({'op': 'arkusz', 'obiekt': {'id': 'a-test', 'od': '2020-01', 'do': '2040-01'}})
        with self.assertRaisesRegex(ValueError, '20 lat'):
            self.bud({'op': 'arkusz', 'obiekt': {'id': 'a-test', 'do': '2045-01'}})   # tylko koniec: sprawdza serwer
        with self.assertRaisesRegex(ValueError, 'po końcu'):
            self.bud({'op': 'arkusz', 'obiekt': {'id': 'a-test', 'od': '2027-01'}})
        with self.assertRaisesRegex(ValueError, 'najwyżej 80 znaków'):
            self.bud({'op': 'arkusz', 'obiekt': {'id': 'a-test', 'nazwa': 'x' * 81}})

    def test_przesuniecie_startu(self):
        with self.assertRaisesRegex(ValueError, 'jego startu nie przesuniesz'):
            self.bud({'op': 'przesun_arkusz', 'arkusz': self.arkusz_bs(), 'o': 6})
        self.wiersz('w1')
        self.komorki('w1', **{'2025_07': 100000})
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'plan:w1:2025-07:1', 'stawka': 8}})   # ręczna zmiana przepada
        self.bud({'op': 'przesun_arkusz', 'arkusz': 'a-test', 'o': 6})
        self.przelicz()
        a = dict(self.con.execute("SELECT * FROM bud_arkusz WHERE id = 'a-test'").fetchone())
        self.assertEqual((a['od'], a['do']), ('2025-07', '2027-06'))
        ps = list(self.plany('w1').values())
        self.assertEqual([(p['miesiac'], p['netto'], p['vat'], p['wystawienie']) for p in ps], [('2026-01', 100000, 23000, '2026-01-10')])

    def test_duplikat_arkusza_na_kolejny_rok(self):
        self.wiersz('w1', sekcja='Biuro')
        self.wiersz('w2', rodzaj=1)
        self.komorki('w1', **{'2026_01': 1000, '2026_06': 2000})
        bez = {'id': 'a-2027', 'nazwa': 'Testowy - kopia', 'folder': 'Firma', 'kategoria': 'Koszty', 'od': '2026-01', 'do': '2027-12'}
        self.bud({'op': 'duplikuj_arkusz', 'arkusz': 'a-test', 'obiekt': bez, 'przesuniecie': 12, 'wartosci': False})
        self.bud({'op': 'duplikuj_arkusz', 'arkusz': 'a-test', 'obiekt': {**bez, 'id': 'a-z-wart'}, 'przesuniecie': 12, 'wartosci': True})
        self.przelicz()
        kopia = self.wiersze('a-2027')
        self.assertEqual(sorted((w['rodzaj'], w['sekcja'], w['kontrahent']) for w in kopia.values()),
                         sorted((w['rodzaj'], w['sekcja'], w['kontrahent']) for w in self.wiersze().values()))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz"
                                          " WHERE w.arkusz = 'a-2027'").fetchone()[0], 0)
        z = self.con.execute("SELECT p.miesiac, p.netto FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz"
                             " WHERE w.arkusz = 'a-z-wart' ORDER BY p.miesiac").fetchall()
        self.assertEqual([tuple(x) for x in z], [('2027-01', 1000), ('2027-06', 2000)])

    def test_usuniecie_arkusza(self):
        with self.assertRaisesRegex(ValueError, 'Arkusz ma płatności rzeczywiste'):
            self.bud({'op': 'arkusz', 'obiekt': {'id': self.arkusz_bs()}, 'usun': True})
        self.wiersz('w1')
        self.komorki('w1', **{'2026_01': 1000})
        self.bud({'op': 'arkusz', 'obiekt': {'id': 'a-test'}, 'usun': True})
        self.przelicz()
        self.assertIsNone(self.con.execute("SELECT 1 FROM bud_wiersz WHERE id = 'w1'").fetchone())
        self.assertEqual(self.plany('w1'), {})


class TestKartaIOdstepstwa(Pakiet3):
    def test_reczna_stawka_na_planie_podswietlona_i_karta_komorki(self):
        self.wiersz('w1')
        self.komorki('w1', **{'2026_11': 100000})
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'plan:w1:2026-11:1', 'stawka': 8, 'termin': '2026-11-30'}})
        self.przelicz()
        k = zapytania_budzet.komorka(self.con, 'w1', '2026-11')
        self.assertEqual(k['kwota'], 100000)
        self.assertEqual(len(k['platnosci']), 1)
        self.assertEqual(set(k['platnosci'][0]['platnosc']['odstepstwa']), {'stawka', 'termin'})

    def test_odstepstwa_wg_regul_wiersza(self):
        w = {'podstawa': 'Faktura (jedna)', 'kontrahent': 'A', 'stawka_vat': 23, 'dzien_wystawienia': '10.', 'dni_na_platnosc': 14,
             'metoda': 'Przelew', 'ksiegowane': 1, 'w_cashflow': 1}
        p = {'miesiac': '2026-11', 'kontrahent': 'A', 'stawka': 23, 'wystawienie': '2026-11-10', 'termin': '2026-11-24',
             'realny': '2026-11-24', 'ksiegowanie': '2026-11-01', 'metoda': 'Przelew', 'ksiegowane': 1, 'w_cashflow': 1}
        self.assertEqual(plan.odstepstwa(p, w), [])
        self.assertEqual(plan.odstepstwa({**p, 'kontrahent': 'B', 'realny': '2026-12-01', 'w_cashflow': 0}, w), ['kontrahent', 'w_cashflow', 'realny'])
        # zmiana dnia wystawienia przesuwa termin: termin nie jest osobnym odstępstwem
        self.assertEqual(plan.odstepstwa({**p, 'wystawienie': '2026-11-12', 'termin': '2026-11-26', 'realny': '2026-11-26',
                                          'ksiegowanie': '2026-11-01'}, w), ['wystawienie'])
        self.assertEqual(plan.odstepstwa(p, {**w, 'dzien_wystawienia': '(auto)', 'metoda': ''}), ['metoda'])

    def test_plan_na_inny_miesiac_przesuwa_daty(self):
        self.bud({'op': 'platnosc', 'obiekt': {'id': 'bs:3', 'miesiac': '2026-12'}})
        self.przelicz()
        p = self.con.execute("SELECT miesiac, termin, realny FROM bud_platnosc WHERE id = 'bs:3'").fetchone()
        self.assertEqual(tuple(p), ('2026-12', '2027-01-07', None))   # z października: daty o 2 miesiące
        with self.assertRaisesRegex(ValueError, 'Płatności rzeczywistej nie przeniesiesz'):
            self.bud({'op': 'platnosc', 'obiekt': {'id': 'bs:1', 'miesiac': '2026-12'}})

    def test_ostatnia_zmiana_do_cofniecia(self):
        self.wiersz('w1')
        wpis = self.bud({'op': 'komorka', 'wiersz': 'w1', 'miesiac': '2026-01', 'kwota': 5})
        self.przelicz()
        self.assertEqual(zapytania_budzet.ostatni(self.con)['wpis'], wpis['id'])
        self.assertEqual(zapytania_budzet.ostatni(self.con)['ops'], ['komorka'])
        zmiany.zapisz('cofnij', {'wpis': wpis['id']})
        self.przelicz()
        self.assertNotEqual(zapytania_budzet.ostatni(self.con)['wpis'], wpis['id'])


class TestKomunikaty(unittest.TestCase):
    def test_komunikaty_mowia_co_zrobic(self):
        for d, tekst in (({'op': 'wiersz', 'obiekt': {'id': 'w', 'komentarz': 'x' * 171}}, 'Komentarz: najwyżej 170 znaków'),
                         ({'op': 'wiersz', 'obiekt': {'id': 'w', 'dni_na_platnosc': 100}}, 'karcie płatności'),
                         ({'op': 'arkusz', 'obiekt': {'id': 'a', 'od': '2026-05', 'do': '2026-01'}}, 'po końcu'),
                         ({'op': 'przesun_arkusz', 'arkusz': 'a', 'o': 0}, 'różna od zera')):
            with self.subTest(d=d), self.assertRaisesRegex(ValueError, tekst):
                zmiany.sprawdz('bud', d)


if __name__ == '__main__':
    unittest.main()
