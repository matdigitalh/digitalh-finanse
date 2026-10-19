"""Odbiór pakietu 6 na prawdziwym eksporcie BS: kopia z BS ma 0 różnic w kontroli sum (arkusz × miesiąc × rodzaj × typ:
liczba, netto, VAT, brutto co do grosza; cash flow i wynik w każdym miesiącu; płatność po płatności), a liczba płatności
równa się liczbie wierszy eksportu z rodzajem 1 i -1.

Część 1 tylko czyta (mapa stałych ID w pamięci). Część 2 przyjmuje kopię w katalogu tymczasowym (dowiązania do Dane,
kopia mapy ID i listy arkuszy), przelicza bazę z kopii i sprawdza, że apka pokazuje te same liczby co przy imporcie
(salda arkuszy, etapy, rozjazdy z bankiem, cash flow, rentowność arkuszy). Prawdziwy folder Finanse nie jest zmieniany.
Opcjonalnie: oczekiwane wartości w Finanse/Aplikacja/odbior.json, klucz „kopia_bs”
({"eksport_bs": nazwa pliku, "platnosci": liczba, "wierszy": liczba wierszy po scaleniu umów, "saldo_netto_gr": saldo razem})."""
import copy
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from finanse import baza, budzet, cashflow, konfig, kopia_bs, odbudowa, rentownosc, zapytania_budzet, zmiany

FINANSE = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
EKSPORTY = sorted((FINANSE / 'Raporty' / 'Dane' / 'Budget Studio').glob('budget_studio_*.csv'))
ODBIOR = FINANSE / 'Aplikacja' / 'odbior.json'


def _oczekiwane():
    try:
        return json.loads(ODBIOR.read_text(encoding='utf-8')).get('kopia_bs')
    except (OSError, ValueError):
        return None


@unittest.skipUnless(EKSPORTY, 'brak eksportu BS')
class OdbiorKopii(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv = EKSPORTY[-1]
        mapa = budzet.nowa_mapa()
        if (FINANSE / 'Aplikacja' / 'mapa_id.json').exists():
            mapa = {**mapa, **json.loads((FINANSE / 'Aplikacja' / 'mapa_id.json').read_text(encoding='utf-8'))}
        ark = FINANSE / 'Aplikacja' / 'arkusze_bs.json'
        cls.kopia = kopia_bs.zbuduj_kopie(cls.csv, ark, copy.deepcopy(mapa), tydzien=1)
        imp = budzet.generuj_import(cls.csv, ark, copy.deepcopy(mapa))
        model = kopia_bs.rozwin(cls.kopia)
        budzet.zastosuj_zdarzenia(model, [])
        cls.raport = kopia_bs.kontrola(kopia_bs.rekordy_bs(imp, kopia_bs._wiersze_csv(cls.csv)),
                                       kopia_bs.rekordy_modelu(model, cls.kopia['pochodzenie']),
                                       kopia_bs._nazwy_arkuszy(model['arkusze']), kopia_bs.liczba_w_csv(cls.csv))

    def test_zero_roznic_co_do_grosza(self):
        r = self.raport
        self.assertEqual(r['roznic'], 0, (r['komorki'][:3], r['platnosci'][:5]))
        self.assertEqual(r['liczba_csv'], r['liczba_bs'])
        self.assertEqual(r['liczba_apka'], r['liczba_bs'])
        self.assertTrue(all(a['zgodny'] for a in r['arkusze']))
        self.assertTrue(all(m['zgodny'] for m in r['miesiace']))
        self.assertEqual(r['razem']['bs'], r['razem']['apka'])
        w = self.kopia['weryfikacja']
        print(f"\n  kopia z {self.csv.name}: {r['liczba_apka']} płatności, {len(self.kopia['wiersze'])} wierszy, {len(self.kopia['komorki'])} komórek,"
              f" {len(self.kopia['pochodzenie'])} planów z komórek, {len(self.kopia['platnosci'])} przeniesionych wprost; worek {w['worek']},"
              f" umowy {w['umowa']}, nadpisania {w['nadpisania']}, jawne {w['jawne']}")

    def test_umowy_scalone_i_oczekiwane(self):
        skladowe = [w for w in self.kopia['wiersze'] if kopia_bs.skladowa_bs(w['podstawa'])]
        self.assertEqual(skladowe, [])
        o = _oczekiwane()
        if o and o.get('eksport_bs') == self.csv.name:
            self.assertEqual(self.raport['liczba_apka'], o['platnosci'])
            if 'wierszy' in o:
                self.assertEqual(len(self.kopia['wiersze']), o['wierszy'])
            if 'saldo_netto_gr' in o:
                self.assertEqual(self.raport['razem']['apka']['netto'], o['saldo_netto_gr'])


@unittest.skipUnless(EKSPORTY and (FINANSE / 'Aplikacja' / 'arkusze_bs.json').exists(), 'brak eksportu BS albo listy arkuszy')
class OdbiorKopiiWBazie(unittest.TestCase):
    """Przyjęcie kopii w katalogu tymczasowym i porównanie liczb apki z kopią i bez niej."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        fin = Path(cls.tmp.name) / 'Finanse'
        (fin / 'Raporty' / 'Dane').mkdir(parents=True)
        for p in (FINANSE / 'Raporty' / 'Dane').iterdir():
            if p.is_dir():
                os.symlink(p, fin / 'Raporty' / 'Dane' / p.name)
        (fin / 'Aplikacja').mkdir()
        for n in ('arkusze_bs.json', 'mapa_id.json', 'ustawienia.json'):
            if (FINANSE / 'Aplikacja' / n).exists():
                shutil.copy(FINANSE / 'Aplikacja' / n, fin / 'Aplikacja' / n)
        cls.stare = {k: os.environ.get(k) for k in ('FINANSE_KATALOG', 'FINANSE_BAZA', 'FINANSE_MAC')}
        os.environ.update(FINANSE_KATALOG=str(fin), FINANSE_BAZA=str(Path(cls.tmp.name) / 'import.sqlite'), FINANSE_MAC='Mac-odbior')
        odbudowa.odbuduj()
        cls.przed = cls.liczby()
        p = kopia_bs.podglad(wpisy=zmiany.wczytaj()[0])
        cls.wpis = kopia_bs.przyjmij(p['eksport_sha256'], zmiany.wczytaj()[0])
        os.environ['FINANSE_BAZA'] = str(Path(cls.tmp.name) / 'kopia.sqlite')
        cls.raport_odbudowy = odbudowa.odbuduj()
        cls.po = cls.liczby()
        con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        cls.zgodnosc = kopia_bs.zgodnosc(con, zmiany.wczytaj()[0])
        cls.rownolegle = con.execute("SELECT COUNT(*) FROM bud_rozjazd WHERE rodzaj IN"
                                     " ('Plan w BS inny niż w apce', 'Wiersz jest tylko w BS', 'Wiersz jest tylko w apce')").fetchone()[0]
        con.close()

    @classmethod
    def tearDownClass(cls):
        for k, v in cls.stare.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        cls.tmp.cleanup()

    @staticmethod
    def liczby():
        con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        try:
            salda = {a['id']: (a['saldo'], a['po_terminie']) for f in zapytania_budzet.drzewo(con)['foldery']
                     for ark in f['kategorie'].values() for a in ark}
            return {'salda': salda,
                    'rozjazdy': con.execute('SELECT rodzaj, COUNT(*), SUM(kwota) FROM bud_rozjazd GROUP BY rodzaj ORDER BY rodzaj').fetchall(),
                    'etapy': con.execute('SELECT etap, etap_wg_bs, aktualnosc, COUNT(*) FROM bud_stan GROUP BY 1, 2, 3 ORDER BY 1, 2, 3').fetchall(),
                    'cashflow': [(t['od'], t['wplywy'], t['wydatki']) for t in cashflow.prognoza(con).get('tygodnie', [])],
                    'rentownosc': [tuple(x.values()) for x in rentownosc.arkusze(con)]}
        finally:
            con.close()

    def test_kopia_w_bazie_bez_roznic(self):
        self.assertEqual(self.raport_odbudowy['bledy'], [])
        self.assertEqual(self.zgodnosc['roznic'], 0)
        self.assertEqual(self.zgodnosc['kopia']['plik'], self.wpis['dane']['plik'])
        self.assertEqual(self.rownolegle, 0)

    def test_te_same_liczby_co_przy_imporcie(self):
        for k in self.przed:
            self.assertEqual([tuple(x) for x in self.przed[k]] if isinstance(self.przed[k], list) else self.przed[k],
                             [tuple(x) for x in self.po[k]] if isinstance(self.po[k], list) else self.po[k], k)


if __name__ == '__main__':
    unittest.main()
