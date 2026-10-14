"""Historia operacji ING, szablon „CFO historia operacji” (CSV UTF-8 z BOM, ';', przecinek dziesiętny).

Plik ma najnowsze operacje na górze. Kolejne eksporty mogą się nakładać, więc importujemy wszystkie
pliki od najnowszego i pomijamy operacje, które już są (klucz w baza.py).
"""
import csv
import io
from pathlib import Path

from ..format import data_iso, grosze, norm
from .wspolne import data_z_nazwy, zapisz_log

RACHUNKI = {'5263': 'główny', '5271': 'online', '5289': 'VAT'}
WYMAGANE = ['data księgowania', 'kwota', 'saldo po transakcji', 'nazwa i adres kontrahenta',
            'rachunek ING "NRB" (26 znaków)', 'numer referencyjny']


def wewnetrzna(kontrahent: str, rachunek: str) -> bool:
    """Przelew między rachunkami DigitalH albo cały rachunek VAT: nie koszt, nie przychód (brief, sekcja 3)."""
    return rachunek == 'VAT' or 'digitalh' in norm(kontrahent).replace(' ', '')


def wczytaj(p: Path) -> list[dict]:
    tekst = p.read_text(encoding='utf-8-sig')
    wiersze = list(csv.reader(io.StringIO(tekst), delimiter=';'))
    if not wiersze:
        return []
    naglowek = [h.strip() for h in wiersze[0]]
    brak = [k for k in WYMAGANE if k not in naglowek]
    if brak:
        raise ValueError(f'{p.name}: brak kolumn {brak}. To nie jest eksport „CFO historia operacji”?')
    wynik = []
    for nr, w in enumerate(wiersze[1:], start=2):
        if not any(c.strip() for c in w):
            continue
        x = dict(zip(naglowek, (c.strip() for c in w)))
        nrb = x['rachunek ING "NRB" (26 znaków)'].replace(' ', '')
        rachunek = RACHUNKI.get(nrb[-4:], '?')
        tytul = ' '.join(x.get(f'szczegóły płatności linia {i}', '') for i in range(1, 5)).strip()
        kwota = grosze(x['kwota'])
        oryg = x.get('oryginalna kwota transakcji', '')
        ref = x['numer referencyjny']
        if ref:
            klucz = f'{ref}|{rachunek}'
        else:
            klucz = f'{data_iso(x["data księgowania"])}|{kwota}|{tytul}|{rachunek}'
        wynik.append({
            'klucz': klucz, 'rachunek': rachunek, 'nrb': nrb,
            'data_transakcji': data_iso(x.get('data transakcji')),
            'data_ksiegowania': data_iso(x['data księgowania']),
            'kwota': kwota, 'waluta': x.get('waluta operacji') or 'PLN',
            'kwota_oryg': grosze(oryg) if oryg else None, 'waluta_oryg': x.get('oryginalna waluta transakcji') or None,
            'saldo_po': grosze(x['saldo po transakcji']) if x['saldo po transakcji'] else None,
            'kontrahent': x['nazwa i adres kontrahenta'], 'rachunek_kontrahenta': x.get('rachunek kontrahenta', ''),
            'opis': x.get('nazwa transakcji i opis', ''), 'tytul': tytul, 'nr_ref': ref,
            'wewnetrzna': int(wewnetrzna(x['nazwa i adres kontrahenta'], rachunek)),
            'wiersz': nr,
        })
    return wynik


def importuj(con, p: Path) -> int:
    operacje = wczytaj(p)
    zrodlo = f'{p.parent.name}/{p.name}'
    data_pliku = data_z_nazwy(p)
    nowych = 0
    for o in operacje:
        cur = con.execute(
            'INSERT OR IGNORE INTO operacje (klucz, rachunek, nrb, data_transakcji, data_ksiegowania, kwota, waluta,'
            ' kwota_oryg, waluta_oryg, saldo_po, kontrahent, rachunek_kontrahenta, opis, tytul, nr_ref, wewnetrzna,'
            ' plik, wiersz, data_pliku) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (o['klucz'], o['rachunek'], o['nrb'], o['data_transakcji'], o['data_ksiegowania'], o['kwota'], o['waluta'],
             o['kwota_oryg'], o['waluta_oryg'], o['saldo_po'], o['kontrahent'], o['rachunek_kontrahenta'], o['opis'],
             o['tytul'], o['nr_ref'], o['wewnetrzna'], zrodlo, o['wiersz'], data_pliku))
        nowych += cur.rowcount
    nieznane = sum(1 for o in operacje if o['rachunek'] == '?')
    zapisz_log(con, 'ING', p, len(operacje), nowych, f'{nieznane} operacji z nieznanego rachunku' if nieznane else '')
    return nowych
