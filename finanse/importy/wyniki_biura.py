"""Wyniki z biura (xls z enova): RZiS narastająco. Punkt odniesienia, nie źródło liczenia.

Układ sprawdzony 14.10.2026: kolumna 0 = kod pozycji (A, B.I …), 2 = opis, 9 = bieżący okres,
12 = poprzedni rok. Szukamy kolumn po nagłówku „Za okres”, żeby przeżyć drobne zmiany układu.
"""
from pathlib import Path

from ..format import grosze
from .wspolne import data_z_nazwy, zapisz_log


def wczytaj(p: Path) -> list[dict]:
    import xlrd
    ks = xlrd.open_workbook(p)
    wynik = []
    for nazwa in ('RZiS',):
        if nazwa not in ks.sheet_names():
            continue
        s = ks.sheet_by_name(nazwa)
        kol_biezaca = kol_poprz = None
        for r in range(s.nrows):
            w = s.row_values(r)
            okresy = [j for j, c in enumerate(w) if isinstance(c, str) and c.startswith('Za okres')]
            if okresy and kol_biezaca is None:
                kol_biezaca = okresy[0]
                kol_poprz = okresy[1] if len(okresy) > 1 else None
                continue
            if kol_biezaca is None:
                continue
            kod, opis = str(w[0]).strip(), str(w[2]).strip()
            wart = w[kol_biezaca]
            if not opis or not isinstance(wart, float):
                continue
            wynik.append({'zestawienie': nazwa, 'kod': kod, 'opis': opis.lstrip('+ -').strip(),
                          'wartosc': grosze(wart),
                          'wartosc_poprzednia': grosze(w[kol_poprz]) if kol_poprz is not None and isinstance(w[kol_poprz], float) else None,
                          'wiersz': r + 1})
    return wynik


def importuj(con, p: Path) -> int:
    pozycje = wczytaj(p)
    zrodlo = f'{p.parent.name}/{p.name}'
    okres = data_z_nazwy(p)
    nowych = 0
    for x in pozycje:
        cur = con.execute('INSERT OR IGNORE INTO wyniki_biura (okres, zestawienie, kod, opis, wartosc, wartosc_poprzednia,'
                          ' plik, wiersz) VALUES (?,?,?,?,?,?,?,?)',
                          (okres, x['zestawienie'], x['kod'], x['opis'], x['wartosc'], x['wartosc_poprzednia'],
                           zrodlo, x['wiersz']))
        nowych += cur.rowcount
    zapisz_log(con, 'Wyniki biura', p, len(pozycje), nowych, f'okres {okres}')
    return nowych
