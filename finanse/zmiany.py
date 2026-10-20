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
    'rezerwa': ('pozycje',),                  # rezerwa gotówki: pozycje włączone, kwota własna (grosze/mies.), lista księgowości
    'bud': ('op',),                           # zmiana w budżecie (arkusz, wiersz, komórka, płatność, przenieś, decyzja planu)
    'ustawienie': ('klucz', 'wartosc'),       # ustawienia apki, np. planowanie w apce włączone
    'estymata': ('klient', 'udzial'),         # udział czasu zespołu dla klienta (%), do rentowności
    'umowa': ('id',),                         # umowa z klientem (rejestr umów)
    'danina': ('danina', 'okres'),            # kwota od biura za okres VAT/CIT (zamraża go), termin, dzień realny (pakiet 8)
    'widok': ('ekran', 'id'),                 # zapisany widok listy: filtry, sortowanie, kolumny (pakiet 7)
    'do_weryfikacji': ('obiekt', 'ref'),      # pozycja przeniesiona do sprawdzenia (Do weryfikacji); usun = sprawdzone
    'seria': ('wpisy',),                      # akcja grupowa na liście: kilka wpisów w jednym, wszystko albo nic
    'cofnij': ('wpis',),                      # unieważnij wcześniejszy wpis
    'kopia_bs': ('plik', 'sha256'),           # pakiet 6: przyjęta kopia z BS (plik Aplikacja/kopia_bs_*.json i jego suma)
    'lista_plac': ('miesiac', 'pozycje'),     # lista płac za miesiąc od biura (dane rzeczywiste, nie planowanie; lista_plac.py)
    'ppk_plan': ('miesiac',),                 # plan PPK w miesiącu listy, dopóki listy płac nie ma (BL-06; lista_plac.py)
}
# Co może wejść do serii z listy (akcje grupowe, pakiet 7); budżet ma własną serię w „bud” (op „seria”, pakiet 1).
TYPY_W_SERII = ('polacz', 'bez_faktury', 'zatwierdz', 'odrzuc', 'poza_bankiem', 'klient_faktura', 'koszt_regula', 'koszt_operacja',
                'do_weryfikacji', 'cofnij')
MAKS_W_SERII = 1000
OPERACJE_BUD = ('arkusz', 'wiersz', 'platnosc', 'komorka', 'przenies', 'decyzja_planu', 'seria',
                # pakiet 3: akcje na wierszach i arkuszu liczone na serwerze (reguły BS w jednym miejscu)
                'scal', 'podziel', 'duplikuj', 'przesun_arkusz', 'duplikuj_arkusz',
                # pakiet 5: rzeczywista zastępuje plan (połącz, odłącz), ręczne dodanie, zamiana planu, lista płac
                # (lista płac od 2026-10-20 to osobny wpis „lista_plac”, nie zdarzenie budżetu)
                'polacz', 'odlacz', 'rzeczywista', 'zamien', 'zamknij_worek',
                # pakiet 4: Biblioteka (słowniki, foldery i kategorie), reguły w biblioteka.py
                'slownik', 'struktura')
MAKS_SERIA = 1000   # operacji w jednym wpisie „seria” (wklejenie bloku, duplikowanie wielu wierszy)
MAKS_MIESIECY = 240   # zakres arkusza: najwyżej 20 lat (A-KOM-07)
# Nazwy pól w komunikatach (po ludzku, jak w BS)
NAZWY_POL = {'nazwa': 'Nazwa arkusza', 'folder': 'Folder', 'kategoria': 'Kategoria', 'komentarz': 'Komentarz', 'kontrahent': 'Kontrahent',
             'przedmiot': 'Przedmiot transakcji', 'sekcja': 'Sekcja', 'metoda': 'Metoda płatności', 'tytul': 'Tytuł',
             'dni_na_platnosc': 'Dni na płatność', 'od': 'Początek zakresu', 'do': 'Koniec zakresu', 'miesiac': 'Miesiąc'}
USTAWIENIA = {'planowanie': ('tak', 'nie'), 'import_bs': ('tak', 'nie')}
LACZENIE_OD = '2026-11-01'   # pakiet 5: od tej daty dokumenty łączy Mat w apce (wcześniejsze są połączone w Budget Studio)
CELE = {'cel_obrot_rok': (0, 10 ** 11), 'cel_marza_proc': (0, 100), 'rezerwa_miesiecy': (0, 24)}
RODZAJE = ('przenoszony', 'staly', 'praca', 'podatki', 'vat', 'dywidenda', 'zwrot', 'nieprzypisany')


def sprawdz(typ: str, dane) -> dict:
    """Waliduje wpis z interfejsu. Zwraca dane tylko z dozwolonymi polami."""
    if typ not in TYPY or not isinstance(dane, dict):
        raise ValueError('nieznany rodzaj wpisu')
    czyste = {}
    if typ == 'bud':
        return _sprawdz_bud(dane)
    if typ == 'danina':
        from .podatki import sprawdz_danine
        return sprawdz_danine(dane)
    if typ == 'ustawienie' and dane.get('klucz') == 'podatki':   # ustawienia podatkowe (pakiet 8), część pól wystarczy
        from .podatki import sprawdz_ustawienia
        return {'klucz': 'podatki', 'wartosc': sprawdz_ustawienia(dane.get('wartosc'))}
    if typ == 'ustawienie' and dane.get('klucz') == 'laczenie_od':   # pakiet 5: data startu łączenia w apce
        return {'klucz': 'laczenie_od', 'wartosc': _data(dane.get('wartosc'), 'Łączenie w apce od') or LACZENIE_OD}
    if typ == 'ustawienie':
        if dane.get('klucz') not in USTAWIENIA or dane.get('wartosc') not in USTAWIENIA[dane.get('klucz')]:
            raise ValueError('nieznane ustawienie')
        return {'klucz': dane['klucz'], 'wartosc': dane['wartosc']}
    if typ == 'umowa':
        return _sprawdz_umowe(dane)
    if typ == 'rezerwa':
        return _sprawdz_rezerwe(dane)
    if typ == 'kopia_bs':
        return _sprawdz_kopie(dane)
    if typ == 'lista_plac':
        return sprawdz_liste_plac(dane)
    if typ == 'ppk_plan':
        return sprawdz_plan_ppk(dane)
    if typ == 'widok':
        return _sprawdz_widok(dane)
    if typ == 'do_weryfikacji':
        return _sprawdz_do_weryfikacji(dane)
    if typ == 'seria':
        return _sprawdz_serie(dane)
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
    if typ == 'poza_bankiem' and dane.get('data'):   # wyjątek poza bankiem z datą przelewu (kompensata, karta w walucie)
        czyste['data'] = _data(dane['data'], 'data zapłaty')
    return czyste


def _sprawdz_rezerwe(dane: dict) -> dict:
    """Wpis „rezerwa” (decyzja Mata 2026-10-20): zmienia tylko podane pozycje; kolejne wpisy nakładają się po czasie, cofnięcie
    przywraca stan sprzed wpisu. Pozycja: {wlaczona: bool, kwota: grosze miesięcznie albo null = średnia z banku}."""
    from .controlling import KLUCZE_POZYCJI
    if set(dane) - {'pozycje', 'ksiegowosc'}:
        raise ValueError('rezerwa: nieznane pole')
    pozycje = dane.get('pozycje', {})
    if not isinstance(pozycje, dict):
        raise ValueError('rezerwa: pozycje jako słownik')
    czyste = {}
    for k, v in pozycje.items():
        if k not in KLUCZE_POZYCJI:
            raise ValueError(f'rezerwa: nieznana pozycja {k}')
        if not isinstance(v, dict) or not v or set(v) - {'wlaczona', 'kwota'}:
            raise ValueError(f'rezerwa: pozycja {k} bez zmian albo z nieznanym polem')
        c = {}
        if 'wlaczona' in v:
            if not isinstance(v['wlaczona'], bool):
                raise ValueError(f'rezerwa: pozycja {k}, włączona tak albo nie')
            c['wlaczona'] = v['wlaczona']
        if 'kwota' in v:
            kw = v['kwota']
            if kw is not None and (not isinstance(kw, int) or isinstance(kw, bool) or not 0 <= kw < 10 ** 10):
                raise ValueError(f'rezerwa: pozycja {k}, kwota własna w groszach (0 lub więcej) albo pusta')
            c['kwota'] = kw
        czyste[k] = c
    wynik = {'pozycje': czyste}
    if 'ksiegowosc' in dane:
        lista = dane['ksiegowosc']
        if not isinstance(lista, list) or len(lista) > 20 or not all(isinstance(x, str) and 0 < len(x.strip()) <= 80 for x in lista):
            raise ValueError('rezerwa: lista kontrahentów księgowości (najwyżej 20 nazw)')
        wynik['ksiegowosc'] = list(dict.fromkeys(x.strip().lower() for x in lista))
    if not czyste and 'ksiegowosc' not in wynik:
        raise ValueError('rezerwa: brak zmian')
    return wynik


def zapisz(typ: str, dane: dict) -> dict:
    """Dopisuje jeden wpis. Zapis jednym write + fsync, plik 600."""
    wpis = {'czas': datetime.now(timezone.utc).isoformat(timespec='microseconds'), 'id': uuid.uuid4().hex,
            'mac': konfig.nazwa_maca(), 'typ': typ, 'dane': sprawdz(typ, dane) if typ == 'kopia_bs' else dane}
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
    wpisy = _rozwin_serie(wpisy, ostrzezenia)
    wpisy.sort(key=lambda w: (w.get('czas', ''), w.get('id', '')))
    return wpisy, ostrzezenia


def _rozwin_serie(wpisy: list[dict], ostrzezenia: list[str]) -> list[dict]:
    """Seria (akcja grupowa na liście) leży w pliku jako jeden wpis, więc zapisuje się w całości albo wcale. Moduły widzą
    jej wpisy jak zwykłe (identyfikator serii z numerem), a cofnięcie serii cofa każdy z nich."""
    wynik, serie = [], {}
    for w in wpisy:
        if w.get('typ') != 'seria':
            wynik.append(w)
            continue
        czlony = (w.get('dane') or {}).get('wpisy')
        if not isinstance(czlony, list):
            ostrzezenia.append(f"seria {w.get('id', '')}: nieczytelny wpis")
            continue
        serie[w['id']] = []
        for i, c in enumerate(czlony, start=1):
            sid = f"{w['id']}:{i}"
            serie[w['id']].append(sid)
            wynik.append({'czas': w.get('czas', ''), 'id': sid, 'mac': w.get('mac', ''), 'typ': c.get('typ'), 'dane': c.get('dane') or {},
                          'seria': w['id']})
    for w in list(wynik):
        cel = (w.get('dane') or {}).get('wpis') if w.get('typ') == 'cofnij' else None
        for j, sid in enumerate(serie.get(cel, []), start=1):
            wynik.append({'czas': w.get('czas', ''), 'id': f"{w['id']}:c{j}", 'mac': w.get('mac', ''), 'typ': 'cofnij', 'dane': {'wpis': sid}})
    return wynik


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
               'od': _miesiac, 'do': _miesiac, 'przypiety': _tak_nie},   # pakiet 4: przypięty = widoczny w drzewie budżetu
    'wiersz': {'id': _niepusty(80), 'arkusz': _niepusty(80), 'rodzaj': _rodzaj, 'podstawa': _podstawa, 'kontrahent': _tekst(200),
               'komentarz': _tekst(170), 'przedmiot': _tekst(200), 'sekcja': _tekst(100), 'stawka_vat': _stawka,
               'dzien_wystawienia': _dzien_wyst, 'dni_na_platnosc': _dni, 'metoda': _tekst(60), 'ksiegowane': _tak_nie,
               'w_cashflow': _tak_nie, 'cykl': _cykl, 'plan': _plan, 'split': _tak_nie, 'proporcje': _proporcje, 'kup': _kup,
               'lista_plac': _tak_nie},   # pakiet 5: wiersz wynagrodzenia bez umowy (np. powołanie prezesa) na liście płac
    'platnosc': {'id': _niepusty(80), 'wzor': _niepusty(80), 'wiersz': _niepusty(80), 'miesiac': _miesiac, 'netto': _kwota,
                 'stawka': _stawka, 'wystawienie': _data, 'termin': _data, 'realny': _data, 'ksiegowanie': _data,
                 'metoda': _tekst(60), 'ksiegowane': _tak_nie, 'w_cashflow': _tak_nie, 'komentarz': _tekst(170), 'tytul': _tekst(200),
                 'aktualna': _tak_nie, 'kontrahent': _tekst(200)},
    # komórka (wiersz × miesiąc): kwota w groszach (netto, kwota bez faktury, brutto umowy o dzieło, pełny koszt umowy),
    # 0 = plan zerowy (będzie płatność, kwota nieznana), brak kwoty = pusta komórka
    'komorka': {'wiersz': _niepusty(80), 'miesiac': _miesiac, 'kwota': _kwota_lub_pusta},
}


# Pakiet 5: dokument rzeczywisty (faktura z Fakturowni, dokument z rejestru biura, przelew ING, płatność dodana ręcznie)
# i źródła rzeczywistych, które da się odłączyć (zamiana planu, lista płac).
_REF = re.compile(r'(faktura|zakup|operacja|reczna):[^\x00-\x1f]{1,300}')
_REF_ODLACZ = re.compile(r'(faktura|zakup|operacja|reczna|zamiana):[^\x00-\x1f]{1,300}|lista:\d{4}-\d{2}:[^\x00-\x1f]{1,80}'
                         r'|worek:[^\x00-\x1f]{1,80}:\d{4}-\d{2}')


def _ref(v, pole):
    if not isinstance(v, str) or not _REF.fullmatch(v):
        raise ValueError(f'{pole}: dokument (faktura, dokument z rejestru, przelew albo płatność dodana ręcznie)')
    return v


def _podstawa_recznej(v, pole):
    if v not in ('Faktura', 'Bez faktury'):
        raise ValueError(f'{pole}: Faktura albo Bez faktury (wynagrodzenia wpisujesz listą płac)')
    return v


POLA_RECZNEJ = {'id': _niepusty(80), 'rodzaj': _rodzaj, 'podstawa': _podstawa_recznej, 'kontrahent': _niepusty(200),
                'nr_dok': _tekst(60), 'nr_wewn': _tekst(60), 'wystawienie': _data, 'sprzedaz': _data, 'termin': _data,
                'realny': _data, 'netto': _kwota, 'stawka': _stawka, 'vat': _kwota_lub_pusta, 'ksiegowanie': _miesiac_lub_pusty,
                'metoda': _tekst(60), 'ksiegowane': _tak_nie, 'w_cashflow': _tak_nie, 'komentarz': _tekst(170), 'oplacona': _data}
# Zamiana planu na rzeczywistą (B-LACZ-06): numer dokumentu i poprawki danych planu
POLA_ZAMIANY = {'nr_dok': _tekst(60), 'nr_wewn': _tekst(60), 'netto': _kwota, 'stawka': _stawka, 'kontrahent': _tekst(200),
                'wystawienie': _data, 'termin': _data, 'realny': _data, 'ksiegowanie': _miesiac_lub_pusty, 'komentarz': _tekst(170),
                'metoda': _tekst(60), 'ksiegowane': _tak_nie, 'w_cashflow': _tak_nie}
BRAKI_RECZNEJ = {'rodzaj': 'rodzaj (wpływ albo obciążenie)', 'podstawa': 'podstawę', 'kontrahent': 'kontrahenta',
                 'wystawienie': 'dzień wystawienia', 'netto': 'kwotę'}
MAKS_CZESCI = 50     # komórek w jednym połączeniu (podział jednej płatności, B-LACZ-03)
MAKS_LISTA = 100     # osób na jednej liście płac


def _sprawdz_laczenie(op: str, d: dict) -> dict:
    """Pakiet 5: połącz, odłącz, ręczna płatność rzeczywista, zamiana planu, lista płac. Odwołania (dokument, komórka,
    plan) sprawdza serwer próbą na modelu."""
    if op == 'polacz':
        cz = d.get('czesci')
        if not isinstance(cz, list) or not 0 < len(cz) <= MAKS_CZESCI:
            raise ValueError(f'Połączenie: wybierz od 1 do {MAKS_CZESCI} komórek budżetu.')
        czesci = []
        for c in cz:
            if not isinstance(c, dict) or set(c) - {'wiersz', 'miesiac', 'kwota'}:
                raise ValueError('Połączenie: każda część to wiersz, miesiąc i kwota.')
            czesci.append({'wiersz': _niepusty(80)(c.get('wiersz'), 'wiersz'), 'miesiac': _miesiac(c.get('miesiac'), 'miesiąc'),
                           'kwota': _kwota(c.get('kwota'), 'kwota części')})
        if len({(c['wiersz'], c['miesiac']) for c in czesci}) != len(czesci):
            raise ValueError('Połączenie: ta sama komórka wybrana dwa razy. Zostaw jedną i wpisz w niej całą kwotę.')
        wynik = {'op': op, 'dokument': _ref(d.get('dokument'), 'Połączenie'), 'czesci': czesci}
        if d.get('reszta') not in (None, '', 'zostaw', 'usun'):
            raise ValueError('Reszta planu: zostaw albo usuń.')
        if d.get('reszta'):
            wynik['reszta'] = d['reszta']
        return wynik
    if op == 'odlacz':
        ref = d.get('dokument')
        if not isinstance(ref, str) or not _REF_ODLACZ.fullmatch(ref):
            raise ValueError('Odłączenie: brak dokumentu')
        return {'op': op, 'dokument': ref}
    if op == 'rzeczywista':
        o = d.get('obiekt')
        if not isinstance(o, dict) or not isinstance(o.get('id'), str) or not o['id']:
            raise ValueError('Płatność rzeczywista: brak identyfikatora')
        if d.get('usun'):
            return {'op': op, 'obiekt': {'id': _niepusty(80)(o['id'], 'id')}, 'usun': True}
        obiekt = _pola(o, POLA_RECZNEJ, 'płatność rzeczywista')
        for k in ('rodzaj', 'podstawa', 'kontrahent', 'wystawienie', 'netto'):
            if obiekt.get(k) in (None, ''):
                raise ValueError(f"Płatność rzeczywista: podaj {BRAKI_RECZNEJ[k]}.")
        return {'op': op, 'obiekt': obiekt, 'usun': False}
    if op == 'zamien':
        wynik = {'op': op, 'plan': _niepusty(120)(d.get('plan'), 'plan')}
        wynik['obiekt'] = _pola(d.get('obiekt') or {}, POLA_ZAMIANY, 'zamiana na rzeczywistą')
        return wynik
    return sprawdz_liste_plac(d)


POLA_LISTY = ('osoba', 'us', 'zus', 'ppk_pracownik', 'ppk_pracodawca', 'pakiet', 'potracenia')
NAZWY_LISTY = {'osoba': 'Wypłata', 'us': 'PIT', 'zus': 'ZUS', 'ppk_pracownik': 'PPK pracownika', 'ppk_pracodawca': 'PPK pracodawcy',
               'pakiet': 'Pakiet medyczny', 'potracenia': 'Potrącenia z wypłaty'}


def sprawdz_liste_plac(d: dict) -> dict:
    """Lista płac za miesiąc (decyzja Mata 12, pola z 2026-10-20): per osoba wypłata na konto, PIT, ZUS, PPK pracownika
    i pracodawcy, pakiet medyczny, potrącenia (grosze; brak pola = brak na liście, nic nie zgadujemy), data wypłaty, uwaga;
    zbiorczy wiersz PPK z BS i jego komórka; uwaga do miesiąca. Odwołania sprawdza serwer próbą na budżecie."""
    if not isinstance(d, dict) or set(d) - {'op', 'miesiac', 'pozycje', 'ppk', 'uwaga', 'usun'}:
        raise ValueError('Lista płac: nieznane pole.')
    wynik = {'miesiac': _miesiac(d.get('miesiac'), 'Lista płac za miesiąc')}
    if d.get('usun'):
        return {**wynik, 'pozycje': [], 'usun': True}
    poz = d.get('pozycje')
    if not isinstance(poz, list) or not 0 < len(poz) <= MAKS_LISTA:
        raise ValueError(f'Lista płac: od 1 do {MAKS_LISTA} osób.')
    pozycje = []
    for x in poz:
        if not isinstance(x, dict) or set(x) - {'wiersz', 'data_wyplaty', 'uwaga', *POLA_LISTY}:
            raise ValueError('Lista płac: każda pozycja to wiersz, kwoty z listy, data wypłaty i uwaga.')
        y = {'wiersz': _niepusty(80)(x.get('wiersz'), 'wiersz')}
        for k in POLA_LISTY:
            if x.get(k) is not None:
                y[k] = _kwota(x[k], NAZWY_LISTY[k])
        if x.get('data_wyplaty'):
            y['data_wyplaty'] = _data(x['data_wyplaty'], 'Data wypłaty')
        if x.get('uwaga'):
            y['uwaga'] = _tekst(300)(x['uwaga'], 'uwaga')
        pozycje.append(y)
    if len({x['wiersz'] for x in pozycje}) != len(pozycje):
        raise ValueError('Lista płac: ta sama osoba dwa razy.')
    wynik['pozycje'] = pozycje
    if d.get('ppk'):
        p = d['ppk']
        if not isinstance(p, dict) or set(p) - {'wiersz', 'miesiac', 'termin'}:
            raise ValueError('Lista płac, PPK: wiersz PPK, miesiąc komórki i termin.')
        wynik['ppk'] = {'wiersz': _niepusty(80)(p.get('wiersz'), 'wiersz PPK')}
        if p.get('miesiac'):
            wynik['ppk']['miesiac'] = _miesiac(p['miesiac'], 'PPK, miesiąc komórki')
        if p.get('termin'):
            wynik['ppk']['termin'] = _data(p['termin'], 'PPK, termin')
    if d.get('uwaga'):
        wynik['uwaga'] = _tekst(500)(d['uwaga'], 'uwaga')
    return wynik


def sprawdz_plan_ppk(d: dict) -> dict:
    """Plan PPK w miesiącu listy (BL-06, decyzja Mata 2026-10-20): miesiąc listy, kwota (grosze, więcej niż 0), termin
    przelewu, zbiorczy wiersz PPK, opcjonalnie komórka BS do zastąpienia (domyślnie miesiąc terminu) i uwaga; albo usun.
    Termin nie wcześniej niż w miesiącu po miesiącu listy. Odwołania sprawdza serwer próbą na budżecie."""
    if not isinstance(d, dict) or set(d) - {'miesiac', 'kwota', 'termin', 'wiersz', 'komorka_bs', 'uwaga', 'usun'}:
        raise ValueError('Plan PPK: nieznane pole.')
    wynik = {'miesiac': _miesiac(d.get('miesiac'), 'Plan PPK, miesiąc listy')}
    if d.get('usun'):
        return {**wynik, 'usun': True}
    kw = _kwota(d.get('kwota'), 'Plan PPK, kwota')
    if not kw:
        raise ValueError('Plan PPK: kwota większa niż 0.')
    termin = _data(d.get('termin'), 'Plan PPK, termin')
    if not termin or termin[:7] <= wynik['miesiac']:
        raise ValueError('Plan PPK: termin przelewu po miesiącu listy.')
    wynik.update(kwota=kw, termin=termin, wiersz=_niepusty(80)(d.get('wiersz'), 'wiersz PPK'))
    if d.get('komorka_bs'):
        wynik['komorka_bs'] = _miesiac(d['komorka_bs'], 'Plan PPK, komórka BS')
    if d.get('uwaga'):
        wynik['uwaga'] = _tekst(300)(d['uwaga'], 'uwaga')
    return wynik


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
    if op in ('slownik', 'struktura'):
        from .biblioteka import sprawdz_op
        return sprawdz_op(d)
    if len(json.dumps(d)) > (8000 if op in ('arkusz', 'wiersz', 'platnosc', 'komorka', 'decyzja_planu') else 120000):
        raise ValueError('za duży wpis')
    if op in ('polacz', 'odlacz', 'rzeczywista', 'zamien', 'lista_plac'):
        return _sprawdz_laczenie(op, d)
    if op == 'zamknij_worek':   # pakiet 5: ręczne zamknięcie worka (otwarcie: odlacz „worek:<wiersz>:<miesiąc>”)
        if set(d) - {'op', 'wiersz', 'miesiac'}:
            raise ValueError('zamknij_worek: tylko wiersz i miesiąc')
        return {'op': op, 'wiersz': _niepusty(80)(d.get('wiersz'), 'wiersz'), 'miesiac': _miesiac(d.get('miesiac'), 'miesiąc')}
    if op in ('arkusz', 'wiersz', 'platnosc'):
        o = d.get('obiekt')
        if not isinstance(o, dict) or not isinstance(o.get('id'), str) or not o['id']:
            raise ValueError('brak obiektu')
        if d.get('usun'):
            return {'op': op, 'obiekt': {'id': _niepusty(80)(o['id'], 'id')}, 'usun': True}
        obiekt = _pola(o, POLA_BUD[op], op)
        if op == 'arkusz':
            sprawdz_zakres(obiekt.get('od'), obiekt.get('do'))
        if op == 'wiersz' and d.get('domyslne') is True:   # pakiet 4: nowy wiersz, resztę pól uzupełni Biblioteka
            return {'op': op, 'obiekt': obiekt, 'usun': False, 'domyslne': True}
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
    if d['decyzja'] == 'zaplacone' and not wynik.get('data'):   # decyzja Mata 3: opłacona z banku, ręcznie tylko z datą
        raise ValueError('Opłaconą oznaczysz ręcznie tylko z datą przelewu (wyjątek poza bankiem: karta w walucie, kompensata). '
                         'Zwykle opłacenie przychodzi samo z wyciągu ING.')
    return wynik


def _sprawdz_kopie(d: dict) -> dict:
    """Wpis kopii z BS (zapisuje go wyłącznie przyjęcie kopii po kontroli sum, nie zwykła zmiana z interfejsu)."""
    if not re.fullmatch(r'kopia_bs_\d{4}-\d{2}-\d{2}(?:_\d{1,3})?\.json', str(d.get('plik') or '')):
        raise ValueError('kopia: zła nazwa pliku')
    for k in ('sha256', 'eksport_sha256'):
        if k in d and not re.fullmatch(r'[0-9a-f]{64}', str(d.get(k) or '')):
            raise ValueError('kopia: zła suma kontrolna')
    if 'sha256' not in d:
        raise ValueError('kopia: brak sumy kontrolnej')
    wynik = {'plik': d['plik'], 'sha256': d['sha256']}
    if d.get('eksport'):
        if not re.fullmatch(r'budget_studio_[\w.-]{1,60}\.csv', str(d['eksport'])):
            raise ValueError('kopia: zła nazwa eksportu')
        wynik['eksport'] = d['eksport']
    if 'eksport_sha256' in d:
        wynik['eksport_sha256'] = d['eksport_sha256']
    if 'roznic' in d:
        if isinstance(d['roznic'], bool) or not isinstance(d['roznic'], int) or d['roznic'] < 0:
            raise ValueError('kopia: liczba różnic')
        wynik['roznic'] = d['roznic']
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
    wynik = {'id': d['id'], 'klient': klient, 'zawarta': data('zawarta'), 'rodzaj': rodzaj, 'do': data('do'),
             'wypowiedzenie_mies': okres, 'koniec_miesiaca': bool(d.get('koniec_miesiaca', True)), 'przedluzenie': bool(d.get('przedluzenie')),
             'wartosc_mies': wartosc, 'alert_dni': alert, 'uwagi': str(d.get('uwagi') or '')[:300]}
    # pakiet 9: powiązanie z budżetem (folder klienta, arkusze przychodowe; brak listy = wszystkie arkusze folderu z wpływami)
    # i okres wypowiedzenia z naszej strony, gdy inny niż klienta. Stare wpisy bez tych pól działają jak dotąd.
    if d.get('folder') not in (None, ''):
        wynik['folder'] = _niepusty(80)(d['folder'], 'folder')
    if d.get('arkusze') not in (None, ''):
        ark = d['arkusze']
        if not isinstance(ark, list) or len(ark) > 100 or not all(isinstance(x, str) and 0 < len(x) <= 80 for x in ark):
            raise ValueError('arkusze umowy: lista identyfikatorów arkuszy')
        wynik['arkusze'] = list(dict.fromkeys(ark))
    if d.get('wypowiedzenie_mies_my') not in (None, ''):
        try:
            my = int(d['wypowiedzenie_mies_my'])
        except (TypeError, ValueError):
            raise ValueError('okres wypowiedzenia z naszej strony musi być liczbą')
        if not 0 <= my <= 24:
            raise ValueError('okres wypowiedzenia z naszej strony: od 0 do 24 miesięcy')
        wynik['wypowiedzenie_mies_my'] = my
    return wynik


def _sprawdz_widok(d: dict) -> dict:
    """Zapisany widok listy (B-LIS-03): nazwa, parametry z adresu (filtry, sortowanie), widoczne kolumny w kolejności."""
    from .widoki import EKRANY
    if d.get('ekran') not in EKRANY:
        raise ValueError('widok: nieznana lista')
    wid = _niepusty(60)(d.get('id'), 'widok')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', wid):
        raise ValueError('widok: identyfikator z liter, cyfr, kropki, kreski')
    if d.get('usun'):
        return {'ekran': d['ekran'], 'id': wid, 'usun': True}
    nazwa = _niepusty(60)(d.get('nazwa'), 'nazwa widoku')
    par = d.get('parametry') or {}
    if not isinstance(par, dict) or len(par) > 60:
        raise ValueError('widok: parametry jako słownik (najwyżej 60)')
    czyste = {}
    for k, v in par.items():
        if not isinstance(k, str) or not re.fullmatch(r'[a-z_]{1,30}', k) or k in ('widok', 'zm', 'strona', 'q', 'id', 'zakladka'):
            raise ValueError(f'widok: nieznany parametr {k}')
        if isinstance(v, bool) or not isinstance(v, (str, int)) or len(str(v)) > 2000:
            raise ValueError(f'widok: wartość parametru {k} za długa albo nie tekst')
        czyste[k] = str(v)
    kol = d.get('kolumny') or []
    if not isinstance(kol, list) or len(kol) > 60 or not all(isinstance(x, str) and re.fullmatch(r'[a-z_]{1,30}', x) for x in kol):
        raise ValueError('widok: kolumny jako lista nazw')
    return {'ekran': d['ekran'], 'id': wid, 'nazwa': nazwa, 'parametry': czyste, 'kolumny': kol, 'usun': False}


def _sprawdz_do_weryfikacji(d: dict) -> dict:
    from .widoki import OBIEKTY
    if d.get('obiekt') not in OBIEKTY:
        raise ValueError('do weryfikacji: operacja, faktura, zakup albo płatność')
    ref = _niepusty(120)(d.get('ref'), 'do weryfikacji')
    if d.get('usun'):
        return {'obiekt': d['obiekt'], 'ref': ref, 'usun': True}
    return {'obiekt': d['obiekt'], 'ref': ref, 'powod': _tekst(200)(d.get('powod'), 'powód'), 'usun': False}


def _sprawdz_serie(d: dict) -> dict:
    """Akcja grupowa: każdy wpis sprawdzany jak pojedynczy; jeden zły odrzuca całą serię (nic nie trafia do pliku)."""
    lista = d.get('wpisy')
    if not isinstance(lista, list) or not 0 < len(lista) <= MAKS_W_SERII:
        raise ValueError(f'seria: od 1 do {MAKS_W_SERII} wpisów')
    wynik = []
    for i, w in enumerate(lista, start=1):
        if not isinstance(w, dict) or w.get('typ') not in TYPY_W_SERII:
            raise ValueError(f'seria, wpis {i}: niedozwolony rodzaj wpisu')
        try:
            wynik.append({'typ': w['typ'], 'dane': sprawdz(w['typ'], w.get('dane'))})
        except ValueError as e:
            raise ValueError(f'seria, wpis {i} z {len(lista)}: {e}')
    if len(json.dumps(wynik, ensure_ascii=False)) > 450000:
        raise ValueError('za duży wpis')
    return {'wpisy': wynik}
