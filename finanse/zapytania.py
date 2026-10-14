"""Odczyty dla interfejsu. Każdy wiersz niesie źródło (plik, wiersz), żeby każdą liczbę dało się sprawdzić."""
from . import konfig

STRONA = 100


def _strona(sql, params, strona, ile, con, porzadek):
    razem = con.execute(f'SELECT COUNT(*) FROM ({sql})', params).fetchone()[0]
    ile = max(1, min(int(ile or STRONA), 500))
    strona = max(1, int(strona or 1))
    wiersze = [dict(r) for r in con.execute(f'{sql} ORDER BY {porzadek} LIMIT ? OFFSET ?',
                                            [*params, ile, (strona - 1) * ile])]
    return {'razem': razem, 'strona': strona, 'ile': ile, 'wiersze': wiersze}


def salda(con) -> dict:
    """Saldo bieżące per rachunek: najnowsza operacja (plik ING ma najnowsze na górze)."""
    wynik = {}
    for r in con.execute('SELECT DISTINCT rachunek FROM operacje'):
        o = con.execute('SELECT saldo_po, data_ksiegowania, plik, wiersz FROM operacje WHERE rachunek=? AND saldo_po IS NOT NULL'
                        ' ORDER BY data_ksiegowania DESC, data_pliku DESC, wiersz ASC LIMIT 1', (r[0],)).fetchone()
        if o:
            wynik[r[0]] = dict(o)
    return wynik


def stan(con) -> dict:
    meta = {r['klucz']: r['wartosc'] for r in con.execute('SELECT * FROM meta')}
    s = salda(con)
    liczby = {t: con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
              for t in ('operacje', 'faktury', 'zakupy', 'wyniki_biura')}
    zakres = con.execute('SELECT MIN(data_ksiegowania), MAX(data_ksiegowania) FROM operacje').fetchone()
    return {'meta': meta, 'salda': s, 'gotowka': sum(v['saldo_po'] for k, v in s.items() if k in ('główny', 'online')),
            'liczby': liczby, 'bank_od': zakres[0], 'bank_do': zakres[1], 'mac': konfig.nazwa_maca(),
            'bledy': [b for b in meta.get('bledy', '').split('\n') if b]}


def operacje(con, rachunek=None, kierunek=None, wewnetrzne=None, q=None, od=None, do=None, strona=1, ile=STRONA,
             sortuj='data_ksiegowania', malejaco=True):
    warunki, params = [], []
    if rachunek:
        warunki.append('rachunek = ?'); params.append(rachunek)
    if kierunek == 'wplywy':
        warunki.append('kwota > 0')
    elif kierunek == 'obciazenia':
        warunki.append('kwota < 0')
    if wewnetrzne == 'bez':
        warunki.append('wewnetrzna = 0')
    elif wewnetrzne == 'tylko':
        warunki.append('wewnetrzna = 1')
    if od:
        warunki.append('data_ksiegowania >= ?'); params.append(od)
    if do:
        warunki.append('data_ksiegowania <= ?'); params.append(do)
    if q:
        warunki.append("(kontrahent || ' ' || tytul || ' ' || opis) LIKE ?"); params.append(f'%{q}%')
    sql = 'SELECT * FROM operacje' + (' WHERE ' + ' AND '.join(warunki) if warunki else '')
    kolumny = {'data_ksiegowania', 'kwota', 'kontrahent', 'rachunek'}
    porzadek = f"{sortuj if sortuj in kolumny else 'data_ksiegowania'} {'DESC' if malejaco else 'ASC'}, data_pliku DESC, wiersz"
    wynik = _strona(sql, params, strona, ile, con, porzadek)
    suma = con.execute(f'SELECT COALESCE(SUM(CASE WHEN kwota>0 THEN kwota END),0), COALESCE(SUM(CASE WHEN kwota<0 THEN kwota END),0)'
                       f' FROM ({sql})', params).fetchone()
    wynik['wplywy'], wynik['obciazenia'] = suma[0], suma[1]
    return wynik


def faktury(con, status=None, q=None, od=None, do=None, strona=1, ile=STRONA):
    warunki, params = [], []
    if status:
        warunki.append('status = ?'); params.append(status)
    if od:
        warunki.append('data_wystawienia >= ?'); params.append(od)
    if do:
        warunki.append('data_wystawienia <= ?'); params.append(do)
    if q:
        warunki.append("(numer || ' ' || nabywca || ' ' || nip || ' ' || ksef) LIKE ?"); params.append(f'%{q}%')
    sql = ('SELECT f.*, (SELECT GROUP_CONCAT(nazwa, ' + "' | '" + ') FROM faktury_pozycje p WHERE p.numer=f.numer) AS pozycje'
           ' FROM faktury f' + (' WHERE ' + ' AND '.join(warunki) if warunki else ''))
    wynik = _strona(sql, params, strona, ile, con, 'data_wystawienia DESC, numer DESC')
    s = con.execute(f'SELECT COALESCE(SUM(netto),0), COALESCE(SUM(brutto),0) FROM ({sql})', params).fetchone()
    wynik['netto'], wynik['brutto'] = s[0], s[1]
    return wynik


def zakupy(con, rejestr=None, q=None, od=None, do=None, strona=1, ile=STRONA):
    warunki, params = [], []
    if rejestr:
        warunki.append('rejestr = ?'); params.append(rejestr)
    if od:
        warunki.append('data >= ?'); params.append(od)
    if do:
        warunki.append('data <= ?'); params.append(do)
    if q:
        warunki.append("(podmiot || ' ' || nr_dok) LIKE ?"); params.append(f'%{q}%')
    sql = 'SELECT * FROM zakupy' + (' WHERE ' + ' AND '.join(warunki) if warunki else '')
    wynik = _strona(sql, params, strona, ile, con, 'data DESC, nr_ewid DESC')
    wynik['netto'] = con.execute(f'SELECT COALESCE(SUM(netto),0) FROM ({sql})', params).fetchone()[0]
    return wynik


def importy(con):
    return [dict(r) for r in con.execute('SELECT * FROM import_log ORDER BY id')]


def wyniki_biura(con):
    return [dict(r) for r in con.execute('SELECT * FROM wyniki_biura ORDER BY okres DESC, wiersz')]
