"""Odbiór pakietu 1 na prawdziwych eksportach BS (tylko odczyt, mapa ID w pamięci): dwa kolejne eksporty dają te same
ID płatności i wierszy dla płatności obecnych w obu, a VAT płatności z importu jest liczony tak samo jak w BS."""
import unittest
from collections import Counter
from pathlib import Path

from finanse import budzet

KATALOG = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
EKSPORTY = sorted((KATALOG / 'Raporty' / 'Dane' / 'Budget Studio').glob('budget_studio_*.csv'))


@unittest.skipUnless(len(EKSPORTY) >= 2, 'potrzebne co najmniej dwa eksporty BS')
class OdbiorStabilneId(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapa = budzet.nowa_mapa()
        ark = KATALOG / 'Aplikacja' / 'arkusze_bs.json'
        cls.stary = budzet.generuj_import(EKSPORTY[-2], ark, cls.mapa)
        cls.nowy = budzet.generuj_import(EKSPORTY[-1], ark, cls.mapa)

    def test_te_same_id_w_kolejnym_eksporcie(self):
        stare = {p['id']: p for p in self.stary['platnosci']}
        nowe = {p['id']: p for p in self.nowy['platnosci']}
        wspolne = set(stare) & set(nowe)
        self.assertGreater(len(wspolne), 0.8 * len(stare))
        for pid in wspolne:
            self.assertEqual(stare[pid]['bs_id'], nowe[pid]['bs_id'], pid)
            self.assertEqual(stare[pid]['wiersz'], nowe[pid]['wiersz'], pid)
        # ta sama liczba części każdego ID BS: żadna płatność nie zgubiła ID przy ponownym imporcie
        ile = Counter(p['bs_id'] for p in self.nowy['platnosci'])
        self.assertEqual(len(nowe), sum(ile.values()))

    def test_wiersze_i_arkusze_tylko_z_mapy(self):
        wiersze = {w['id']: w['arkusz'] for w in self.nowy['wiersze']}
        for p in self.nowy['platnosci']:
            self.assertEqual(self.mapa['platnosci'][p['id']], p['wiersz'])
            self.assertEqual(self.mapa['wiersze'][p['wiersz']], wiersze[p['wiersz']])

    def test_vat_z_netto_jak_w_bs(self):
        """VAT liczony przez apkę (stawka z płatności) zgadza się z VAT z eksportu BS co do grosza albo jednego grosza
        różnicy z zaokrąglenia po pozycjach faktury; faktury z kilkoma stawkami (bez stawki standardowej) pomijamy."""
        wiersze = {w['id']: w for w in self.nowy['wiersze']}
        sprawdzone, rozne = 0, []
        for p in self.nowy['platnosci']:
            w = wiersze[p['wiersz']]
            if not budzet.ma_vat(w['podstawa']) or budzet.stawka_proc(p['stawka']) is None:
                continue
            sprawdzone += 1
            if abs(budzet.vat_od_netto(p['netto'], p['stawka'], w['podstawa']) - p['vat']) > 1:
                rozne.append(p['id'])
        self.assertGreater(sprawdzone, 100)
        self.assertLessEqual(len(rozne), sprawdzone // 100, rozne[:10])


if __name__ == '__main__':
    unittest.main()
