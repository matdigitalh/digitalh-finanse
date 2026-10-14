"""Eksport płatności z Budget Studio (CSV UTF-8, tabulator, przecinek dziesiętny).

Tylko źródło podpowiedzi w okresie równoległym: do jakiego klienta (folderu) należy faktura i jak Mat
skategoryzował koszty danego kontrahenta. Reguły Mata w aplikacji zawsze wygrywają. Bierzemy najnowszy plik.
"""
import csv
from pathlib import Path

from ..format import data_iso, grosze
from .wspolne import zapisz_log

WYMAGANE = ['ID', 'Rodzaj', 'Status aktualności', 'Numer dokumentu', 'Kontrahent', 'Netto (wartość)',
            'Brutto (wartość)', 'Miesiąc budżetowy', 'Arkusz', 'Folder', 'Kategoria']


def _dzien(x):
    for k in ('Dzień płatności - realny', 'Dzień płatności'):
        try:
            d = data_iso(x.get(k))
        except ValueError:
            d = None
        if d:
            return d
    return None


def importuj(con, p: Path) -> int:
    zrodlo = f'{p.parent.name}/{p.name}'
    with open(p, encoding='utf-8-sig', newline='') as f:
        czytnik = csv.DictReader(f, delimiter='\t')
        brak = [k for k in WYMAGANE if k not in (czytnik.fieldnames or [])]
        if brak:
            raise ValueError(f'{p.name}: brak kolumn {brak}')
        wiersze = 0
        for nr, x in enumerate(czytnik, start=2):
            if x['Rodzaj'] not in ('1', '-1'):
                continue
            wiersze += 1
            con.execute('INSERT INTO bs (id, rodzaj, status, numer, kontrahent, netto, brutto, miesiac, arkusz, folder,'
                        ' kategoria, dzien, plik, wiersz) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (x['ID'], int(x['Rodzaj']), x['Status aktualności'], x['Numer dokumentu'].strip(),
                         x['Kontrahent'].strip(), grosze(x['Netto (wartość)']), grosze(x['Brutto (wartość)']),
                         (data_iso(x['Miesiąc budżetowy']) or '')[:7], x['Arkusz'].strip(), x['Folder'].strip(),
                         x['Kategoria'].strip(), _dzien(x), zrodlo, nr))
    zapisz_log(con, 'Budget Studio', p, wiersze, wiersze, 'tylko podpowiedzi klientów i kategorii kosztów')
    return wiersze
