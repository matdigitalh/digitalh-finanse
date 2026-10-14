"""Eksport faktur sprzedażowych z Fakturowni (CSV UTF-8, ',', kropka dziesiętna).

Układ sprawdzony 14.10.2026: jeden wiersz = jedna faktura. Kolumny 0–44 to dane faktury, od kolumny 45
pozycje w blokach po 12 kolumn (Produkt/usługa … Wartość dodatkowego pola). Wiersze z pustym „Typ”
to uwagi do faktury (Rodzaj informacji, Treść informacji na końcu wiersza).
Importujemy tylko najnowszy plik: statusy i kwoty opłacone zmieniają się w czasie.
"""
import csv
from pathlib import Path

from ..format import data_iso, grosze
from .wspolne import zapisz_log

POCZATEK_POZYCJI = 45
DLUGOSC_POZYCJI = 12
WYMAGANE = ['numer', 'Typ', 'Status', 'Data wystawienia', 'Termin płatności', 'Nabywca', 'NIP',
            'Wartość netto PLN', 'VAT PLN', 'Wartość brutto PLN', 'Kwota opłacona', 'Numer KSeF', 'Produkt/usługa']


def kw(s):
    return grosze(s, przecinek_dziesietny=False)


def wczytaj(p: Path):
    with open(p, encoding='utf-8-sig', newline='') as f:
        wiersze = list(csv.reader(f))
    naglowek = wiersze[0]
    brak = [k for k in WYMAGANE if k not in naglowek]
    if brak:
        raise ValueError(f'{p.name}: brak kolumn {brak}')
    i = {k: naglowek.index(k) for k in naglowek}
    assert i['Produkt/usługa'] == POCZATEK_POZYCJI, 'zmienił się układ kolumn eksportu Fakturowni'
    faktury, pozycje, uwagi = {}, [], {}
    for nr, w in enumerate(wiersze[1:], start=2):
        if not any(w):
            continue
        g = lambda k: w[i[k]].strip() if i[k] < len(w) else ''
        numer = g('numer')
        if not g('Typ'):
            tresc = w[-1].strip() if len(w) > 1 else ''
            if numer and tresc:
                uwagi.setdefault(numer, []).append(tresc)
            continue
        brutto = kw(g('Wartość brutto PLN'))
        typ = g('Typ')
        korekta = int(brutto < 0 or 'kor' in typ.lower() or bool(g('Oryginalny dokument')))
        faktury[numer] = {
            'numer': numer, 'typ': typ, 'status': g('Status'),
            'data_wystawienia': data_iso(g('Data wystawienia')), 'data_sprzedazy': data_iso(g('Data sprzedaży')),
            'termin': data_iso(g('Termin płatności')), 'nabywca': g('Nabywca'), 'nip': g('NIP').replace('-', ''),
            'netto': kw(g('Wartość netto PLN')), 'vat': kw(g('VAT PLN')), 'brutto': brutto,
            'oplacono': kw(g('Kwota opłacona')), 'waluta': g('Waluta') or 'PLN', 'ksef': g('Numer KSeF'),
            'korekta': korekta, 'oryginal': g('Oryginalny dokument'), 'przyczyna_korekty': g('Przyczyna korekty'),
            'wiersz': nr,
        }
        for lp, start in enumerate(range(POCZATEK_POZYCJI, len(w), DLUGOSC_POZYCJI), start=1):
            blok = w[start:start + DLUGOSC_POZYCJI]
            if len(blok) < 8 or not blok[0].strip():
                continue
            pozycje.append({'numer': numer, 'lp': lp, 'nazwa': blok[0].strip(), 'ilosc': blok[1].strip(),
                            'stawka': blok[4].strip(), 'vat': kw(blok[5]), 'netto': kw(blok[6]),
                            'brutto': kw(blok[7]), 'wiersz': nr})
    for numer, lista in uwagi.items():
        if numer in faktury:
            faktury[numer]['uwagi'] = '\n'.join(lista)
    return list(faktury.values()), pozycje


def importuj(con, p: Path) -> int:
    faktury, pozycje = wczytaj(p)
    zrodlo = f'{p.parent.name}/{p.name}'
    nowych = 0
    for f in faktury:
        cur = con.execute(
            'INSERT OR IGNORE INTO faktury (numer, typ, status, data_wystawienia, data_sprzedazy, termin, nabywca, nip,'
            ' netto, vat, brutto, oplacono, waluta, ksef, korekta, oryginal, przyczyna_korekty, uwagi, plik, wiersz)'
            ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (f['numer'], f['typ'], f['status'], f['data_wystawienia'], f['data_sprzedazy'], f['termin'], f['nabywca'],
             f['nip'], f['netto'], f['vat'], f['brutto'], f['oplacono'], f['waluta'], f['ksef'], f['korekta'],
             f['oryginal'], f['przyczyna_korekty'], f.get('uwagi', ''), zrodlo, f['wiersz']))
        nowych += cur.rowcount
    for x in pozycje:
        con.execute('INSERT OR IGNORE INTO faktury_pozycje (numer, lp, nazwa, ilosc, stawka, netto, vat, brutto, plik, wiersz)'
                    ' VALUES (?,?,?,?,?,?,?,?,?,?)',
                    (x['numer'], x['lp'], x['nazwa'], x['ilosc'], x['stawka'], x['netto'], x['vat'], x['brutto'],
                     zrodlo, x['wiersz']))
    # sanity: suma pozycji netto = netto faktury
    rozjazd = con.execute(
        'SELECT COUNT(*) FROM faktury f WHERE f.plik=? AND f.netto != '
        '(SELECT COALESCE(SUM(netto),0) FROM faktury_pozycje p WHERE p.numer=f.numer)', (zrodlo,)).fetchone()[0]
    zapisz_log(con, 'Fakturownia', p, len(faktury), nowych,
               f'{len(pozycje)} pozycji' + (f'; {rozjazd} faktur z sumą pozycji różną od netto' if rozjazd else ''))
    return nowych
