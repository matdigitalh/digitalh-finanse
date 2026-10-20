"""Odbiór pakietu 5 na prawdziwych plikach (tylko odczyt: Dane podpięte dowiązaniami, baza, plik zmian i pliki apki
w katalogu tymczasowym, nic nie trafia do Finanse/Aplikacja).

Sprawdza zasady, które działają bez żadnej decyzji Mata:
  - etap BS „Niewymagana” nigdy nie jest opłacony: każda rzeczywista z BS z przyszłym terminem (w tym PIT i ZUS z umów)
    zostaje w cash flow,
  - nic nie łączy się bez kliknięcia: bez zdarzeń w budżecie nie ma ani jednej płatności z dokumentu „połączonej w apce”,
    a plan wynagrodzenia nie jest opłacony z przelewu,
  - każdy dokument rzeczywisty ma stan łączenia; przy starcie łączenia od 1.10.2026 lista „Do połączenia” ma podpowiedzi
    tylko zgodne z regułami BS (ten sam rodzaj, zgodna podstawa, komórka z planem), a komórka nie-worek trafia do jednej
    podpowiedzi.
Liczby są wypisywane, nie porównywane z wartościami w repo."""
import os
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from finanse import baza, cashflow, konfig, laczenie, odbudowa, zmiany

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
DANE = FINANSE / 'Raporty' / 'Dane'
EKSPORTY = sorted((DANE / 'Budget Studio').glob('budget_studio_*.csv'))


@unittest.skipUnless(EKSPORTY and (FINANSE / 'Aplikacja' / 'arkusze_bs.json').exists(), 'brak eksportu BS')
class OdbiorLaczenie(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        fin = Path(cls.tmp.name) / 'Finanse'
        (fin / 'Raporty' / 'Dane').mkdir(parents=True)
        for p in DANE.iterdir():
            if p.is_dir():
                os.symlink(p, fin / 'Raporty' / 'Dane' / p.name)
        (fin / 'Aplikacja').mkdir()
        shutil.copy(FINANSE / 'Aplikacja' / 'arkusze_bs.json', fin / 'Aplikacja' / 'arkusze_bs.json')
        cls.stare = {k: os.environ.get(k) for k in ('FINANSE_KATALOG', 'FINANSE_BAZA', 'FINANSE_MAC')}
        os.environ['FINANSE_KATALOG'] = str(fin)
        os.environ['FINANSE_BAZA'] = str(Path(cls.tmp.name) / 'finanse.sqlite')
        os.environ['FINANSE_MAC'] = 'Odbior-P5'
        cls.raport = odbudowa.odbuduj()
        cls.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()
        cls.tmp.cleanup()
        for k, v in cls.stare.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_niewymagana_w_cashflow_i_nic_polaczonego_bez_klikniecia(self):
        self.assertEqual(self.raport['bledy'], [])
        dzis = self.con.execute("SELECT wartosc FROM meta WHERE klucz = 'dzien_stanu'").fetchone()[0]
        niewym = [dict(r) for r in self.con.execute(
            "SELECT p.id, p.realny, p.termin, p.w_cashflow, p.aktualna, w.podstawa, s.etap FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz"
            " JOIN bud_stan s ON s.platnosc = p.id WHERE p.etap_bs = 'Niewymagana'")]
        self.assertFalse([x for x in niewym if x['etap'] in ('Opłacona wg BS',)], 'Niewymagana nie może być opłacona wg BS')
        przyszle = [x for x in niewym if (x['realny'] or x['termin'] or '') > dzis and x['w_cashflow'] and x['aktualna']
                    and x['etap'] not in ('Opłacona', 'Wystawiona', 'Częściowo opłacona')]
        # pakiet 9: pozycje cash flow po dniu stanu (scenariusz pełny: zaległości też na liście)
        zd = cashflow.pozycje(self.con, cashflow._d(dzis), None, cashflow._d(dzis) + cashflow.timedelta(days=400), cashflow.parametry(scenariusz='pelny'))['pozycje']
        w_cf = {z['zrodlo'] for z in zd}
        self.assertLessEqual({x['id'] for x in przyszle}, w_cf)
        wyn = [x for x in przyszle if x['podstawa'].startswith('Umowa')]
        print(f'\n  Niewymagana w BS: {len(niewym)} płatności, z przyszłym terminem w cash flow: {len(przyszle)} (wynagrodzenia: {len(wyn)})')
        self.assertFalse(self.con.execute("SELECT 1 FROM bud_platnosc WHERE COALESCE(dokument, '') != ''").fetchone())
        plany_wyn_opl = self.con.execute(
            "SELECT COUNT(*) FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_stan s ON s.platnosc = p.id"
            " WHERE p.typ = 'plan' AND (w.podstawa LIKE 'Umowa%' OR p.skladowa IS NOT NULL) AND s.etap = 'Opłacona'").fetchone()[0]
        self.assertEqual(plany_wyn_opl, 0)

    def test_stany_dokumentow_i_podpowiedzi_zgodne_z_regulami(self):
        stany = Counter(r[0] for r in self.con.execute('SELECT stan FROM bud_laczenie'))
        print(f'  dokumenty przy starcie łączenia {laczenie.laczenie_od(self.con)}: {dict(stany)}')
        self.assertFalse(stany.get('polaczony'))
        # próba ze startem łączenia od 1.10: podpowiedzi zgodne z regułami BS, komórka nie-worek tylko raz
        zmiany.zapisz('ustawienie', zmiany.sprawdz('ustawienie', {'klucz': 'laczenie_od', 'wartosc': '2026-10-01'}))
        self.con.close()
        odbudowa.odbuduj()
        self.__class__.con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        lista = laczenie.lista(self.con, {'wszystkie': '1'})
        z_pod = [x for x in lista['wiersze'] if x['pod_wiersz']]
        komorki = Counter((x['pod_wiersz'], x['pod_miesiac']) for x in z_pod if x['pod_podstawa'] not in ('Faktura (w worku)', 'Bez faktury (w worku)'))
        self.assertFalse([k for k, n in komorki.items() if n > 1])
        for x in z_pod:
            w = self.con.execute('SELECT rodzaj, podstawa FROM bud_wiersz WHERE id = ?', (x['pod_wiersz'],)).fetchone()
            self.assertEqual(w['rodzaj'], x['rodzaj'])
            if x['rodzina'] != 'bank':
                self.assertEqual(w['podstawa'].split(' (')[0], x['rodzina'])
            self.assertTrue(self.con.execute("SELECT 1 FROM bud_platnosc WHERE wiersz = ? AND miesiac = ? AND typ = 'plan'",
                                             (x['pod_wiersz'], x['pod_miesiac'])).fetchone())
        pew = Counter(x['pewnosc'] or 'brak' for x in lista['wiersze'])
        print(f"  do połączenia od 1.10: {lista['razem']} dokumentów, podpowiedzi: {dict(pew)}")

    def test_lista_plac_widzi_skladowe_umow_z_kopii_bs(self):
        """Kopia BS trzyma wypłatę, PIT i ZUS w osobnych wierszach („Umowa o pracę - PIT”): lista płac grupuje je w osobę,
        a plan składowej nie zamienia się na rzeczywistą poza listą płac (decyzja 12)."""
        from finanse import budzet
        skl = self.con.execute("SELECT COUNT(*) FROM bud_wiersz WHERE podstawa LIKE 'Umowa % - %'").fetchone()[0]
        if not skl:
            self.skipTest('brak wierszy składowych umów')
        dzis = self.con.execute("SELECT wartosc FROM meta WHERE klucz = 'dzien_stanu'").fetchone()[0]
        f = laczenie.lista_plac(self.con, dzis[:7])
        z_planem = [o for o in f['osoby'] if o['plan']]
        print(f'  lista płac {dzis[:7]}: {len(f["osoby"])} osób, z planem {len(z_planem)}; wierszy składowych w BS: {skl}')
        self.assertTrue(z_planem)
        for o in z_planem:
            self.assertTrue(o['umowa'] or o['podstawa'] not in ('Umowa o pracę', 'Umowa zlecenie', 'Umowa o dzieło'))
        w = dict(self.con.execute("SELECT * FROM bud_wiersz WHERE podstawa LIKE 'Umowa % - PIT' LIMIT 1").fetchone())
        self.assertTrue(budzet.wynagrodzenie(w))
