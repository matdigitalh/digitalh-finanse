"""Biblioteka budżetu (pakiet 4: A-KON-01 do 12, A-KOL-03 do 05, A-BUD-05 do 11): słowniki kontrahentów, przedmiotów
transakcji, sekcji i metod płatności oraz struktura folderów i kategorii.

Słowniki i struktura są częścią stanu budżetu (st['slownik'], st['struktura'] obok arkuszy i wierszy), więc zmiany idą
tą samą drogą co reszta budżetu: zdarzenie „bud” z operacją „slownik” albo „struktura”, próba na modelu z blokadami BS,
cały wpis albo nic (seria), historia i cofanie. Bez wpisów słowniki i struktura wynikają z danych (kopia z BS albo
import): wartości z wierszy, płatności i ręcznych zmian planów, foldery i kategorie z arkuszy, ustawienia domyślne
kontrahenta z jego najczęstszego wiersza. Plików Mata nic nie przepisuje; każda zmiana to nowy wpis w pliku zmian.

Kluczem jest nazwa (w BS wiersz i płatność też niosą nazwę), więc zmiana nazwy i połączenie duplikatów przepinają
wszystkie wystąpienia (wiersze, płatności, ręczne zmiany planów) jednym wpisem. Wartość wpisana w wierszu, której
w słowniku nie ma, trafia tam sama po zapisie (wpis uproszczony, A-KOL-03); nowy kontrahent dostaje wtedy ustawienia
wiersza jako swoje domyślne (A-KOL-05).
"""
import json
import re
from collections import Counter, defaultdict

from . import plan
from .filtry import klucz_pl
from .format import norm

RODZAJE = ('kontrahent', 'przedmiot', 'sekcja', 'metoda')
NAZWY = {'kontrahent': 'Kontrahent', 'przedmiot': 'Przedmiot transakcji', 'sekcja': 'Sekcja', 'metoda': 'Metoda płatności'}
MAKS = {'kontrahent': 200, 'przedmiot': 200, 'sekcja': 100, 'metoda': 60}   # jak pola wiersza (zmiany.POLA_BUD)
MAKS_STRUKTURY = 80
# Pusta wartość to wpis systemowy (BS: kontrahent domyślny, przedmiot „Przedmiot transakcji”, sekcja „-”).
SYSTEMOWE = {'kontrahent': 'Bez kontrahenta', 'przedmiot': 'Przedmiot transakcji', 'sekcja': '-'}
FOLDER_SYSTEMOWY = 'System'   # arkusz systemowy Opłaty urzędowe (pakiet 8)
RACHUNKI = ('główny', 'online', 'VAT', 'karta')
PODSTAWY_DOMYSLNE = ('Faktura (jedna)', 'Faktura (w worku)', 'Bez faktury', 'Bez faktury (w worku)')
POLA_USTAWIEN = ('rodzaj', 'podstawa', 'stawka_vat', 'dzien_wystawienia', 'dni_na_platnosc', 'metoda', 'split', 'ksiegowane',
                 'w_cashflow', 'przedmiot', 'sekcja')
# Ustawienia systemowego kontrahenta domyślnego na start (to samo, co apka wpisywała do nowego wiersza w pakiecie 3).
USTAWIENIA_STARTOWE = {'rodzaj': -1, 'podstawa': 'Faktura (jedna)', 'stawka_vat': 23, 'dzien_wystawienia': 'Ostatni', 'dni_na_platnosc': 14,
                       'metoda': 'Konto firmowe', 'split': False, 'ksiegowane': True, 'w_cashflow': True}
AKCJE_SLOWNIKA = ('dodaj', 'zmien', 'polacz', 'usun')
AKCJE_STRUKTURY = ('dodaj_folder', 'dodaj_kategorie', 'zmien_folder', 'zmien_kategorie', 'usun_folder', 'usun_kategorie',
                   'kolejnosc')


def uzywane_przez_system() -> dict:
    """Nazwy, których używa arkusz systemowy Opłaty urzędowe (podatki.dolacz): takich wpisów nie usuniesz."""
    from .podatki import URZAD
    return {'kontrahent': {URZAD}, 'metoda': {'Przelew'},
            'przedmiot': {'Podatek VAT', 'Podatek dochodowy (CIT)', 'Zwrot VAT', 'Zwrot CIT'}, 'sekcja': set()}


def _po_polsku(xs):
    return sorted(xs, key=lambda x: (klucz_pl(x), x))


def etykieta(rodzaj: str, nazwa: str) -> str:
    return nazwa or SYSTEMOWE.get(rodzaj, '')


# ---------- Stan: z danych albo z modelu po wcześniejszych zdarzeniach ----------

def stan(model: dict) -> dict:
    """Słowniki i struktura do stanu budżetu (budzet._stan). Model po zdarzeniach niesie je w sobie (zastosuj_zdarzenia
    je odkłada), model z kopii albo importu dostaje je wyprowadzone z danych."""
    if 'slownik' in model and 'struktura' in model:
        return {'slownik': {(r['rodzaj'], r['nazwa']): dict(r) for r in model['slownik']},
                'struktura': {f: tuple(k) for f, k in model['struktura']}}
    zast = zastapione(model.get('arkusze', []), model.get('wiersze', []))
    return {'slownik': _z_danych(model), 'struktura': _struktura_z_arkuszy([a for a in model.get('arkusze', []) if a['id'] not in zast])}


def odloz(model: dict, st: dict):
    """Stan biblioteki z powrotem do modelu (lista i pary, bez kluczy krotek)."""
    model['slownik'] = [st['slownik'][k] for k in sorted(st['slownik'])]
    model['struktura'] = [[f, list(k)] for f, k in st['struktura'].items()]


def zastapione(arkusze, wiersze) -> set:
    """Arkusze podatkowe z BS, które w bazie zastępuje arkusz systemowy (podatki.dolacz): mają wiersze z podstawą
    podatkową i żadnych innych. W Bibliotece ich nie ma, więc nie blokują usuwania folderu."""
    podatkowe, inne = set(), set()
    for w in (wiersze.values() if isinstance(wiersze, dict) else wiersze):
        (podatkowe if w.get('podstawa') in plan.PODATKI else inne).add(w.get('arkusz'))
    return podatkowe - inne


def _struktura_z_arkuszy(arkusze) -> dict:
    kat = defaultdict(set)
    for a in arkusze:
        if a.get('zrodlo') != 'system' and a.get('folder'):
            kat[a['folder']].add(a.get('kategoria') or '')
    return {f: tuple(_po_polsku(kat[f])) for f in _po_polsku(kat)}


def ustawienia_wiersza(w: dict) -> dict | None:
    """Ustawienia wiersza jako wzorzec dla kontrahenta (A-KOL-05). Umowa nie: potrzebuje kwot od księgowej."""
    from .budzet import stawka_proc
    pod = w.get('podstawa')
    if pod not in PODSTAWY_DOMYSLNE:
        return None
    u = {'rodzaj': w.get('rodzaj', -1), 'podstawa': pod, 'stawka_vat': stawka_proc(w.get('stawka_vat')) if plan.ma_vat(pod) else None,
         'dni_na_platnosc': plan.dni_na_platnosc(w.get('dni_na_platnosc')), 'metoda': (w.get('metoda') or '').strip(),
         'split': bool(w.get('split')), 'ksiegowane': bool(w.get('ksiegowane', True)), 'w_cashflow': bool(w.get('w_cashflow', True))}
    if pod not in plan.WOREK:
        try:
            r = plan.regula(w.get('dzien_wystawienia'))
        except ValueError:
            r = None
        if r:   # „(auto)” z importu (różne dni w płatnościach): bez reguły, zostaje ta z kontrahenta domyślnego
            u['dzien_wystawienia'] = plan.regula_tekst(r)
    return u


def _rekord(rodzaj: str, nazwa: str, **kw) -> dict:
    r = {'rodzaj': rodzaj, 'nazwa': nazwa}
    if rodzaj == 'kontrahent':
        r.update(pelna=nazwa, nip='', ustawienia=None)
    elif rodzaj == 'metoda':
        r.update(rachunek='', bank='')
    r.update(kw)
    return r


def _systemowe() -> dict:
    return {('kontrahent', ''): _rekord('kontrahent', '', pelna='', systemowy=True, domyslny=True, ustawienia=dict(USTAWIENIA_STARTOWE)),
            ('przedmiot', ''): _rekord('przedmiot', '', systemowy=True, domyslny=True),
            ('sekcja', ''): _rekord('sekcja', '', systemowy=True)}


def _z_danych(model: dict) -> dict:
    """Słowniki z danych (kopia z BS albo import): każda wartość z wierszy, płatności i ręcznych zmian planów to wpis
    uproszczony; ustawienia domyślne kontrahenta = najczęstsze ustawienia jego wierszy (remis: pierwszy wiersz po ID)."""
    sl = _systemowe()
    wzorce = defaultdict(Counter)
    for w in sorted(model.get('wiersze', []), key=lambda x: x['id']):
        for r in RODZAJE:
            v = (w.get(r) or '').strip()
            if v and (r, v) not in sl:
                sl[(r, v)] = _rekord(r, v)
        k = (w.get('kontrahent') or '').strip()
        u = ustawienia_wiersza(w) if k else None
        if u:
            wzorce[k][json.dumps(u, sort_keys=True, ensure_ascii=False)] += 1
    for p in model.get('platnosci', []):
        for r in ('kontrahent', 'metoda'):
            v = (p.get(r) or '').strip()
            if v and (r, v) not in sl:
                sl[(r, v)] = _rekord(r, v)
    for n in (model.get('nadpisane') or {}).values():
        for r in ('kontrahent', 'metoda'):
            v = (n.get(r) or '').strip() if isinstance(n.get(r), str) else ''
            if v and (r, v) not in sl:
                sl[(r, v)] = _rekord(r, v)
    for k, c in wzorce.items():
        najlepszy = max(c.items(), key=lambda x: x[1])[0]   # Counter zachowuje kolejność dodania: remis = pierwszy wiersz
        sl[('kontrahent', k)] = {**sl[('kontrahent', k)], 'ustawienia': json.loads(najlepszy)}
    return sl


def wchlon(st: dict, ops: list[dict]):
    """Po udanym wpisie: nowe wartości z wierszy i płatności trafiają do słowników (wpis uproszczony, A-KOL-03), nowe
    foldery i kategorie arkuszy do struktury (na koniec). Nowy kontrahent z wiersza dostaje ustawienia tego wiersza jako
    domyślne (A-KOL-05: wiersz zaczęty od niego ma już ustawienia kontrahenta domyślnego, więc te same)."""
    sl = st['slownik']
    for o in ops:
        if o['op'] == 'wiersz' and not o.get('usun'):
            w = st['wiersz'].get(o['obiekt']['id'])
            if not w:
                continue
            for r in RODZAJE:
                v = (w.get(r) or '').strip()
                if r in o['obiekt'] and v and (r, v) not in sl:
                    sl[(r, v)] = _rekord(r, v, **({'ustawienia': ustawienia_wiersza(w)} if r == 'kontrahent' else {}))
        elif o['op'] == 'platnosc' and not o.get('usun'):
            for r in ('kontrahent', 'metoda'):
                v = (o['obiekt'].get(r) or '').strip() if isinstance(o['obiekt'].get(r), str) else ''
                if v and (r, v) not in sl:
                    sl[(r, v)] = _rekord(r, v)
        elif o['op'] in ('arkusz', 'duplikuj_arkusz') and not o.get('usun'):
            a = st['arkusz'].get(o['obiekt']['id'])
            if a and a.get('folder'):
                _dopisz_miejsce(st, a['folder'], a.get('kategoria', ''))


def _dopisz_miejsce(st: dict, folder: str, kategoria: str):
    s = st['struktura']
    if folder not in s:
        s[folder] = (kategoria,)
    elif kategoria not in s[folder]:
        s[folder] = s[folder] + (kategoria,)


def pelna_struktura(st: dict) -> dict:
    """Struktura z wpisów plus foldery i kategorie arkuszy, których w niej nie ma (np. z nowszego eksportu BS)."""
    s = dict(st['struktura'])
    brak = defaultdict(set)
    zast = zastapione(st['arkusz'], st['wiersz'])
    for a in st['arkusz'].values():
        if a['id'] not in zast and a.get('zrodlo') != 'system' and a.get('folder') and a.get('kategoria', '') not in s.get(a['folder'], ()):
            brak[a['folder']].add(a.get('kategoria', ''))
    for f in _po_polsku(brak):
        s[f] = s.get(f, ()) + tuple(_po_polsku(brak[f]))
    return s


# ---------- Nowy wiersz z ustawień Biblioteki (A-ARK-10, A-KOL-04, A-KOL-05) ----------

def domyslny(st: dict, rodzaj: str) -> dict:
    """Wpis domyślny dla nowych wierszy (kontrahent, przedmiot); zawsze dokładnie jeden, na start systemowy."""
    for (r, _), x in st['slownik'].items():
        if r == rodzaj and x.get('domyslny'):
            return x
    return _systemowe()[(rodzaj, '')]


def ustawienia_kontrahenta(st: dict, nazwa: str | None) -> dict:
    """Ustawienia domyślne kontrahenta warstwami: start, kontrahent domyślny, ten kontrahent (gdy ma własne)."""
    dom = domyslny(st, 'kontrahent')
    rek = st['slownik'].get(('kontrahent', nazwa)) if nazwa is not None else None
    return {**USTAWIENIA_STARTOWE, **(dom.get('ustawienia') or {}), **((rek or {}).get('ustawienia') or {})}


def uzupelnij_wiersz(st: dict, obiekt: dict) -> dict:
    """Nowy wiersz z „Dodaj +”: pola podane przez Mata zostają, reszta z Biblioteki. Gdy pierwszą akcją był wybór
    kontrahenta, jego ustawienia domyślne; inaczej kontrahent domyślny i jego ustawienia (A-KOL-04, A-KOL-05).
    Przedmiot: z ustawień kontrahenta albo przedmiot domyślny (A-ARK-10)."""
    kontr = obiekt['kontrahent'] if 'kontrahent' in obiekt else domyslny(st, 'kontrahent')['nazwa']
    u = ustawienia_kontrahenta(st, kontr)
    wynik = {**{k: v for k, v in u.items() if k not in ('przedmiot', 'sekcja')},
             'przedmiot': u.get('przedmiot') or domyslny(st, 'przedmiot')['nazwa'], 'sekcja': u.get('sekcja') or '',
             'komentarz': '', 'kontrahent': kontr, **obiekt}
    if not plan.ma_vat(wynik['podstawa']):
        wynik['stawka_vat'] = None
    if wynik['podstawa'] in plan.WOREK:
        wynik.pop('dzien_wystawienia', None)
    return wynik


# ---------- Walidacja kształtu (zmiany._sprawdz_bud) ----------

def _nazwa(rodzaj: str, v, pole='nazwa', pusta=False) -> str:
    if not isinstance(v, str):
        raise ValueError(f'{NAZWY[rodzaj]}: oczekiwana nazwa')
    v = re.sub(r'\s+', ' ', v).strip()
    if not v and not pusta:
        raise ValueError(f'{NAZWY[rodzaj]}: nazwa nie może być pusta. Wpisz nazwę.')
    if len(v) > MAKS[rodzaj]:
        raise ValueError(f'{NAZWY[rodzaj]}: najwyżej {MAKS[rodzaj]} znaków (jest {len(v)}). Skróć nazwę.')
    return v


def _miejsce(v, co: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ValueError(f'{co}: nazwa nie może być pusta. Wpisz nazwę.')
    v = re.sub(r'\s+', ' ', v).strip()
    if len(v) > MAKS_STRUKTURY:
        raise ValueError(f'{co}: najwyżej {MAKS_STRUKTURY} znaków (jest {len(v)}). Skróć nazwę.')
    return v


def sprawdz_nip(v) -> str:
    """NIP opcjonalny: polski 10 cyfr z sumą kontrolną (myślniki i spacje usuwane, prefiks PL dozwolony) albo
    zagraniczny numer VAT (litery kraju i do 15 znaków)."""
    t = re.sub(r'[\s-]', '', str(v or '')).upper()
    if not t:
        return ''
    if re.fullmatch(r'(PL)?\d{10}', t):
        c = t[-10:]
        if sum(int(a) * b for a, b in zip(c, (6, 5, 7, 2, 3, 4, 5, 6, 7))) % 11 != int(c[9]):
            raise ValueError(f'NIP {c} ma złą sumę kontrolną. Sprawdź cyfry.')
        return c
    if not re.fullmatch(r'[A-Z]{2}[0-9A-Z]{2,15}', t):
        raise ValueError('NIP: 10 cyfr (polski) albo numer VAT z kodem kraju, np. DE123456789.')
    return t


def sprawdz_ustawienia(u) -> dict | None:
    """Ustawienia domyślne kontrahenta: te same reguły co pola wiersza; podstawa bez umów (umowa potrzebuje kwot od księgowej)."""
    if u is None:
        return None
    from . import zmiany
    if not isinstance(u, dict) or set(u) - set(POLA_USTAWIEN):
        raise ValueError(f"ustawienia domyślne: dozwolone pola {', '.join(POLA_USTAWIEN)}")
    spr = {'rodzaj': zmiany._rodzaj, 'stawka_vat': zmiany._stawka, 'dzien_wystawienia': zmiany._dzien_wyst, 'dni_na_platnosc': zmiany._dni,
           'metoda': zmiany._tekst(60), 'split': zmiany._tak_nie, 'ksiegowane': zmiany._tak_nie, 'w_cashflow': zmiany._tak_nie,
           'przedmiot': zmiany._tekst(200), 'sekcja': zmiany._tekst(100)}
    wynik = {}
    for k, v in u.items():
        if k == 'podstawa':
            if v not in PODSTAWY_DOMYSLNE:
                raise ValueError('Podstawa w ustawieniach domyślnych: faktura albo bez faktury (jedna lub w worku). '
                                 'Umowę ustawisz w wierszu, bo potrzebuje kwot od księgowej.')
            wynik[k] = v
        elif k == 'stawka_vat' and v in (None, '', '-'):
            wynik[k] = None
        elif k == 'dzien_wystawienia' and v in (None, '', '(auto)'):
            continue
        else:
            wynik[k] = spr[k](v, k)
    return wynik


def sprawdz_op(d: dict) -> dict:
    """Kształt operacji „slownik” i „struktura”. Odwołania (czy wpis istnieje, czy nazwa wolna) sprawdza próba na modelu."""
    op = d['op']
    if len(json.dumps(d)) > 60000:
        raise ValueError('za duży wpis')
    if op == 'slownik':
        akcja, rodzaj = d.get('akcja'), d.get('rodzaj')
        if akcja not in AKCJE_SLOWNIKA or rodzaj not in RODZAJE:
            raise ValueError('Biblioteka: nieznana akcja albo słownik')
        wynik = {'op': op, 'akcja': akcja, 'rodzaj': rodzaj}
        if akcja == 'usun':
            n = d.get('nazwy')
            if not isinstance(n, list) or not 0 < len(n) <= 1000:
                raise ValueError('Biblioteka: zaznacz od 1 do 1000 pozycji do usunięcia')
            wynik['nazwy'] = [_nazwa(rodzaj, x, pusta=True) for x in n]
            return wynik
        if akcja == 'polacz':
            zr = d.get('zrodla')
            if not isinstance(zr, list) or not 0 < len(zr) <= 100:
                raise ValueError('Połącz: wybierz od 1 do 100 pozycji do połączenia')
            wynik['zrodla'] = [_nazwa(rodzaj, x, pusta=True) for x in zr]
            wynik['cel'] = _nazwa(rodzaj, d.get('cel'), pusta=True)
            if wynik['cel'] in wynik['zrodla'] or len(set(wynik['zrodla'])) != len(wynik['zrodla']):
                raise ValueError('Połącz: pozycja docelowa nie może być na liście łączonych, a każda pozycja raz')
        else:
            wynik['nazwa'] = _nazwa(rodzaj, d.get('nazwa'), pusta=akcja == 'zmien')
            if akcja == 'zmien' and 'nowa' in d:
                wynik['nowa'] = _nazwa(rodzaj, d['nowa'])
        pola = {'kontrahent': ('pelna', 'nip', 'domyslny', 'ustawienia'), 'przedmiot': ('domyslny',), 'sekcja': (),
                'metoda': ('rachunek', 'bank')}[rodzaj]
        znane = {'op', 'akcja', 'rodzaj', 'nazwa', 'nowa', 'zrodla', 'cel'} | set(pola)
        if set(d) - znane:
            raise ValueError(f"Biblioteka: nieznane pole {', '.join(sorted(set(d) - znane))}")
        for k in pola:
            if k not in d:
                continue
            v = d[k]
            if k == 'pelna':
                wynik[k] = re.sub(r'\s+', ' ', str(v or '')).strip()[:300]
            elif k == 'nip':
                wynik[k] = sprawdz_nip(v)
            elif k == 'domyslny':
                if v is not True and v is not False:
                    raise ValueError('domyślny: tak albo nie')
                wynik[k] = v
            elif k == 'ustawienia':
                wynik[k] = sprawdz_ustawienia(v)
            elif k == 'rachunek':
                if v not in ('',) + RACHUNKI:
                    raise ValueError(f"Rachunek metody płatności: {', '.join(RACHUNKI)} albo brak")
                wynik[k] = v
            elif k == 'bank':
                wynik[k] = re.sub(r'\s+', ' ', str(v or '')).strip()[:60]
        return wynik
    akcja = d.get('akcja')
    if akcja not in AKCJE_STRUKTURY:
        raise ValueError('Foldery i kategorie: nieznana akcja')
    znane = {'op', 'akcja', 'folder', 'kategoria', 'nazwa', 'do_folderu', 'do_kategorii', 'foldery', 'kategorie'}
    if set(d) - znane:
        raise ValueError(f"Foldery i kategorie: nieznane pole {', '.join(sorted(set(d) - znane))}")
    wynik = {'op': op, 'akcja': akcja}
    if akcja == 'kolejnosc':
        if 'foldery' in d:
            lista = d['foldery']
            if not isinstance(lista, list) or not 0 < len(lista) <= 1000:
                raise ValueError('Kolejność: lista folderów')
            wynik['foldery'] = [_miejsce(x, 'Folder') for x in lista]
        else:
            wynik['folder'] = _miejsce(d.get('folder'), 'Folder')
            lista = d.get('kategorie')
            if not isinstance(lista, list) or not 0 < len(lista) <= 1000:
                raise ValueError('Kolejność: lista kategorii')
            wynik['kategorie'] = [_miejsce(x, 'Kategoria') for x in lista]
        return wynik
    wynik['folder'] = _miejsce(d.get('folder'), 'Folder')
    if akcja in ('dodaj_folder', 'dodaj_kategorie', 'zmien_kategorie', 'usun_kategorie'):
        wynik['kategoria'] = _miejsce(d.get('kategoria'), 'Kategoria')
    if akcja in ('zmien_folder', 'zmien_kategorie'):
        wynik['nazwa'] = _miejsce(d.get('nazwa'), 'Nowa nazwa')
    if akcja in ('usun_folder', 'usun_kategorie') and d.get('do_folderu'):
        wynik['do_folderu'] = _miejsce(d['do_folderu'], 'Folder docelowy')
        if akcja == 'usun_kategorie':
            wynik['do_kategorii'] = _miejsce(d.get('do_kategorii'), 'Kategoria docelowa')
    return wynik


# ---------- Operacje na stanie (budzet._zastosuj_op) ----------

def zastosuj(st: dict, d: dict, scisle: bool):
    """Jedna operacja „slownik” albo „struktura”. Zwraca (powód odrzucenia albo None, było, id obiektu); przy powodzie
    stan zostaje nietknięty (budzet._zastosuj_wpis i tak pracuje na kopii)."""
    if d['op'] == 'slownik':
        return _slownik(st, d, scisle)
    return _struktura(st, d, scisle)


def _znajdz(st: dict, rodzaj: str, nazwa: str, bez=None):
    """Wpis o tej samej nazwie bez względu na wielkość liter (nazwa ma być jednoznaczna, A-KON-09)."""
    n = nazwa.casefold()
    return next((x for (r, k), x in st['slownik'].items() if r == rodzaj and k.casefold() == n and k != bez), None)


def uzycia(st: dict, rodzaj: str, nazwa: str) -> int:
    """Wystąpienia w stanie budżetu (wiersze i płatności, bez wierszy podatkowych z BS, które zastępuje arkusz systemowy)."""
    wie = st['wiersz']
    pod = {wid for wid, w in wie.items() if w.get('podstawa') in plan.PODATKI}
    n = sum(1 for wid, w in wie.items() if wid not in pod and (w.get(rodzaj) or '').strip() == nazwa)
    if rodzaj in ('kontrahent', 'metoda'):
        for p in st['platnosc'].values():
            if p['wiersz'] in pod or p.get('ukryty') or p['wiersz'] not in wie:
                continue
            v = (p.get(rodzaj) or (wie[p['wiersz']].get('kontrahent') if rodzaj == 'kontrahent' else '') or '').strip()
            n += v == nazwa
    else:
        n += sum(1 for p in st['platnosc'].values()
                 if p['wiersz'] in wie and p['wiersz'] not in pod and not p.get('ukryty') and (wie[p['wiersz']].get(rodzaj) or '').strip() == nazwa)
    return n


def _przepnij(st: dict, rodzaj: str, stare: set, nowa: str):
    """Wszystkie wystąpienia nazw ze zbioru stare dostają nową nazwę: wiersze, płatności i ręczne zmiany planów (A-KON-06).
    Obiekty podmieniamy, nie zmieniamy w miejscu (seria musi dać się odrzucić)."""
    wie = st['wiersz']
    for wid, w in list(wie.items()):
        if (w.get(rodzaj) or '').strip() in stare:
            wie[wid] = {**w, rodzaj: nowa}
    if rodzaj in ('kontrahent', 'metoda'):
        pla, nad = st['platnosc'], st['nadpisane']
        for pid, p in list(pla.items()):
            if isinstance(p.get(rodzaj), str) and p[rodzaj] and p[rodzaj].strip() in stare:
                pla[pid] = {**p, rodzaj: nowa}
        for pid, n in list(nad.items()):
            if isinstance(n.get(rodzaj), str) and n[rodzaj] and n[rodzaj].strip() in stare:
                nad[pid] = {**n, rodzaj: nowa}


def _ustaw_domyslny(st: dict, rodzaj: str, nazwa: str):
    sl = st['slownik']
    for k, x in list(sl.items()):
        if k[0] == rodzaj and bool(x.get('domyslny')) != (k[1] == nazwa):
            sl[k] = {**x, 'domyslny': k[1] == nazwa}


def _pola_wpisu(d: dict) -> dict:
    return {k: d[k] for k in ('pelna', 'nip', 'ustawienia', 'rachunek', 'bank') if k in d}


def _slownik(st: dict, d: dict, scisle: bool):
    sl, r = st['slownik'], d['rodzaj']
    nazwa_r = NAZWY[r].lower()
    if d['akcja'] == 'dodaj':
        n = d['nazwa']
        oid = f'{r}:{n}'
        ist = _znajdz(st, r, n)
        if ist and scisle:
            return (f'{NAZWY[r]} „{etykieta(r, ist["nazwa"])}” już jest w Bibliotece. Wybierz go z listy albo zmień nazwę nowego.',
                    None, oid)
        bylo = dict(sl[(r, n)]) if (r, n) in sl else None
        rek = {**(bylo or _rekord(r, n)), **_pola_wpisu(d)}
        if r == 'kontrahent' and 'pelna' not in d and not bylo:
            rek['pelna'] = n   # wpis uproszczony: pełna = skrócona (A-KOL-03)
        sl[(r, n)] = rek
        if d.get('domyslny'):
            _ustaw_domyslny(st, r, n)
        return None, bylo, oid
    if d['akcja'] == 'usun':
        return _usun(st, d, scisle)
    if d['akcja'] == 'polacz':
        return _polacz(st, d, scisle)
    n = d['nazwa']
    oid = f'{r}:{n}'
    if (r, n) not in sl:
        return f'nie ma pozycji „{etykieta(r, n)}” ({nazwa_r}) w Bibliotece', None, oid
    bylo = dict(sl[(r, n)])
    nowa = d.get('nowa', n)
    if nowa != n:
        if bylo.get('systemowy'):
            return f'„{etykieta(r, n)}” to wpis systemowy, więc jego nazwy nie zmienisz.', None, oid
        ist = _znajdz(st, r, nowa, bez=n)
        if ist and scisle:
            return (f'{NAZWY[r]} „{ist["nazwa"]}” już jest. Żeby zostawić jeden wpis, użyj „Połącz z istniejącym”.', None, oid)
    if d.get('domyslny') is False and bylo.get('domyslny') and scisle:
        return ('Jeden wpis musi być domyślny dla nowych wierszy. Ustaw jako domyślny inny wpis, a ten przestanie nim być sam.',
                None, oid)
    rek = {**bylo, **_pola_wpisu(d)}
    if nowa != n:
        sl.pop((r, n))
        rek['nazwa'] = nowa
        if r == 'kontrahent' and rek.get('pelna') == n and 'pelna' not in d:
            rek['pelna'] = nowa
        if (r, nowa) in sl:   # ta sama nazwa (np. odtworzenie historii): wpisy się łączą
            rek = {**sl[(r, nowa)], **rek}
        _przepnij(st, r, {n}, nowa)
    sl[(r, nowa)] = rek
    if d.get('domyslny'):
        _ustaw_domyslny(st, r, nowa)
    return None, bylo, oid


def _polacz(st: dict, d: dict, scisle: bool):
    """A-KON-06: wszystkie wystąpienia łączonych pozycji przechodzą na wpis docelowy (z danymi wybranymi przez Mata),
    duplikaty znikają; jeden wpis w pliku zmian."""
    sl, r, cel = st['slownik'], d['rodzaj'], d['cel']
    oid = f'{r}:{cel}'
    brak = [x for x in [cel, *d['zrodla']] if (r, x) not in sl]
    if brak:
        return f"nie ma w Bibliotece: {', '.join(etykieta(r, x) for x in brak)}", None, oid
    sys_ = [x for x in d['zrodla'] if sl[(r, x)].get('systemowy')]
    if sys_:
        return (f'„{etykieta(r, sys_[0])}” to wpis systemowy, więc go nie połączysz z innym. '
                'Połącz inne pozycje z nim (wybierz go jako ten, który zostaje).'), None, oid
    bylo = {'cel': dict(sl[(r, cel)]), 'zrodla': [dict(sl[(r, x)]) for x in d['zrodla']]}
    domyslny_ = any(sl[(r, x)].get('domyslny') for x in d['zrodla'])
    for x in d['zrodla']:
        sl.pop((r, x))
    _przepnij(st, r, set(d['zrodla']), cel)
    sl[(r, cel)] = {**sl[(r, cel)], **_pola_wpisu(d)}
    if domyslny_ or d.get('domyslny'):
        _ustaw_domyslny(st, r, cel)
    return None, bylo, oid


def _usun(st: dict, d: dict, scisle: bool):
    """A-KON-07: tylko pozycje bez wystąpień (licznik 0), nie systemowe i nie domyślne; kilka naraz albo żadna."""
    sl, r = st['slownik'], d['rodzaj']
    oid = f"{r}:{','.join(d['nazwy'])}"[:200]
    sys_uz = uzywane_przez_system().get(r, set())
    bylo = []
    for n in d['nazwy']:
        x = sl.get((r, n))
        if not x:
            return f'nie ma pozycji „{etykieta(r, n)}” w Bibliotece', None, oid
        if scisle:
            if x.get('systemowy'):
                return f'„{etykieta(r, n)}” to wpis systemowy, więc go nie usuniesz.', None, oid
            if x.get('domyslny'):
                return (f'„{etykieta(r, n)}” jest domyślny dla nowych wierszy. Ustaw jako domyślny inny wpis, potem usuń ten.',
                        None, oid)
            if n in sys_uz:
                return (f'„{n}” jest używany przez arkusz systemowy Opłaty urzędowe (podatki), więc go nie usuniesz.', None, oid)
            ile = uzycia(st, r, n)
            if ile:
                return (f'„{n}” ma {ile} {"wystąpienie" if ile == 1 else "wystąpienia" if ile % 10 in (2, 3, 4) and ile % 100 not in (12, 13, 14) else "wystąpień"} '
                        '(wiersze i płatności), więc go nie usuniesz. Połącz go z innym wpisem albo najpierw zmień go w wierszach.'), None, oid
        bylo.append(dict(x))
    for n in d['nazwy']:
        sl.pop((r, n))
    return None, bylo, oid


# ---------- Struktura: foldery i kategorie (A-BUD-05 do 11) ----------

def _folder(s: dict, nazwa: str, bez=None):
    n = nazwa.casefold()
    return next((f for f in s if f.casefold() == n and f != bez), None)


def sprawdz_miejsce(st: dict, obiekt: dict) -> str | None:
    """Arkusz z folderem i kategorią (dodanie, przeniesienie, duplikat): bez folderu systemowego i bez drugiej nazwy
    różniącej się tylko wielkością liter (A-BUD-05, 06; A-INN-05)."""
    f, k = obiekt.get('folder'), obiekt.get('kategoria')
    if not f and not k:
        return None
    a = st['arkusz'].get(obiekt.get('id')) or {}
    f, k = f or a.get('folder', ''), k or a.get('kategoria', '')
    if f.casefold() == FOLDER_SYSTEMOWY.casefold():
        return f'Folder „{FOLDER_SYSTEMOWY}” jest zarezerwowany dla arkusza systemowego z podatkami. Wybierz inny folder.'
    s = pelna_struktura(st)
    inny = _folder(s, f, bez=f)
    if inny and f not in s:
        return f'Folder „{inny}” już jest (nazwa różni się tylko wielkością liter). Wybierz go z listy zamiast dodawać drugi raz.'
    kat = s.get(f, ())
    inna = next((x for x in kat if x.casefold() == k.casefold() and x != k), None)
    if inna and k not in kat:
        return f'Kategoria „{inna}” już jest w folderze „{f}”. Wybierz ją z listy zamiast dodawać drugi raz.'
    return None


def _arkusze_w(st: dict, folder: str, kategoria: str | None = None) -> list[str]:
    zast = zastapione(st['arkusz'], st['wiersz'])
    return [aid for aid, a in st['arkusz'].items()
            if aid not in zast and a.get('folder') == folder and (kategoria is None or a.get('kategoria') == kategoria)]


def _przenies_arkusze(st: dict, ids, folder: str, kategoria: str | None = None):
    for aid in ids:
        a = st['arkusz'][aid]
        st['arkusz'][aid] = {**a, 'folder': folder, 'kategoria': kategoria or a['kategoria'], 'zrodlo': 'apka'}


def _struktura(st: dict, d: dict, scisle: bool):
    s = pelna_struktura(st)
    akcja = d['akcja']
    f = d.get('folder', '')
    oid = f"{f}/{d['kategoria']}" if d.get('kategoria') else f
    if akcja == 'kolejnosc':
        if 'foldery' in d:
            obecne = [x for x in s]
            if sorted(d['foldery']) != sorted(obecne):
                return 'Kolejność folderów: lista nie zgadza się z obecnymi folderami. Odśwież ekran i spróbuj jeszcze raz.', None, 'foldery'
            st['struktura'] = {x: s[x] for x in d['foldery']}
            return None, {'foldery': obecne}, 'foldery'
        if f not in s:
            return f'nie ma folderu „{f}”', None, oid
        if sorted(d['kategorie']) != sorted(s[f]):
            return 'Kolejność kategorii: lista nie zgadza się z kategoriami folderu. Odśwież ekran i spróbuj jeszcze raz.', None, oid
        st['struktura'] = {**s, f: tuple(d['kategorie'])}
        return None, {'kategorie': list(s[f])}, oid
    if f.casefold() == FOLDER_SYSTEMOWY.casefold():
        return f'Folder „{FOLDER_SYSTEMOWY}” należy do arkusza systemowego z podatkami: tu nic nie zmienisz.', None, oid
    if akcja == 'dodaj_folder':
        if _folder(s, f):
            return f'Folder „{_folder(s, f)}” już jest. Nazwa folderu musi być unikalna w całej apce.', None, oid
        st['struktura'] = {**s, f: (d['kategoria'],)}
        return None, None, oid
    if f not in s:
        return f'nie ma folderu „{f}”', None, oid
    kat = s[f]
    if akcja == 'dodaj_kategorie':
        k = d['kategoria']
        if any(x.casefold() == k.casefold() for x in kat):
            return f'Kategoria „{k}” już jest w folderze „{f}”. Ta sama nazwa może być tylko w innym folderze.', None, oid
        st['struktura'] = {**s, f: kat + (k,)}
        return None, None, oid
    if akcja == 'zmien_folder':
        n = d['nazwa']
        if n == f:
            return None, None, oid
        if _folder(s, n, bez=f):
            return f'Folder „{_folder(s, n, bez=f)}” już jest. Wybierz inną nazwę.', None, oid
        if n.casefold() == FOLDER_SYSTEMOWY.casefold():
            return f'Nazwa „{FOLDER_SYSTEMOWY}” jest zarezerwowana dla arkusza systemowego. Wybierz inną.', None, oid
        st['struktura'] = {(n if x == f else x): v for x, v in s.items()}
        _przenies_arkusze(st, _arkusze_w(st, f), n)
        return None, {'folder': f}, oid
    if akcja == 'zmien_kategorie':
        k, n = d['kategoria'], d['nazwa']
        if k not in kat:
            return f'nie ma kategorii „{k}” w folderze „{f}”', None, oid
        if n == k:
            return None, None, oid
        if any(x.casefold() == n.casefold() and x != k for x in kat):
            return f'Kategoria „{n}” już jest w folderze „{f}”. Wybierz inną nazwę.', None, oid
        st['struktura'] = {**s, f: tuple(n if x == k else x for x in kat)}
        _przenies_arkusze(st, _arkusze_w(st, f, k), f, n)
        return None, {'kategoria': k}, oid
    if akcja == 'usun_folder':
        ark = _arkusze_w(st, f)
        cel = d.get('do_folderu')
        if ark and not cel:
            return (f'Folder „{f}” ma arkusze ({len(ark)}), więc go nie usuniesz. Przenieś je do innego folderu '
                    '(przy usuwaniu wybierz folder docelowy) albo usuń arkusze.'), None, oid
        if cel:
            if cel == f or cel not in s:
                return f'nie ma folderu docelowego „{cel}”' if cel != f else 'Folder docelowy musi być inny niż usuwany.', None, oid
            nowe = dict(s)
            for aid in ark:   # kategoria o tej samej nazwie (bez względu na wielkość liter) łączy się z istniejącą
                a = st['arkusz'][aid]
                k = next((x for x in nowe[cel] if x.casefold() == a['kategoria'].casefold()), a['kategoria'])
                if k not in nowe[cel]:
                    nowe[cel] = nowe[cel] + (k,)
                _przenies_arkusze(st, [aid], cel, k)
            s = nowe
        st['struktura'] = {x: v for x, v in s.items() if x != f}
        return None, {'folder': f, 'kategorie': list(kat), 'arkusze': len(ark)}, oid
    if akcja == 'usun_kategorie':
        k = d['kategoria']
        if k not in kat:
            return f'nie ma kategorii „{k}” w folderze „{f}”', None, oid
        if len(kat) == 1:
            return (f'„{k}” to ostatnia kategoria folderu „{f}”, a folder musi mieć co najmniej jedną. '
                    'Usuń cały folder albo najpierw dodaj inną kategorię.'), None, oid
        ark = _arkusze_w(st, f, k)
        cf, ck = d.get('do_folderu'), d.get('do_kategorii')
        if ark and not cf:
            return (f'Kategoria „{k}” ma arkusze ({len(ark)}), więc jej nie usuniesz. Przenieś je do innej kategorii '
                    '(przy usuwaniu wybierz kategorię docelową) albo usuń arkusze.'), None, oid
        if cf:
            if ck not in s.get(cf, ()):
                return f'nie ma kategorii docelowej „{ck}” w folderze „{cf}”', None, oid
            if (cf, ck) == (f, k):
                return 'Kategoria docelowa musi być inna niż usuwana.', None, oid
            _przenies_arkusze(st, ark, cf, ck)
        st['struktura'] = {**s, f: tuple(x for x in kat if x != k)}
        return None, {'folder': f, 'kategoria': k, 'arkusze': len(ark)}, oid
    return 'nieznana akcja', None, oid


# ---------- Zapis do bazy i odczyt dla interfejsu ----------

def zapisz(con, model: dict):
    """Tabele Biblioteki po odbudowie: słowniki (z oznaczeniem wpisów, których używa arkusz systemowy) i struktura
    (z folderem systemowym na końcu). Liczniki wystąpień liczy zapytanie, z tych samych tabel co reszta apki."""
    st = stan(model)
    sl = st['slownik']
    sys_ark = {a['id'] for a in model['arkusze'] if a.get('zrodlo') == 'system'}
    sys_w = [w for w in model['wiersze'] if w['arkusz'] in sys_ark]
    sys_ids = {w['id'] for w in sys_w}
    uzyte = defaultdict(set)
    for w in sys_w:
        for r in RODZAJE:
            if (w.get(r) or '').strip():
                uzyte[r].add(w[r].strip())
    for p in model['platnosci']:
        if p['wiersz'] in sys_ids:
            for r in ('kontrahent', 'metoda'):
                if (p.get(r) or '').strip():
                    uzyte[r].add(p[r].strip())
    for r, xs in uzyte.items():
        for x in xs:
            sl[(r, x)] = {**sl.get((r, x), _rekord(r, x)), 'arkusz_systemowy': True}
    # wartości spoza słownika (np. wiersze z nowszego eksportu BS dołożone po wpisach) też są w Bibliotece
    zwykle = [w for w in model['wiersze'] if w['arkusz'] not in sys_ark]
    for w in zwykle:
        for r in RODZAJE:
            v = (w.get(r) or '').strip()
            if v and (r, v) not in sl:
                sl[(r, v)] = _rekord(r, v)
    con.executemany('INSERT INTO bud_slownik (rodzaj, nazwa, dane) VALUES (?,?,?)',
                    [(r, n, json.dumps(x, ensure_ascii=False, sort_keys=True)) for (r, n), x in sl.items()])
    s = dict(st['struktura'])
    for a in model['arkusze']:
        if a.get('zrodlo') != 'system':
            if a['folder'] not in s:
                s[a['folder']] = (a['kategoria'],)
            elif a['kategoria'] not in s[a['folder']]:
                s[a['folder']] = s[a['folder']] + (a['kategoria'],)
    wiersze = [(f, k, i, j, 0) for i, (f, ks) in enumerate(s.items()) for j, k in enumerate(ks)]
    sys_kat = sorted({(a['folder'], a['kategoria']) for a in model['arkusze'] if a.get('zrodlo') == 'system'})
    wiersze += [(f, k, len(s), j, 1) for j, (f, k) in enumerate(sys_kat)]
    con.executemany('INSERT INTO bud_struktura (folder, kategoria, kf, kk, systemowy) VALUES (?,?,?,?,?)', wiersze)


def kolejnosc_folderow(con) -> dict:
    """Pozycja folderu i kategorii w strukturze (drzewo budżetu idzie w tej kolejności)."""
    return {(r['folder'], r['kategoria']): (r['kf'], r['kk']) for r in con.execute('SELECT * FROM bud_struktura')}


def _liczniki(con) -> dict:
    """Wystąpienia: wiersze i płatności (bez ukrytych planów zerowych) z tą wartością; płatność dziedziczy przedmiot
    i sekcję z wiersza, kontrahenta z wiersza, gdy nie ma własnego (bud_platnosc ma już wartość skuteczną)."""
    wynik = defaultdict(lambda: [0, 0])
    for r in RODZAJE:
        for n, ile in con.execute(f"SELECT TRIM(COALESCE({r}, '')), COUNT(*) FROM bud_wiersz GROUP BY 1"):
            wynik[(r, n)][0] += ile
    for r in ('kontrahent', 'metoda'):
        for n, ile in con.execute(f"SELECT TRIM(COALESCE({r}, '')), COUNT(*) FROM bud_platnosc WHERE COALESCE(ukryty, 0) = 0 GROUP BY 1"):
            wynik[(r, n)][1] += ile
    for r in ('przedmiot', 'sekcja'):
        for n, ile in con.execute(f"SELECT TRIM(COALESCE(w.{r}, '')), COUNT(*) FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz"
                                  " WHERE COALESCE(p.ukryty, 0) = 0 GROUP BY 1"):
            wynik[(r, n)][1] += ile
    return wynik


def _podpowiedzi_nip(con, nazwy) -> dict:
    """Pełna nazwa i NIP z Fakturowni dla kontrahenta bez NIP-u: nabywca, którego krótka nazwa to nazwa kontrahenta
    (albo zaczyna się od niej całym słowem); tylko gdy wynik jest jednoznaczny (jeden NIP)."""
    from .klienci import krotka_nazwa
    try:
        fv = con.execute("SELECT DISTINCT nabywca, nip FROM faktury WHERE COALESCE(nip, '') != '' AND COALESCE(nabywca, '') != ''").fetchall()
    except Exception:
        return {}
    po_kluczu = defaultdict(set)
    for nab, nip in fv:
        po_kluczu[norm(krotka_nazwa(nab))].add((nab.strip(), re.sub(r'\D', '', nip) or nip))
    wynik = {}
    for n in nazwy:
        k = norm(n)
        if len(k) < 3:
            continue
        traf = set(po_kluczu.get(k, set()))
        if not traf and len(k) >= 4:
            for kk, xs in po_kluczu.items():
                if kk.startswith(k + ' '):
                    traf |= xs
        if len({nip for _, nip in traf}) == 1:
            nab, nip = sorted(traf)[0]
            wynik[n] = {'nip': nip, 'pelna': nab}
    return wynik


def widok(con, planowanie: bool) -> dict:
    """Biblioteka dla interfejsu: słowniki z licznikami wystąpień, struktura z liczbą arkuszy, lista wszystkich arkuszy."""
    licz = _liczniki(con)
    rek = defaultdict(list)
    for r in con.execute('SELECT rodzaj, nazwa, dane FROM bud_slownik'):
        x = json.loads(r['dane'])
        w, p = licz.get((r['rodzaj'], r['nazwa']), (0, 0))
        x.update(etykieta=etykieta(r['rodzaj'], r['nazwa']), wiersze=w, platnosci=p, uzyc=w + p)
        rek[r['rodzaj']].append(x)
    podp = _podpowiedzi_nip(con, [x['nazwa'] for x in rek['kontrahent'] if x['nazwa'] and not x.get('nip')])
    for x in rek['kontrahent']:
        if x['nazwa'] in podp:
            x['podpowiedz'] = podp[x['nazwa']]
    for r in RODZAJE:
        rek[r].sort(key=lambda x: (not x.get('systemowy'), klucz_pl(x['nazwa']), x['nazwa']))
    arkusze = [dict(a) for a in con.execute(
        'SELECT a.id, a.folder, a.kategoria, a.nazwa, a.od, a.do, a.zrodlo, COUNT(w.id) AS wierszy FROM bud_arkusz a'
        ' LEFT JOIN bud_wiersz w ON w.arkusz = a.id GROUP BY a.id')]
    kolej = kolejnosc_folderow(con)
    arkusze.sort(key=lambda a: (kolej.get((a['folder'], a['kategoria']), (10 ** 6, 0)), klucz_pl(a['nazwa'])))
    po_miejscu = defaultdict(list)
    for a in arkusze:
        po_miejscu[(a['folder'], a['kategoria'])].append(a)
    struktura = []
    for r in con.execute('SELECT * FROM bud_struktura ORDER BY kf, kk'):
        if not struktura or struktura[-1]['folder'] != r['folder']:
            struktura.append({'folder': r['folder'], 'systemowy': bool(r['systemowy']), 'kategorie': []})
        ark = po_miejscu.get((r['folder'], r['kategoria']), [])
        struktura[-1]['kategorie'].append({'kategoria': r['kategoria'], 'arkusze': ark})
    for f in struktura:
        f['arkuszy'] = sum(len(k['arkusze']) for k in f['kategorie'])
    return {'planowanie': planowanie, 'kontrahent': rek['kontrahent'], 'przedmiot': rek['przedmiot'], 'sekcja': rek['sekcja'],
            'metoda': rek['metoda'], 'struktura': struktura, 'arkusze': arkusze, 'rachunki': list(RACHUNKI),
            'podstawy': list(PODSTAWY_DOMYSLNE), 'systemowe': SYSTEMOWE, 'folder_systemowy': FOLDER_SYSTEMOWY}


def dla_arkusza(con) -> dict:
    """Listy wyboru w kolumnach arkusza (A-ARK-14) i ustawienia domyślne do nowego wiersza (A-ARK-10, A-KOL-04)."""
    slowniki, wzorce, dom = defaultdict(list), {}, {}
    for r in con.execute('SELECT rodzaj, nazwa, dane FROM bud_slownik'):
        x = json.loads(r['dane'])
        if r['nazwa']:
            slowniki[r['rodzaj']].append(r['nazwa'])
        if x.get('domyslny'):
            dom[r['rodzaj']] = r['nazwa']
        if r['rodzaj'] == 'kontrahent' and x.get('ustawienia'):
            wzorce[r['nazwa']] = x['ustawienia']
    wynik = {r: _po_polsku(slowniki[r]) for r in RODZAJE}
    wynik['domyslne'] = {'kontrahent': dom.get('kontrahent', ''), 'przedmiot': dom.get('przedmiot', '')}
    d = dom.get('kontrahent', '')
    wzorce[d] = {**USTAWIENIA_STARTOWE, **wzorce.get(d, {})}   # kontrahent domyślny zawsze ma pełne ustawienia
    struktura = []
    for r in con.execute('SELECT folder, kategoria, systemowy FROM bud_struktura ORDER BY kf, kk'):
        if r['systemowy']:
            continue
        if not struktura or struktura[-1]['folder'] != r['folder']:
            struktura.append({'folder': r['folder'], 'kategorie': []})
        struktura[-1]['kategorie'].append(r['kategoria'])
    wynik['struktura'] = struktura
    return {'slowniki': wynik, 'wzorce': wzorce}
