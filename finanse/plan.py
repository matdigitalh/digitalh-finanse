"""Model planu jak w Budget Studio (pakiet 2): wiersz to generator, komórka (wiersz × miesiąc) ma kwotę,
a płatności planowane są jej pochodną liczoną przy każdej odbudowie.

Same reguły, bez bazy i plików (testowalne wprost):
  - podstawy i liczba płatności z jednej komórki (faktura, worek, bez faktury, umowy, daniny),
  - reguła dnia wystawienia (pierwszy, ostatni, wybrany dzień, przesunięcie o N miesięcy, księgowanie wg budżetu),
  - worek: tygodnie (domyślnie od wtorku, jak w BS) przycięte do miesiąca, kwota proporcjonalnie do dni, reszta groszy do ostatniego,
  - umowy: udziały z kwot referencyjnych od księgowej (bez własnych wzorów podatkowych), reszta zaokrąglenia do osoby,
  - nadpisania pojedynczego planu i reguła „zmiana w wierszu kasuje ręczny wyjątek”,
  - etap i aktualność jak w BS.
Kwoty w groszach (int), proporcje jako Fraction, zaokrąglenie połówkami w górę.
"""
import calendar
import math
import re
from datetime import date, timedelta
from fractions import Fraction

# Podstawy wiersza (BS) i składowe z eksportu BS (tam umowa o pracę ma trzy osobne wiersze; zostają do kopii z pakietu 6).
PODSTAWY_WIERSZA = ['Faktura (jedna)', 'Faktura (w worku)', 'Bez faktury', 'Bez faktury (w worku)', 'Umowa o dzieło',
                    'Umowa zlecenie', 'Umowa o pracę', 'Podatek VAT', 'Podatek dochodowy']
PODSTAWY_SKLADOWE_BS = ['Umowa o pracę - dla wykonawcy', 'Umowa o pracę - PIT', 'Umowa o pracę - ZUS']
WOREK = {'Faktura (w worku)', 'Bez faktury (w worku)'}
UMOWY = {'Umowa o dzieło': ('osoba', 'us'), 'Umowa zlecenie': ('osoba', 'us', 'zus'), 'Umowa o pracę': ('osoba', 'us', 'zus')}
PODATKI = {'Podatek VAT', 'Podatek dochodowy'}
# Odbiorca składowej na listach (kontrahent wszystkich składowych = osoba, „spinacz”)
ETYKIETY_SKLADOWYCH = {
    'Umowa o pracę': {'osoba': 'Umowa o pracę - dla pracownika', 'us': 'Umowa o pracę - PIT', 'zus': 'Umowa o pracę - ZUS'},
    'Umowa zlecenie': {'osoba': 'Umowa zlecenie - dla wykonawcy', 'us': 'Umowa zlecenie - PIT', 'zus': 'Umowa zlecenie - ZUS'},
    'Umowa o dzieło': {'osoba': 'Umowa o dzieło - dla wykonawcy', 'us': 'Umowa o dzieło - PIT'},
}
# Terminy składowych: PIT do 20., ZUS do 15. dnia miesiąca po miesiącu wypłaty (sp. z o.o.)
DZIEN_SKLADOWEJ = {'us': 20, 'zus': 15}

# Cecha-generator wiersza → pola planu, które ustawia (reguła nadpisań A-KOL-20, B-POD-05)
GENERATORY = {'kontrahent': ('kontrahent',), 'stawka_vat': ('stawka',),
              'dzien_wystawienia': ('wystawienie', 'termin', 'realny', 'ksiegowanie'), 'dni_na_platnosc': ('termin', 'realny'),
              'metoda': ('metoda',), 'ksiegowane': ('ksiegowane',), 'w_cashflow': ('w_cashflow',), 'komentarz': ('komentarz',)}
# Co wolno nadpisać na pojedynczym planie (poza decyzjami przesuń, zapłacone, anuluj, które wolno zawsze)
NADPISANIA_ZWYKLE = {'kontrahent', 'komentarz', 'stawka', 'wystawienie', 'termin', 'realny', 'ksiegowanie', 'metoda',
                     'ksiegowane', 'w_cashflow', 'tytul', 'aktualna'}
NADPISANIA_WOREK = {'kontrahent', 'komentarz'}
POLA_DECYZJI = {'decyzja', 'aktualna', 'termin', 'realny'}


def jest_umowa(podstawa: str) -> bool:
    return podstawa in UMOWY


def ma_vat(podstawa: str) -> bool:
    return (podstawa or '').startswith('Faktura')


def _zaokr(x: Fraction) -> int:
    """Połówki w górę (kwoty są nieujemne)."""
    return math.floor(x + Fraction(1, 2))


# ---------- Reguła dnia wystawienia ----------

_REGULA = re.compile(r'(?:(?P<slowo>ostatni|pierwszy)|(?P<dzien>[1-9]|[12]\d|3[01])\.?)(?:\s*(?P<przes>[+-]\d{1,2}))?(?:\s*(?P<b>b))?')


def regula(tekst) -> dict | None:
    """„Ostatni”, „Pierwszy”, „10.”, „10. +1”, „9. +1 B” (księgowanie wg miesiąca budżetu), „20. -1”. None dla „(auto)”
    i pustej (worek albo brak reguły: ostatni dzień). ValueError dla innych zapisów albo przesunięcia ponad 12 miesięcy."""
    t = str(tekst or '').strip()
    if t in ('', '(auto)'):
        return None
    m = _REGULA.fullmatch(t.lower())
    if not m:
        raise ValueError('dzień wystawienia: „Ostatni”, „Pierwszy” albo dzień miesiąca, opcjonalnie przesunięcie o miesiące (+1, -1)')
    dzien = 'ostatni' if m['slowo'] == 'ostatni' else 1 if m['slowo'] == 'pierwszy' else int(m['dzien'])
    przes = int(m['przes'] or 0)
    if abs(przes) > 12:
        raise ValueError('dzień wystawienia: przesunięcie najwyżej o 12 miesięcy')
    # księgowanie wg miesiąca budżetu tylko przy przesunięciu i dniu 1–15; dzień 16 i dalej: zawsze wg wystawienia
    budzet = bool(m['b']) and przes != 0 and dzien != 'ostatni' and dzien <= 15
    return {'dzien': dzien, 'przes': przes, 'budzet': budzet}


def regula_tekst(r: dict | None) -> str:
    """Zapis kanoniczny reguły (to trafia do wiersza)."""
    if not r:
        return '(auto)'
    t = 'Ostatni' if r['dzien'] == 'ostatni' else f"{r['dzien']}."
    if r['przes']:
        t += f" {r['przes']:+d}"
        if r['budzet']:
            t += ' B'
    return t


def regula_opis(tekst) -> str:
    """Po ludzku, do interfejsu: „10. dzień, miesiąc później, księgowanie wg budżetu”."""
    try:
        r = regula(tekst)
    except ValueError:
        return str(tekst or '')
    if not r:
        return 'automatycznie'
    d = 'ostatni dzień' if r['dzien'] == 'ostatni' else 'pierwszy dzień' if r['dzien'] == 1 else f"{r['dzien']}. dzień"
    p = r['przes']
    if p:
        n = abs(p)
        d += f", {'miesiąc' if n == 1 else f'{n} mies.'} {'później' if p > 0 else 'wcześniej'}"
        d += ', księgowanie wg budżetu' if r['budzet'] else ', księgowanie wg wystawienia'
    return d


def przesun_miesiac(m: str, o: int) -> str:
    r, mm = int(m[:4]), int(m[5:7]) - 1 + o
    return f'{r + mm // 12}-{mm % 12 + 1:02d}'


def ostatni_dzien(m: str) -> int:
    return calendar.monthrange(int(m[:4]), int(m[5:7]))[1]


def wystawienie_z_reguly(m: str, tekst) -> tuple[str, str]:
    """(data wystawienia, miesiąc księgowania jako RRRR-MM-01) dla komórki miesiąca m (miesiąc budżetowy)."""
    r = regula(tekst) or {'dzien': 'ostatni', 'przes': 0, 'budzet': False}
    cel = przesun_miesiac(m, r['przes'])
    ost = ostatni_dzien(cel)
    d = ost if r['dzien'] == 'ostatni' else min(r['dzien'], ost)
    wyst = f'{cel}-{d:02d}'
    return wyst, f"{m if r['budzet'] else cel}-01"


def dni_na_platnosc(v) -> int:
    """Liczba dni z zapisu wiersza (14, '14', 'Natychmiast', '46 (nietypowe)'); brak = 0."""
    if isinstance(v, bool) or v is None:
        return 0
    if isinstance(v, int):
        return v
    t = str(v).strip()
    if t.lower() == 'natychmiast':
        return 0
    m = re.match(r'\d+', t)
    return int(m.group()) if m else 0


def plus_dni(d: str, n: int) -> str:
    return (date.fromisoformat(d) + timedelta(days=n)).isoformat()


# ---------- Worek i umowy ----------

# Pierwszy dzień tygodnia worka: 1 = wtorek (decyzja Mata 2026-10-19, wieczór): BS dzieli tygodnie od wtorku do poniedziałku, a celem jest
# zgodność 1:1 z BS. Zmiana w Finanse/Aplikacja/ustawienia.json: "worek_pierwszy_dzien_tygodnia" (0 = poniedziałek).
PIERWSZY_DZIEN_TYGODNIA = 1


def tygodnie(m: str, pierwszy: int = PIERWSZY_DZIEN_TYGODNIA) -> list[tuple[str, int]]:
    """Tygodnie kalendarzowe (domyślnie od wtorku) zahaczające o miesiąc, przycięte do jego granic: (pierwszy dzień części, liczba dni)."""
    ost = ostatni_dzien(m)
    wynik, d = [], 1
    while d <= ost:
        start = date(int(m[:4]), int(m[5:7]), d)
        dlugosc = min(7 - (start.weekday() - pierwszy) % 7, ost - d + 1)
        wynik.append((start.isoformat(), dlugosc))
        d += dlugosc
    return wynik


def podziel_worek(kwota: int, m: str, pierwszy: int = PIERWSZY_DZIEN_TYGODNIA) -> list[tuple[str, int]]:
    """Kwota miesięczna na tygodnie proporcjonalnie do liczby dni; zaokrąglenie do grosza, reszta do ostatniego tygodnia."""
    tyg = tygodnie(m, pierwszy)
    dni = ostatni_dzien(m)
    czesci = [(start, _zaokr(Fraction(kwota * n, dni))) for start, n in tyg[:-1]]
    return czesci + [(tyg[-1][0], kwota - sum(k for _, k in czesci))]


def podziel_umowe(kwota: int, proporcje: dict | None, skladowe=('osoba', 'us', 'zus')) -> dict[str, int]:
    """Komórka umowy na składowe wg udziałów z kwot referencyjnych (udział = kwota / suma, pełna precyzja).
    US i ZUS zaokrąglone połówkami w górę, osoba = reszta, więc suma zawsze równa komórce. Udział może być 0."""
    prop = {k: int((proporcje or {}).get(k) or 0) for k in skladowe}
    suma = sum(prop.values())
    if not suma:
        return {k: (kwota if k == 'osoba' else 0) for k in skladowe}
    wynik = {k: _zaokr(Fraction(kwota * prop[k], suma)) for k in skladowe if k != 'osoba'}
    wynik['osoba'] = kwota - sum(wynik.values())
    return {k: wynik[k] for k in skladowe}


# ---------- Generator płatności planowanych z komórki ----------

def vat(netto: int, stawka, podstawa: str) -> int:
    if stawka in (None, '') or not ma_vat(podstawa):
        return 0
    return _zaokr(Fraction(int(netto) * int(stawka), 100))


def _stawka_wiersza(w: dict):
    from .budzet import stawka_proc
    return stawka_proc(w.get('stawka_vat')) if ma_vat(w.get('podstawa', '')) else None


def id_planu(wid: str, m: str, k: str) -> str:
    return f'plan:{wid}:{m}:{k}'


def nadpisz(p: dict, n: dict, dni: int):
    """Ręczne zmiany pojedynczego planu na wartościach z wiersza. Zmiana dnia wystawienia przesuwa termin o te same dni,
    zmiana terminu ustawia dzień realny = termin (chyba że realny też zmieniony ręcznie)."""
    for k in ('kontrahent', 'komentarz', 'metoda', 'ksiegowane', 'w_cashflow', 'stawka', 'tytul', 'aktualna', 'decyzja'):
        if k in n:
            p[k] = n[k]
    if n.get('wystawienie'):
        p['wystawienie'] = n['wystawienie']
        p['termin'] = plus_dni(n['wystawienie'], dni)
        p['ksiegowanie'] = n['wystawienie'][:7] + '-01'
    if n.get('termin'):
        p['termin'] = n['termin']
    p['realny'] = n.get('realny') or p['termin']
    if n.get('ksiegowanie'):
        p['ksiegowanie'] = n['ksiegowanie']


def podzial_pasuje(podzial, kwota: int) -> bool:
    """Podział komórki przeniesiony z kopii BS (pakiet 6) obowiązuje, dopóki sumuje się do kwoty do podziału;
    po zmianie kwoty komórki (albo rzeczywistych w worku) plany liczą się znowu z reguły."""
    if isinstance(podzial, dict):
        return sum(int(v) for v in podzial.values()) == kwota
    return isinstance(podzial, list) and bool(podzial) and sum(int(k) for _, k in podzial) == kwota


def generuj_komorke(w: dict, m: str, kwota: int, nadpisane: dict | None = None,
                    pierwszy_dzien_tygodnia: int = PIERWSZY_DZIEN_TYGODNIA, podzial=None) -> list[dict]:
    """Płatności planowane z kwoty w komórce wg podstawy wiersza. Kwota 0 = jeden ukryty plan 0 (miejsce na rzeczywistą).
    nadpisane: {id planu: {pole: wartość}} z kart płatności. podzial: podział z kopii BS (worek: [[dzień, kwota], ...],
    umowa: {osoba, us, zus}), używany tylko, gdy sumuje się do kwoty."""
    nadpisane = nadpisane or {}
    if podzial is not None and not podzial_pasuje(podzial, kwota):
        podzial = None
    pod = w.get('podstawa', '')
    dni = dni_na_platnosc(w.get('dni_na_platnosc'))
    umowa = jest_umowa(pod)
    stawka = _stawka_wiersza(w)
    baza = {'wiersz': w['id'], 'miesiac': m, 'typ': 'plan', 'etap_bs': 'Planowana', 'aktualna': True, 'nr_dok': '', 'nr_wewn': '',
            'tytul': '', 'metoda': w.get('metoda', ''), 'ksiegowane': True if umowa else bool(w.get('ksiegowane', True)),
            'w_cashflow': bool(w.get('w_cashflow', True)), 'komentarz': w.get('komentarz', ''), 'stawka': stawka,
            'zrodlo': 'komórka', 'generowany': True}

    def plan(k, netto, wyst, ksieg, skladowa=None):
        p = {**baza, 'id': id_planu(w['id'], m, k), 'netto': netto, 'wystawienie': wyst, 'termin': plus_dni(wyst, dni),
             'ksiegowanie': ksieg}
        p['realny'] = p['termin']
        if skladowa:
            p['skladowa'] = skladowa
        n = nadpisane.get(p['id'], {})
        nadpisz(p, n, dni)
        if p.get('stawka') is not None and not ma_vat(pod):
            p['stawka'] = None
        p['vat'] = vat(p['netto'], p.get('stawka'), pod)
        p['brutto'] = p['netto'] + p['vat']
        p['nadpisane'] = dict(n)
        return p

    if pod in WOREK:
        czesci = ([(d, int(k)) for d, k in podzial] if isinstance(podzial, list) else
                  podziel_worek(kwota, m, pierwszy_dzien_tygodnia) if kwota else [(f'{m}-01', 0)])
        wynik = [plan(f't{i}', k, start, f'{m}-01') for i, (start, k) in enumerate(czesci, start=1)]
    elif umowa:
        skladowe = UMOWY[pod]
        kwoty = ({k: int(podzial.get(k, 0)) for k in skladowe} if isinstance(podzial, dict) else
                 podziel_umowe(kwota, w.get('proporcje'), skladowe) if kwota else {'osoba': 0})
        wyst, ksieg = wystawienie_z_reguly(m, w.get('dzien_wystawienia'))
        osoba = plan('osoba', kwoty['osoba'], wyst, ksieg, 'osoba')
        wynik = [osoba]
        for s in skladowe[1:]:
            if s not in kwoty:
                continue
            # US i ZUS: wystawienie = składowej dla osoby (nieedytowalne), termin 20./15. dnia miesiąca po wypłacie
            p = plan(s, kwoty[s], osoba['wystawienie'], osoba['ksiegowanie'], s)
            n = nadpisane.get(p['id'], {})
            p['termin'] = n.get('termin') or f"{przesun_miesiac(osoba['termin'][:7], 1)}-{DZIEN_SKLADOWEJ[s]:02d}"
            p['realny'] = n.get('realny') or p['termin']
            p['spinacz'] = osoba['id']
            wynik.append(p)
    else:
        wyst, ksieg = wystawienie_z_reguly(m, w.get('dzien_wystawienia'))
        wynik = [plan('1', kwota, wyst, ksieg)]
    if not kwota:
        for p in wynik:
            p['ukryty'] = True
    return wynik


def przelicz_jawny(p: dict, w: dict, pola: set) -> dict:
    """Plan spoza komórki (z importu BS, kopia) po zmianie cech-generatorów w wierszu: te cechy przechodzą z wiersza
    (ręczne zmiany tych cech giną). Rzeczywistych ta funkcja nie dostaje."""
    p = dict(p)
    pod = w.get('podstawa', '')
    dni = dni_na_platnosc(w.get('dni_na_platnosc'))
    if 'kontrahent' in pola:
        p.pop('kontrahent', None)
    for k in ('komentarz', 'metoda', 'w_cashflow'):
        if k in pola:
            p[k] = w.get(k, '' if k != 'w_cashflow' else True)
    if 'ksiegowane' in pola:
        p['ksiegowane'] = True if jest_umowa(pod) else bool(w.get('ksiegowane', True))
    if 'dzien_wystawienia' in pola and pod not in WOREK:
        p['wystawienie'], p['ksiegowanie'] = wystawienie_z_reguly(p['miesiac'], w.get('dzien_wystawienia'))
        pola = pola | {'dni_na_platnosc'}
    if 'dni_na_platnosc' in pola and p.get('wystawienie'):
        p['termin'] = plus_dni(p['wystawienie'], dni)
        p['realny'] = p['termin']
    if 'stawka_vat' in pola:
        p['stawka'] = _stawka_wiersza(w)
        p['vat'] = vat(p['netto'], p['stawka'], pod)
        p['brutto'] = p['netto'] + p['vat']
    return p


# ---------- Odstępstwa płatności od ustawień wiersza (A-ARK-11, A-KOL-20) ----------

def odstepstwa(p: dict, w: dict) -> list[str]:
    """Cechy planu różne od tego, co wynika z ustawień wiersza, czyli ręczne wyjątki (A-ARK-11). Interfejs podświetla je
    na pomarańczowo w karcie i w panelu podglądu. Rzeczywista ma dane z dokumentu (kontrahent, komentarz, daty z faktury
    zawsze wygrywają), więc nie jest wyjątkiem: dla niej lista pusta. Daty sprawdzamy wg reguły dnia wystawienia i dni
    na płatność; przy regule „(auto)” (wiersz z importu bez jednej reguły) dat nie oceniamy."""
    from .budzet import stawka_proc
    if p.get('typ', 'plan') != 'plan':
        return []
    pod = w.get('podstawa', '')
    umowa = jest_umowa(pod)
    wynik = []
    if (p.get('kontrahent') or w.get('kontrahent') or '') != (w.get('kontrahent') or ''):
        wynik.append('kontrahent')
    for k in ('komentarz', 'metoda'):
        if (p.get(k) or '') != (w.get(k) or ''):
            wynik.append(k)
    if bool(p.get('ksiegowane', True)) != (True if umowa else bool(w.get('ksiegowane', True))):
        wynik.append('ksiegowane')
    if bool(p.get('w_cashflow', True)) != bool(w.get('w_cashflow', True)):
        wynik.append('w_cashflow')
    if ma_vat(pod) and stawka_proc(p.get('stawka')) != stawka_proc(w.get('stawka_vat')):
        wynik.append('stawka')
    if p.get('skladowa') in ('us', 'zus') or not p.get('wystawienie'):
        return wynik
    dni = dni_na_platnosc(w.get('dni_na_platnosc'))
    if pod not in WOREK:
        try:
            r = regula(w.get('dzien_wystawienia'))
        except ValueError:
            r = None
        if r is None:   # „(auto)” albo zapis spoza reguł: daty bez oceny
            return wynik
        wyst, ksieg = wystawienie_z_reguly(p['miesiac'], w.get('dzien_wystawienia'))
        if p['wystawienie'] != wyst:
            wynik.append('wystawienie')
            ksieg = p['wystawienie'][:7] + '-01'
        if p.get('ksiegowanie') and p['ksiegowanie'][:7] != ksieg[:7]:
            wynik.append('ksiegowanie')
    termin = plus_dni(p['wystawienie'], dni)
    if p.get('termin') and p['termin'] != termin:
        wynik.append('termin')
    if p.get('realny') and p['realny'] != (p.get('termin') or termin):
        wynik.append('realny')
    return wynik


# ---------- Etap i aktualność (B-MOD-08 do 10) ----------

def etap_wg_bs(typ: str, oplacona: bool, termin: str | None, dzis: str) -> str:
    """Plan: „Planowana”; rzeczywista opłacona: „Opłacona”; nieopłacona po dniu płatności: „Po terminie”; reszta: „Niewymagana”."""
    if typ == 'plan':
        return 'Planowana'
    if oplacona:
        return 'Opłacona'
    if termin and dzis > termin:
        return 'Po terminie'
    return 'Niewymagana'


def aktualna_wg_bs(typ: str, oplacona: bool, wystawienie, termin, realny, dzis: str) -> bool:
    """Plan nieaktualny, gdy minął którykolwiek z jego dni (wystawienia, płatności, realnej płatności). Rzeczywista
    nieaktualna, gdy nieopłacona i minął dzień realnej płatności. Opłacona zawsze aktualna. „Minął” = data < dzień stanu."""
    if typ == 'plan':
        return not any(d and d < dzis for d in (wystawienie, termin, realny))
    if oplacona:
        return True
    r = realny or termin
    return not (r and r < dzis)


def zakres_daty_planu(d: str, dzis: str):
    """Data wpisana ręcznie na planie: najwyżej 5 lat od dnia stanu w obie strony (B-CEC-11)."""
    if not d:
        return
    od, do = f'{int(dzis[:4]) - 5}{dzis[4:]}', f'{int(dzis[:4]) + 5}{dzis[4:]}'
    if not od <= d <= do:
        raise ValueError(f'data {d} poza zakresem: plan może mieć datę najwyżej 5 lat od dziś')
