"""Pakiet 11 (A-BUD-07, A-BUD-14, B-INNE-02): rentowność budżetu jak w Budget Studio, tabela przestawna.

Wiersze: poziomy do wyboru (folder, kategoria, arkusz, sekcja, przedmiot transakcji, kontrahent), z rozwijaniem; kolumny:
miesiące roku; wartości: wpływy, obciążenia, wynik (wpływy minus obciążenia) i marża (wynik do wpływów) na każdym poziomie.
Jak w BS liczą się tylko płatności budżetu z Księgowane = tak (plany i rzeczywiste, kwoty netto), bez arkusza systemowego
Opłaty urzędowe. Płatność bierze tę samą aktualność co komórka arkusza (aktualna = 1), więc wynik arkusza w tabeli jest
równy sumie jego komórek z Księgowane = tak, a wynik folderu sumie jego arkuszy.

Oś czasu: miesiąc budżetowy (kolumna komórki, jak rentowność w BS) albo miesiąc księgowania (jak podatki).
Obok wynik zarządczy apki (bank i dokumenty, finanse/wynik.py), żeby widać było różnicę między planem a wykonaniem.
Kwoty w groszach, marża w procentach z jednym miejscem po przecinku (Decimal, połówki w górę)."""
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from . import wynik as wynik_zarzadczy
from .filtry import klucz_pl
from .zapytania_budzet import _dzien_stanu

POZIOMY = {
    'folder': 'Folder', 'kategoria': 'Kategoria', 'arkusz': 'Arkusz', 'sekcja': 'Sekcja',
    'przedmiot': 'Przedmiot transakcji', 'kontrahent': 'Kontrahent',
}
DOMYSLNE = ('folder', 'kategoria', 'arkusz')
OSIE = {'budzet': 'p.miesiac', 'ksiegowanie': "substr(COALESCE(NULLIF(p.ksiegowanie, ''), p.miesiac), 1, 7)"}


def marza(wynik: int, wplywy: int):
    if wplywy <= 0:
        return None
    return float((Decimal(wynik) * 100 / Decimal(wplywy)).quantize(Decimal('0.1'), ROUND_HALF_UP))


def _poziomy(tekst) -> list[str]:
    if isinstance(tekst, (list, tuple)):
        lista = list(tekst)
    else:
        lista = [x for x in str(tekst or '').split(',') if x]
    lista = [x for x in lista if x in POZIOMY]
    wynik = []
    for x in lista:
        if x not in wynik:
            wynik.append(x)
    return wynik[:4] or list(DOMYSLNE)


def lata(con) -> list[str]:
    return [r[0] for r in con.execute("SELECT DISTINCT substr(miesiac, 1, 4) FROM bud_platnosc WHERE miesiac != '' ORDER BY 1 DESC")]


def _wezel(klucz, nazwa, poziom):
    return {'klucz': klucz, 'nazwa': nazwa, 'poziom': poziom, 'm': defaultdict(lambda: [0, 0]), 'dzieci': {}}


def _wyjscie(w: dict, miesiace: list[str]) -> dict:
    mies = {}
    wp = ob = 0
    for m in miesiace:
        a, b = w['m'].get(m, (0, 0))
        wp += a
        ob += b
        if a or b:
            mies[m] = {'wplywy': a, 'obciazenia': b, 'wynik': a - b, 'marza': marza(a - b, a)}
    dzieci = sorted(w['dzieci'].values(), key=lambda x: klucz_pl(x['nazwa']))
    return {'klucz': w['klucz'], 'nazwa': w['nazwa'], 'poziom': w['poziom'], 'miesiace': mies,
            'wplywy': wp, 'obciazenia': ob, 'wynik': wp - ob, 'marza': marza(wp - ob, wp),
            'dzieci': [_wyjscie(d, miesiace) for d in dzieci]}


def policz(con, rok=None, poziomy=None, os='budzet', folder=None) -> dict:
    """Tabela przestawna dla roku. folder: tylko ten folder (karta klienta)."""
    rok = rok if rok and len(str(rok)) == 4 and str(rok).isdigit() else wynik_zarzadczy._rok_domyslny(con)
    poz = _poziomy(poziomy)
    os = os if os in OSIE else 'budzet'
    miesiace = [f'{rok}-{m:02d}' for m in range(1, 13)]
    sql = (f"SELECT a.id AS arkusz_id, a.nazwa AS arkusz, a.folder AS g_folder, a.kategoria AS g_kategoria,"
           " COALESCE(NULLIF(w.sekcja, ''), '-') AS g_sekcja, COALESCE(NULLIF(w.przedmiot, ''), '(bez przedmiotu)') AS g_przedmiot,"
           " COALESCE(NULLIF(p.kontrahent, ''), NULLIF(w.kontrahent, ''), '(bez kontrahenta)') AS g_kontrahent,"
           f" {OSIE[os]} AS m, p.rodzaj, SUM(p.netto) AS netto FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz"
           " JOIN bud_arkusz a ON a.id = w.arkusz"
           " WHERE p.aktualna = 1 AND COALESCE(p.ksiegowane, 1) = 1 AND COALESCE(a.zrodlo, '') != 'system'"
           f" AND {OSIE[os]} BETWEEN ? AND ?")
    params = [miesiace[0], miesiace[-1]]
    if folder is not None:
        sql += ' AND a.folder = ?'
        params.append(folder)
    sql += ' GROUP BY a.id, g_sekcja, g_przedmiot, g_kontrahent, m, p.rodzaj'
    korzen = _wezel('', 'Razem', -1)
    ark_bez_folderu = 'arkusz' in poz and ('folder' not in poz or poz.index('folder') > poz.index('arkusz'))
    for r in con.execute(sql, params):
        w = korzen
        for i, p in enumerate(poz):
            if p == 'arkusz':
                kl, nazwa = r['arkusz_id'], (f"{r['arkusz']} ({r['g_folder']})" if ark_bez_folderu else r['arkusz'])
            else:
                kl = nazwa = r[f'g_{p}']
            w = w['dzieci'].setdefault(kl, _wezel(kl, nazwa, i))
            wiersz = w['m'][r['m']]
            if r['rodzaj'] == 1:
                wiersz[0] += r['netto']
            else:
                wiersz[1] += r['netto']
        wiersz = korzen['m'][r['m']]
        if r['rodzaj'] == 1:
            wiersz[0] += r['netto']
        else:
            wiersz[1] += r['netto']
    razem = _wyjscie(korzen, miesiace)
    # nasz wynik zarządczy (bank i dokumenty) w tych samych miesiącach, obok budżetu; dla jednego folderu go nie ma
    # (wynik zarządczy jest dla całej firmy, klienta pokazuje karta klienta)
    zarz = None
    if folder is None:
        z = wynik_zarzadczy.wynik_zarzadczy(con, rok)
        wiersze_z = {x['klucz']: x for x in z['wiersze']}
        zarz = {'wynik': {m: wiersze_z['wynik']['miesiace'].get(m, 0) for m in miesiace if m in z['miesiace']},
                'obrot': {m: wiersze_z['obrot']['miesiace'].get(m, 0) for m in miesiace if m in z['miesiace']},
                'niepelne': z['niepelne']}
        zarz['razem_wynik'] = sum(zarz['wynik'].values())
        zarz['razem_obrot'] = sum(zarz['obrot'].values())
    return {'rok': rok, 'lata': sorted(set(lata(con)) | {rok}, reverse=True), 'miesiace': miesiace, 'poziomy': poz,
            'nazwy_poziomow': POZIOMY, 'os': os, 'folder': folder, 'wiersze': razem['dzieci'],
            'razem': {k: razem[k] for k in ('miesiace', 'wplywy', 'obciazenia', 'wynik', 'marza')}, 'zarzadczy': zarz,
            'dzien_stanu': _dzien_stanu(con)}
