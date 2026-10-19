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
    zr = con.execute("SELECT wartosc FROM meta WHERE klucz='import_bs'").fetchone()
    return {'foldery': list(foldery.values()), 'import': json.loads(zr[0]) if zr else None, 'planowanie': planowanie(con),
            'osierocone': osierocone_ile(con)}


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
        ' FROM bud_wiersz w WHERE w.arkusz = ? ORDER BY w.rodzaj DESC, w.kontrahent, w.komentarz', (aid,))]
    kwoty_komorek = {(r['wiersz'], r['miesiac']): r['kwota'] for r in con.execute(
        'SELECT k.* FROM bud_komorka k JOIN bud_wiersz w ON w.id = k.wiersz WHERE w.arkusz = ?', (aid,))}
    komorki = {}
    for r in con.execute('SELECT p.id, p.wiersz, p.miesiac, p.netto, p.brutto, p.rodzaj, p.typ, p.aktualna, s.etap FROM bud_platnosc p'
                         ' JOIN bud_wiersz w ON w.id = p.wiersz LEFT JOIN bud_stan s ON s.platnosc = p.id WHERE w.arkusz = ? ORDER BY p.id', (aid,)):
        k = komorki.setdefault((r['wiersz'], r['miesiac']), {'netto': 0, 'platnosci': [], 'etapy': [], 'kwoty': {}})
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
                                   'kwota': kwoty_komorek.get((w['id'], m))}   # kwota wpisana w apce (plany z niej liczone)
        w['plan'] = json.loads(w['plan']) if w['plan'] else None
        w['proporcje'] = json.loads(w['proporcje']) if w.get('proporcje') else None
        w['ma_rzeczywiste'] = bool(w['ma_rzeczywiste'])
        w['dzien_opis'] = 'tydzień (worek)' if w['podstawa'] in reguly.WOREK else reguly.regula_opis(w['dzien_wystawienia'])
        w['ksiegowane'], w['w_cashflow'], w['split'] = bool(w['ksiegowane']), bool(w['w_cashflow']), bool(w['split'])
    podsumowanie = []
    narast = 0
    for m in miesiace:
        wp = sum(w['komorki'][m]['netto'] for w in wiersze if m in w['komorki'] and w['komorki'][m]['netto'] > 0)
        ob = sum(w['komorki'][m]['netto'] for w in wiersze if m in w['komorki'] and w['komorki'][m]['netto'] < 0)
        narast += wp + ob
        podsumowanie.append({'miesiac': m, 'wplywy': wp, 'obciazenia': ob, 'saldo': wp + ob, 'narastajaco': narast})
    inne = [dict(r) for r in con.execute('SELECT id, folder, kategoria, nazwa FROM bud_arkusz ORDER BY folder, nazwa')]
    return {'arkusz': a, 'miesiace': miesiace, 'wiersze': wiersze, 'podsumowanie': podsumowanie, 'planowanie': planowanie(con),
            'arkusze': inne, 'podstawy': reguly.PODSTAWY_WIERSZA}


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
    w['dni'] = reguly.dni_na_platnosc(w['dni_na_platnosc'])
    w['dzien_opis'] = reguly.regula_opis(w['dzien_wystawienia'])
    k = con.execute('SELECT kwota FROM bud_komorka WHERE wiersz = ? AND miesiac = ?', (p['wiersz'], p['miesiac'])).fetchone()
    return {'platnosc': p, 'wiersz': w, 'kwota_komorki': k[0] if k else None, 'powiazania': pow_, 'historia': historia,
            'planowanie': planowanie(con)}


LISTY = {
    'wszystkie': 'Wszystkie płatności',
    'nieoplacone': 'Nadal nieopłacone',
    'niewystawione': 'Nadal niewystawione',
    'po_terminie': 'Po terminie płatności',
    'do_wystawienia': 'Do wystawienia (najbliższe 2 tyg.)',
    'do_zaplacenia': 'Do zapłacenia (najbliższe 2 tyg.)',
    'zaplacone': 'Zapłacone (ostatnie 2 tyg.)',
}


def lista(con, nazwa='wszystkie', rodzaj=None, q=None, strona=1, ile=100) -> dict:
    """Listy płatności planu ze stronicowaniem i wyszukiwarką (kontrahent, tytuł, numer dokumentu, arkusz).
    Suma liczona ze wszystkich pozycji listy, nie tylko z widocznej strony."""
    dzien = _dzien_stanu(con)
    za2 = (date.fromisoformat(dzien) + timedelta(days=14)).isoformat()
    przed2 = (date.fromisoformat(dzien) - timedelta(days=14)).isoformat()
    bez_faktury = "NOT EXISTS (SELECT 1 FROM bud_powiazanie b WHERE b.platnosc = p.id AND b.typ = 'faktura')"
    warunki = {
        'wszystkie': '1=1',
        'nieoplacone': f"p.rodzaj = 1 AND (s.etap IN ('Wystawiona', 'Częściowo opłacona') OR (s.etap = 'Po terminie' AND NOT {bez_faktury}))",
        'niewystawione': f"p.rodzaj = 1 AND p.aktualna = 1 AND {bez_faktury} AND s.etap IN ('Planowana', 'Po terminie') AND p.miesiac <= '{dzien[:7]}'",
        'po_terminie': "s.etap = 'Po terminie'",
        'do_wystawienia': f"p.rodzaj = 1 AND s.etap = 'Planowana' AND {bez_faktury} AND COALESCE(p.wystawienie, s.termin_efektywny) BETWEEN '{dzien}' AND '{za2}'",
        'do_zaplacenia': f"p.rodzaj = -1 AND s.etap IN ('Planowana', 'Po terminie') AND s.termin_efektywny <= '{za2}'",
        'zaplacone': f"s.etap = 'Opłacona' AND s.data_zaplaty BETWEEN '{przed2}' AND '{dzien}'",
    }[nazwa if nazwa in LISTY else 'wszystkie']
    params = []   # daty w warunkach pochodzą z bazy (dzień stanu), wartości od użytkownika tylko jako parametry
    sql = ("SELECT p.*, s.etap, s.termin_efektywny, s.data_zaplaty, s.uwaga AS uwaga_stanu, s.etap_wg_bs, s.aktualnosc,"
           " COALESCE(NULLIF(p.kontrahent, ''), w.kontrahent) AS w_kontrahent, w.podstawa,"
           ' a.nazwa AS arkusz, a.folder, a.id AS arkusz_id FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz'
           f' JOIN bud_arkusz a ON a.id = w.arkusz JOIN bud_stan s ON s.platnosc = p.id WHERE ({warunki})')
    if rodzaj in ('1', '-1'):
        sql += ' AND p.rodzaj = ?'
        params.append(int(rodzaj))
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
        elif x['ref'] and x['ref'].startswith('FV'):
            f = con.execute('SELECT fk.klient, f.data_wystawienia FROM faktury f LEFT JOIN faktury_klient fk USING(numer) WHERE f.numer = ?',
                            (x['ref'],)).fetchone()
            x.update(kontrahent=x['ref'], arkusz=f[0] if f else '', miesiac=(f[1] or '')[:7] if f else '')
        wynik.append(x)
    return wynik


def historia(con) -> dict:
    """Zmiany planów (ostatnie 500) i zdarzenia bez obiektu, do których nie ma się już do czego odnieść."""
    return {'zmiany': [dict(r) for r in con.execute('SELECT * FROM bud_historia ORDER BY czas DESC LIMIT 500')],
            'osierocone': [dict(r) for r in con.execute('SELECT * FROM bud_osierocone ORDER BY czas DESC')]}
