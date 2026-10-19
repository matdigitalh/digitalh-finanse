"""Odbudowa bazy z plików źródłowych. Buduje do pliku tymczasowego i podmienia atomowo,
więc przerwana odbudowa nigdy nie zostawia połowicznej bazy."""
import hashlib
import os
from pathlib import Path

from . import baza, budzet, dopasowanie, klienci, konfig, laczenie, zmiany
from .importy import budget_studio, fakturownia, faktury_dysk, ing, rejestr_biura, wyniki_biura
from .importy.wspolne import pliki, sha256, teraz

# (rodzaj, wzorzec względem Dane/, moduł, wszystkie pliki czy tylko najnowszy)
ZRODLA = [
    ('ING', 'ING/ing_historia_*.csv', ing, True),
    ('Fakturownia', 'Fakturownia/fakturownia_sprzedaz_*.csv', fakturownia, False),
    ('Rejestr zakupów', 'Biuro/biuro_rejestr_zakupow_*.xlsx', rejestr_biura, True),
    ('Wyniki biura', 'Biuro/biuro_wyniki_*.xls', wyniki_biura, True),
    ('Budget Studio', 'Budget Studio/budget_studio_*.csv', budget_studio, False),
]
OPCJONALNE = {'Budget Studio'}   # bez tego pliku apka działa, tylko bez podpowiedzi


def odcisk_kodu() -> str:
    """Układ bazy i zasady dopasowania. Po aktualizacji apki baza przebudowuje się sama, bez klikania."""
    h = hashlib.sha256(baza.SCHEMAT.encode('utf-8'))
    h.update(Path(dopasowanie.__file__).read_bytes())
    h.update(Path(klienci.__file__).read_bytes())
    h.update(Path(faktury_dysk.__file__).read_bytes())
    h.update(Path(budzet.__file__).read_bytes())
    h.update(Path(laczenie.__file__).read_bytes())
    h.update((Path(budzet.__file__).parent / 'plan.py').read_bytes())
    h.update((Path(budzet.__file__).parent / 'umowy.py').read_bytes())
    h.update((Path(budzet.__file__).parent / 'kopia_bs.py').read_bytes())
    return h.hexdigest()[:16]


def odcisk_zrodel() -> str:
    """Zmienia się, gdy w Dane/ pojawi się nowy lub inny plik, nowy wpis w zmianach albo nowa wersja apki."""
    dane = konfig.katalog_dane()
    czesci = [f'kod:{odcisk_kodu()}']
    for _, wzorzec, _, _ in ZRODLA:
        for p in pliki(dane, wzorzec):
            czesci.append(f'{p.name}:{p.stat().st_size}:{int(p.stat().st_mtime)}')
    czesci += [f'faktury:{p.parent.parent.name}/{p.name}' for p in faktury_dysk.pliki()]
    ark = konfig.katalog_finanse() / 'Aplikacja' / 'arkusze_bs.json'
    if ark.exists():
        czesci.append(f'arkusze:{ark.stat().st_size}:{int(ark.stat().st_mtime)}')
    for p in sorted((konfig.katalog_finanse() / 'Aplikacja').glob('kopia_bs_*.json')):   # kopia z BS dociągnięta przez iCloud później
        czesci.append(f'kopia:{p.name}:{p.stat().st_size}')
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
        wpisy, ostrzezenia = zmiany.wczytaj()
        bez_bs = not budzet.import_bs_wlaczony(wpisy)   # pakiet 6: po 1.01.2027 apka nie czyta eksportów BS
        for rodzaj, wzorzec, modul, wszystkie in ZRODLA:
            if rodzaj == 'Budget Studio' and bez_bs:
                continue
            lista = pliki(dane, wzorzec)
            if not lista:
                if rodzaj not in OPCJONALNE:
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
        ile_plikow = faktury_dysk.importuj(con)   # tylko nazwy plików z Finanse/Faktury/*/Zweryfikowane
        con.execute('INSERT INTO import_log (rodzaj, plik, sha256, wierszy, nowych, pominietych, uwagi, czas) VALUES (?,?,?,?,?,?,?,?)',
                    ('Faktury kosztowe (folder)', 'Faktury/*/Zweryfikowane', '', ile_plikow, ile_plikow, 0,
                     'nazwy plików: kwota, data, konto reklamowe', teraz()))
        raport['bledy'] += ostrzezenia
        con.execute('SAVEPOINT dopasowanie')
        try:
            raport['dopasowanie'] = dopasowanie.policz(con, wpisy)
            con.execute('RELEASE dopasowanie')
        except Exception as e:  # błąd dopasowania nie blokuje podglądu danych z etapu 1
            con.execute('ROLLBACK TO dopasowanie')
            con.execute('RELEASE dopasowanie')
            raport['bledy'].append(f'Dopasowanie wpłat: {e}')
        con.execute('SAVEPOINT klienci')
        try:
            raport['klienci'] = klienci.policz(con, wpisy)
            con.execute('RELEASE klienci')
        except Exception as e:
            con.execute('ROLLBACK TO klienci')
            con.execute('RELEASE klienci')
            raport['bledy'].append(f'Klienci i koszty: {e}')
        for nazwa, krok in (('budzet', lambda: budzet.zbuduj(con, wpisy)), ('laczenie', lambda: laczenie.policz(con))):
            con.execute(f'SAVEPOINT {nazwa}')
            try:
                raport[nazwa] = krok()
                con.execute(f'RELEASE {nazwa}')
            except Exception as e:
                con.execute(f'ROLLBACK TO {nazwa}')
                con.execute(f'RELEASE {nazwa}')
                raport['bledy'].append(f'{"Budżet" if nazwa == "budzet" else "Łączenie planów"}: {e}')
        if (raport.get('budzet') or {}).get('blad'):
            raport['bledy'].append(f"Kopia z BS: {raport['budzet']['blad']}")
        for k, v in (('odbudowa', teraz()), ('odcisk', odcisk_zrodel()), ('mac', konfig.nazwa_maca()),
                     ('zmian', str(len(wpisy))), ('bledy', '\n'.join(raport['bledy']))):
            con.execute('INSERT INTO meta VALUES (?,?)', (k, v))
        con.execute('COMMIT')
    finally:
        con.close()
    os.chmod(tymczasowy, 0o600)
    os.replace(tymczasowy, cel)
    return raport
