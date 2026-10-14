"""Odbudowa bazy z plików źródłowych. Buduje do pliku tymczasowego i podmienia atomowo,
więc przerwana odbudowa nigdy nie zostawia połowicznej bazy."""
import os
from pathlib import Path

from . import baza, konfig, zmiany
from .importy import fakturownia, ing, rejestr_biura, wyniki_biura
from .importy.wspolne import pliki, sha256, teraz

# (rodzaj, wzorzec względem Dane/, moduł, wszystkie pliki czy tylko najnowszy)
ZRODLA = [
    ('ING', 'ING/ing_historia_*.csv', ing, True),
    ('Fakturownia', 'Fakturownia/fakturownia_sprzedaz_*.csv', fakturownia, False),
    ('Rejestr zakupów', 'Biuro/biuro_rejestr_zakupow_*.xlsx', rejestr_biura, True),
    ('Wyniki biura', 'Biuro/biuro_wyniki_*.xls', wyniki_biura, True),
]


def odcisk_zrodel() -> str:
    """Zmienia się, gdy w Dane/ pojawi się nowy lub inny plik albo nowy wpis w zmianach."""
    dane = konfig.katalog_dane()
    czesci = []
    for _, wzorzec, _, _ in ZRODLA:
        for p in pliki(dane, wzorzec):
            czesci.append(f'{p.name}:{p.stat().st_size}:{int(p.stat().st_mtime)}')
    return '|'.join(czesci) + '#' + zmiany.odcisk()


def odbuduj(cel: Path | None = None) -> dict:
    cel = cel or konfig.plik_bazy()
    konfig.katalog_prywatny(cel.parent)
    tymczasowy = cel.with_suffix('.tmp')
    con = baza.nowa(tymczasowy)
    con.isolation_level = None
    con.execute('BEGIN')
    raport = {'zrodla': [], 'bledy': []}
    try:
        dane = konfig.katalog_dane()
        widziane = set()
        for rodzaj, wzorzec, modul, wszystkie in ZRODLA:
            lista = pliki(dane, wzorzec)
            if not lista:
                raport['bledy'].append(f'Brak plików {wzorzec} w Dane/')
                continue
            for p in (lista if wszystkie else lista[:1]):
                h = sha256(p)
                if h in widziane:   # ten sam plik pod inną nazwą: nic nie dubluje
                    con.execute('INSERT INTO import_log (rodzaj, plik, sha256, wierszy, nowych, pominietych, uwagi, czas)'
                                ' VALUES (?,?,?,0,0,0,?,?)', (rodzaj, p.name, h, 'kopia pliku już zaimportowanego', teraz()))
                    continue
                widziane.add(h)
                con.execute('SAVEPOINT plik')
                try:
                    nowych = modul.importuj(con, p)
                    con.execute('RELEASE plik')
                    raport['zrodla'].append((rodzaj, p.name, nowych))
                except Exception as e:  # jeden zły plik nie blokuje reszty, błąd widać w apce
                    con.execute('ROLLBACK TO plik')
                    con.execute('RELEASE plik')
                    raport['bledy'].append(f'{p.name}: {e}')
        wpisy, ostrzezenia = zmiany.wczytaj()
        raport['bledy'] += ostrzezenia
        for k, v in (('odbudowa', teraz()), ('odcisk', odcisk_zrodel()), ('mac', konfig.nazwa_maca()),
                     ('zmian', str(len(wpisy))), ('bledy', '\n'.join(raport['bledy']))):
            con.execute('INSERT INTO meta VALUES (?,?)', (k, v))
        con.execute('COMMIT')
    finally:
        con.close()
    os.chmod(tymczasowy, 0o600)
    os.replace(tymczasowy, cel)
    return raport
