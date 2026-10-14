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
    from .klienci import klucz_nabywcy
    for w in wynik['wiersze']:
        w['nabywca_klucz'] = klucz_nabywcy(w)
        k = con.execute('SELECT klient, zrodlo FROM faktury_klient WHERE numer = ?', (w['numer'],)).fetchone()
        w['klient'], w['klient_zrodlo'] = (k[0], k[1]) if k else ('', '')
    s = con.execute(f'SELECT COALESCE(SUM(netto),0), COALESCE(SUM(brutto),0) FROM ({sql})', params).fetchone()
    wynik['netto'], wynik['brutto'] = s[0], s[1]
    return wynik


def zakupy(con, rejestr=None, q=None, od=None, do=None, strona=1, ile=STRONA, stan=None):
    warunki, params = [], []
    if rejestr:
        warunki.append('z.rejestr = ?'); params.append(rejestr)
    if od:
        warunki.append('z.data >= ?'); params.append(od)
    if do:
        warunki.append('z.data <= ?'); params.append(do)
    if q:
        warunki.append("(z.podmiot || ' ' || z.nr_dok) LIKE ?"); params.append(f'%{q}%')
    if stan:
        warunki.append('s.stan = ?'); params.append(stan)
    sql = ('SELECT z.*, s.stan, o.data_ksiegowania AS data_platnosci, o.kwota AS kwota_platnosci FROM zakupy z'
           ' LEFT JOIN zakupy_stan s USING(nr_ewid) LEFT JOIN operacje o ON o.id = s.operacja_id'
           + (' WHERE ' + ' AND '.join(warunki) if warunki else ''))
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
    warunki, params = ['w.stan = ?'], [stan if stan in ('nieznana', 'sprzed_eksportu', 'bez_faktury', 'dopasowana', 'zwrot_zakupu') else 'nieznana']
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
    # Korekta w tytule wpłaty, a faktura wisi na różnicy: podpowiedź korekty ręcznej (eksport bez korekt).
    z_korekta = set()
    for r in con.execute(
            "SELECT f.numer, f.nabywca, s.pozostalo, o.data_ksiegowania, o.tytul FROM faktury_stan s JOIN faktury f USING(numer)"
            " JOIN dopasowania d ON d.numer = f.numer JOIN operacje o ON o.id = d.operacja_id"
            " WHERE s.pozostalo > 0 AND (o.tytul LIKE '%korekt%' OR o.tytul LIKE '%FK2%')"):
        x = dict(r)
        import re
        m = re.search(r'F\s*K\s*(\d{4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,3})', x['tytul'] or '', re.I)
        nr = f'FK{m.group(1)}/{int(m.group(2)):02d}/{m.group(3)}' if m else ''
        z_korekta.add(x['numer'])
        lista.append({'rodzaj': 'korekta_w_tytule', 'tytul': 'Korekta w tytule wpłaty, brak jej w eksporcie', 'numer': x['numer'],
                      'data': x['data_ksiegowania'], 'kwota': x['pozostalo'], 'kontrahent': x['nabywca'], 'faktury': x['numer'],
                      'korekta': nr, 'opis': f"w tytule: {x['tytul']}; dodaj korektę {nr or ''} na {x['pozostalo']} gr".strip()})
    for r in con.execute(
            "SELECT f.numer, f.nabywca, f.termin, s.pozostalo, s.dni_po_terminie FROM faktury_stan s JOIN faktury f USING(numer)"
            " WHERE f.status = 'Opłacona' AND s.pozostalo > 0 ORDER BY f.data_wystawienia"):
        x = dict(r)
        if x['numer'] in z_korekta:
            continue
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


# ---------- Etap 3: klienci, wydatki, reguły ----------

KOSZT_SQL = 'CASE WHEN w.dokument = \'dokument\' THEN w.netto_dok ELSE -o.kwota END'


def _rok(rok):
    return str(rok) if rok and str(rok).isdigit() else None


def klienci_lista(con, rok=None) -> dict:
    """Foldery klientów jak w Budget Studio: przychód netto, wpłaty, należność, koszty klienta, marża wstępna.
    Koszt klienta: netto z dokumentu z rejestru, a gdy płatność nie ma dokumentu, kwota z banku (brutto)."""
    rok = _rok(rok)
    filtr_f = " AND substr(COALESCE(f.data_sprzedazy, f.data_wystawienia), 1, 4) = ?" if rok else ''
    filtr_o = " AND substr(o.data_ksiegowania, 1, 4) = ?" if rok else ''
    p = [rok] if rok else []
    k = {}
    for r in con.execute('SELECT fk.klient, COUNT(*) AS faktur, SUM(f.netto) AS przychod FROM faktury f'
                         ' JOIN faktury_klient fk USING(numer) WHERE 1=1' + filtr_f + ' GROUP BY fk.klient', p):
        k[r['klient']] = {'klient': r['klient'], 'faktur': r['faktur'], 'przychod': r['przychod'] or 0, 'wplaty': 0,
                          'naleznosc': 0, 'po_terminie': 0, 'koszty': 0, 'koszty_bez_dok': 0, 'wydatkow': 0}
    for r in con.execute('SELECT fk.klient, SUM(s.zaplacono) AS wp, SUM(s.pozostalo) AS nal,'
                         ' SUM(CASE WHEN s.dni_po_terminie > 0 THEN s.pozostalo ELSE 0 END) AS po FROM faktury_stan s'
                         ' JOIN faktury_klient fk USING(numer) JOIN faktury f USING(numer) WHERE 1=1' + filtr_f + ' GROUP BY fk.klient', p):
        if r['klient'] in k:
            k[r['klient']].update(wplaty=r['wp'] or 0, naleznosc=r['nal'] or 0, po_terminie=r['po'] or 0)
    for r in con.execute(f"SELECT w.klient, COUNT(*) AS ile, SUM({KOSZT_SQL}) AS koszt,"
                         " SUM(CASE WHEN w.dokument != 'dokument' THEN -o.kwota ELSE 0 END) AS bez FROM wydatki w"
                         " JOIN operacje o ON o.id = w.operacja_id WHERE w.rodzaj = 'przenoszony' AND w.klient != ''"
                         + filtr_o + ' GROUP BY w.klient', p):
        x = k.setdefault(r['klient'], {'klient': r['klient'], 'faktur': 0, 'przychod': 0, 'wplaty': 0, 'naleznosc': 0,
                                       'po_terminie': 0})
        x.update(koszty=r['koszt'] or 0, koszty_bez_dok=r['bez'] or 0, wydatkow=r['ile'])
    lista = sorted(k.values(), key=lambda x: -x['przychod'])
    for x in lista:
        x['marza'] = x['przychod'] - x.get('koszty', 0)
        x['marza_proc'] = round(100 * x['marza'] / x['przychod'], 1) if x['przychod'] > 0 else None
    lata = [r[0] for r in con.execute("SELECT DISTINCT substr(COALESCE(data_sprzedazy, data_wystawienia), 1, 4) FROM faktury ORDER BY 1 DESC")]
    bez_klienta = con.execute(f"SELECT COUNT(*), COALESCE(SUM({KOSZT_SQL}), 0) FROM wydatki w JOIN operacje o ON o.id = w.operacja_id"
                              " WHERE w.rodzaj = 'przenoszony' AND w.klient = ''" + filtr_o, p).fetchone()
    return {'klienci': lista, 'rok': rok, 'lata': lata, 'przenoszone_bez_klienta': {'ile': bez_klienta[0], 'kwota': bez_klienta[1]}}


def klient(con, nazwa, rok=None) -> dict:
    rok = _rok(rok)
    miesiace = {}
    faktury = [dict(r) for r in con.execute(
        'SELECT f.numer, f.nabywca, f.nip, f.netto, f.brutto, f.data_wystawienia, f.data_sprzedazy, fk.zrodlo, s.stan, s.pozostalo,'
        ' s.dni_po_terminie FROM faktury f JOIN faktury_klient fk USING(numer) LEFT JOIN faktury_stan s USING(numer)'
        ' WHERE fk.klient = ? ORDER BY f.data_wystawienia DESC', (nazwa,))]
    for f in faktury:
        m = (f['data_sprzedazy'] or f['data_wystawienia'] or '')[:7]
        if not rok or m.startswith(rok):
            miesiace.setdefault(m, {'przychod': 0, 'koszty': 0})['przychod'] += f['netto']
    koszty = [dict(r) for r in con.execute(
        f"SELECT o.id, o.data_ksiegowania, o.kwota, o.kontrahent, o.tytul, w.dokument, w.netto_dok, w.zrodlo, {KOSZT_SQL} AS koszt"
        " FROM wydatki w JOIN operacje o ON o.id = w.operacja_id WHERE w.rodzaj = 'przenoszony' AND w.klient = ?"
        ' ORDER BY o.data_ksiegowania DESC', (nazwa,))]
    for x in koszty:
        m = x['data_ksiegowania'][:7]
        if not rok or m.startswith(rok):
            miesiace.setdefault(m, {'przychod': 0, 'koszty': 0})['koszty'] += x['koszt'] or 0
    if rok:
        faktury = [f for f in faktury if (f['data_sprzedazy'] or f['data_wystawienia'] or '').startswith(rok)]
        koszty = [x for x in koszty if x['data_ksiegowania'].startswith(rok)]
    return {'klient': nazwa, 'rok': rok, 'miesiace': [{'miesiac': m, **v} for m, v in sorted(miesiace.items())],
            'faktury': faktury, 'koszty': koszty}


def wydatki(con, rodzaj=None, klient=None, dokument=None, zrodlo=None, q=None, od=None, do=None, strona=1, ile=STRONA):
    warunki, params = [], []
    for kol, v in (('w.rodzaj', rodzaj), ('w.dokument', dokument)):
        if v:
            warunki.append(f'{kol} = ?'); params.append(v)
    if klient is not None and klient != '':
        warunki.append('w.klient = ?'); params.append('' if klient == '-' else klient)
    if zrodlo == 'mat':
        warunki.append("w.zrodlo LIKE '%Mata%'")
    elif zrodlo == 'bs':
        warunki.append("w.zrodlo LIKE 'Budget Studio%'")
    elif zrodlo == 'brak':
        warunki.append("w.zrodlo = ''")
    if od:
        warunki.append('o.data_ksiegowania >= ?'); params.append(od)
    if do:
        warunki.append('o.data_ksiegowania <= ?'); params.append(do)
    if q:
        warunki.append("(o.kontrahent || ' ' || o.tytul || ' ' || o.opis) LIKE ?"); params.append(f'%{q}%')
    sql = ("SELECT o.*, w.rodzaj, w.klient, w.zrodlo, w.wpis, w.kontrahent_klucz, w.dokument, w.netto_dok,"
           " (SELECT GROUP_CONCAT(z.podmiot || ' ' || z.nr_dok, '; ') FROM wydatki_dok d JOIN zakupy z USING(nr_ewid)"
           '  WHERE d.operacja_id = o.id) AS dokumenty FROM wydatki w JOIN operacje o ON o.id = w.operacja_id'
           + (' WHERE ' + ' AND '.join(warunki) if warunki else ''))
    wynik = _strona(sql, params, strona, ile, con, 'data_ksiegowania DESC, o.id DESC')
    wynik['suma'] = con.execute(f'SELECT COALESCE(SUM(kwota), 0) FROM ({sql})', params).fetchone()[0]
    wynik['klienci'] = [r[0] for r in con.execute(
        "SELECT klient FROM faktury_klient UNION SELECT klient FROM wydatki WHERE klient != '' ORDER BY 1")]
    wynik['podsumowanie'] = [dict(r) for r in con.execute(
        'SELECT w.rodzaj, COUNT(*) AS ile, SUM(o.kwota) AS kwota FROM wydatki w JOIN operacje o ON o.id = w.operacja_id'
        ' GROUP BY w.rodzaj ORDER BY kwota')]
    return wynik


def reguly(con) -> list[dict]:
    return [dict(r) for r in con.execute('SELECT * FROM reguly ORDER BY typ, klucz')]


def historia_salda(con) -> list[dict]:
    """Saldo gotówki (główny + online) na koniec każdego dnia, z przeniesieniem salda na dni bez operacji."""
    from datetime import date, timedelta
    na_dzien = {}
    for r in con.execute("SELECT rachunek, data_ksiegowania, saldo_po FROM operacje WHERE rachunek IN ('główny', 'online')"
                         ' AND saldo_po IS NOT NULL ORDER BY data_ksiegowania, data_pliku DESC, wiersz ASC'):
        na_dzien.setdefault((r[0], r[1]), r[2])   # pierwszy wiersz dnia w pliku ING = ostatnia operacja dnia
    if not na_dzien:
        return []
    dni = sorted({d for _, d in na_dzien})
    d, koniec = date.fromisoformat(dni[0]), date.fromisoformat(dni[-1])
    ostatnie, wynik = {}, []
    for rach in ('główny', 'online'):   # saldo przed pierwszą operacją rachunku = saldo po niej minus jej kwota
        r = con.execute('SELECT saldo_po - kwota FROM operacje WHERE rachunek = ? AND saldo_po IS NOT NULL'
                        ' ORDER BY data_ksiegowania, data_pliku DESC, wiersz DESC LIMIT 1', (rach,)).fetchone()
        if r:
            ostatnie[rach] = r[0]
    while d <= koniec:
        s = d.isoformat()
        for rach in ('główny', 'online'):
            if (rach, s) in na_dzien:
                ostatnie[rach] = na_dzien[(rach, s)]
        wynik.append({'x': s, 'y': sum(ostatnie.values()), 'glowny': ostatnie.get('główny', 0), 'online': ostatnie.get('online', 0)})
        d += timedelta(days=1)
    return wynik


def konta_reklamowe(con) -> list[dict]:
    return [dict(r) for r in con.execute('SELECT * FROM konta_reklamowe ORDER BY klient IS NOT NULL, suma DESC')]


def nieprzypisane_grupy(con) -> list[dict]:
    """Nieprzypisane wydatki zgrupowane po kontrahencie: jedna reguła załatwia całą grupę."""
    return [dict(r) for r in con.execute(
        "SELECT w.kontrahent_klucz AS klucz, COUNT(*) AS ile, -SUM(o.kwota) AS kwota, MIN(o.kontrahent) AS przyklad,"
        " MAX(o.data_ksiegowania) AS ostatnia, MAX(w.konto) AS konto FROM wydatki w JOIN operacje o ON o.id = w.operacja_id"
        " WHERE w.rodzaj = 'nieprzypisany' GROUP BY w.kontrahent_klucz ORDER BY kwota DESC")]


def korekty_reczne(con) -> list[dict]:
    return [dict(r) for r in con.execute('SELECT * FROM korekty_reczne ORDER BY faktura')]
