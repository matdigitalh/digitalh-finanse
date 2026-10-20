"""Odczyty budżetu dla interfejsu: drzewo arkuszy, widok arkusza z miesiącami, karta płatności, listy jak w BS,
rozjazdy BS ↔ bank ↔ Fakturownia, historia zmian planów, ustawienia."""
import json
from datetime import date, timedelta

from . import plan as reguly
from .zapytania import _strona

ETAP_KOLOR = {'Opłacona': 'oplacona', 'Planowana': 'planowana', 'Po terminie': 'po-terminie', 'Wystawiona': 'wystawiona',
              'Częściowo opłacona': 'czesciowo', 'Opłacona wg BS': 'wg-bs', 'Nieaktualna': 'nieaktualna'}


def _dzien_stanu(con) -> str:  # „dziś” w logice = ostatni dzień księgowania w ING
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone()
    return r[0] if r and r[0] else date.today().isoformat()


def planowanie(con) -> bool:
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='planowanie'").fetchone()
    return bool(r) and r[0] == 'tak'


def _miesiace(od: str, do: str) -> list[str]:
    wynik, m = [], od
    while m <= do and len(wynik) < 60:
        wynik.append(m)
        r, mm = int(m[:4]), int(m[5:7])
        m = f'{r + (mm == 12)}-{1 if mm == 12 else mm + 1:02d}'
    return wynik


def drzewo(con) -> dict:
    arkusze = [dict(r) for r in con.execute(
        'SELECT a.*, COUNT(DISTINCT w.id) AS wierszy,'
        ' COALESCE(SUM(p.netto * p.rodzaj), 0) AS saldo,'   # jak w BS: razem z nieaktualnymi
        " SUM(CASE WHEN s.etap = 'Po terminie' THEN 1 ELSE 0 END) AS po_terminie"
        ' FROM bud_arkusz a LEFT JOIN bud_wiersz w ON w.arkusz = a.id LEFT JOIN bud_platnosc p ON p.wiersz = w.id'
        ' LEFT JOIN bud_stan s ON s.platnosc = p.id GROUP BY a.id ORDER BY a.folder, a.kategoria, a.nazwa')]
    foldery = {}
    for a in arkusze:
        f = foldery.setdefault(a['folder'], {'folder': a['folder'], 'kategorie': {}, 'saldo': 0})
        f['kategorie'].setdefault(a['kategoria'], []).append(a)
        f['saldo'] += a['saldo']
    foldery = _wg_struktury(con, foldery)   # pakiet 4: kolejność folderów i kategorii z Biblioteki
    zr = con.execute("SELECT wartosc FROM meta WHERE klucz='import_bs'").fetchone()
    kopia = con.execute("SELECT wartosc FROM meta WHERE klucz='kopia_bs'").fetchone()
    imp_wl = con.execute("SELECT wartosc FROM meta WHERE klucz='import_bs_wl'").fetchone()
    return {'foldery': list(foldery.values()), 'import': json.loads(zr[0]) if zr else None, 'planowanie': planowanie(con),
            'osierocone': osierocone_ile(con), 'kopia_bs': json.loads(kopia[0]) if kopia else None,
            'import_bs': not imp_wl or imp_wl[0] != 'nie'}


def _wg_struktury(con, foldery: dict) -> dict:
    """Foldery i kategorie drzewa w kolejności ustawionej w Bibliotece (pakiet 4); nieznane na końcu, alfabetycznie."""
    from .biblioteka import kolejnosc_folderow
    kol = kolejnosc_folderow(con)
    poz_f = {}
    for (f, _), (kf, _) in kol.items():
        poz_f[f] = min(kf, poz_f.get(f, kf))
    wynik = {}
    for nazwa in sorted(foldery, key=lambda f: (poz_f.get(f, 10 ** 6), f)):
        f = foldery[nazwa]
        f['kategorie'] = dict(sorted(f['kategorie'].items(), key=lambda kv: (kol.get((nazwa, kv[0]), (0, 10 ** 6))[1], kv[0])))
        wynik[nazwa] = f
    return wynik


def osierocone_ile(con) -> int:
    return con.execute('SELECT COUNT(*) FROM bud_osierocone').fetchone()[0]


def arkusz(con, aid: str) -> dict:
    a = con.execute('SELECT * FROM bud_arkusz WHERE id = ?', (aid,)).fetchone()
    if not a:
        raise ValueError('nie ma takiego arkusza')
    a = dict(a)
    miesiace = _miesiace(a['od'], a['do'])
    wiersze = [dict(r) for r in con.execute(
        "SELECT w.*, EXISTS (SELECT 1 FROM bud_platnosc p WHERE p.wiersz = w.id AND p.typ != 'plan') AS ma_rzeczywiste"
        ' FROM bud_wiersz w WHERE w.arkusz = ? ORDER BY w.kolejnosc, w.id', (aid,))]
    kwoty_komorek = {(r['wiersz'], r['miesiac']): r['kwota'] for r in con.execute(
        'SELECT k.* FROM bud_komorka k JOIN bud_wiersz w ON w.id = k.wiersz WHERE w.arkusz = ?', (aid,))}
    komorki = {}
    poza_zakresem = {}   # miesiące płatności spoza zakresu arkusza (do kalendarza „Zmodyfikuj czas trwania”)
    for r in con.execute('SELECT p.id, p.wiersz, p.miesiac, p.netto, p.brutto, p.rodzaj, p.typ, p.aktualna, p.ukryty, p.zrodlo, s.etap, s.aktualnosc'
                         ' FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz LEFT JOIN bud_stan s ON s.platnosc = p.id'
                         ' WHERE w.arkusz = ? ORDER BY p.id', (aid,)):
        if not a['od'] <= r['miesiac'] <= a['do']:
            x = poza_zakresem.setdefault(r['miesiac'], {'rzeczywiste': 0, 'plany': 0})
            x['rzeczywiste' if r['typ'] != 'plan' else 'plany'] += 1
        k = komorki.setdefault((r['wiersz'], r['miesiac']), {'netto': 0, 'platnosci': [], 'etapy': [], 'kwoty': {}, 'rzeczywiste': 0,
                                                              'nieaktualne': 0, 'plany': 0, 'oplacone': 0, 'z_listy': 0})
        k['z_listy'] += r['zrodlo'] == 'lista płac'   # kwota z listy płac od biura (zastąpiła BS albo plan)
        k['rzeczywiste'] += r['typ'] != 'plan'   # do koloru komórki jak w BS: tło planów, kropka nieaktualnych
        k['plany'] += r['typ'] == 'plan' and not r['ukryty'] and bool(r['aktualna'])
        k['oplacone'] += r['etap'] == 'Opłacona'
        k['nieaktualne'] += bool(r['aktualna'] and r['aktualnosc'] == 'Nieaktualna')
        if r['aktualna']:
            k['netto'] += r['netto'] * r['rodzaj']
            k['kwoty'][r['id']] = r['netto']   # do akcji na wierszach (kopie, podział) liczonych po stronie serwera
        k['platnosci'].append(r['id'])
        k['etapy'].append(r['etap'])
    for w in wiersze:
        w['komorki'] = {}
        for m in miesiace:
            k = komorki.get((w['id'], m))
            if k:
                etapy = set(k['etapy'])
                stan = ('po-terminie' if 'Po terminie' in etapy else 'oplacona' if etapy <= {'Opłacona', 'Nieaktualna'}
                        else 'wg-bs' if 'Opłacona wg BS' in etapy else 'planowana')
                w['komorki'][m] = {'netto': k['netto'], 'platnosci': k['platnosci'], 'kwoty': k['kwoty'], 'stan': stan,
                                   'rzeczywiste': k['rzeczywiste'], 'nieaktualne': k['nieaktualne'], 'plany': k['plany'],
                                   'oplacone': k['oplacone'], 'z_listy': k['z_listy'],
                                   'kwota': kwoty_komorek.get((w['id'], m))}   # kwota wpisana w apce (plany z niej liczone)
        w['plan'] = json.loads(w['plan']) if w['plan'] else None
        w['proporcje'] = json.loads(w['proporcje']) if w.get('proporcje') else None
        w['ma_rzeczywiste'] = bool(w['ma_rzeczywiste'])
        w['dzien_opis'] = 'tydzień (worek)' if w['podstawa'] in reguly.WOREK else reguly.regula_opis(w['dzien_wystawienia'])
        w['ksiegowane'], w['w_cashflow'], w['split'] = bool(w['ksiegowane']), bool(w['w_cashflow']), bool(w['split'])
        w['stawka'] = _stawka(w['stawka_vat'])
        w['dni'] = reguly.dni_na_platnosc(w['dni_na_platnosc'])
    podsumowanie = []
    narast = 0
    for m in miesiace:
        wp = sum(w['komorki'][m]['netto'] for w in wiersze if m in w['komorki'] and w['komorki'][m]['netto'] > 0)
        ob = sum(w['komorki'][m]['netto'] for w in wiersze if m in w['komorki'] and w['komorki'][m]['netto'] < 0)
        narast += wp + ob
        podsumowanie.append({'miesiac': m, 'wplywy': wp, 'obciazenia': ob, 'saldo': wp + ob, 'narastajaco': narast})
    inne = [dict(r) for r in con.execute('SELECT id, folder, kategoria, nazwa, od, do FROM bud_arkusz ORDER BY folder, nazwa')]
    systemowy = a.get('zrodlo') == 'system'   # Opłaty urzędowe (pakiet 8): plany liczy apka, arkusz tylko do odczytu
    return {'arkusz': a, 'miesiace': miesiace, 'wiersze': wiersze, 'podsumowanie': podsumowanie,
            'planowanie': planowanie(con) and not systemowy, 'systemowy': systemowy,
            'arkusze': inne, 'podstawy': reguly.PODSTAWY_WIERSZA, 'slowniki': slowniki(con), 'wzorce': wzorce_kontrahentow(con, aid),
            'poza_zakresem': poza_zakresem, 'limit_wierszy': 1000,
            'umowa': _umowa_arkusza(con, aid)}   # pakiet 9: umowa klienta, brak umowy, plany po końcu umowy


def _umowa_arkusza(con, aid: str) -> dict:
    from .umowy import dla_arkusza
    return dla_arkusza(con, aid)


def _stawka(s):
    from .budzet import stawka_proc
    return stawka_proc(s)


def slowniki(con) -> dict:
    """Wartości do list wyboru w arkuszu (kontrahent, sekcja, przedmiot, metoda) z Biblioteki (pakiet 4), plus wpisy
    domyślne dla nowych wierszy i struktura folderów (także pustych) do wyboru miejsca arkusza."""
    from .biblioteka import dla_arkusza
    return dla_arkusza(con)['slowniki']


def wzorce_kontrahentow(con, aid: str) -> dict:
    """Ustawienia domyślne kontrahentów z Biblioteki (A-KOL-04, pakiet 4), do podglądu nowego wiersza w arkuszu; nowy
    wiersz uzupełnia i tak serwer (biblioteka.uzupelnij_wiersz)."""
    from .biblioteka import dla_arkusza
    return dla_arkusza(con)['wzorce']


def komorka(con, wid: str, m: str) -> dict:
    """Karta komórki (A-ARK-13, B-LIS-13): wszystkie płatności komórki (plany i rzeczywiste, bez limitu), kwota komórki,
    ustawienia wiersza i cechy każdej płatności różne od wiersza (pomarańczowe podświetlenie)."""
    w = con.execute('SELECT * FROM bud_wiersz WHERE id = ?', (wid,)).fetchone()
    if not w:
        raise ValueError('nie ma takiego wiersza')
    ids = [r[0] for r in con.execute("SELECT id FROM bud_platnosc WHERE wiersz = ? AND miesiac = ?"
                                     " ORDER BY typ = 'plan', COALESCE(wystawienie, ''), id", (wid, m))]
    platnosci = [platnosc(con, pid) for pid in ids]
    k = con.execute('SELECT kwota FROM bud_komorka WHERE wiersz = ? AND miesiac = ?', (wid, m)).fetchone()
    a = dict(con.execute('SELECT * FROM bud_arkusz WHERE id = ?', (w['arkusz'],)).fetchone())
    w = dict(w)
    w['dzien_opis'] = 'tydzień (worek)' if w['podstawa'] in reguly.WOREK else reguly.regula_opis(w['dzien_wystawienia'])
    w['dni'] = reguly.dni_na_platnosc(w['dni_na_platnosc'])
    w['stawka'] = _stawka(w['stawka_vat'])
    w['ksiegowane'], w['w_cashflow'], w['split'] = bool(w['ksiegowane']), bool(w['w_cashflow']), bool(w['split'])
    w['proporcje'] = json.loads(w['proporcje']) if w.get('proporcje') else None
    rz = [x['platnosc'] for x in platnosci if x['platnosc']['typ'] != 'plan']
    real = con.execute("SELECT wartosc FROM meta WHERE klucz = 'realizacja'").fetchone()
    stan = next((x[2] for x in json.loads(real[0]) if x[0] == wid and x[1] == m), None) if real and real[0] else None
    worek = w['podstawa'] in reguly.WOREK
    plany_tyg = [x['platnosc'] for x in platnosci if x['platnosc']['typ'] == 'plan' and x['platnosc']['aktualna']]
    return {'wiersz': w, 'arkusz': a, 'miesiac': m, 'kwota': k[0] if k else None, 'platnosci': platnosci,
            'rzeczywiste': sum(p['netto'] for p in rz), 'ma_rzeczywiste': bool(rz),
            # pakiet 5: karta worka (podpięte rzeczywiste, niezrealizowane plany tygodniowe, zamknięcie ręczne)
            'worek': ({'zamkniety': stan == 'zamknieta', 'rzeczywistych': len(rz), 'plany': sum(p['netto'] for p in plany_tyg),
                       'planow': len(plany_tyg)} if worek else None),
            'planowanie': planowanie(con) and a.get('zrodlo') != 'system'}


def ostatni(con) -> dict | None:
    """Ostatnia zmiana budżetu, która jeszcze obowiązuje (do „Cofnij” i Cmd+Z)."""
    r = con.execute('SELECT wpis, MAX(czas) AS czas, mac, COUNT(*) AS ile, MIN(op) AS op, GROUP_CONCAT(DISTINCT op) AS ops, MIN(obiekt) AS obiekt'
                    ' FROM bud_historia GROUP BY wpis ORDER BY czas DESC LIMIT 1').fetchone()
    if not r:
        return None
    r = dict(r)
    r['ops'] = sorted({o.replace('seria: ', '') for o in (r['ops'] or '').split(',') if o})
    return r


def platnosc(con, pid: str) -> dict:
    p = con.execute("SELECT p.*, COALESCE(NULLIF(p.kontrahent, ''), w.kontrahent) AS w_kontrahent, w.podstawa, w.komentarz AS w_komentarz,"
                    ' a.nazwa AS arkusz, a.folder, a.kategoria, a.id AS arkusz_id, w.przedmiot, w.sekcja,'
                    ' s.etap, s.zaplacono, s.data_zaplaty, s.termin_efektywny, s.uwaga AS uwaga_stanu, s.etap_wg_bs, s.aktualnosc FROM bud_platnosc p'
                    ' JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz LEFT JOIN bud_stan s ON s.platnosc = p.id'
                    ' WHERE p.id = ?', (pid,)).fetchone()
    if not p:
        raise ValueError('nie ma takiej płatności')
    pow_ = []
    for r in con.execute('SELECT * FROM bud_powiazanie WHERE platnosc = ?', (pid,)):
        x = dict(r)
        if x['typ'] == 'faktura':
            f = con.execute('SELECT f.numer, f.nabywca, f.netto, f.brutto, f.data_wystawienia, s.stan FROM faktury f'
                            ' LEFT JOIN faktury_stan s USING(numer) WHERE f.numer = ?', (x['ref'],)).fetchone()
            x['opis'] = f"{f['numer']} · {f['nabywca']} · netto {f['netto']} gr · {f['stan']}" if f else x['ref']
        elif x['typ'] == 'bank':
            o = con.execute('SELECT data_ksiegowania, kwota, kontrahent, tytul FROM operacje WHERE id = ?', (int(x['ref']),)).fetchone()
            x['opis'] = f"{o['data_ksiegowania']} · {o['kontrahent']} · {o['kwota']} gr · {o['tytul']}" if o else x['ref']
        else:
            z = con.execute('SELECT nr_dok, podmiot, netto, data FROM zakupy WHERE nr_ewid = ?', (x['ref'],)).fetchone()
            x['opis'] = f"{z['nr_dok']} · {z['podmiot']} · {z['data']}" if z else x['ref']
        pow_.append(x)
    historia = [dict(r) for r in con.execute('SELECT * FROM bud_historia WHERE obiekt = ? OR obiekt = ? OR obiekt = ? ORDER BY czas',
                                             (pid, p['wiersz'], f"{p['wiersz']}:{p['miesiac']}"))]
    p = dict(p)
    p['nadpisane'] = json.loads(p['nadpisane']) if p['nadpisane'] else {}
    p['podstawa_platnosci'] = reguly.ETYKIETY_SKLADOWYCH.get(p['podstawa'], {}).get(p['skladowa'] or '', p['podstawa'])
    w = dict(con.execute('SELECT * FROM bud_wiersz WHERE id = ?', (p['wiersz'],)).fetchone())
    p['odstepstwa'] = reguly.odstepstwa(p, w)   # cechy różne od wiersza: pomarańczowe w karcie (A-ARK-11)
    w['dni'] = reguly.dni_na_platnosc(w['dni_na_platnosc'])
    w['dzien_opis'] = reguly.regula_opis(w['dzien_wystawienia'])
    w['stawka'] = _stawka(w['stawka_vat'])
    k = con.execute('SELECT kwota FROM bud_komorka WHERE wiersz = ? AND miesiac = ?', (p['wiersz'], p['miesiac'])).fetchone()
    return {'platnosc': p, 'wiersz': w, 'kwota_komorki': k[0] if k else None, 'powiazania': pow_, 'historia': historia,
            'planowanie': planowanie(con) and not str(p['wiersz']).startswith('sys:')}


LISTY = {
    'wszystkie': 'Wszystkie płatności',
    'nieoplacone': 'Nadal nieopłacone',
    'niewystawione': 'Nadal niewystawione',
    'po_terminie': 'Po terminie płatności',
    'do_wystawienia': 'Do wystawienia (najbliższe 2 tyg.)',
    'do_zaplacenia': 'Do zapłacenia (najbliższe 2 tyg.)',
    'zaplacone': 'Zapłacone (ostatnie 2 tyg.)',
}


def _warunki_list(dzien: str) -> dict:
    """Warunki SQL list jak w BS (B-LIS-03); daty pochodzą z bazy (dzień stanu), nie od użytkownika."""
    za2 = (date.fromisoformat(dzien) + timedelta(days=14)).isoformat()
    przed2 = (date.fromisoformat(dzien) - timedelta(days=14)).isoformat()
    bez_faktury = "NOT EXISTS (SELECT 1 FROM bud_powiazanie b WHERE b.platnosc = p.id AND b.typ = 'faktura')"
    return {
        'wszystkie': '1=1',
        'nieoplacone': f"p.rodzaj = 1 AND (s.etap IN ('Wystawiona', 'Częściowo opłacona') OR (s.etap = 'Po terminie' AND NOT {bez_faktury}))",
        'niewystawione': f"p.rodzaj = 1 AND p.aktualna = 1 AND {bez_faktury} AND s.etap IN ('Planowana', 'Po terminie') AND p.miesiac <= '{dzien[:7]}'",
        'po_terminie': "s.etap = 'Po terminie'",
        'do_wystawienia': f"p.rodzaj = 1 AND s.etap = 'Planowana' AND {bez_faktury} AND COALESCE(p.wystawienie, s.termin_efektywny) BETWEEN '{dzien}' AND '{za2}'",
        'do_zaplacenia': f"p.rodzaj = -1 AND s.etap IN ('Planowana', 'Po terminie') AND s.termin_efektywny <= '{za2}'",
        'zaplacone': f"s.etap = 'Opłacona' AND s.data_zaplaty BETWEEN '{przed2}' AND '{dzien}'",
    }


def kafle(con) -> dict:
    """Pulpit jak w BS: dla każdej listy (poza „wszystkie”) liczba płatności i suma brutto osobno dla wpływów
    i obciążeń. Te same warunki co listy, więc kafel i lista po kliknięciu pokazują to samo."""
    dzien = _dzien_stanu(con)
    wynik = {}
    for nazwa, warunek in _warunki_list(dzien).items():
        if nazwa == 'wszystkie':
            continue
        r = {1: {'ile': 0, 'kwota': 0}, -1: {'ile': 0, 'kwota': 0}}
        for x in con.execute('SELECT p.rodzaj, COUNT(*), COALESCE(SUM(p.brutto), 0) FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz'
                             f' JOIN bud_arkusz a ON a.id = w.arkusz JOIN bud_stan s ON s.platnosc = p.id WHERE ({warunek}) GROUP BY p.rodzaj'):
            if x[0] in r:
                r[x[0]] = {'ile': x[1], 'kwota': x[2] * x[0]}
        wynik[nazwa] = {'nazwa': LISTY[nazwa], 'wplywy': r[1], 'obciazenia': r[-1]}
    return {'dzien_stanu': dzien, 'listy': wynik}


def lista(con, nazwa='wszystkie', rodzaj=None, q=None, strona=1, ile=100, arkusz=None) -> dict:
    """Listy płatności planu ze stronicowaniem i wyszukiwarką (kontrahent, tytuł, numer dokumentu, arkusz).
    Suma liczona ze wszystkich pozycji listy, nie tylko z widocznej strony. arkusz: tylko płatności tego arkusza."""
    dzien = _dzien_stanu(con)
    warunki = _warunki_list(dzien)[nazwa if nazwa in LISTY else 'wszystkie']
    params = []   # daty w warunkach pochodzą z bazy (dzień stanu), wartości od użytkownika tylko jako parametry
    sql = ("SELECT p.*, s.etap, s.termin_efektywny, s.data_zaplaty, s.uwaga AS uwaga_stanu, s.etap_wg_bs, s.aktualnosc,"
           " COALESCE(NULLIF(p.kontrahent, ''), w.kontrahent) AS w_kontrahent, w.podstawa,"
           ' a.nazwa AS arkusz, a.folder, a.id AS arkusz_id FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz'
           f' JOIN bud_arkusz a ON a.id = w.arkusz JOIN bud_stan s ON s.platnosc = p.id WHERE ({warunki})')
    if rodzaj in ('1', '-1'):
        sql += ' AND p.rodzaj = ?'
        params.append(int(rodzaj))
    if arkusz:
        sql += ' AND a.id = ?'
        params.append(arkusz)
    if q:
        sql += (" AND (COALESCE(NULLIF(p.kontrahent, ''), w.kontrahent, '') || ' ' || COALESCE(p.tytul, '') || ' ' || COALESCE(p.nr_dok, '') || ' '"
                " || COALESCE(p.nr_wewn, '') || ' ' || COALESCE(a.nazwa, '')) LIKE ?")
        params.append(f'%{q}%')
    suma = con.execute(f'SELECT COALESCE(SUM(brutto * rodzaj), 0) FROM ({sql})', params).fetchone()[0]
    wynik = _strona(sql, params, strona, ile, con, 's.termin_efektywny DESC, p.id')
    for x in wynik['wiersze']:   # odbiorca składowej umowy (PIT, ZUS) widoczny w podstawie, kontrahent = osoba
        x['podstawa_platnosci'] = reguly.ETYKIETY_SKLADOWYCH.get(x['podstawa'], {}).get(x.get('skladowa') or '', x['podstawa'])
    return {**wynik, 'lista': nazwa, 'nazwa': LISTY.get(nazwa, LISTY['wszystkie']), 'suma': suma, 'dzien_stanu': dzien, 'listy': LISTY}


def rozjazdy(con) -> list[dict]:
    wynik = []
    for r in con.execute('SELECT * FROM bud_rozjazd ORDER BY rodzaj, ABS(kwota) DESC'):
        x = dict(r)
        if x['ref'] and x['ref'].startswith(('bs:', 'plan:')):
            p = con.execute('SELECT p.miesiac, w.kontrahent, a.nazwa, a.id FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz'
                            ' JOIN bud_arkusz a ON a.id = w.arkusz WHERE p.id = ?', (x['ref'],)).fetchone()
            if p:
                x.update(miesiac=p[0], kontrahent=p[1], arkusz=p[2], arkusz_id=p[3])
        elif x['ref'] and x['ref'].startswith(('komorka:', 'wiersz:')):   # pakiet 6: plan w BS inny niż w apce, wiersz tylko w apce
            wid, m = (x['ref'][8:].rsplit(':', 1) if x['ref'].startswith('komorka:') else (x['ref'][7:], ''))
            w = con.execute('SELECT w.kontrahent, a.nazwa, a.id FROM bud_wiersz w JOIN bud_arkusz a ON a.id = w.arkusz WHERE w.id = ?',
                            (wid,)).fetchone()
            if w:
                x.update(kontrahent=w[0], arkusz=w[1], arkusz_id=w[2], miesiac=m)
        elif x['ref'] and x['ref'].startswith('FV'):
            f = con.execute('SELECT fk.klient, f.data_wystawienia FROM faktury f LEFT JOIN faktury_klient fk USING(numer) WHERE f.numer = ?',
                            (x['ref'],)).fetchone()
            x.update(kontrahent=x['ref'], arkusz=f[0] if f else '', miesiac=(f[1] or '')[:7] if f else '')
        # pakiet 5 (B-LACZ-07): faktura i wydatek bez pozycji w BS dają się połączyć z budżetem (nowy wiersz albo plan)
        dok = None
        if x['rodzaj'] == 'Faktura bez pozycji w BS':
            dok = con.execute('SELECT * FROM bud_laczenie WHERE ref = ?', (f"faktura:{x['ref']}",)).fetchone()
        elif x['rodzaj'] == 'Wydatek z banku bez pozycji w BS' and str(x['ref']).isdigit():
            dok = con.execute('SELECT * FROM bud_laczenie WHERE operacja_id = ? ORDER BY typ = \'operacja\'', (int(x['ref']),)).fetchone()
        if dok and dok['stan'] in ('sprzed', 'do_polaczenia'):
            from .laczenie import nazwa_krotka, NAZWA_ZRODLA
            x['dok'] = {**dict(dok), 'kontrahent_krotko': nazwa_krotka(dok['kontrahent']), 'zrodlo_nazwa': NAZWA_ZRODLA.get(dok['typ'], dok['typ'])}
        wynik.append(x)
    return wynik


def historia(con) -> dict:
    """Zmiany planów (ostatnie 500) i zdarzenia bez obiektu, do których nie ma się już do czego odnieść."""
    return {'zmiany': [dict(r) for r in con.execute('SELECT * FROM bud_historia ORDER BY czas DESC LIMIT 500')],
            'osierocone': [dict(r) for r in con.execute('SELECT * FROM bud_osierocone ORDER BY czas DESC')]}
