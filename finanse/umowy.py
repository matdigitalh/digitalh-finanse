"""Rejestr umów z klientami (brief, MVP pkt 8). Dane wpisuje Mat (wpisy „umowa” w pliku zmian), apka liczy terminy.

Rodzaje:
- określony bez przedłużenia: umowa wygasa w dniu „do”; alert przed końcem,
- określony z automatycznym przedłużeniem: ostatni dzień na wypowiedzenie = koniec minus okres wypowiedzenia,
- nieokreślony: najwcześniejszy koniec przy wypowiedzeniu dziś (okres wypowiedzenia, opcjonalnie na koniec miesiąca).
Alert na ekranie X dni przed terminem (domyślnie 30). Kanał zewnętrzny później, za zgodą.
"""
import calendar
import json
from datetime import date, timedelta


def _plus_miesiace(d: date, n: int) -> date:
    m = d.month - 1 + n
    r, m = d.year + m // 12, m % 12 + 1
    return date(r, m, min(d.day, calendar.monthrange(r, m)[1]))


def _koniec_miesiaca(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def wczytaj(wpisy: list[dict]) -> dict:
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    umowy = {}
    for w in wpisy:
        if w.get('typ') != 'umowa' or w.get('id') in cofniete:
            continue
        d = w['dane']
        if d.get('usun'):
            umowy.pop(d['id'], None)
        else:
            umowy[d['id']] = {**umowy.get(d['id'], {}), **d, 'wpis': w['id'], 'czas': w['czas']}
    return umowy


def zapisz_do_bazy(con, wpisy):
    con.executemany('INSERT INTO umowy (id, dane) VALUES (?,?)',
                    [(k, json.dumps(v, ensure_ascii=False)) for k, v in wczytaj(wpisy).items()])


def termin(u: dict, dzis: date) -> dict:
    """Wylicza, co i kiedy trzeba zrobić z umową."""
    okres = int(u.get('wypowiedzenie_mies') or 0)
    na_koniec = bool(u.get('koniec_miesiaca', True))
    alert = int(u.get('alert_dni') or 30)
    if u.get('rodzaj') == 'okreslony' and u.get('do'):
        koniec = date.fromisoformat(u['do'])
        if u.get('przedluzenie'):
            ostatni = _plus_miesiace(koniec, -okres)
            co = 'ostatni dzień na wypowiedzenie (inaczej umowa się przedłuży)'
        else:
            ostatni = koniec
            co = 'umowa wygasa'
    else:
        start = dzis
        koniec = _plus_miesiace(start, okres)
        if na_koniec:
            koniec = _koniec_miesiaca(koniec)
        ostatni = None
        co = 'czas nieokreślony: najwcześniejszy koniec przy wypowiedzeniu dziś'
    data = ostatni or koniec
    dni = (data - dzis).days
    if ostatni is None:
        stan = 'bez terminu'
    elif dni < 0:
        stan = 'minął'
    elif dni <= alert:
        stan = 'alert'
    else:
        stan = 'ok'
    return {'data': data.isoformat(), 'co': co, 'dni': dni, 'stan': stan, 'koniec': koniec.isoformat()}


def dzien_stanu(con) -> date:
    """„Dziś” w logice = dzień stanu (ostatnia data księgowania ING), jak w reszcie apki; bez banku: data systemowa."""
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone()
    return date.fromisoformat(r[0]) if r and r[0] else date.today()


def lista(con, dzis: date | None = None) -> dict:
    dzis = dzis or dzien_stanu(con)
    umowy = []
    for r in con.execute('SELECT dane FROM umowy'):
        u = json.loads(r[0])
        umowy.append({**u, **termin(u, dzis)})
    kolej = {'minął': 0, 'alert': 1, 'ok': 2, 'bez terminu': 3}
    umowy.sort(key=lambda u: (kolej[u['stan']], u['data']))
    return {'umowy': umowy, 'dzis': dzis.isoformat(), 'wartosc_mies': sum(int(u.get('wartosc_mies') or 0) for u in umowy),
            'alerty': sum(1 for u in umowy if u['stan'] in ('alert', 'minął'))}
