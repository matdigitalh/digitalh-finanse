"""Pakiet 6 (kopia z BS i kontrola zgodności) na zmyślonych danych: kopia jako model planu (komórki, ustawienia wierszy,
nadpisania, podziały), umowa o pracę z trzech wierszy BS w jeden, kontrola sum co do grosza, przyjęcie tylko przy 0 różnic,
kopia jako źródło budżetu, okres równoległy (nowy eksport BS kontra plany apki), przełącznik importu BS, cofnięcie kopii."""
import csv
import http.client
import io
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from openpyxl import load_workbook

from finanse import baza, budzet, konfig, kopia_bs, odbudowa, plan, serwer, zmiany
from testy.pomoc import Srodowisko
from testy.test_budzet import KOLUMNY, dane

DZIS = '2026-10-13'
A1 = ('Obsługa Alfa', 'Alfa', 'Obsługa stała')
A2 = ('Pracownicy', 'Firma', 'Zespół')
A3 = ('Opłaty 2026', 'Firma', 'Podatki')


def kw(gr: int, rodzaj: str) -> str:
    s = f'{gr // 100},{gr % 100:02d}'
    return f'-{s}' if rodzaj == '-1' and gr else s


def r(id_, rodzaj, etap, podstawa, kontrahent, miesiac, netto, vat, wyst, termin, realny, ksieg, ark, komentarz='', przedmiot='Usługi',
      nr='', status='Aktualne', stawka='0,23'):
    w = dict.fromkeys(KOLUMNY, '')
    w.update({'ID': id_, 'Rodzaj': rodzaj, 'Status aktualności': status, 'Etap płatności': etap, 'Podstawa płatności': podstawa,
              'Numer dokumentu': nr, 'Kontrahent': kontrahent, 'Tytuł': przedmiot, 'Netto (wartość)': kw(netto, rodzaj),
              'Brutto (wartość)': kw(netto + vat, rodzaj), 'VAT': kw(vat, rodzaj), 'Stawka VAT': stawka, 'Miesiąc budżetowy': f'{miesiac}-01',
              'Dzień wystawienia': wyst, 'Dzień płatności': termin, 'Dzień płatności - realny': realny, 'Miesiąc księgowania': ksieg,
              'Metoda płatności': 'Przelew', 'Księgowane': 'Tak', 'W cash flow': 'Tak', 'Komentarz': komentarz, 'Komentarz w arkuszu': komentarz,
              'Arkusz': ark[0], 'Folder': ark[1], 'Kategoria': ark[2], 'Sekcja': '-', 'Przedmiot transakcji': przedmiot,
              'Data utworzenia': '2026-03-01 10:00:00', 'Data modyfikacji': '2026-10-01 10:00:00'})
    return w


def eksport_bs():
    """29 płatności: faktura z regułą „10. +1” (nieaktualny plan, inny dzień realny, inny dzień wystawienia, plan zerowy),
    worek (miniony miesiąc zwinięty, bieżący z rzeczywistymi i pozostałymi tygodniami, pełny miesiąc od wtorku),
    umowa o pracę jako trzy wiersze BS (wypłata wrześniowa rzeczywista, plany październik i listopad z innymi groszami),
    podatek VAT, dwa plany faktury w jednej komórce, bez faktury."""
    F = lambda *a, **k: r(*a, ark=A1, komentarz='Abonament', **k)
    W = lambda *a, **k: r(*a, ark=A1, komentarz='Reklama', przedmiot='Reklama', **k)
    U = lambda *a, **k: r(*a, ark=A2, komentarz='Etat', przedmiot='Wynagrodzenia', stawka='', **k)
    wiersze = [
        F('F1-8', '1', 'Opłacona', 'Faktura ', 'Alfa', '2026-08', 100000, 23000, '2026-09-10', '2026-09-24', '2026-09-24', '2026-09-01', nr='FV2026/09/9'),
        F('F1-9', '1', 'Planowana', 'Faktura ', 'Alfa', '2026-09', 100000, 23000, '2026-10-10', '2026-10-24', '2026-10-24', '2026-10-01', status='Nieaktualne'),
        F('F1-10', '1', 'Planowana', 'Faktura ', 'Alfa', '2026-10', 100000, 23000, '2026-11-10', '2026-11-24', '2026-11-28', '2026-11-01'),
        F('F1-11', '1', 'Planowana', 'Faktura ', 'Alfa', '2026-11', 100000, 23000, '2026-12-05', '2026-12-19', '2026-12-19', '2026-12-01'),
        F('F1-12', '1', 'Planowana', 'Faktura ', 'Alfa', '2026-12', 0, 0, '2027-01-10', '2027-01-24', '2027-01-24', '2027-01-01', stawka=''),
        W('W1-8', '-1', 'Planowana', 'Faktura (w worku)', 'Meta', '2026-08', 310000, 71300, '2026-08-31', '2026-08-31', '2026-08-31', '2026-08-01', status='Nieaktualne'),
        W('W1-10a', '-1', 'Opłacona', 'Faktura (w worku)', 'Meta', '2026-10', 50000, 11500, '2026-10-05', '2026-10-05', '2026-10-05', '2026-10-01', nr='M/1'),
        W('W1-10b', '-1', 'Opłacona', 'Faktura (w worku)', 'Meta', '2026-10', 70000, 16100, '2026-10-12', '2026-10-12', '2026-10-12', '2026-10-01', nr='M/2'),
        W('W1-10c', '-1', 'Planowana', 'Faktura (w worku)', 'Meta', '2026-10', 30000, 6900, '2026-10-13', '2026-10-13', '2026-10-13', '2026-10-01'),
        W('W1-10d', '-1', 'Planowana', 'Faktura (w worku)', 'Meta', '2026-10', 30000, 6900, '2026-10-20', '2026-10-20', '2026-10-20', '2026-10-01'),
        W('W1-10e', '-1', 'Planowana', 'Faktura (w worku)', 'Meta', '2026-10', 20000, 4600, '2026-10-27', '2026-10-27', '2026-10-27', '2026-10-01'),
    ]
    for i, (d, k) in enumerate([('2026-11-01', 20000), ('2026-11-03', 70000), ('2026-11-10', 70000), ('2026-11-17', 70000), ('2026-11-24', 70000)]):
        wiersze.append(W(f'W1-11{"abcde"[i]}', '-1', 'Planowana', 'Faktura (w worku)', 'Meta', '2026-11', k, k * 23 // 100, d, d, d, '2026-11-01'))
    for id_, etap, m, kwoty, wyst, t_os, t_pit, t_zus in (
            ('U-9', 'Opłacona', '2026-09', (590000, 60000, 350000), '2026-09-30', '2026-10-07', '2026-11-20', '2026-11-15'),
            ('U-10', 'Planowana', '2026-10', (590000, 60000, 350000), '2026-10-31', '2026-11-07', '2026-12-20', '2026-12-15'),
            ('U-11', 'Planowana', '2026-11', (590100, 59900, 350000), '2026-11-30', '2026-12-07', '2027-01-20', '2027-01-15')):
        for pod, k, t in (('Umowa o pracę - dla wykonawcy', kwoty[0], t_os), ('Umowa o pracę - PIT', kwoty[1], t_pit), ('Umowa o pracę - ZUS', kwoty[2], t_zus)):
            wiersze.append(U(id_, '-1', etap, pod, 'Jan Testowy', m, k, 0, wyst, t, t, f'{m}-01'))
    wiersze += [
        r('V-11', '-1', 'Planowana', 'Podatek VAT', 'Urząd Skarbowy', '2026-11', 200000, 0, '2026-11-30', '2026-12-25', '2026-12-25', '2026-11-01',
          A3, przedmiot='Podatek VAT', stawka=''),
        r('D1', '-1', 'Planowana', 'Faktura ', 'Drukarnia', '2026-11', 10000, 2300, '2026-11-30', '2026-12-14', '2026-12-14', '2026-11-01', A1, 'Druk', 'Druk'),
        r('D2', '-1', 'Planowana', 'Faktura ', 'Drukarnia', '2026-11', 20000, 4600, '2026-11-30', '2026-12-14', '2026-12-14', '2026-11-01', A1, 'Druk', 'Druk'),
        r('B1', '-1', 'Planowana', 'Bez faktury ', 'Kawiarnia', '2026-11', 5000, 0, '2026-11-15', '2026-11-15', '2026-11-15', '2026-11-01', A1, 'Spotkania',
          'Spotkania', stawka=''),
    ]
    return wiersze


def zapisz_eksport(srod, wiersze, nazwa='budget_studio_2026-10-14.csv'):
    katalog = srod.dane / 'Budget Studio'
    for p in katalog.glob('budget_studio_*.csv'):
        if p.name != nazwa and nazwa == 'budget_studio_2026-10-14.csv':
            p.unlink()
    with open(katalog / nazwa, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=KOLUMNY, delimiter='\t')
        w.writeheader()
        w.writerows(wiersze)


def przygotuj(srod):
    dane(srod)   # bank i Fakturownia z testów budżetu; eksport BS podmieniony na bogatszy
    zapisz_eksport(srod, eksport_bs())
    (srod.katalog / 'Finanse' / 'Aplikacja' / 'arkusze_bs.json').write_text(json.dumps({'arkusze': [
        {'nazwa': a[0], 'folder': a[1], 'kategoria': a[2], 'od': '2026-01', 'do': '2026-12'} for a in (A1, A2, A3)]}), encoding='utf-8')


class Baza(unittest.TestCase):
    def setUp(self):
        self.srod = Srodowisko().__enter__()
        przygotuj(self.srod)
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

    def przyjmij(self):
        p = kopia_bs.podglad(wpisy=zmiany.wczytaj()[0])
        self.assertEqual(p['roznic'], 0, p['platnosci'][:5])
        wpis = kopia_bs.przyjmij(p['eksport_sha256'], zmiany.wczytaj()[0])
        self.przelicz()
        return wpis

    def wiersz(self, kontrahent):
        return self.con.execute('SELECT * FROM bud_wiersz WHERE kontrahent = ?', (kontrahent,)).fetchone()

    def bud(self, d):
        czyste = zmiany.sprawdz('bud', d)
        budzet.sprawdz_wpis(czyste, zmiany.wczytaj()[0], dzis=DZIS)
        return zmiany.zapisz('bud', czyste)

    def rozjazdy(self, rodzaj):
        return [dict(x) for x in self.con.execute('SELECT * FROM bud_rozjazd WHERE rodzaj = ?', (rodzaj,))]


class TestKopia(Baza):
    def test_podglad_zero_roznic_i_model_jak_w_bs(self):
        p = kopia_bs.podglad()
        self.assertEqual((p['roznic'], p['liczba_csv'], p['liczba_bs'], p['liczba_apka']), (0, 29, 29, 29))
        self.assertTrue(all(a['zgodny'] for a in p['arkusze']) and all(m['zgodny'] for m in p['miesiace']))
        kopia = kopia_bs.zbuduj_kopie(kopia_bs.eksporty()[0], None, budzet.nowa_mapa())
        w = {x['kontrahent']: x for x in kopia['wiersze']}
        self.assertEqual(len(kopia['wiersze']), 6)   # umowa z trzech wierszy BS w jeden
        self.assertEqual((w['Alfa']['dzien_wystawienia'], w['Alfa']['dni_na_platnosc'], w['Alfa']['stawka_vat']), ('10. +1', 14, 23))
        self.assertEqual((w['Meta']['dzien_wystawienia'], w['Meta']['dni_na_platnosc']), ('(auto)', 0))
        u = w['Jan Testowy']
        self.assertEqual((u['podstawa'], u['rodzaj'], u['dzien_wystawienia'], u['dni_na_platnosc']), ('Umowa o pracę', -1, 'Ostatni', 7))
        self.assertEqual(u['proporcje'], {'osoba': 590100, 'us': 59900, 'zus': 350000})   # z najpóźniejszej komórki z planami
        self.assertEqual(len(kopia['wiersze_bs']), 2)
        self.assertEqual((w['Urząd Skarbowy']['dzien_wystawienia'], w['Urząd Skarbowy']['dni_na_platnosc']), ('Ostatni', 25))
        self.assertEqual(w['Kawiarnia']['dzien_wystawienia'], '15.')
        # nadpisania: nieaktualny plan, inny dzień realny, inny dzień wystawienia (termin idzie za nim), stawka planu zerowego
        n = {pid.split(':', 2)[2]: x for pid, x in kopia['nadpisane'].items() if pid.startswith(f"plan:{w['Alfa']['id']}:")}
        self.assertEqual(n['2026-09:1'], {'aktualna': False})
        self.assertEqual(n['2026-10:1'], {'realny': '2026-11-28'})
        self.assertEqual(n['2026-11:1'], {'wystawienie': '2026-12-05'})
        self.assertEqual(n['2026-12:1'], {'stawka': None})
        # worki: podział wprost z eksportu (zwinięty sierpień, październik z rzeczywistymi), listopad zgodny z regułą od wtorku
        wid = w['Meta']['id']
        self.assertEqual(kopia['podzialy'][f'{wid}:2026-08'], [['2026-08-31', 310000]])
        self.assertEqual(kopia['podzialy'][f'{wid}:2026-10'], [['2026-10-13', 30000], ['2026-10-20', 30000], ['2026-10-27', 20000]])
        kom = {(k['wiersz'], k['miesiac']): k['kwota'] for k in kopia['komorki']}
        self.assertEqual(kom[(wid, '2026-10')], 200000)   # rzeczywiste 1 200 zł + pozostałe plany 800 zł
        ver = kopia['weryfikacja']
        self.assertEqual(ver['worek'], {'zgodne': 1, 'inne': 2})
        self.assertEqual(ver['worek_inne'], {'miniony miesiąc zwinięty do jednego planu z ostatniego dnia': 1,
                                             'bieżący miesiąc: tylko pozostałe tygodnie': 1})
        self.assertEqual(ver['umowa'], {'zgodne': 1, 'inne': 1})   # październik: proporcje z listopada dają 1 gr inaczej
        self.assertEqual(ver['umowa_maks_gr'], 100)
        self.assertEqual(kopia['podzialy'][f"{u['id']}:2026-10"], {'osoba': 590000, 'us': 60000, 'zus': 350000})
        self.assertEqual(ver['jawne'], {'2 plany w komórce (nie worek)': 2})
        self.assertEqual(ver['tydzien'], 1)
        # rzeczywiste umowy: składowa i spinacz
        rz = [x for x in kopia['platnosci'] if x['wiersz'] == u['id']]
        self.assertEqual(sorted(x['skladowa'] for x in rz), ['osoba', 'us', 'zus'])
        osoba = next(x for x in rz if x['skladowa'] == 'osoba')
        self.assertTrue(all(x.get('spinacz') == osoba['id'] for x in rz if x is not osoba))

    def test_kontrola_lapie_zmiane(self):
        csv_path = kopia_bs.eksporty()[0]
        kopia = kopia_bs.zbuduj_kopie(csv_path, None, budzet.nowa_mapa())
        imp = budzet.generuj_import(csv_path, kopia_bs._arkusze_json(), budzet.nowa_mapa())
        bs = kopia_bs.rekordy_bs(imp, kopia_bs._wiersze_csv(csv_path))
        alfa = next(x['id'] for x in kopia['wiersze'] if x['kontrahent'] == 'Alfa')
        next(k for k in kopia['komorki'] if k['wiersz'] == alfa and k['miesiac'] == '2026-11')['kwota'] += 1
        model = kopia_bs.rozwin(kopia)
        r = kopia_bs.kontrola(bs, kopia_bs.rekordy_modelu(model, kopia['pochodzenie']), {}, 29)
        self.assertEqual((r['roznic_komorek'], r['roznic_platnosci']), (1, 1))
        self.assertEqual(r['komorki'][0]['apka']['netto'] - r['komorki'][0]['bs']['netto'], 1)
        self.assertIn('inne netto', r['platnosci'][0]['przyczyny'])
        self.assertEqual(r['roznic'], r['roznic_komorek'] + r['roznic_miesiecy'] + r['roznic_platnosci'])
        wb = load_workbook(io.BytesIO(kopia_bs.xlsx({**r, 'eksport': csv_path.name})))
        self.assertEqual(wb.sheetnames, ['Podsumowanie', 'Różnice komórek', 'Arkusze', 'Miesiące', 'Płatności'])

    def test_przyjecie_kopia_zrodlem_budzetu(self):
        wpis = self.przyjmij()
        self.assertEqual(wpis['typ'], 'kopia_bs')
        p = kopia_bs.plik_kopii(wpis['dane']['plik'])
        self.assertEqual(oct(p.stat().st_mode)[-3:], '600')
        self.assertEqual(oct(p.with_name(p.stem + '_kontrola.xlsx').stat().st_mode)[-3:], '600')
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM bud_wiersz').fetchone()[0], 6)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM bud_platnosc').fetchone()[0], 29)
        self.assertGreater(self.con.execute('SELECT COUNT(*) FROM bud_komorka').fetchone()[0], 5)
        u = self.wiersz('Jan Testowy')
        self.assertEqual((u['podstawa'], u['zrodlo']), ('Umowa o pracę', 'kopia BS'))
        z = kopia_bs.zgodnosc(self.con, zmiany.wczytaj()[0])
        self.assertEqual((z['roznic'], z['kopia']['plik']), (0, wpis['dane']['plik']))
        self.assertEqual(self.rozjazdy('Plan w BS inny niż w apce'), [])
        # plan z kopii ma pochodzenie z BS (ID, tytuł)
        x = self.con.execute("SELECT * FROM bud_platnosc WHERE id = ?", (f"plan:{self.wiersz('Alfa')['id']}:2026-11:1",)).fetchone()
        self.assertEqual((x['bs_id'], x['tytul'], x['wystawienie'], x['termin']), ('F1-11', 'Usługi', '2026-12-05', '2026-12-19'))

    def test_kolejny_eksport_nie_nadpisuje_kopii_tylko_porownuje(self):
        self.przyjmij()
        nowy = eksport_bs()
        x = next(w for w in nowy if w['ID'] == 'F1-10')
        x['Netto (wartość)'], x['VAT'], x['Brutto (wartość)'] = '1100,00', '253,00', '1353,00'
        nowy.append(r('N1', '-1', 'Planowana', 'Faktura ', 'Nowy dostawca', '2026-11', 50000, 11500, '2026-11-30', '2026-11-30', '2026-11-30',
                      '2026-11-01', A1, 'Nowość', 'Nowość'))
        zapisz_eksport(self.srod, nowy, 'budget_studio_2026-10-20.csv')
        self.przelicz()
        alfa = self.wiersz('Alfa')['id']
        self.assertEqual(self.con.execute('SELECT netto FROM bud_platnosc WHERE id = ?', (f'plan:{alfa}:2026-10:1',)).fetchone()[0], 100000)
        self.assertIsNone(self.wiersz('Nowy dostawca'))
        plan_inny = self.rozjazdy('Plan w BS inny niż w apce')
        self.assertEqual([(x['ref'], x['kwota']) for x in plan_inny], [(f'komorka:{alfa}:2026-10', 10000)])
        self.assertEqual(len(self.rozjazdy('Wiersz jest tylko w BS')), 1)
        z = kopia_bs.zgodnosc(self.con, zmiany.wczytaj()[0])
        self.assertEqual(z['eksport'], 'budget_studio_2026-10-20.csv')
        self.assertGreater(z['roznic'], 0)
        self.assertIn('brak w apce', [y for x in z['platnosci'] for y in x['przyczyny']])
        # rozjazd z odnośnikiem do arkusza i miesiąca na liście Rozjazdów
        from finanse import zapytania_budzet
        r_ = next(x for x in zapytania_budzet.rozjazdy(self.con) if x['rodzaj'] == 'Plan w BS inny niż w apce')
        self.assertEqual((r_['arkusz'], r_['miesiac'], r_['kontrahent']), ('Obsługa Alfa', '2026-10', 'Alfa'))

    def test_aktualnosc_z_bs_po_kopii_nie_jest_roznica(self):
        """BS sam przestawia plan na nieaktualny, gdy minie data: po kopii to nie jest różnica w planach."""
        self.przyjmij()
        nowy = eksport_bs()
        next(w for w in nowy if w['ID'] == 'F1-10')['Status aktualności'] = 'Nieaktualne'
        zapisz_eksport(self.srod, nowy, 'budget_studio_2026-10-20.csv')
        self.przelicz()
        z = kopia_bs.zgodnosc(self.con, zmiany.wczytaj()[0])
        self.assertEqual((z['roznic'], z['z_aktualnoscia']), (0, False))
        self.assertEqual(self.rozjazdy('Plan w BS inny niż w apce'), [])
        # przy przyjmowaniu kopii aktualność musi się zgadzać płatność po płatności
        p = kopia_bs.podglad()
        self.assertTrue(p['z_aktualnoscia'])
        self.assertEqual(p['roznic'], 0)

    def test_zmiana_kwoty_w_apce_widoczna_w_rozjazdach(self):
        """Kryterium odbioru: zmiana jednej kwoty w apce bez zmiany w BS pojawia się w „Plan w BS inny niż w apce”."""
        self.przyjmij()
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        alfa = self.wiersz('Alfa')['id']
        self.bud({'op': 'komorka', 'wiersz': alfa, 'miesiac': '2026-11', 'kwota': 150000})
        self.przelicz()
        x = self.con.execute('SELECT * FROM bud_platnosc WHERE id = ?', (f'plan:{alfa}:2026-11:1',)).fetchone()
        self.assertEqual((x['netto'], x['vat'], x['wystawienie']), (150000, 34500, '2026-12-05'))   # ręczna data z kopii zostaje
        self.assertEqual([(y['ref'], y['kwota']) for y in self.rozjazdy('Plan w BS inny niż w apce')], [(f'komorka:{alfa}:2026-11', -50000)])
        # nowy wiersz tylko w apce
        self.bud({'op': 'wiersz', 'obiekt': {'id': 'w-nowy', 'arkusz': self.wiersz('Alfa')['arkusz'], 'rodzaj': -1, 'podstawa': 'Faktura (jedna)',
                                             'kontrahent': 'Tylko apka', 'stawka_vat': 23}})
        self.przelicz()
        self.assertEqual([y['ref'] for y in self.rozjazdy('Wiersz jest tylko w apce')], ['wiersz:w-nowy'])

    def test_podzial_z_bs_obowiazuje_do_zmiany_kwoty(self):
        self.przyjmij()
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        meta = self.wiersz('Meta')['id']
        ps = lambda: [dict(x) for x in self.con.execute("SELECT * FROM bud_platnosc WHERE wiersz = ? AND miesiac = '2026-08' ORDER BY id", (meta,))]
        self.assertEqual([(x['wystawienie'], x['netto']) for x in ps()], [('2026-08-31', 310000)])
        self.bud({'op': 'komorka', 'wiersz': meta, 'miesiac': '2026-08', 'kwota': 620000})
        self.przelicz()   # sierpień 2026 od wtorku: 1–3, 4–10, 11–17, 18–24, 25–31
        self.assertEqual([x['wystawienie'] for x in ps()], ['2026-08-01', '2026-08-04', '2026-08-11', '2026-08-18', '2026-08-25'])
        self.assertEqual(sum(x['netto'] for x in ps()), 620000)

    def test_zmiany_sprzed_kopii_nie_obowiazuja(self):
        zmiany.zapisz('ustawienie', {'klucz': 'planowanie', 'wartosc': 'tak'})
        alfa = self.wiersz('Alfa')['id']
        self.bud({'op': 'komorka', 'wiersz': alfa, 'miesiac': '2026-11', 'kwota': 70000})
        self.przelicz()
        self.assertEqual(kopia_bs.podglad(wpisy=zmiany.wczytaj()[0])['zdarzen_przed'], 1)
        self.przyjmij()
        x = self.con.execute('SELECT netto FROM bud_platnosc WHERE id = ?', (f'plan:{alfa}:2026-11:1',)).fetchone()
        self.assertEqual(x[0], 100000)

    def test_import_bs_wylaczony(self):
        self.przyjmij()
        zmiany.zapisz('ustawienie', {'klucz': 'import_bs', 'wartosc': 'nie'})
        raport = self.przelicz()
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM bs').fetchone()[0], 0)   # plik BS nie jest czytany
        self.assertNotIn('Budget Studio', [z[0] for z in raport['zrodla']])
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM bud_platnosc').fetchone()[0], 29)   # budżet z kopii działa dalej
        self.assertEqual(self.con.execute("SELECT wartosc FROM meta WHERE klucz = 'import_bs_wl'").fetchone()[0], 'nie')
        self.assertIsNone(kopia_bs.zgodnosc(self.con, zmiany.wczytaj()[0])['eksport'])

    def test_bez_kopii_i_bez_importu_pusty_budzet(self):
        zmiany.zapisz('ustawienie', {'klucz': 'import_bs', 'wartosc': 'nie'})
        raport = self.przelicz()
        self.assertEqual(raport['budzet']['arkuszy'], 0)

    def test_cofniecie_kopii_wraca_do_importu(self):
        wpis = self.przyjmij()
        zmiany.zapisz('cofnij', {'wpis': wpis['id']})
        self.przelicz()
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM bud_wiersz').fetchone()[0], 8)   # składowe umowy znowu osobno

    def test_zmieniony_plik_kopii_widoczny_jako_blad(self):
        wpis = self.przyjmij()
        p = kopia_bs.plik_kopii(wpis['dane']['plik'])
        p.write_text(p.read_text(encoding='utf-8').replace('Abonament', 'Abonamentx'), encoding='utf-8')
        raport = self.przelicz()
        self.assertTrue(any(b.startswith('Kopia z BS:') for b in raport['bledy']), raport['bledy'])
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM bud_wiersz').fetchone()[0], 8)   # import z eksportu

    def test_przyjecie_odrzucone(self):
        p = kopia_bs.podglad()
        with self.assertRaisesRegex(ValueError, 'zmienił się'):
            kopia_bs.przyjmij('0' * 64, zmiany.wczytaj()[0])
        zly = dict(kopia_bs.kontrola([], [], {}))
        zly['roznic'] = 1
        with mock.patch.object(kopia_bs, 'kontrola', return_value=zly):
            with self.assertRaisesRegex(ValueError, 'różnic'):
                kopia_bs.przyjmij(p['eksport_sha256'], zmiany.wczytaj()[0])
        self.assertEqual(list((self.srod.katalog / 'Finanse' / 'Aplikacja').glob('kopia_bs_*')), [])
        self.assertEqual([w for w in zmiany.wczytaj()[0] if w['typ'] == 'kopia_bs'], [])

    def test_wpis_kopii_walidowany(self):
        with self.assertRaises(ValueError):
            zmiany.sprawdz('kopia_bs', {'plik': '../x.json', 'sha256': 'a' * 64})
        with self.assertRaises(ValueError):
            zmiany.sprawdz('kopia_bs', {'plik': 'kopia_bs_2026-10-19.json', 'sha256': 'xyz'})
        self.assertEqual(zmiany.sprawdz('ustawienie', {'klucz': 'import_bs', 'wartosc': 'nie'}), {'klucz': 'import_bs', 'wartosc': 'nie'})


class TestGenerator(unittest.TestCase):
    def test_domyslnie_tydzien_od_wtorku(self):
        self.assertEqual(plan.PIERWSZY_DZIEN_TYGODNIA, 1)
        self.assertEqual(plan.podziel_worek(300000, '2026-11')[:2], [('2026-11-01', 20000), ('2026-11-03', 70000)])

    def test_podzial_z_kopii_tylko_gdy_sumuje_sie_do_kwoty(self):
        w = {'id': 'w', 'podstawa': 'Faktura (w worku)', 'stawka_vat': 23, 'dni_na_platnosc': 0}
        ps = plan.generuj_komorke(w, '2026-08', 310000, podzial=[['2026-08-31', 310000]])
        self.assertEqual([(p['wystawienie'], p['netto'], p['vat']) for p in ps], [('2026-08-31', 310000, 71300)])
        self.assertEqual(len(plan.generuj_komorke(w, '2026-08', 310001, podzial=[['2026-08-31', 310000]])), 5)
        u = {'id': 'u', 'podstawa': 'Umowa o pracę', 'proporcje': {'osoba': 59, 'us': 6, 'zus': 35}, 'dni_na_platnosc': 7}
        ps = {p['skladowa']: p['netto'] for p in plan.generuj_komorke(u, '2026-10', 1000000, podzial={'osoba': 590001, 'us': 59999, 'zus': 350000})}
        self.assertEqual(ps, {'osoba': 590001, 'us': 59999, 'zus': 350000})
        ps = {p['skladowa']: p['netto'] for p in plan.generuj_komorke(u, '2026-10', 1000000, podzial={'osoba': 1, 'us': 0, 'zus': 0})}
        self.assertEqual(ps, {'osoba': 590000, 'us': 60000, 'zus': 350000})


class TestSerwerKopii(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srod = Srodowisko().__enter__()
        przygotuj(cls.srod)
        odbudowa.odbuduj()
        cls.stary_port = konfig.PORT
        cls.http = ThreadingHTTPServer((konfig.HOST, 0), serwer.Obsluga)
        konfig.PORT = cls.http.server_address[1]
        threading.Thread(target=cls.http.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        konfig.PORT = cls.stary_port
        cls.srod.__exit__()

    def zadanie(self, metoda, sciezka, cialo=None):
        c = http.client.HTTPConnection('127.0.0.1', konfig.PORT, timeout=10)
        h = {'Host': f'127.0.0.1:{konfig.PORT}', 'X-Finanse': '1', 'Content-Type': 'application/json'}
        c.request(metoda, sciezka, body=json.dumps(cialo) if cialo is not None else None, headers=h)
        r = c.getresponse()
        return r, r.read()

    def test_podglad_przyjecie_zgodnosc(self):
        r, t = self.zadanie('GET', '/api/budzet/kopia')
        self.assertEqual(r.status, 200)
        p = json.loads(t)
        self.assertEqual(p['roznic'], 0)
        self.assertEqual([w for w in zmiany.wczytaj()[0] if w['typ'] == 'kopia_bs'], [])   # podgląd nic nie zapisuje
        r, t = self.zadanie('POST', '/api/zmiana', {'typ': 'kopia_bs', 'dane': {'plik': 'kopia_bs_2026-10-19.json', 'sha256': 'a' * 64}})
        self.assertEqual(r.status, 400)
        r, t = self.zadanie('GET', '/api/eksport/kontrola-bs?podglad=1')
        self.assertEqual(r.status, 200)
        self.assertIn('spreadsheetml', r.getheader('Content-Type'))
        r, t = self.zadanie('POST', '/api/kopia-bs', {'eksport_sha256': p['eksport_sha256']})
        self.assertEqual(r.status, 200, t)
        r, t = self.zadanie('GET', '/api/budzet/zgodnosc')
        z = json.loads(t)
        self.assertEqual((z['roznic'], z['import_bs']), (0, True))
        self.assertTrue(z['kopia']['plik'].startswith('kopia_bs_'))


if __name__ == '__main__':
    unittest.main()
