"""Odbiór pakietu 2 na prawdziwym eksporcie BS (tylko odczyt, mapa ID w pamięci, nic nie jest zapisywane).

Sprawdza, że model planu z apki odtwarza to, co BS wygenerował z komórek:
  - worek: podział na tygodnie w pełnych przyszłych miesiącach (przy tygodniu od wtorku, jak w eksporcie z 14.10.2026),
  - umowa o pracę: podział komórki wg proporcji z innego miesiąca tej samej osoby (do 2 gr na składowej, suma co do grosza),
  - kwota komórki faktury: VAT planu z komórki = VAT z BS, gdy stawka standardowa,
  - model bez zdarzeń = import (żadnej zmiany liczb przez samo wdrożenie pakietu 2).
Wyniki porównania (ile zgodnych) są wypisywane, bo to materiał dla kopii z BS (pakiet 6)."""
import copy
import unittest
from collections import defaultdict
from pathlib import Path

from finanse import budzet, plan

KATALOG = Path.home() / 'Documents' / 'DigitalH' / 'Finanse'
EKSPORTY = sorted((KATALOG / 'Raporty' / 'Dane' / 'Budget Studio').glob('budget_studio_*.csv'))
SKLADOWE_BS = {'Umowa o pracę - dla wykonawcy': 'osoba', 'Umowa o pracę - PIT': 'us', 'Umowa o pracę - ZUS': 'zus'}


@unittest.skipUnless(EKSPORTY, 'brak eksportu BS')
class OdbiorModelPlanu(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = budzet.generuj_import(EKSPORTY[-1], KATALOG / 'Aplikacja' / 'arkusze_bs.json', budzet.nowa_mapa())
        cls.wiersze = {w['id']: w for w in cls.model['wiersze']}
        cls.komorki = defaultdict(list)
        for p in cls.model['platnosci']:
            cls.komorki[(p['wiersz'], p['miesiac'])].append(p)

    def test_model_bez_zdarzen_rowny_importowi(self):
        m = copy.deepcopy(self.model)
        budzet.zastosuj_zdarzenia(m, [])
        sumy = lambda ps: (len(ps), sum(p['netto'] for p in ps), sum(p['vat'] for p in ps), sum(p['brutto'] for p in ps))
        self.assertEqual(sumy(m['platnosci']), sumy(self.model['platnosci']))
        self.assertEqual(m['komorki'], [])

    def test_worek_tygodnie_jak_w_bs(self):
        zgodne, inne = 0, []
        for (wid, mies), ps in self.komorki.items():
            # pełne przyszłe miesiące: same aktualne plany, co najmniej 4 tygodnie (bieżący i miniony BS przelicza inaczej)
            if (self.wiersze[wid]['podstawa'] not in plan.WOREK or len(ps) < 4
                    or any(p['typ'] != 'plan' or not p['aktualna'] for p in ps)):
                continue
            bs = sorted((p['wystawienie'], p['netto']) for p in ps)
            if plan.podziel_worek(sum(k for _, k in bs), mies, 1) == bs:
                zgodne += 1
            else:
                inne.append((wid, mies))
        print(f'\n  worek, tydzień od wtorku: {zgodne} komórek zgodnych z BS, {len(inne)} innych')
        if zgodne + len(inne):
            self.assertGreaterEqual(zgodne, 0.9 * (zgodne + len(inne)), inne[:5])

    def test_umowa_o_prace_z_proporcji(self):
        po_osobie = defaultdict(dict)
        for p in self.model['platnosci']:
            s = SKLADOWE_BS.get(self.wiersze[p['wiersz']]['podstawa'])
            if s:
                po_osobie[(self.wiersze[p['wiersz']]['kontrahent'], p['bs_id'])][s] = (p['miesiac'], p['netto'])
        osoby = defaultdict(list)
        for (kto, _), x in po_osobie.items():
            if len(x) == 3:
                osoby[kto].append((x['osoba'][0], {k: v[1] for k, v in x.items()}))
        sprawdzone, dokladne = 0, 0
        for kto, lista in osoby.items():
            lista.sort(key=lambda t: t[0])
            for (_, ref), (_, bs) in zip(lista, lista[1:]):   # proporcje z poprzedniego miesiąca
                apka = plan.podziel_umowe(sum(bs.values()), ref)
                self.assertEqual(sum(apka.values()), sum(bs.values()))
                self.assertTrue(all(abs(apka[k] - bs[k]) <= 2 for k in bs), (kto[:3], bs, apka))
                sprawdzone += 1
                dokladne += apka == bs
        print(f'\n  umowa o pracę: {dokladne} z {sprawdzone} miesięcy co do grosza, reszta do 2 gr (proporcje z kwot BS, nie od księgowej)')

    def test_vat_planu_z_komorki_jak_w_bs(self):
        sprawdzone, rozne = 0, []
        for (wid, mies), ps in self.komorki.items():
            w = self.wiersze[wid]
            if w['podstawa'] != 'Faktura (jedna)' or len(ps) != 1 or ps[0]['typ'] != 'plan' or budzet.stawka_proc(ps[0]['stawka']) is None:
                continue
            p = ps[0]
            gen = plan.generuj_komorke({**w, 'stawka_vat': budzet.stawka_proc(p['stawka'])}, mies, p['netto'])[0]
            sprawdzone += 1
            if abs(gen['vat'] - p['vat']) > 1 or gen['netto'] != p['netto']:
                rozne.append(p['id'])
        self.assertGreater(sprawdzone, 50)
        self.assertLessEqual(len(rozne), sprawdzone // 100, rozne[:10])


if __name__ == '__main__':
    unittest.main()
