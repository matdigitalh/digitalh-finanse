"""Lista płac jako dane rzeczywiste (2026-10-20) na zmyślonych danych: działa przy wyłączonym planowaniu i w miesiącach
z płatnościami rzeczywistymi z kopii BS (lista ma pierwszeństwo, BS widać jako zastąpioną kwotę z różnicą), nowe pola (PPK
pracownika i pracodawcy jako płatność w zbiorczym wierszu PPK zamiast kwoty BS, pakiet medyczny i potrącenia bez płatności),
powołanie zarządu rozbite na wypłatę, zdrowotną i PIT bez zmiany sumy, koszt pracodawcy, terminy, ostrzeżenie „do wpisania”,
cash flow bez podwójnego PPK, przetrwanie przyjęcia kopii z BS i nowego eksportu BS, cofnięcie listy. Wszystkie liczby zmyślone."""
import csv
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from finanse import baza, cashflow, konfig, kopia_bs, laczenie, lista_plac, odbudowa, przestawna, serwer, zapytania_budzet, zmiany
from testy.pomoc import Srodowisko, operacja, zapisz_fakturownie, zapisz_ing
from testy.test_budzet import KOLUMNY, bs

DZIS = '2026-10-13'
ARK = ('Pracownicy', 'Firma', 'Koszty stałe')


def _bs(id_, etap, podstawa, kto, kwota, m, termin, komentarz='UoP', realny=''):
    return bs(id_, '-1', etap, podstawa, kto, f'-{kwota}', m, termin, *ARK, komentarz=komentarz, realny=realny)


def wiersze_bs():
    """Eksport BS: umowa o pracę Anny (trzy składowe, ta sama płatność BS), powołanie prezesa jedną kwotą brutto, zbiorczy
    wiersz PPK (miesiąc przelewu) i plany na październik."""
    w = []
    for i, (m, wyp, nast) in enumerate((('2026-01', '2026-02-07', '2026-03'), ('2026-02', '2026-03-07', '2026-04'),
                                         ('2026-10', '2026-11-07', '2026-12')), start=1):
        etap = 'Planowana' if m == '2026-10' else 'Opłacona'
        w += [_bs(str(100 + i), etap, 'Umowa o pracę - dla wykonawcy', 'Anna Nowak', '7350,26', m, wyp, realny=wyp if etap == 'Opłacona' else ''),
              _bs(str(100 + i), etap, 'Umowa o pracę - PIT', 'Anna Nowak', '780,03', m, f'{nast}-20'),
              _bs(str(100 + i), etap, 'Umowa o pracę - ZUS', 'Anna Nowak', '4279,15', m, f'{nast}-15')]
        w.append(_bs(str(200 + i), etap, 'Bez faktury', 'Prezes', '11819,70', m, wyp, komentarz='', realny=wyp if etap == 'Opłacona' else ''))
    for i, (m, kw, etap) in enumerate((('2026-01', '280,00', 'Opłacona'), ('2026-02', '275,73', 'Opłacona'), ('2026-03', '594,78', 'Opłacona'),
                                        ('2026-04', '765,86', 'Opłacona'), ('2026-11', '765,86', 'Planowana'), ('2026-12', '765,86', 'Planowana')), start=1):
        w.append(_bs(str(300 + i), etap, 'Bez faktury', 'Kontrahent', kw, m, f'{m}-21', komentarz='PPK'))
    return w


def zapisz_bs(srod, nazwa, wiersze):
    p = srod.dane / 'Budget Studio' / nazwa
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=KOLUMNY, delimiter='\t')
        w.writeheader()
        w.writerows(wiersze)
    return p


def przygotuj(srod):
    zapisz_fakturownie(srod.dane, 'fakturownia_sprzedaz_2026-10-13.csv', [])
    zapisz_ing(srod.dane, 'ing_historia_2026-01-01_2026-10-13.csv', [
        operacja('2026-10-13', '-10,00', '50000,00', 'ING BANK', 'OPŁATA', ref='X'),
        operacja('2026-03-13', '-337,58', '50010,00', 'PKO EMERYTURA- SFIO', 'SKŁADKI PPK 2026 02 DIGITALH', ref='PPK1'),
        operacja('2026-03-13', '-2357,00', '50347,58', 'Urząd Skarbowy', '/TI/N1/OKR/26M02/SFP/PIT-4 /TXT/PIT-4', ref='US1'),
        operacja('2026-03-13', '-5110,44', '52704,58', 'ZUS', 'DRA 01/02', ref='ZUS1'),
        operacja('2026-02-12', '-4000,00', '57815,02', 'ZUS', 'DRA 01/01', ref='ZUS0'),
        operacja('2026-02-04', '-9367,93', '61815,02', 'PREZES JAN', 'WYNAGRODZENIE ZA 01.2026 ZARZĄD', ref='W2'),
        operacja('2026-02-04', '-6242,73', '71182,95', 'NOWAK ANNA', 'WYNAGRODZENIE ZA 01.2026', ref='W1'),
    ])
    zapisz_bs(srod, 'budget_studio_2026-10-13.csv', wiersze_bs())
    (srod.katalog / 'Finanse' / 'Aplikacja').mkdir(parents=True, exist_ok=True)
    (srod.katalog / 'Finanse' / 'Aplikacja' / 'arkusze_bs.json').write_text(json.dumps({'arkusze': [
        {'nazwa': ARK[0], 'folder': ARK[1], 'kategoria': ARK[2], 'od': '2026-01', 'do': '2026-12'}]}), encoding='utf-8')


# lista za styczeń (wypłata 4.02): Anna z PPK, pakietem i potrąceniem; prezes (powołanie) bez składek społecznych
ANNA = {'osoba': 624273, 'us': 96900, 'zus': 404667, 'ppk_pracownik': 19290, 'ppk_pracodawca': 14468, 'pakiet': 8900, 'potracenia': 8000}
PREZES = {'osoba': 936793, 'us': 138800, 'zus': 106377, 'ppk_pracownik': 0, 'ppk_pracodawca': 0, 'pakiet': 0, 'potracenia': 0}


class Baza(unittest.TestCase):
    def setUp(self):
        self.srod = Srodowisko().__enter__()
        przygotuj(self.srod)
        odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        self.assertFalse(zapytania_budzet.planowanie(self.con))   # planowanie wyłączone (jak dziś u Mata)
        self.anna = self.wiersz('Anna Nowak', 'Umowa o pracę - dla wykonawcy')
        self.prezes = self.wiersz('Prezes', 'Bez faktury')
        self.ppk = self.wiersz('Kontrahent', 'Bez faktury')

    def tearDown(self):
        self.con.close()
        self.srod.__exit__()

    def wiersz(self, kto, podstawa):
        r = self.con.execute('SELECT id FROM bud_wiersz WHERE kontrahent = ? AND podstawa = ?', (kto, podstawa)).fetchone()
        return r[0] if r else None

    def przelicz(self):
        self.con.close()
        r = odbudowa.odbuduj()
        self.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        return r

    def lista(self, d, przelicz=True):
        czyste = zmiany.sprawdz('lista_plac', d)
        serwer._sprawdz_odwolania(self.con, 'lista_plac', czyste)
        w = zmiany.zapisz('lista_plac', czyste)
        if przelicz:
            self.przelicz()
        return w

    def blad(self, d) -> str:
        with self.assertRaises(ValueError) as e:
            czyste = zmiany.sprawdz('lista_plac', d)
            serwer._sprawdz_odwolania(self.con, 'lista_plac', czyste)
        return str(e.exception)

    def styczen(self, **kw):
        d = {'miesiac': '2026-01', 'pozycje': [{'wiersz': self.anna, 'data_wyplaty': '2026-02-04', **ANNA},
                                               {'wiersz': self.prezes, 'data_wyplaty': '2026-02-04', **PREZES}],
             'ppk': {'wiersz': self.ppk}, **kw}
        return self.lista(d)

    def platnosci(self, sql='', *arg):
        return [dict(r) for r in self.con.execute(
            'SELECT p.*, w.kontrahent AS w_kontrahent, w.podstawa, s.etap FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz'
            ' LEFT JOIN bud_stan s ON s.platnosc = p.id WHERE 1=1 ' + sql + ' ORDER BY p.id', arg)]

    def komorka(self, kto, podstawa, m):
        return self.platnosci('AND w.kontrahent = ? AND w.podstawa = ? AND p.miesiac = ?', kto, podstawa, m)

    def ppk_po_miesiacach(self):
        po_m = {}
        for p in self.platnosci('AND p.wiersz = ?', self.ppk):
            po_m.setdefault(p['miesiac'], []).append((p['netto'], p['zrodlo']))
        return {m: sorted(v) for m, v in po_m.items()}


class TestRzeczywistaZBS(Baza):
    def test_lista_zastepuje_kwoty_bs_przy_wylaczonym_planowaniu(self):
        """Pkt 1: styczeń ma płatności rzeczywiste z kopii BS; lista płac je zastępuje (osoba, miesiąc, składowa), BS zostaje
        do wglądu z różnicą, oznaczenie „z listy płac” w arkuszu, ostrzeżenie „do wpisania” znika."""
        o = laczenie.ostrzezenia(self.con)
        self.assertIn(('lista_do_wpisania', self.anna, '2026-01'), {(x['rodzaj'], x['wiersz'], x['miesiac']) for x in o})
        f = laczenie.lista_plac(self.con, '2026-01')
        anna = next(x for x in f['osoby'] if x['wiersz'] == self.anna)
        self.assertEqual((anna['z_kopii'], anna['mozna'], anna['bs']), (True, True, {'osoba': 735026, 'us': 78003, 'zus': 427915}))
        self.styczen()
        for podstawa, s in (('Umowa o pracę - dla wykonawcy', 'osoba'), ('Umowa o pracę - PIT', 'us'), ('Umowa o pracę - ZUS', 'zus')):
            ps = self.komorka('Anna Nowak', podstawa, '2026-01')
            self.assertEqual([(p['typ'], p['netto'], p['zrodlo']) for p in ps], [('rzeczywista', ANNA[s], 'lista płac')])
        wyp = self.komorka('Anna Nowak', 'Umowa o pracę - dla wykonawcy', '2026-01')[0]
        self.assertIn('w BS było 7 350,26 zł', wyp['tytul'])
        self.assertEqual(json.loads(wyp['skladniki']), ANNA)
        f = laczenie.lista_plac(self.con, '2026-01')
        anna = next(x for x in f['osoby'] if x['wiersz'] == self.anna)
        self.assertEqual((anna['z_listy'], anna['wpisane'], anna['bs'], anna['bs_razem']),
                         (True, ANNA, {'osoba': 735026, 'us': 78003, 'zus': 427915}, 1240944))
        self.assertEqual(anna['roznica_bs'], 624273 + 96900 + 404667 - 1240944)
        self.assertNotIn(('lista_do_wpisania', '2026-01'), {(x['rodzaj'], x['miesiac']) for x in laczenie.ostrzezenia(self.con)})
        self.assertIn(('lista_do_wpisania', '2026-02'), {(x['rodzaj'], x['miesiac']) for x in laczenie.ostrzezenia(self.con)})
        # arkusz: komórka z listy płac oznaczona
        aid = self.con.execute('SELECT arkusz FROM bud_wiersz WHERE id = ?', (self.anna,)).fetchone()[0]
        w = next(x for x in zapytania_budzet.arkusz(self.con, aid)['wiersze'] if x['id'] == self.anna)
        self.assertEqual((w['komorki']['2026-01']['z_listy'], w['komorki']['2026-02']['z_listy']), (1, 0))

    def test_terminy_i_etap_z_bs(self):
        """Terminy: wypłata = data z listy, ZUS 15., PIT 20. miesiąca po wypłacie; etap BS przechodzi z płatności zastąpionej
        (lista poprawia kwotę), a przelew z banku nadal oznacza opłacenie."""
        self.styczen()
        ps = {(p['w_kontrahent'], p['skladowa'] or p['podstawa']): p for p in self.platnosci("AND p.zrodlo = 'lista płac'")}
        wyp = ps[('Anna Nowak', 'Umowa o pracę - dla wykonawcy')]
        self.assertEqual((wyp['termin'], wyp['realny'], wyp['etap']), ('2026-02-04', '2026-02-04', 'Opłacona'))   # przelew 6 242,73
        self.assertEqual(ps[('Anna Nowak', 'Umowa o pracę - ZUS')]['termin'], '2026-03-15')
        self.assertEqual(ps[('Anna Nowak', 'Umowa o pracę - PIT')]['termin'], '2026-03-20')
        self.assertEqual(ps[('Anna Nowak', 'Umowa o pracę - PIT')]['etap_bs'], 'Opłacona')
        self.assertEqual(ps[('Anna Nowak', 'Umowa o pracę - PIT')]['spinacz'], wyp['id'])

    def test_bud_lista_plac_nie_istnieje_a_lista_dziala_bez_planowania(self):
        """Stara ścieżka (zdarzenie budżetu) odrzucona: lista płac to osobny wpis, nie planowanie."""
        with self.assertRaises(ValueError):
            zmiany.sprawdz('bud', {'op': 'lista_plac', 'miesiac': '2026-01', 'pozycje': [{'wiersz': self.anna, 'osoba': 1}]})
        self.assertIn('Planowanie w apce jest wyłączone', self._blad_bud({'op': 'odlacz', 'dokument': 'lista:2026-01:x'}))
        self.styczen()   # bez planowania zapis przechodzi

    def _blad_bud(self, d):
        with self.assertRaises(ValueError) as e:
            serwer._sprawdz_odwolania(self.con, 'bud', zmiany.sprawdz('bud', d))
        return str(e.exception)

    def test_puste_pole_zostawia_bs_i_niczego_nie_zgaduje(self):
        """Pole bez kwoty (brak na liście) = składowa zostaje jak w BS; 0 = zero."""
        self.lista({'miesiac': '2026-02', 'pozycje': [{'wiersz': self.anna, 'osoba': 671806, 'zus': 435884}]})
        self.assertEqual([(p['netto'], p['zrodlo']) for p in self.komorka('Anna Nowak', 'Umowa o pracę - PIT', '2026-02')], [(78003, 'Budget Studio')])
        self.assertEqual([p['zrodlo'] for p in self.komorka('Anna Nowak', 'Umowa o pracę - ZUS', '2026-02')], ['lista płac'])
        self.assertIn('co najmniej jedną kwotę', self.blad({'miesiac': '2026-02', 'pozycje': [{'wiersz': self.anna, 'pakiet': 8900}]}))


class TestNowePolaIPPK(Baza):
    def test_ppk_w_miesiacu_listy_jak_zus_i_pit(self):
        """Decyzja Mata 2026-10-20: PPK z listy za styczeń stoi w budżecie w styczniu (koszt, rentowność, wynik), jak ZUS i PIT
        tej listy; termin bez zmian (wypłata 4.02, PPK do 15.03); komórka BS marzec (miesiąc przelewu) ustępuje liście, a BS
        stycznia (PPK za grudzień 2025) zostaje. Rozjazd z BS = układ miesięcy (+2), nie kwota."""
        self.styczen()
        po_m = self.ppk_po_miesiacach()
        self.assertEqual(po_m['2026-01'], sorted([(19290 + 14468, 'lista płac'), (28000, 'Budget Studio')]))
        self.assertNotIn('2026-03', po_m)   # komórka BS marzec zastąpiona listą za styczeń
        self.assertEqual(po_m['2026-02'], [(27573, 'Budget Studio')])
        p1 = next(p for p in self.platnosci("AND p.wiersz = ? AND p.zrodlo = 'lista płac'", self.ppk))
        zus = self.komorka('Anna Nowak', 'Umowa o pracę - ZUS', '2026-01')[0]
        self.assertEqual((p1['miesiac'], p1['termin'], p1['realny'], p1['etap']), ('2026-01', '2026-03-15', '2026-03-15', 'Opłacona'))
        self.assertEqual((p1['miesiac'], p1['termin']), (zus['miesiac'], zus['termin']))   # jak ZUS z tej listy
        self.assertEqual(p1['ksiegowanie'][:7], '2026-01')
        self.assertIn('w BS w komórce marzec 2026: 594,78 zł', p1['tytul'])
        f = laczenie.lista_plac(self.con, '2026-01')
        self.assertEqual({k: f['ppk'][k] for k in ('wiersz', 'miesiac', 'miesiac_budzetu', 'termin', 'bs', 'lista', 'roznica')},
                         {'wiersz': self.ppk, 'miesiac': '2026-03', 'miesiac_budzetu': '2026-01', 'termin': '2026-03-15', 'bs': 59478,
                          'lista': 33758, 'roznica': 33758 - 59478})
        mapa = {(x['budzet'], x['lista']): (x['komorka'], x['przesuniecie'], x['bs'], x['z_listy']) for x in f['ppk_mapa']}
        self.assertEqual(mapa[('2026-01', '2026-01')], ('2026-03', 2, 59478, 33758))
        self.assertEqual(mapa[('2026-01', None)], ('2026-01', 0, 28000, None))
        self.assertNotIn(('2026-03', None), mapa)
        # rentowność budżetu (oś: miesiąc budżetowy): PPK z listy w styczniu, w marcu PPK już nie ma
        ark = przestawna.policz(self.con, '2026', 'arkusz,kontrahent', 'budzet')['wiersze'][0]
        ppk = next(x for x in ark['dzieci'] if x['nazwa'] == 'Kontrahent')['miesiace']
        self.assertEqual((ppk['2026-01']['obciazenia'], ppk.get('2026-03', {}).get('obciazenia', 0)), (28000 + 33758, 0))

    def test_ppk_bez_dublowania_przy_kilku_listach_i_ponownym_zapisie(self):
        """Listy za styczeń, luty i marzec: każda w swoim miesiącu, komórki BS marzec i kwiecień (przelewy za I i II) zastąpione,
        BS stycznia i lutego (listy 2025) zostaje; ponowny zapis listy za styczeń przechodzi, choć w zastępowanej komórce BS
        marzec stoi już PPK z listy za marzec, i niczego nie dubluje."""
        self.styczen()
        self.lista({'miesiac': '2026-02', 'pozycje': [{'wiersz': self.anna, 'data_wyplaty': '2026-03-04', 'ppk_pracownik': 20778,
                                                       'ppk_pracodawca': 15584}], 'ppk': {'wiersz': self.ppk}})
        self.lista({'miesiac': '2026-03', 'pozycje': [{'wiersz': self.anna, 'data_wyplaty': '2026-04-08', 'ppk_pracownik': 7229,
                                                       'ppk_pracodawca': 5422}], 'ppk': {'wiersz': self.ppk}})
        oczek = {'2026-01': sorted([(33758, 'lista płac'), (28000, 'Budget Studio')]),
                 '2026-02': sorted([(20778 + 15584, 'lista płac'), (27573, 'Budget Studio')]),
                 '2026-03': [(7229 + 5422, 'lista płac')]}
        po_m = self.ppk_po_miesiacach()
        self.assertEqual({m: po_m[m] for m in oczek}, oczek)
        self.assertNotIn('2026-04', po_m)   # BS kwiecień = PPK z listy za luty
        terminy = {p['miesiac']: p['termin'] for p in self.platnosci("AND p.wiersz = ? AND p.zrodlo = 'lista płac'", self.ppk)}
        self.assertEqual(terminy, {'2026-01': '2026-03-15', '2026-02': '2026-04-15', '2026-03': '2026-05-15'})
        self.styczen()   # ponowny zapis (próba na budżecie z listą za marzec w komórce marzec)
        self.assertEqual(self.ppk_po_miesiacach(), po_m)
        self.lista({'miesiac': '2026-01', 'usun': True})   # usunięcie: wraca BS marzec, lista za marzec zostaje obok
        self.assertEqual(self.ppk_po_miesiacach()['2026-03'], sorted([(59478, 'Budget Studio'), (7229 + 5422, 'lista płac')]))

    def test_ppk_bez_podwojnego_liczenia_w_cash_flow(self):
        """PPK z listy za wrzesień (wypłata 6.10, termin 15.11) stoi w budżecie we wrześniu i zastępuje plan BS w komórce
        listopad; w cash flow termin bez zmian: jedna pozycja PPK w listopadzie (z listy, zamiast planu BS 765,86 z terminem
        21.11), a plan BS z grudnia zostaje."""
        self.lista({'miesiac': '2026-09', 'pozycje': [{'wiersz': self.anna, 'data_wyplaty': '2026-10-06', 'ppk_pracownik': 20778,
                                                       'ppk_pracodawca': 15584}], 'ppk': {'wiersz': self.ppk}})
        po_m = self.ppk_po_miesiacach()
        self.assertEqual((po_m['2026-09'], po_m.get('2026-11')), ([(20778 + 15584, 'lista płac')], None))
        poz = cashflow.pozycje(self.con, cashflow._d(DZIS), None, cashflow._d('2027-03-31'), cashflow.parametry(scenariusz='pelny'))['pozycje']
        ppk = sorted((str(z['data'])[:7], z['kwota']) for z in poz if z.get('kontrahent') == 'Kontrahent')
        self.assertEqual(ppk, [('2026-11', -(20778 + 15584)), ('2026-12', -76586)])

    def test_pakiet_i_potracenia_bez_platnosci_koszt_pracodawcy(self):
        """Pkt 4: koszt pracodawcy = wypłata + ZUS + PIT + PPK obu stron + pakiet + potrącenia; pakiet i potrącenia nie są
        płatnościami (opłaca je faktura za pakiet medyczny)."""
        self.styczen()
        self.assertEqual(lista_plac.koszt_pracodawcy(ANNA), 624273 + 404667 + 96900 + 19290 + 14468 + 8900 + 8000)
        f = laczenie.lista_plac(self.con, '2026-01')
        anna = next(x for x in f['osoby'] if x['wiersz'] == self.anna)
        self.assertEqual(anna['koszt_pracodawcy'], 1176498)
        k = f['koszt'][0]
        self.assertEqual((k['miesiac'], k['koszt_pracodawcy'], k['przez_fakture'], k['platnosci']),
                         ('2026-01', 1176498 + 1181970, 16900, 1176498 + 1181970 - 16900))
        suma_platnosci = sum(p['netto'] for p in self.platnosci("AND p.zrodlo = 'lista płac' AND p.dokument LIKE 'lista:2026-01:%'"))
        self.assertEqual(suma_platnosci, k['platnosci'])   # w budżecie: wypłaty, ZUS, PIT i PPK, bez pakietu i potrąceń


class TestPowolanie(Baza):
    def test_powolanie_rozbite_bez_zmiany_sumy(self):
        """Pkt 3: 11 819,70 z BS = 9 367,93 na konto + 1 063,77 zdrowotna (ZUS) + 1 388 PIT; suma kosztu ta sama, terminy
        ZUS 15. i PIT 20. po miesiącu wypłaty, wiersz staje się wierszem listy płac."""
        self.assertIn('wszystkie części', self.blad({'miesiac': '2026-01', 'pozycje': [{'wiersz': self.prezes, 'osoba': 936793, 'us': 138800}]}))
        self.styczen()
        ps = {p['skladowa']: p for p in self.komorka('Prezes', 'Bez faktury', '2026-01')}
        self.assertEqual({s: p['netto'] for s, p in ps.items()}, {'osoba': 936793, 'zus': 106377, 'us': 138800})
        self.assertEqual(sum(p['netto'] for p in ps.values()), 1181970)
        self.assertEqual((ps['osoba']['termin'], ps['zus']['termin'], ps['us']['termin']), ('2026-02-04', '2026-03-15', '2026-03-20'))
        self.assertEqual(self.con.execute('SELECT lista_plac FROM bud_wiersz WHERE id = ?', (self.prezes,)).fetchone()[0], 1)
        f = laczenie.lista_plac(self.con, '2026-01')
        prezes = next(x for x in f['osoby'] if x['wiersz'] == self.prezes)
        self.assertEqual((prezes['bs'], prezes['koszt_pracodawcy'], prezes['roznica_bs']), ({'osoba': 1181970}, 1181970, 0))

    def test_zus_i_pit4_porownane_z_przelewem_za_miesiac_wyplaty(self):
        """Pkt 5: ZUS z list za styczeń (wypłata w lutym) porównany z DRA za luty, nie za styczeń; zgodne kwoty = brak ostrzeżenia."""
        self.styczen()
        o = [x for x in laczenie.ostrzezenia(self.con) if x['rodzaj'] == 'lista_vs_przelew' and x['miesiac'] == '2026-01']
        self.assertEqual(o, [])


class TestTrwalosc(Baza):
    def test_cofniecie_i_usuniecie_przywracaja_bs(self):
        w = self.styczen()
        self.lista({'miesiac': '2026-01', 'usun': True})
        self.assertEqual([p['zrodlo'] for p in self.komorka('Anna Nowak', 'Umowa o pracę - ZUS', '2026-01')], ['Budget Studio'])
        self.assertEqual([p['netto'] for p in self.platnosci('AND p.wiersz = ? AND p.miesiac = ?', self.ppk, '2026-03')], [59478])
        zmiany.zapisz('cofnij', {'wpis': w['id']})   # cofnięcie wpisu listy: wcześniejszy stan (tu też BS)
        self.przelicz()
        self.assertEqual(len(self.komorka('Prezes', 'Bez faktury', '2026-01')), 1)

    def test_nowy_eksport_bs_i_przyjecie_kopii_nie_kasuja_listy_ani_nie_dubluja_ppk(self):
        """Pkt 6, regresja: lista płac przetrwa nowy eksport BS (inne kwoty BS) i przyjęcie kopii z BS (dwa razy); PPK z listy
        jest w budżecie jeden raz, w miesiącu listy, a kwota BS z komórki przelewu (marzec) nie wraca."""
        self.styczen()

        def stan():
            skl = {'Umowa o pracę - dla wykonawcy': 'osoba', 'Umowa o pracę - PIT': 'us', 'Umowa o pracę - ZUS': 'zus'}
            listy = sorted((p['w_kontrahent'], p['skladowa'] or skl.get(p['podstawa'], p['podstawa']), p['netto'], p['termin'])
                           for p in self.platnosci("AND p.zrodlo = 'lista płac'"))
            ppk = {m: [(k, z == 'lista płac') for k, z in v] for m, v in self.ppk_po_miesiacach().items() if m in ('2026-01', '2026-03')}
            return listy, ppk
        przed = stan()
        self.assertEqual(przed[1], {'2026-01': [(28000, False), (33758, True)]})   # marzec BS nie wraca
        # nowy eksport BS z inną estymacją wynagrodzenia i PPK
        nowe = [dict(x) for x in wiersze_bs()]
        for x in nowe:
            if x['Netto (wartość)'] == '-7350,26':
                x['Netto (wartość)'] = x['Brutto (wartość)'] = '-7400,00'
        zapisz_bs(self.srod, 'budget_studio_2026-10-14.csv', nowe)
        self.przelicz()
        self.assertEqual(stan(), przed)
        for _ in range(2):   # przyjęcie kopii z BS (zdarzenia budżetu sprzed kopii przestają obowiązywać, lista płac nie)
            p = kopia_bs.podglad(wpisy=zmiany.wczytaj()[0])
            self.assertEqual(p['roznic'], 0, p['platnosci'][:3])
            kopia_bs.przyjmij(p['eksport_sha256'], zmiany.wczytaj()[0])
            r = self.przelicz()
            self.assertEqual(stan(), przed, r)
            self.assertEqual(self.con.execute('SELECT COUNT(*) FROM bud_osierocone').fetchone()[0], 0)
        anna = self.wiersz('Anna Nowak', 'Umowa o pracę')   # w kopii składowe umowy są jednym wierszem
        self.assertEqual(anna, self.anna)
        f = laczenie.lista_plac(self.con, '2026-01')
        self.assertEqual(next(x for x in f['osoby'] if x['wiersz'] == self.anna)['bs'], {'osoba': 740000, 'us': 78003, 'zus': 427915})


class TestSerwerListy(unittest.TestCase):
    def test_post_listy_bez_planowania_i_get(self):
        with Srodowisko() as srod:
            przygotuj(srod)
            odbudowa.odbuduj()
            con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
            anna = con.execute("SELECT id FROM bud_wiersz WHERE kontrahent = 'Anna Nowak' AND podstawa LIKE '%wykonawcy'").fetchone()[0]
            con.close()
            stary = konfig.PORT
            h = ThreadingHTTPServer((konfig.HOST, 0), serwer.Obsluga)
            konfig.PORT = h.server_address[1]
            threading.Thread(target=h.serve_forever, daemon=True).start()
            try:
                def wyslij(metoda, sciezka, cialo=None):
                    c = http.client.HTTPConnection('127.0.0.1', konfig.PORT, timeout=20)
                    c.request(metoda, sciezka, body=json.dumps(cialo) if cialo is not None else None,
                              headers={'Host': f'127.0.0.1:{konfig.PORT}', 'X-Finanse': '1', 'Content-Type': 'application/json'})
                    r = c.getresponse()
                    return r.status, json.loads(r.read() or b'{}')
                kod, w = wyslij('POST', '/api/zmiana', {'typ': 'lista_plac', 'dane': {'miesiac': '2026-01', 'pozycje': [{'wiersz': anna, **ANNA}]}})
                self.assertEqual(kod, 200, w)
                self.assertTrue(w['wpis'])
                kod, w = wyslij('POST', '/api/zmiana', {'typ': 'lista_plac', 'dane': {'miesiac': '2026-01', 'pozycje': [{'wiersz': 'nie-ma'}]}})
                self.assertEqual(kod, 400)
                kod, w = wyslij('POST', '/api/zmiana', {'typ': 'lista_plac', 'dane': {'miesiac': '2026-01', 'pozycje': [{'wiersz': anna, 'osoba': -5}]}})
                self.assertEqual(kod, 400)
                kod, w = wyslij('GET', '/api/lista-plac?miesiac=2026-01')
                self.assertEqual((kod, next(o for o in w['osoby'] if o['wiersz'] == anna)['z_listy']), (200, True))
            finally:
                h.shutdown()
                h.server_close()
                konfig.PORT = stary


if __name__ == '__main__':
    unittest.main()
