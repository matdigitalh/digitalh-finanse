"""Filtry list (pakiet 7): zakres dat z trybów Budget Studio liczony od dnia stanu (A-FIL-01 do 07), sortowanie
tekstu po polsku, sortowanie z białej listy kolumn (APK-BRAK-09) i podsumowanie zaznaczenia. Czyste funkcje bez bazy.

Zapis filtra daty w adresie (`d_<typ daty>=…`), przeliczany przy każdym otwarciu listy:
  wszystko                         filtr nieaktywny
  biezacy:<tydzien|miesiac|kwartal|rok>     bieżący okres (tydzień nie dla miesięcy, kwartał tylko dla miesięcy)
  dokonca:<tydzien|miesiac|kwartal|rok>     od dziś do końca bieżącego okresu
  zakres:<od>:<do>                 zakres statyczny (RRRR-MM-DD, dla miesięcy RRRR-MM); jedna strona może być pusta
  ruchomy:<jednostka>:<N>:<K>[:<dzień tygodnia>]   zakres ruchomy: start = początek(bieżący okres) + K, koniec = start + N - 1
      jednostka: dzien (od dziś), dzien_tyg (kotwica w wybranym dniu tygodnia, 0 = poniedziałek), miesiac, kwartal, rok
“Dziś” = dzień stanu (ostatni dzień księgowania w ING), jak w całej apce.
"""
import calendar
from datetime import date, timedelta

JEDNOSTKI_OKRESU = ('tydzien', 'miesiac', 'kwartal', 'rok')
JEDNOSTKI_RUCHOME = ('dzien', 'dzien_tyg', 'miesiac', 'kwartal', 'rok')
MAKS_N = 3660          # dni (10 lat); dla miesięcy, kwartałów i lat mniej, patrz _sprawdz_n
MAKS_K = 3660


def _plus_mies(d: date, n: int) -> date:
    """Pierwszy dzień miesiąca przesuniętego o n miesięcy względem miesiąca daty d."""
    x = d.year * 12 + d.month - 1 + n
    return date(x // 12, x % 12 + 1, 1)


def _koniec_mies(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def poczatek_okresu(dzis: date, jednostka: str, pierwszy_dzien_tyg: int = 0) -> date:
    if jednostka == 'tydzien':
        return dzis - timedelta(days=(dzis.weekday() - pierwszy_dzien_tyg) % 7)
    if jednostka == 'miesiac':
        return date(dzis.year, dzis.month, 1)
    if jednostka == 'kwartal':
        return date(dzis.year, 3 * ((dzis.month - 1) // 3) + 1, 1)
    if jednostka == 'rok':
        return date(dzis.year, 1, 1)
    raise ValueError('nieznana jednostka okresu')


def koniec_okresu(dzis: date, jednostka: str, pierwszy_dzien_tyg: int = 0) -> date:
    p = poczatek_okresu(dzis, jednostka, pierwszy_dzien_tyg)
    if jednostka == 'tydzien':
        return p + timedelta(days=6)
    return _plus_mies(p, {'miesiac': 1, 'kwartal': 3, 'rok': 12}[jednostka]) - timedelta(days=1)


def _liczba(t: str, pole: str, lo: int, hi: int) -> int:
    try:
        v = int(t)
    except (TypeError, ValueError):
        raise ValueError(f'filtr daty: {pole} musi być liczbą całkowitą')
    if not lo <= v <= hi:
        raise ValueError(f'filtr daty: {pole} od {lo} do {hi}')
    return v


def _data_lub_miesiac(t: str, miesieczny: bool, koniec: bool) -> date | None:
    if not t:
        return None
    try:
        if len(t) == 7:
            d = date.fromisoformat(t + '-01')
            return _koniec_mies(d) if koniec else d
        d = date.fromisoformat(t)
    except ValueError:
        raise ValueError('filtr daty: data RRRR-MM-DD albo miesiąc RRRR-MM')
    if miesieczny:   # zakres miesięcy: od początku miesiąca „od” do końca miesiąca „do”
        return _koniec_mies(d) if koniec else date(d.year, d.month, 1)
    return d


def zakres(spec: str | None, dzis: date, miesieczny: bool = False, pierwszy_dzien_tyg: int = 0) -> tuple | None:
    """(od, do) jako daty (każda może być None przy zakresie otwartym) albo None, gdy filtr nieaktywny.
    miesieczny: miesiąc księgowania i budżetowy (bez trybów dziennych i tygodnia, z kwartałem)."""
    spec = (spec or '').strip()
    if not spec or spec == 'wszystko':
        return None
    czesci = spec.split(':')
    tryb = czesci[0]
    if tryb in ('biezacy', 'dokonca'):
        if len(czesci) != 2 or czesci[1] not in JEDNOSTKI_OKRESU:
            raise ValueError('filtr daty: okres tydzień, miesiąc, kwartał albo rok')
        j = czesci[1]
        if miesieczny and j == 'tydzien':
            raise ValueError('filtr daty: tydzień niedostępny dla miesiąca księgowania i budżetowego')
        if tryb == 'biezacy' and not miesieczny and j == 'kwartal':
            raise ValueError('filtr daty: bieżący kwartał tylko dla miesiąca księgowania i budżetowego')
        start = poczatek_okresu(dzis, j, pierwszy_dzien_tyg) if tryb == 'biezacy' else dzis
        if miesieczny:
            start = date(start.year, start.month, 1)
        return start, koniec_okresu(dzis, j, pierwszy_dzien_tyg)
    if tryb == 'zakres':
        if len(czesci) != 3:
            raise ValueError('filtr daty: zakres od:do')
        od, do = _data_lub_miesiac(czesci[1], miesieczny, False), _data_lub_miesiac(czesci[2], miesieczny, True)
        if od is None and do is None:
            return None
        if od and do and od > do:
            raise ValueError('filtr daty: początek zakresu po końcu')
        return od, do
    if tryb == 'ruchomy':
        if len(czesci) not in (4, 5) or czesci[1] not in JEDNOSTKI_RUCHOME:
            raise ValueError('filtr daty: zakres ruchomy jednostka:długość:przesunięcie')
        j = czesci[1]
        if miesieczny and j in ('dzien', 'dzien_tyg'):
            raise ValueError('filtr daty: dla miesiąca księgowania i budżetowego jednostka miesiąc, kwartał albo rok')
        mnoznik = {'dzien': 1, 'dzien_tyg': 1, 'miesiac': 1, 'kwartal': 3, 'rok': 12}[j]
        hi = MAKS_N if mnoznik == 1 else MAKS_N // 30 // mnoznik
        n = _liczba(czesci[2], 'długość', 1, hi)
        k = _liczba(czesci[3], 'przesunięcie', -MAKS_K // (1 if mnoznik == 1 else 30 * mnoznik), MAKS_K // (1 if mnoznik == 1 else 30 * mnoznik))
        if j in ('dzien', 'dzien_tyg'):
            if j == 'dzien_tyg':
                if len(czesci) != 5:
                    raise ValueError('filtr daty: wybierz dzień tygodnia')
                wd = _liczba(czesci[4], 'dzień tygodnia', 0, 6)
                poczatek = dzis - timedelta(days=(dzis.weekday() - wd) % 7)
            else:
                poczatek = dzis
            start = poczatek + timedelta(days=k)
            return start, start + timedelta(days=n - 1)
        poczatek = poczatek_okresu(dzis, j)
        start = _plus_mies(poczatek, k * mnoznik)
        return start, _plus_mies(start, n * mnoznik) - timedelta(days=1)
    raise ValueError('filtr daty: nieznany tryb')


def warunek(kolumna_sql: str, spec: str | None, dzis: date, miesieczny: bool = False, pierwszy_dzien_tyg: int = 0):
    """(fragment SQL, parametry) dla kolumny z datą ISO; dla miesięcy porównanie po RRRR-MM. Brak filtra: (None, [])."""
    z = zakres(spec, dzis, miesieczny, pierwszy_dzien_tyg)
    if not z:
        return None, []
    od, do = z
    wyr = f'substr({kolumna_sql}, 1, 7)' if miesieczny else f'substr({kolumna_sql}, 1, 10)'
    warunki, params = [], []
    if od:
        warunki.append(f'{wyr} >= ?')
        params.append(od.isoformat()[:7] if miesieczny else od.isoformat())
    if do:
        warunki.append(f'{wyr} <= ?')
        params.append(do.isoformat()[:7] if miesieczny else do.isoformat())
    return '(' + ' AND '.join(warunki) + ')', params


def podglad(spec: str, dzis: date, miesieczny: bool = False, pierwszy_dzien_tyg: int = 0) -> dict:
    """Symulacja jak w BS: jakie daty filtr obejmie dziś, jutro i za miesiąc."""
    def f(d):
        z = zakres(spec, d, miesieczny, pierwszy_dzien_tyg)
        return None if not z else [x.isoformat() if x else None for x in z]
    jutro = dzis + timedelta(days=1)
    za_miesiac = _plus_mies(dzis, 1)
    za_miesiac = za_miesiac.replace(day=min(dzis.day, calendar.monthrange(za_miesiac.year, za_miesiac.month)[1]))
    return {'dzis': f(dzis), 'jutro': f(jutro), 'za_miesiac': f(za_miesiac),
            'daty': [dzis.isoformat(), jutro.isoformat(), za_miesiac.isoformat()]}


# ---------- Sortowanie ----------

_POLSKIE = {'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z'}
_RANGA = {'ź': '\x01', 'ż': '\x02'}


def klucz_pl(s) -> str:
    """Klucz porządku alfabetu polskiego: a < ą < b ... z < ź < ż, bez rozróżniania wielkości liter."""
    wynik = []
    for c in str(s or '').casefold():
        b = _POLSKIE.get(c)
        wynik.append(c + '\x00' if b is None else b + _RANGA.get(c, '\x01'))
    return ''.join(wynik)


def porownaj_pl(a, b) -> int:
    ka, kb = klucz_pl(a), klucz_pl(b)
    return (ka > kb) - (ka < kb)


def z_kolacja(con):
    """Rejestruje porządek PL na połączeniu (sortowanie tekstu w listach)."""
    con.create_collation('PL', porownaj_pl)
    return con


def porzadek(sortuj, kolejnosc, kolumny: dict, domyslny: str, dalej: str = '') -> str:
    """ORDER BY z białej listy: klucz z interfejsu → (wyrażenie SQL, tekst?). Nieznany klucz = porządek domyślny.
    Tekst sortowany po polsku, puste na końcu w obu kierunkach; zawsze ze stabilnym dalszym porządkiem."""
    if sortuj not in kolumny:
        return domyslny + (f', {dalej}' if dalej else '')
    wyr, tekst = kolumny[sortuj]
    kier = 'ASC' if kolejnosc == 'rosnaco' else 'DESC'
    puste = f'({wyr}) IS NULL OR ({wyr}) = \'\''
    czesc = f'{puste}, ({wyr}) COLLATE PL {kier}' if tekst else f'({wyr}) IS NULL, ({wyr}) {kier}'
    return czesc + (f', {dalej}' if dalej else '')


def lista_wartosci(v) -> list[str]:
    """Wielokrotny wybór w adresie: wartości rozdzielone znakiem |."""
    if v is None or v == '':
        return []
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if str(x) != '']
    return [x for x in str(v).split('|') if x != '']


# ---------- Podsumowanie zaznaczenia ----------

def podsumuj(wiersze) -> dict:
    """Pasek podsumowania zaznaczenia: liczba, netto, VAT, brutto osobno dla wpływów i obciążeń oraz razem.
    Wiersz: rodzaj (1 albo -1) i kwoty ze znakiem (obciążenia ujemne); brak kwoty (None) nie liczy się do sumy."""
    pusty = lambda: {'ile': 0, 'netto': 0, 'vat': 0, 'brutto': 0}
    w = {'wplywy': pusty(), 'obciazenia': pusty()}
    for x in wiersze:
        g = w['wplywy' if (x.get('rodzaj') or 0) > 0 else 'obciazenia']
        g['ile'] += 1
        for k in ('netto', 'vat', 'brutto'):
            if x.get(k) is not None:
                g[k] += int(x[k])
    w['ile'] = w['wplywy']['ile'] + w['obciazenia']['ile']
    w['razem'] = {k: w['wplywy'][k] + w['obciazenia'][k] for k in ('netto', 'vat', 'brutto')}
    return w
