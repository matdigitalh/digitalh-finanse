"""Wpisy Mata (reguły, umowy, zatwierdzenia dopasowań) jako dziennik zmian w iCloud.

Każdy Mac dopisuje wyłącznie do własnego pliku `zmiany/<nazwa-Maca>.jsonl`, więc iCloud nigdy nie
widzi dwóch wersji jednego pliku. Stan powstaje przez złożenie wpisów ze wszystkich plików po czasie.
"""
import json
import re
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from . import konfig


def _plik_tego_maca() -> Path:
    return konfig.katalog_prywatny(konfig.katalog_zmian()) / f'{konfig.nazwa_maca()}.jsonl'


# Dozwolone wpisy i ich wymagane pola (etap 2: decyzje o wpłatach i fakturach).
TYPY = {
    'polacz': ('operacja', 'faktury'),        # połącz wpłatę z fakturami
    'bez_faktury': ('operacja', 'powod'),     # wpłata nie dotyczy faktury (zwrot, cashback, odsetki)
    'zatwierdz': ('operacja', 'faktura'),     # potwierdź dopasowanie „prawdopodobne”
    'odrzuc': ('operacja', 'faktura'),        # odrzuć dopasowanie automatu
    'poza_bankiem': ('faktura', 'powod'),     # faktura opłacona inaczej (kompensata, gotówka)
    'klient_nip': ('nabywca', 'klient'),      # faktury tego nabywcy (NIP) należą do klienta
    'klient_faktura': ('faktura', 'klient'),  # jedna faktura należy do klienta (nabywca płaci za kilku klientów)
    'koszt_regula': ('kontrahent', 'rodzaj', 'klient'),   # wszystkie płatności do kontrahenta: rodzaj i klient
    'koszt_operacja': ('operacja', 'rodzaj', 'klient'),   # jedna płatność: rodzaj i klient
    'korekta': ('numer', 'faktura', 'kwota'),  # korekta wpisana ręcznie: numer, faktura pierwotna, kwota brutto (grosze)
    'konto_reklamowe': ('konto', 'klient'),   # konto Google Ads / Meta należy do klienta
    'cel': ('klucz', 'wartosc'),              # cel controllingu: obrót roczny (grosze), marża %, rezerwa w miesiącach
    'bud': ('op',),                           # zmiana w budżecie (arkusz, wiersz, komórka, płatność, przenieś, decyzja planu)
    'ustawienie': ('klucz', 'wartosc'),       # ustawienia apki, np. planowanie w apce włączone
    'estymata': ('klient', 'udzial'),         # udział czasu zespołu dla klienta (%), do rentowności
    'umowa': ('id',),                         # umowa z klientem (rejestr umów)
    'cofnij': ('wpis',),                      # unieważnij wcześniejszy wpis
}
OPERACJE_BUD = ('arkusz', 'wiersz', 'platnosc', 'komorka', 'przenies', 'decyzja_planu', 'seria',
                # pakiet 3: akcje na wierszach i arkuszu liczone na serwerze (reguły BS w jednym miejscu)
                'scal', 'podziel', 'duplikuj', 'przesun_arkusz', 'duplikuj_arkusz')
MAKS_SERIA = 1000   # operacji w jednym wpisie „seria” (wklejenie bloku, duplikowanie wielu wierszy)
MAKS_MIESIECY = 240   # zakres arkusza: najwyżej 20 lat (A-KOM-07)
# Nazwy pól w komunikatach (po ludzku, jak w BS)
NAZWY_POL = {'nazwa': 'Nazwa arkusza', 'folder': 'Folder', 'kategoria': 'Kategoria', 'komentarz': 'Komentarz', 'kontrahent': 'Kontrahent',
             'przedmiot': 'Przedmiot transakcji', 'sekcja': 'Sekcja', 'metoda': 'Metoda płatności', 'tytul': 'Tytuł',
             'dni_na_platnosc': 'Dni na płatność', 'od': 'Początek zakresu', 'do': 'Koniec zakresu', 'miesiac': 'Miesiąc'}
USTAWIENIA = {'planowanie': ('tak', 'nie')}
CELE = {'cel_obrot_rok': (0, 10 ** 11), 'cel_marza_proc': (0, 100), 'rezerwa_miesiecy': (0, 24)}
RODZAJE = ('przenoszony', 'staly', 'praca', 'podatki', 'vat', 'dywidenda', 'zwrot', 'nieprzypisany')


def sprawdz(typ: str, dane) -> dict:
    """Waliduje wpis z interfejsu. Zwraca dane tylko z dozwolonymi polami."""
    if typ not in TYPY or not isinstance(dane, dict):
        raise ValueError('nieznany rodzaj wpisu')
    czyste = {}
    if typ == 'bud':
        return _sprawdz_bud(dane)
    if typ == 'ustawienie':
        if dane.get('klucz') not in USTAWIENIA or dane.get('wartosc') not in USTAWIENIA[dane.get('klucz')]:
            raise ValueError('nieznane ustawienie')
        return {'klucz': dane['klucz'], 'wartosc': dane['wartosc']}
    if typ == 'umowa':
        return _sprawdz_umowe(dane)
    if typ == 'estymata':
        try:
            u = float(str(dane.get('udzial')).replace(',', '.'))
        except ValueError:
            raise ValueError('udział w procentach')
        if not 0 <= u <= 100 or not str(dane.get('klient') or '').strip():
            raise ValueError('udział 0–100% i klient')
        return {'klient': str(dane['klient']).strip()[:80], 'udzial': u, 'od': str(dane.get('od') or '')[:7]}
    for pole in TYPY[typ]:
        v = dane.get(pole)
        if pole == 'faktury':
            if not isinstance(v, list) or not v or not all(isinstance(x, str) and 0 < len(x) <= 60 for x in v) or len(v) > 30:
                raise ValueError('lista faktur jest pusta albo nieprawidłowa')
        elif pole == 'powod':
            v = str(v or '').strip()[:200]
        elif pole == 'klient':
            v = str(v or '').strip()[:80]
            if typ in ('klient_nip', 'klient_faktura') and not v:
                raise ValueError('brak nazwy klienta')
        elif pole == 'klucz' and typ == 'cel':
            if v not in CELE:
                raise ValueError('nieznany cel')
        elif pole == 'kwota':
            try:
                v = abs(int(str(v)))
            except ValueError:
                raise ValueError('kwota korekty w groszach')
            if not 0 < v < 10 ** 10:
                raise ValueError('kwota korekty poza zakresem')
        elif pole == 'numer':
            v = str(v or '').strip()[:60]
            if not v:
                raise ValueError('brak numeru korekty')
        elif pole == 'wartosc':
            try:
                v = float(str(v).replace(',', '.'))
            except ValueError:
                raise ValueError('wartość celu musi być liczbą')
            lo, hi = CELE.get(dane.get('klucz'), (0, 0))
            if not lo <= v <= hi:
                raise ValueError('wartość celu poza zakresem')
            v = int(v) if dane.get('klucz') == 'cel_obrot_rok' else v
        elif pole == 'rodzaj':
            if v not in RODZAJE:
                raise ValueError('nieznany rodzaj kosztu')
        elif not isinstance(v, str) or not v or len(v) > 300:
            raise ValueError(f'brak pola {pole}')
        czyste[pole] = v
    return czyste


def zapisz(typ: str, dane: dict) -> dict:
    """Dopisuje jeden wpis. Zapis jednym write + fsync, plik 600."""
    wpis = {'czas': datetime.now(timezone.utc).isoformat(timespec='microseconds'), 'id': uuid.uuid4().hex,
            'mac': konfig.nazwa_maca(), 'typ': typ, 'dane': dane}
    p = _plik_tego_maca()
    fd = os.open(p, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(wpis, ensure_ascii=False) + '\n').encode('utf-8'))
        os.fsync(fd)
    finally:
        os.close(fd)
    return wpis


def wczytaj() -> tuple[list[dict], list[str]]:
    """Wszystkie wpisy ze wszystkich Maców, po czasie. Drugi element: ostrzeżenia (np. ucięta linia)."""
    katalog = konfig.katalog_zmian()
    wpisy, ostrzezenia = [], []
    if not katalog.exists():
        return wpisy, ostrzezenia
    for p in sorted(katalog.glob('*.jsonl')):
        for nr, linia in enumerate(p.read_text(encoding='utf-8').splitlines(), start=1):
            if not linia.strip():
                continue
            try:
                wpisy.append(json.loads(linia))
            except json.JSONDecodeError:
                ostrzezenia.append(f'{p.name}, linia {nr}: nieczytelny wpis (może jeszcze się synchronizuje)')
    for p in katalog.glob('*conflict*'):
        ostrzezenia.append(f'iCloud zrobił kopię konfliktu: {p.name}')
    wpisy.sort(key=lambda w: (w.get('czas', ''), w.get('id', '')))
    return wpisy, ostrzezenia


def odcisk() -> str:
    """Stan plików zmian (nazwa, rozmiar, czas) do wykrycia wpisów z drugiego Maca."""
    katalog = konfig.katalog_zmian()
    if not katalog.exists():
        return ''
    return ';'.join(f'{p.name}:{p.stat().st_size}:{int(p.stat().st_mtime)}' for p in sorted(katalog.glob('*.jsonl')))


_DATA = re.compile(r'\d{4}-\d{2}-\d{2}')
_MIESIAC = re.compile(r'\d{4}-(0[1-9]|1[0-2])')


def _tekst(maks):
    def f(v, pole):
        if v is None:
            return ''
        if not isinstance(v, (str, int)) or isinstance(v, bool):
            raise ValueError(f'{NAZWY_POL.get(pole, pole)}: oczekiwany tekst')
        v = str(v).strip()
        if len(v) > maks:
            raise ValueError(f'{NAZWY_POL.get(pole, pole)}: najwyżej {maks} znaków (jest {len(v)}). Skróć tekst.')
        return v
    return f


def _niepusty(maks):
    t = _tekst(maks)

    def f(v, pole):
        v = t(v, pole)
        if not v:
            raise ValueError(f'{NAZWY_POL.get(pole, pole)}: pole nie może być puste. Wpisz wartość.')
        return v
    return f


def _kwota(v, pole):
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < 10 ** 11:
        raise ValueError(f'{pole}: kwota w groszach, liczba całkowita od 0')
    return v


def _rodzaj(v, pole):
    if v not in (1, -1) or isinstance(v, bool):
        raise ValueError(f'{pole}: 1 (wpływ) albo -1 (obciążenie)')
    return v


def _stawka(v, pole):
    from .budzet import stawka_proc
    return stawka_proc(v, scisle=True)


def _data(v, pole):
    if v in (None, ''):
        return None
    if not isinstance(v, str) or not _DATA.fullmatch(v):
        raise ValueError(f'{pole}: data RRRR-MM-DD')
    try:
        date.fromisoformat(v)
    except ValueError:
        raise ValueError(f'{pole}: nie ma takiej daty')
    return v


def _miesiac(v, pole):
    if not isinstance(v, str) or not _MIESIAC.fullmatch(v):
        raise ValueError(f'{pole}: miesiąc RRRR-MM')
    return v


def _miesiac_lub_pusty(v, pole):
    return '' if v in (None, '') else _miesiac(v, pole)


def _dni(v, pole):
    """Dni na płatność 0–99; zapis BS („Natychmiast”, „45 (nietypowe)”) zamieniany na liczbę."""
    if isinstance(v, str):
        t = v.strip()
        v = 0 if t.lower() == 'natychmiast' else int(m.group()) if (m := re.match(r'\d+', t)) else None
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= 99:
        raise ValueError('Dni na płatność: liczba od 0 do 99. Dłuższy termin ustaw na karcie płatności (dzień płatności).')
    return v


def _tak_nie(v, pole):
    if v not in (True, False, 0, 1):
        raise ValueError(f'{pole}: tak albo nie')
    return bool(v)


def _podstawa(v, pole):
    from .budzet import PODSTAWY
    if v not in PODSTAWY:
        raise ValueError(f'{pole}: nieznana podstawa płatności')
    return v


def _cykl(v, pole):
    from .budzet import CYKLE
    if v not in CYKLE:
        raise ValueError(f'{pole}: co miesiąc, kwartał, rok albo jednorazowo')
    return v


def _dzien_wyst(v, pole):
    """Reguła dnia wystawienia (A-KOL-12): „Ostatni”, „Pierwszy”, „10.”, „10. +1”, „9. +1 B”, „20. -1”; zapis kanoniczny."""
    from .plan import regula, regula_tekst
    v = _tekst(20)(v, pole)
    if not v or v == '(auto)':
        return v
    return regula_tekst(regula(v))


def _proporcje(v, pole):
    """Kwoty referencyjne umowy od księgowej (grosze): dla osoby, PIT (US), ZUS. Udział = kwota / suma; zero dozwolone."""
    if v is None:
        return None
    if not isinstance(v, dict) or not v or set(v) - {'osoba', 'us', 'zus'}:
        raise ValueError(f'{pole}: kwoty dla osoby, PIT (us) i ZUS (zus)')
    wynik = {k: _kwota(x, pole) for k, x in v.items()}
    if not sum(wynik.values()):
        raise ValueError(f'{pole}: co najmniej jedna kwota większa od zera')
    return wynik


def _kup(v, pole):
    if v in (None, ''):
        return None
    if v not in (20, 50) or isinstance(v, bool):
        raise ValueError(f'{pole}: koszty uzyskania przychodu 20 albo 50 %')
    return v


def _kwota_lub_pusta(v, pole):
    return None if v is None else _kwota(v, pole)


def _czesci(v, pole):
    if v is None:
        return None
    if not isinstance(v, list) or len(v) > 10:
        raise ValueError(f'{pole}: lista najwyżej 10 części')
    wynik = []
    for c in v:
        if not isinstance(c, dict) or set(c) - {'nazwa', 'kwota', 'dzien_platnosci'}:
            raise ValueError(f'{pole}: część to nazwa, kwota i dzień płatności')
        dz = c.get('dzien_platnosci')
        if dz is not None and (isinstance(dz, bool) or not isinstance(dz, int) or not 1 <= dz <= 31):
            raise ValueError(f'{pole}: dzień płatności części 1–31')
        wynik.append({'nazwa': _tekst(60)(c.get('nazwa'), pole), 'kwota': _kwota(c.get('kwota'), pole), 'dzien_platnosci': dz})
    return wynik


POLA_PLANU = {'netto': _kwota, 'stawka_vat': _stawka, 'cykl': _cykl, 'od': _miesiac_lub_pusty, 'do': _miesiac_lub_pusty,
              'dzien_wystawienia': _dzien_wyst, 'dni_na_platnosc': _dni, 'czesci': _czesci}


def _plan(v, pole):
    if v is None:
        return None
    return _pola(v, POLA_PLANU, 'plan')


# Biała lista pól obiektów budżetu (APK-BUG-05): nieznane pole albo zła wartość = odrzucenie z komunikatem.
POLA_BUD = {
    'arkusz': {'id': _niepusty(80), 'nazwa': _niepusty(80), 'folder': _niepusty(80), 'kategoria': _niepusty(80),
               'od': _miesiac, 'do': _miesiac},
    'wiersz': {'id': _niepusty(80), 'arkusz': _niepusty(80), 'rodzaj': _rodzaj, 'podstawa': _podstawa, 'kontrahent': _tekst(200),
               'komentarz': _tekst(170), 'przedmiot': _tekst(200), 'sekcja': _tekst(100), 'stawka_vat': _stawka,
               'dzien_wystawienia': _dzien_wyst, 'dni_na_platnosc': _dni, 'metoda': _tekst(60), 'ksiegowane': _tak_nie,
               'w_cashflow': _tak_nie, 'cykl': _cykl, 'plan': _plan, 'split': _tak_nie, 'proporcje': _proporcje, 'kup': _kup},
    'platnosc': {'id': _niepusty(80), 'wzor': _niepusty(80), 'wiersz': _niepusty(80), 'miesiac': _miesiac, 'netto': _kwota,
                 'stawka': _stawka, 'wystawienie': _data, 'termin': _data, 'realny': _data, 'ksiegowanie': _data,
                 'metoda': _tekst(60), 'ksiegowane': _tak_nie, 'w_cashflow': _tak_nie, 'komentarz': _tekst(170), 'tytul': _tekst(200),
                 'aktualna': _tak_nie, 'kontrahent': _tekst(200)},
    # komórka (wiersz × miesiąc): kwota w groszach (netto, kwota bez faktury, brutto umowy o dzieło, pełny koszt umowy),
    # 0 = plan zerowy (będzie płatność, kwota nieznana), brak kwoty = pusta komórka
    'komorka': {'wiersz': _niepusty(80), 'miesiac': _miesiac, 'kwota': _kwota_lub_pusta},
}


def sprawdz_zakres(od, do):
    """Zakres arkusza: początek nie po końcu, najwyżej 20 lat (A-KOM-07, A-OPS-01). Gdy podano tylko jedną granicę,
    resztę sprawdza serwer na bieżącym arkuszu."""
    if od and do:
        if od > do:
            raise ValueError('Początek zakresu jest po końcu. Wybierz najpierw miesiąc startu, potem miesiąc końca.')
        ile = (int(do[:4]) - int(od[:4])) * 12 + int(do[5:7]) - int(od[5:7]) + 1
        if ile > MAKS_MIESIECY:
            raise ValueError(f'Arkusz może mieć najwyżej 20 lat (240 miesięcy), a wybrany zakres ma {ile}. Podziel plan na kilka arkuszy.')


def _pola(o, slownik: dict, nazwa: str) -> dict:
    if not isinstance(o, dict):
        raise ValueError(f'{nazwa}: oczekiwany obiekt')
    nieznane = sorted(set(o) - set(slownik))
    if nieznane:
        raise ValueError(f'{nazwa}: nieznane pole {", ".join(nieznane)}')
    return {k: slownik[k](v, k) for k, v in o.items()}


def _sprawdz_bud(d: dict, w_serii=False) -> dict:
    """Zdarzenie budżetu: kształt, pola i zakresy. Odwołania (czy arkusz, wiersz istnieje) sprawdza serwer próbą na modelu."""
    op = d.get('op') if isinstance(d, dict) else None
    if op not in OPERACJE_BUD or (w_serii and op == 'seria'):
        raise ValueError('nieznana operacja budżetu')
    if op == 'seria':
        ops = d.get('operacje')
        if not isinstance(ops, list) or not 0 < len(ops) <= MAKS_SERIA:
            raise ValueError(f'seria: od 1 do {MAKS_SERIA} operacji')
        wynik = {'op': op, 'operacje': [_sprawdz_bud(x, w_serii=True) for x in ops]}
        if len(json.dumps(wynik)) > 400000:
            raise ValueError('za duży wpis')
        return wynik
    if len(json.dumps(d)) > (8000 if op in ('arkusz', 'wiersz', 'platnosc', 'komorka', 'decyzja_planu') else 120000):
        raise ValueError('za duży wpis')
    if op in ('arkusz', 'wiersz', 'platnosc'):
        o = d.get('obiekt')
        if not isinstance(o, dict) or not isinstance(o.get('id'), str) or not o['id']:
            raise ValueError('brak obiektu')
        if d.get('usun'):
            return {'op': op, 'obiekt': {'id': _niepusty(80)(o['id'], 'id')}, 'usun': True}
        obiekt = _pola(o, POLA_BUD[op], op)
        if op == 'arkusz':
            sprawdz_zakres(obiekt.get('od'), obiekt.get('do'))
        return {'op': op, 'obiekt': obiekt, 'usun': False}
    if op in ('scal', 'duplikuj'):
        ws = d.get('wiersze')
        if not isinstance(ws, list) or not ws or len(ws) > 1000 or not all(isinstance(x, str) and 0 < len(x) <= 80 for x in ws):
            raise ValueError('brak zaznaczonych wierszy')
        if len(set(ws)) != len(ws):
            raise ValueError('ten sam wiersz zaznaczony dwa razy')
        if op == 'scal':
            if len(ws) < 2:
                raise ValueError('Do scalenia zaznacz co najmniej dwa wiersze.')
            return {'op': op, 'wiersze': ws}
        nowe = d.get('nowe')
        if not isinstance(nowe, list) or len(nowe) != len(ws) or len(set(nowe)) != len(nowe):
            raise ValueError('duplikuj: lista nowych identyfikatorów tej samej długości co wiersze')
        wynik = {'op': op, 'wiersze': ws, 'nowe': [_niepusty(80)(x, 'id') for x in nowe]}
        if d.get('do_arkusza'):
            wynik['do_arkusza'] = _niepusty(80)(d['do_arkusza'], 'id')
        return wynik
    if op == 'podziel':
        if set(d) - {'op', 'wiersz'}:
            raise ValueError('podziel: tylko wiersz')
        return {'op': op, 'wiersz': _niepusty(80)(d.get('wiersz'), 'id')}
    if op == 'przesun_arkusz':
        o_ = d.get('o')
        if isinstance(o_, bool) or not isinstance(o_, int) or not 0 < abs(o_) <= MAKS_MIESIECY:
            raise ValueError('Przesunięcie startu: liczba miesięcy różna od zera (najwyżej 240 w każdą stronę).')
        return {'op': op, 'arkusz': _niepusty(80)(d.get('arkusz'), 'id'), 'o': o_}
    if op == 'duplikuj_arkusz':
        o = _pola(d.get('obiekt'), POLA_BUD['arkusz'], 'arkusz')
        if not all(o.get(k) for k in ('id', 'nazwa', 'folder', 'kategoria', 'od', 'do')):
            raise ValueError('Kopia arkusza: podaj nazwę, folder, kategorię i zakres miesięcy.')
        sprawdz_zakres(o['od'], o['do'])
        prz = d.get('przesuniecie', 0)
        if isinstance(prz, bool) or not isinstance(prz, int) or abs(prz) > MAKS_MIESIECY:
            raise ValueError('Przesunięcie wartości: liczba miesięcy (najwyżej 240 w każdą stronę).')
        return {'op': op, 'arkusz': _niepusty(80)(d.get('arkusz'), 'id'), 'obiekt': o, 'przesuniecie': prz,
                'wartosci': _tak_nie(d.get('wartosci', False), 'wartosci')}
    if op == 'komorka':
        if not d.get('wiersz') or not d.get('miesiac'):
            raise ValueError('komórka: wiersz i miesiąc')
        if set(d) - {'op', 'wiersz', 'miesiac', 'kwota'}:
            raise ValueError(f"komórka: nieznane pole {', '.join(sorted(set(d) - {'op', 'wiersz', 'miesiac', 'kwota'}))}")
        return {'op': op, **_pola({k: d.get(k) for k in ('wiersz', 'miesiac', 'kwota')}, POLA_BUD['komorka'], 'komórka')}
    if op == 'przenies':
        if not isinstance(d.get('wiersze'), list) or not d['wiersze'] or not d.get('do_arkusza'):
            raise ValueError('brak wierszy albo arkusza docelowego')
        if len(d['wiersze']) > 1000:
            raise ValueError('Naraz przeniesiesz najwyżej 1000 wierszy.')
        return {'op': op, 'wiersze': [str(x) for x in d['wiersze']], 'do_arkusza': str(d['do_arkusza'])}
    if d.get('decyzja') not in ('przesun', 'zaplacone', 'anuluj') or not d.get('platnosc'):
        raise ValueError('decyzja: przesun, zaplacone albo anuluj')
    wynik = {'op': op, 'platnosc': str(d['platnosc']), 'decyzja': d['decyzja']}
    if d['decyzja'] == 'przesun':
        if not _data(d.get('termin'), 'nowy termin'):
            raise ValueError('nowy termin RRRR-MM-DD')
        wynik['termin'] = d['termin']
    if d.get('data'):
        wynik['data'] = _data(d['data'], 'data')
    return wynik


def _sprawdz_umowe(d: dict) -> dict:
    if not isinstance(d.get('id'), str) or not d['id'] or len(d['id']) > 60:
        raise ValueError('brak identyfikatora umowy')
    if d.get('usun'):
        return {'id': d['id'], 'usun': True}
    data = lambda k: d.get(k) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(d.get(k) or '')) else None
    klient = str(d.get('klient') or '').strip()[:80]
    if not klient:
        raise ValueError('brak klienta')
    rodzaj = d.get('rodzaj') if d.get('rodzaj') in ('okreslony', 'nieokreslony') else None
    if not rodzaj:
        raise ValueError('rodzaj: określony albo nieokreślony')
    if rodzaj == 'okreslony' and not data('do'):
        raise ValueError('umowa na czas określony potrzebuje daty końca')
    try:
        okres = int(d.get('wypowiedzenie_mies') or 0)
        alert = int(d.get('alert_dni') or 30)
        wartosc = int(d.get('wartosc_mies') or 0)
    except (TypeError, ValueError):
        raise ValueError('okres wypowiedzenia, alert i wartość muszą być liczbami')
    if not (0 <= okres <= 24 and 0 <= alert <= 365 and 0 <= wartosc < 10 ** 10):
        raise ValueError('wartości poza zakresem')
    return {'id': d['id'], 'klient': klient, 'zawarta': data('zawarta'), 'rodzaj': rodzaj, 'do': data('do'),
            'wypowiedzenie_mies': okres, 'koniec_miesiaca': bool(d.get('koniec_miesiaca', True)), 'przedluzenie': bool(d.get('przedluzenie')),
            'wartosc_mies': wartosc, 'alert_dni': alert, 'uwagi': str(d.get('uwagi') or '')[:300]}
