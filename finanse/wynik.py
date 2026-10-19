"""Etap 4: wynik zarządczy miesięcznie, obroty wg klientów i kategorii, VAT.

Liczone przy zapytaniu z tabel z etapów 2–3. Zasady przypisania do miesiąca (memoriałowo, na ile się da):
- przychód: faktury netto wg daty sprzedaży (korekty ze znakiem minus),
- koszt z dokumentem z rejestru biura: netto, miesiąc daty dokumentu,
- koszt bez dokumentu: kwota z banku (brutto), miesiąc płatności,
- koszty pracy: miesiąc, którego dotyczą (z tytułu: „ZA 07.2026”, „DRA 01/07”, „OKR/26M07”, „PPK 2026 07”);
  bez okresu w tytule: płatność do 25. dnia to poprzedni miesiąc.
VAT i podział zysku są poza wynikiem. Podatki (CIT, opłaty urzędowe) pokazane pod wynikiem.
"""
import calendar
import json
import re
from collections import defaultdict
from datetime import date

from . import konfig

W_WYNIKU = ('przenoszony', 'praca', 'staly', 'nieprzypisany')
OKRES_ZA = re.compile(r'\bZA\s*(\d{1,2})[./-](\d{4})\b', re.I)
OKRES_DRA = re.compile(r'\bDRA\s*\d{2}/(\d{2})\b', re.I)
OKRES_US = re.compile(r'/OKR/(\d{2})M(\d{2})/', re.I)
OKRES_PPK = re.compile(r'PPK\s*(\d{4})\s*(\d{2})\b', re.I)


def _poprzedni(miesiac: str) -> str:
    r, m = int(miesiac[:4]), int(miesiac[5:7])
    return f'{r - 1}-12' if m == 1 else f'{r}-{m - 1:02d}'


def okres_pracy(tytul: str, data_platnosci: str) -> str:
    t = tytul or ''
    if (m := OKRES_ZA.search(t)):
        return f'{m.group(2)}-{int(m.group(1)):02d}'
    if (m := OKRES_US.search(t)):
        return f'20{m.group(1)}-{m.group(2)}'
    if (m := OKRES_PPK.search(t)):
        return f'{m.group(1)}-{m.group(2)}'
    if (m := OKRES_DRA.search(t)):
        mies, rok = int(m.group(1)), int(data_platnosci[:4])
        if mies > int(data_platnosci[5:7]):
            rok -= 1
        return f'{rok}-{mies:02d}'
    return _poprzedni(data_platnosci[:7]) if int(data_platnosci[8:10]) <= 25 else data_platnosci[:7]


def koszty(con) -> list[dict]:
    """Każdy wydatek z banku jako pozycja kosztowa: miesiąc, rodzaj, klient, kwota (dodatnia), skąd kwota."""
    wynik = []
    for r in con.execute(
            "SELECT o.id, o.data_ksiegowania, o.kwota, o.kontrahent, o.tytul, w.rodzaj, w.klient, w.kontrahent_klucz,"
            " w.dokument, w.netto_dok, (SELECT MIN(z.data) FROM wydatki_dok d JOIN zakupy z USING(nr_ewid)"
            " WHERE d.operacja_id = o.id) AS data_dok FROM wydatki w JOIN operacje o ON o.id = w.operacja_id"):
        if r['dokument'] == 'dokument' and r['netto_dok'] is not None:   # także podwykonawca na fakturze
            miesiac, kwota, skad = (r['data_dok'] or r['data_ksiegowania'])[:7], r['netto_dok'], 'dokument netto'
        elif r['rodzaj'] == 'praca':
            miesiac, kwota, skad = okres_pracy(r['tytul'], r['data_ksiegowania']), -r['kwota'], 'bank'
        elif r['rodzaj'] in ('vat', 'podatki'):
            miesiac, kwota, skad = okres_pracy(r['tytul'], r['data_ksiegowania']) if '/OKR/' in (r['tytul'] or '') \
                else r['data_ksiegowania'][:7], -r['kwota'], 'bank'
        else:
            miesiac, kwota, skad = r['data_ksiegowania'][:7], -r['kwota'], 'bank brutto'
        wynik.append({'id': r['id'], 'miesiac': miesiac, 'rodzaj': r['rodzaj'], 'klient': r['klient'] or '',
                      'kontrahent': r['kontrahent'], 'klucz': r['kontrahent_klucz'], 'kwota': kwota, 'skad': skad})
    return wynik


def obroty(con) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT substr(COALESCE(f.data_sprzedazy, f.data_wystawienia), 1, 7) AS miesiac, COALESCE(fk.klient, f.nabywca) AS klient,"
        " f.netto, f.vat FROM faktury f LEFT JOIN faktury_klient fk USING(numer)")]


def ustawienia() -> dict:
    """Cele roczne Mata, poza repo: Finanse/Aplikacja/ustawienia.json. Brak pliku = brak paska celu."""
    p = konfig.katalog_finanse() / 'Aplikacja' / 'ustawienia.json'
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def _rok_domyslny(con) -> str:
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone()
    return (r[0] if r and r[0] else date.today().isoformat())[:4]


def _miesiace(rok, *zbiory):
    m = sorted({x['miesiac'] for z in zbiory for x in z if x['miesiac'] and x['miesiac'].startswith(rok)})
    return m


def wynik_zarzadczy(con, rok=None) -> dict:
    rok = rok or _rok_domyslny(con)
    k, o = koszty(con), obroty(con)
    miesiace = _miesiace(rok, k, o)
    tab = defaultdict(lambda: defaultdict(int))
    ile_bez_dok = defaultdict(int)
    for x in o:
        if x['miesiac'] in miesiace:
            tab['obrot'][x['miesiac']] += x['netto']
    for x in k:
        if x['miesiac'] in miesiace:
            tab[x['rodzaj']][x['miesiac']] += x['kwota']
            if x['skad'] == 'bank brutto' and x['rodzaj'] in W_WYNIKU:
                ile_bez_dok[x['miesiac']] += 1
    for m in miesiace:
        tab['pna'][m] = tab['obrot'][m] - tab['przenoszony'][m]
        tab['wynik'][m] = tab['pna'][m] - tab['praca'][m] - tab['staly'][m] - tab['nieprzypisany'][m]
    wiersze = []
    for klucz, nazwa, znak, typ in (
            ('obrot', 'Obrót netto (faktury)', 1, ''), ('przenoszony', 'Koszty klientów (media, druk, podwykonawcy)', -1, ''),
            ('pna', 'Przychód netto agencji', 1, 'suma'), ('praca', 'Koszty pracy (wynagrodzenia, ZUS, PIT-4, PPK)', -1, ''),
            ('staly', 'Koszty stałe', -1, ''), ('nieprzypisany', 'Koszty nieprzypisane', -1, 'uwaga'),
            ('wynik', 'Wynik zarządczy', 1, 'wynik'),
            ('podatki', 'Podatki i opłaty urzędowe (poza wynikiem)', -1, 'poza'), ('dywidenda', 'Podział zysku (poza wynikiem)', -1, 'poza'),
            ('vat', 'VAT zapłacony (poza wynikiem)', -1, 'poza'), ('zwrot', 'Zwroty dla klientów (poza wynikiem)', -1, 'poza')):
        wart = {m: znak * tab[klucz][m] for m in miesiace}
        wiersze.append({'klucz': klucz, 'nazwa': nazwa, 'typ': typ, 'miesiace': wart, 'razem': sum(wart.values())})
    obrot, wyn = sum(tab['obrot'].values()), sum(tab['wynik'][m] for m in miesiace)
    from .controlling import cele as cele_mata
    cele = cele_mata(con)
    dzien = (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0]
    czesc_roku = (date.fromisoformat(dzien).timetuple().tm_yday / (366 if calendar.isleap(int(rok)) else 365)) if dzien.startswith(rok) else 1
    biuro = [dict(r) for r in con.execute(
        "SELECT okres, kod, opis, wartosc FROM wyniki_biura WHERE zestawienie = 'RZiS' AND kod IN ('A', 'B', 'C', 'D', 'L')"
        " AND okres LIKE ? ORDER BY okres DESC, wiersz", (f'{rok}%',))]
    okres_biura = biuro[0]['okres'] if biuro else None
    porownanie = None
    if okres_biura:
        do_m = [m for m in miesiace if m <= okres_biura]
        porownanie = {'okres': okres_biura, 'biuro': {b['kod']: b['wartosc'] for b in biuro if b['okres'] == okres_biura},
                      'opisy': {b['kod']: b['opis'] for b in biuro if b['okres'] == okres_biura},
                      'aplikacja_obrot': sum(tab['obrot'][m] for m in do_m), 'aplikacja_wynik': sum(tab['wynik'][m] for m in do_m)}
    lata = sorted({x['miesiac'][:4] for x in o if x['miesiac']}, reverse=True)
    # Miesiąc stanu i poprzedni są niepełne: faktury za bieżący miesiąc wystawiamy na końcu, a ZUS, PIT-4 i VAT
    # za poprzedni płacimy 15.–25. następnego miesiąca.
    niepelne = [m for m in miesiace if dzien and m >= _poprzedni(dzien[:7])]
    return {'rok': rok, 'lata': lata, 'miesiace': miesiace, 'niepelne': niepelne, 'wiersze': wiersze, 'bez_dokumentu': dict(ile_bez_dok),
            'obrot': obrot, 'wynik': wyn, 'marza_proc': round(100 * wyn / obrot, 1) if obrot else None,
            'cele': {'obrot': cele['cel_obrot_rok'], 'zysk': round(cele['cel_obrot_rok'] * cele['cel_marza_proc'] / 100),
                     'czesc_roku': round(czesc_roku, 3)},
            'porownanie_z_biurem': porownanie, 'dzien_stanu': dzien}


def obroty_klientow(con, rok=None) -> dict:
    rok = rok or _rok_domyslny(con)
    o, k = obroty(con), koszty(con)
    miesiace = _miesiace(rok, o)
    tab = defaultdict(lambda: {'miesiace': defaultdict(int), 'obrot': 0, 'koszty': 0})
    for x in o:
        if x['miesiac'] in miesiace:
            tab[x['klient']]['miesiace'][x['miesiac']] += x['netto']
            tab[x['klient']]['obrot'] += x['netto']
    for x in k:
        if x['rodzaj'] == 'przenoszony' and x['klient'] and x['miesiac'].startswith(rok):
            tab[x['klient']]['koszty'] += x['kwota']
    razem = sum(v['obrot'] for v in tab.values()) or 1
    lista = []
    for n, v in tab.items():
        if not v['obrot'] and not v['koszty']:
            continue
        lista.append({'klient': n, 'miesiace': dict(v['miesiace']), 'obrot': v['obrot'], 'koszty': v['koszty'],
                      'pna': v['obrot'] - v['koszty'], 'udzial': round(100 * v['obrot'] / razem, 1),
                      'marza_proc': round(100 * (v['obrot'] - v['koszty']) / v['obrot'], 1) if v['obrot'] > 0 else None})
    lista.sort(key=lambda x: -x['obrot'])
    return {'rok': rok, 'miesiace': miesiace, 'klienci': lista}


def koszty_kategorii(con, rok=None, rodzaj=None) -> dict:
    rok = rok or _rok_domyslny(con)
    k = [x for x in koszty(con) if x['miesiac'].startswith(rok)]
    miesiace = _miesiace(rok, k, obroty(con))
    tab = defaultdict(lambda: defaultdict(int))
    nazwy = {}
    for x in k:
        if rodzaj:
            if x['rodzaj'] != rodzaj:
                continue
            klucz = x['klucz'] or '(bez nazwy)'
            nazwy.setdefault(klucz, x['kontrahent'])
        else:
            klucz = x['rodzaj']
        tab[klucz][x['miesiac']] += x['kwota']
    lista = [{'klucz': kl, 'nazwa': nazwy.get(kl, kl), 'miesiace': dict(v), 'razem': sum(v.values())} for kl, v in tab.items()]
    lista.sort(key=lambda x: -x['razem'])
    return {'rok': rok, 'rodzaj': rodzaj, 'miesiace': miesiace, 'pozycje': lista}


def vat(con, rok=None) -> dict:
    """VAT należny (faktury) minus naliczony (rejestr krajowy biura) kontra zapłacony (bank, okres z tytułu)."""
    rok = rok or _rok_domyslny(con)
    tab = defaultdict(lambda: {'nalezny': 0, 'naliczony': 0, 'zaplacony': 0})
    for x in obroty(con):
        if x['miesiac'].startswith(rok):
            tab[x['miesiac']]['nalezny'] += x['vat'] or 0
    for r in con.execute("SELECT substr(data, 1, 7) AS m, SUM(vat) FROM zakupy WHERE rejestr = 'krajowe' GROUP BY m"):
        if r[0] and r[0].startswith(rok):
            tab[r[0]]['naliczony'] += r[1] or 0
    for x in koszty(con):
        if x['rodzaj'] == 'vat' and x['miesiac'].startswith(rok):
            tab[x['miesiac']]['zaplacony'] += x['kwota']
    koniec = (con.execute("SELECT wartosc FROM meta WHERE klucz='koniec_rejestru'").fetchone() or [''])[0]
    lista = [{'miesiac': m, **v, 'do_zaplaty': v['nalezny'] - v['naliczony'], 'rejestr': bool(koniec) and m <= koniec[:7]}
             for m, v in sorted(tab.items())]
    return {'rok': rok, 'miesiace': lista, 'koniec_rejestru': koniec}
