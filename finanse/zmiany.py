"""Wpisy Mata (reguły, umowy, zatwierdzenia dopasowań) jako dziennik zmian w iCloud.

Każdy Mac dopisuje wyłącznie do własnego pliku `zmiany/<nazwa-Maca>.jsonl`, więc iCloud nigdy nie
widzi dwóch wersji jednego pliku. Stan powstaje przez złożenie wpisów ze wszystkich plików po czasie.
"""
import json
import re
import os
import uuid
from datetime import datetime, timezone
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
    'bud': ('op',),                           # zmiana w budżecie (arkusz, wiersz, płatność, przenieś, decyzja planu)
    'ustawienie': ('klucz', 'wartosc'),       # ustawienia apki, np. planowanie w apce włączone
    'estymata': ('klient', 'udzial'),         # udział czasu zespołu dla klienta (%), do rentowności
    'umowa': ('id',),                         # umowa z klientem (rejestr umów)
    'cofnij': ('wpis',),                      # unieważnij wcześniejszy wpis
}
OPERACJE_BUD = ('arkusz', 'wiersz', 'platnosc', 'przenies', 'decyzja_planu')
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


def _sprawdz_bud(d: dict) -> dict:
    """Zdarzenie budżetu: kształt i rozmiar. Odwołania (czy arkusz, wiersz istnieje) sprawdza serwer."""
    op = d.get('op')
    if op not in OPERACJE_BUD:
        raise ValueError('nieznana operacja budżetu')
    if len(json.dumps(d)) > 8000:
        raise ValueError('za duży wpis')
    if op in ('arkusz', 'wiersz', 'platnosc'):
        o = d.get('obiekt')
        if not isinstance(o, dict) or not isinstance(o.get('id'), str) or not o['id']:
            raise ValueError('brak obiektu')
        return {'op': op, 'obiekt': o, 'usun': bool(d.get('usun'))}
    if op == 'przenies':
        if not isinstance(d.get('wiersze'), list) or not d['wiersze'] or not d.get('do_arkusza'):
            raise ValueError('brak wierszy albo arkusza docelowego')
        return {'op': op, 'wiersze': [str(x) for x in d['wiersze']][:200], 'do_arkusza': str(d['do_arkusza'])}
    if d.get('decyzja') not in ('przesun', 'zaplacone', 'anuluj') or not d.get('platnosc'):
        raise ValueError('decyzja: przesun, zaplacone albo anuluj')
    wynik = {'op': op, 'platnosc': str(d['platnosc']), 'decyzja': d['decyzja']}
    if d['decyzja'] == 'przesun':
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(d.get('termin', ''))):
            raise ValueError('nowy termin RRRR-MM-DD')
        wynik['termin'] = d['termin']
    if d.get('data'):
        wynik['data'] = str(d['data'])[:10]
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
