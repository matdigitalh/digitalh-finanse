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
    naleznosci = podsumowanie_naleznosci(con) if con.execute("SELECT name FROM sqlite_master WHERE name='faktury_stan'").fetchone() else None
    return {'naleznosci': naleznosci, 'meta': meta, 'salda': s, 'gotowka': sum(v['saldo_po'] for k, v in s.items() if k in ('główny', 'online')),
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
    sql = ("SELECT operacje.*, (SELECT GROUP_CONCAT(numer, ', ') FROM dopasowania d WHERE d.operacja_id = operacje.id) AS faktury,"
           ' (SELECT stan FROM wplaty w WHERE w.operacja_id = operacje.id) AS stan_wplaty FROM operacje'
           + (' WHERE ' + ' AND '.join(warunki) if warunki else ''))
    kolumny = {'data_ksiegowania', 'kwota', 'kontrahent', 'rachunek'}
    porzadek = f"{sortuj if sortuj in kolumny else 'data_ksiegowania'} {'DESC' if malejaco else 'ASC'}, data_pliku DESC, wiersz"
    wynik = _strona(sql, params, strona, ile, con, porzadek)
    suma = con.execute(f'SELECT COALESCE(SUM(CASE WHEN kwota>0 THEN kwota END),0), COALESCE(SUM(CASE WHEN kwota<0 THEN kwota END),0)'
                       f' FROM ({sql})', params).fetchone()
    wynik['wplywy'], wynik['obciazenia'] = suma[0], suma[1]
    return wynik


def faktury(con, status=None, q=None, od=None, do=None, strona=1, ile=STRONA, bank=None):
    warunki, params = [], []
    if status:
        warunki.append('status = ?'); params.append(status)
    if od:
        warunki.append('data_wystawienia >= ?'); params.append(od)
    if do:
        warunki.append('data_wystawienia <= ?'); params.append(do)
    if q:
        warunki.append("(f.numer || ' ' || nabywca || ' ' || nip || ' ' || ksef) LIKE ?"); params.append(f'%{q}%')
    if bank:
        warunki.append('s.stan = ?'); params.append(bank)
    sql = ('SELECT f.*, (SELECT GROUP_CONCAT(nazwa, ' + "' | '" + ') FROM faktury_pozycje p WHERE p.numer=f.numer) AS pozycje,'
           ' s.stan AS stan_bank, s.pozostalo, s.zaplacono, s.dni_po_terminie, s.ostatnia_wplata,'
           " (SELECT GROUP_CONCAT(o.data_ksiegowania || ' ' || d.kwota, '; ') FROM dopasowania d JOIN operacje o ON o.id = d.operacja_id"
           '  WHERE d.numer = f.numer) AS wplaty'
           ' FROM faktury f LEFT JOIN faktury_stan s USING(numer)' + (' WHERE ' + ' AND '.join(warunki) if warunki else ''))
    wynik = _strona(sql, params, strona, ile, con, 'data_wystawienia DESC, f.numer DESC')
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


# ---------- Etap 2: należności, dopasowania, weryfikacja ----------

PRZEDZIALY = ['przed terminem', '1–30 dni', '31–60 dni', '61–90 dni', 'ponad 90 dni']


def dzien_stanu(con) -> str:
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone()
    return r[0] if r else ''


def podsumowanie_naleznosci(con) -> dict:
    """Kafle: razem do zapłaty, po terminie, wiekowanie, liczniki do połączenia i weryfikacji."""
    przedzialy = {p: [0, 0] for p in PRZEDZIALY}
    for r in con.execute("SELECT przedzial, COUNT(*), SUM(pozostalo) FROM faktury_stan WHERE pozostalo > 0 GROUP BY przedzial"):
        przedzialy[r[0]] = [r[1], r[2]]
    po_terminie = [dict(r) for r in con.execute(
        'SELECT f.nabywca, COUNT(*) AS faktur, SUM(s.pozostalo) AS kwota, MAX(s.dni_po_terminie) AS najstarsza'
        ' FROM faktury_stan s JOIN faktury f USING(numer) WHERE s.pozostalo > 0 AND s.dni_po_terminie > 0'
        ' GROUP BY f.nabywca ORDER BY kwota DESC')]
    return {'dzien_stanu': dzien_stanu(con), 'przedzialy': przedzialy,
            'razem': sum(v[1] for v in przedzialy.values()),
            'po_terminie': sum(v[1] for p, v in przedzialy.items() if p != 'przed terminem'),
            'nabywcy_po_terminie': po_terminie,
            'do_polaczenia': con.execute("SELECT COUNT(*) FROM wplaty WHERE stan='nieznana'").fetchone()[0],
            'do_weryfikacji': len(do_weryfikacji(con))}


def naleznosci(con, przedzial=None, po_terminie=None, q=None, strona=1, ile=STRONA):
    warunki, params = ['s.pozostalo > 0'], []
    if przedzial:
        warunki.append('s.przedzial = ?'); params.append(przedzial)
    if po_terminie:
        warunki.append('s.dni_po_terminie > 0')
    if q:
        warunki.append("(f.numer || ' ' || f.nabywca || ' ' || f.nip) LIKE ?"); params.append(f'%{q}%')
    sql = ('SELECT f.*, s.naleznosc, s.korekty, s.zaplacono, s.pozostalo, s.stan AS stan_bank, s.dni_po_terminie,'
           ' s.przedzial, s.ostatnia_wplata FROM faktury_stan s JOIN faktury f USING(numer) WHERE ' + ' AND '.join(warunki))
    wynik = _strona(sql, params, strona, ile, con, 'dni_po_terminie DESC, termin, numer')
    wynik['pozostalo'] = con.execute(f'SELECT COALESCE(SUM(pozostalo),0) FROM ({sql})', params).fetchone()[0]
    wynik['dzien_stanu'] = dzien_stanu(con)
    return wynik


def wplaty(con, stan='nieznana', q=None, strona=1, ile=STRONA):
    """Wpłaty od klientów z ich stanem dopasowania (Do połączenia)."""
    warunki, params = ['w.stan = ?'], [stan if stan in ('nieznana', 'sprzed_eksportu', 'bez_faktury', 'dopasowana') else 'nieznana']
    if q:
        warunki.append("(o.kontrahent || ' ' || o.tytul || ' ' || o.opis) LIKE ?"); params.append(f'%{q}%')
    sql = ('SELECT o.*, w.stan, w.pewnosc, w.nadplata, w.uwaga, w.podpowiedz, w.wpis,'
           " (SELECT GROUP_CONCAT(numer, ', ') FROM dopasowania d WHERE d.operacja_id = o.id) AS faktury"
           ' FROM wplaty w JOIN operacje o ON o.id = w.operacja_id WHERE ' + ' AND '.join(warunki))
    wynik = _strona(sql, params, strona, ile, con, 'data_ksiegowania DESC, o.id DESC')
    wynik['suma'] = con.execute(f'SELECT COALESCE(SUM(kwota),0) FROM ({sql})', params).fetchone()[0]
    wynik['liczniki'] = {r[0]: r[1] for r in con.execute('SELECT stan, COUNT(*) FROM wplaty GROUP BY stan')}
    return wynik


def wplata(con, operacja_id) -> dict:
    """Karta wpłaty: operacja, jej dopasowania i otwarte faktury do ręcznego połączenia."""
    o = con.execute('SELECT o.*, w.stan, w.pewnosc, w.nadplata, w.uwaga, w.podpowiedz, w.wpis FROM operacje o'
                    ' JOIN wplaty w ON w.operacja_id = o.id WHERE o.id = ?', (int(operacja_id),)).fetchone()
    if not o:
        raise ValueError('nie ma takiej wpłaty')
    dop = [dict(r) for r in con.execute(
        'SELECT d.*, f.nabywca, f.brutto, f.data_wystawienia FROM dopasowania d JOIN faktury f USING(numer)'
        ' WHERE d.operacja_id = ? ORDER BY f.data_wystawienia', (o['id'],))]
    # Otwarte faktury: najpierw te, których nabywca dzieli słowo z nazwą płatnika, potem najbliższe datą.
    from .dopasowanie import tokeny
    slowa = tokeny(o['kontrahent'])
    otwarte = []
    for r in con.execute('SELECT f.numer, f.nabywca, f.brutto, f.data_wystawienia, f.termin, s.pozostalo FROM faktury_stan s'
                         ' JOIN faktury f USING(numer) WHERE s.pozostalo > 0'):
        x = dict(r)
        x['podobny'] = bool(slowa & tokeny(x['nabywca']))
        x['rowna_kwota'] = x['pozostalo'] == o['kwota']
        otwarte.append(x)
    otwarte.sort(key=lambda x: (not x['rowna_kwota'], not x['podobny'], abs(_dni(x['data_wystawienia'], o['data_ksiegowania']))))
    return {'operacja': dict(o), 'dopasowania': dop, 'otwarte': otwarte[:40]}


def _dni(a, b):
    from datetime import date
    if not a or not b:
        return 9999
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def do_weryfikacji(con) -> list[dict]:
    """Rzeczy, które wymagają oka Mata. Każda pozycja ma rodzaj, opis i odnośniki do wpłaty lub faktury."""
    lista = []
    for r in con.execute(
            "SELECT o.id, o.klucz, o.data_ksiegowania, o.kwota, o.kontrahent, o.tytul, w.uwaga,"
            " GROUP_CONCAT(d.numer, ', ') AS faktury, GROUP_CONCAT(d.metoda, '; ') AS metody"
            " FROM wplaty w JOIN operacje o ON o.id = w.operacja_id JOIN dopasowania d ON d.operacja_id = o.id"
            " WHERE d.pewnosc = 'prawdopodobne' GROUP BY o.id ORDER BY o.data_ksiegowania DESC"):
        x = dict(r)
        lista.append({'rodzaj': 'prawdopodobne', 'tytul': 'Dopasowanie do potwierdzenia', 'operacja_id': x['id'],
                      'klucz': x['klucz'], 'data': x['data_ksiegowania'], 'kwota': x['kwota'], 'kontrahent': x['kontrahent'],
                      'faktury': x['faktury'], 'opis': ' · '.join(filter(None, [x['metody'].split('; ')[0], x['uwaga'], x['tytul']]))})
    for r in con.execute(
            'SELECT o.id, o.klucz, o.data_ksiegowania, o.kwota, o.kontrahent, o.tytul, w.nadplata,'
            " (SELECT GROUP_CONCAT(numer, ', ') FROM dopasowania d WHERE d.operacja_id = o.id) AS faktury"
            ' FROM wplaty w JOIN operacje o ON o.id = w.operacja_id WHERE w.nadplata > 0 ORDER BY o.data_ksiegowania DESC'):
        x = dict(r)
        lista.append({'rodzaj': 'nadplata', 'tytul': 'Nadpłata albo podwójna wpłata', 'operacja_id': x['id'], 'klucz': x['klucz'],
                      'data': x['data_ksiegowania'], 'kwota': x['nadplata'], 'kontrahent': x['kontrahent'],
                      'faktury': x['faktury'], 'opis': f"wpłata {x['kwota']} gr, faktury już opłacone; {x['tytul']}"})
    for r in con.execute(
            "SELECT f.numer, f.nabywca, f.termin, s.pozostalo, s.dni_po_terminie FROM faktury_stan s JOIN faktury f USING(numer)"
            " WHERE f.status = 'Opłacona' AND s.pozostalo > 0 ORDER BY f.data_wystawienia"):
        x = dict(r)
        lista.append({'rodzaj': 'fakturownia_oplacona', 'tytul': 'W Fakturowni opłacona, w banku brak wpłaty', 'numer': x['numer'],
                      'data': x['termin'], 'kwota': x['pozostalo'], 'kontrahent': x['nabywca'], 'faktury': x['numer'],
                      'opis': 'sprawdź: kompensata, gotówka, inny rachunek albo błędne odhaczenie w Fakturowni'})
    for r in con.execute(
            "SELECT f.numer, f.nabywca, s.ostatnia_wplata, f.brutto FROM faktury_stan s JOIN faktury f USING(numer)"
            " WHERE f.status != 'Opłacona' AND s.stan = 'opłacona' AND f.brutto > 0 ORDER BY f.data_wystawienia"):
        x = dict(r)
        lista.append({'rodzaj': 'do_odhaczenia', 'tytul': 'Zapłacona w banku, w Fakturowni nieodhaczona', 'numer': x['numer'],
                      'data': x['ostatnia_wplata'], 'kwota': x['brutto'], 'kontrahent': x['nabywca'], 'faktury': x['numer'],
                      'opis': 'odhacz w Fakturowni jako opłaconą'})
    return lista
