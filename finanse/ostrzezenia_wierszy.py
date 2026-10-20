"""Pakiet 11 (A-CF-17, A-INN): ostrzeżenia o ustawieniach wiersza, które psują prognozę. Tylko podpowiedź: nic nie
zmienia i niczego nie blokuje. Liczone przy zapytaniu z bazy (wiersze, płatności, dokumenty z rejestru biura).

Reguły (rdzeń `dla_wiersza` bez bazy, testowalny wprost):
- worek przy stałej opłacie: wiersz „w worku”, a w co najmniej 3 miesiącach przyszła dokładnie jedna płatność rzeczywista
  i w żadnym więcej (stała miesięczna faktura; worek rozkłada plan na tygodnie, więc cash flow pokazuje go w złe dni),
- faktura kosztowa z wyłączonym „W cash flow” (znika z prognozy płynności; w porządku tylko przy koszcie opłaconym prywatnie),
- stawka 23% u kontrahenta z zagranicy (dokumenty wiersza w rejestrze zagranicznym biura, faktury wiersza z 0% albo nazwa
  firmy zagranicznej: Inc, Ltd, Limited, LLC, GmbH...); zwykle 0% (import usług),
- dzień wystawienia niezgodny z historią faktur: co najmniej 3 rzeczywiste wiersza i w 2/3 z nich data wystawienia różni się
  o ponad 5 dni od daty, którą dałaby reguła wiersza dla tego samego miesiąca budżetu.
"""
import re
from collections import Counter
from datetime import date

from . import plan
from .budzet import stawka_proc

TYTULY = {
    'worek_stala': 'Worek przy stałej opłacie',
    'cf_off_koszt': 'Faktura kosztowa poza cash flow',
    'vat_zagranica': 'Stawka 23% u kontrahenta z zagranicy',
    'dzien_historia': 'Dzień wystawienia inny niż na fakturach',
}
ZAGRANICZNA = re.compile(r'\b(inc|ltd|limited|llc|gmbh|pty|b\.v|unlimited company|corp|corporation|pbc|fze|s\.r\.o|sarl|sas)\b\.?',
                         re.IGNORECASE)
MIN_MIESIECY = 3     # worek: tyle miesięcy z dokładnie jedną rzeczywistą
MIN_FAKTUR = 3       # dzień wystawienia: najmniej rzeczywistych do porównania
ODCHYLKA_DNI = 5     # dzień wystawienia: różnica w dniach, od której data „nie pasuje”


def zagraniczna_nazwa(nazwa: str) -> bool:
    return bool(ZAGRANICZNA.search(str(nazwa or '')))


def _dni(a: str, b: str) -> int:
    return (date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days


def dla_wiersza(w: dict, platnosci: list[dict], zagraniczny_rejestr: bool = False) -> list[dict]:
    """w: podstawa, rodzaj, stawka_vat, w_cashflow, dzien_wystawienia, kontrahent; platnosci: typ, miesiac, wystawienie,
    stawka (tylko płatności tego wiersza). Zwraca listę ostrzeżeń {rodzaj, tytul, opis, rada}."""
    wynik = []
    pod = w.get('podstawa') or ''
    rzecz = [p for p in platnosci if p.get('typ') != 'plan']
    stawka = stawka_proc(w.get('stawka_vat')) if plan.ma_vat(pod) else None

    def dodaj(rodzaj, opis, rada):
        wynik.append({'rodzaj': rodzaj, 'tytul': TYTULY[rodzaj], 'opis': opis, 'rada': rada})

    if pod in plan.WOREK:
        ile = Counter(p['miesiac'] for p in rzecz if p.get('miesiac'))
        if len(ile) >= MIN_MIESIECY and max(ile.values()) == 1:
            dodaj('worek_stala', f'W {len(ile)} miesiącach przyszła dokładnie jedna płatność, czyli to stała miesięczna opłata. '
                  'Worek dzieli plan na tygodnie, więc cash flow pokazuje kwotę w złe dni.',
                  'Zmień podstawę na „Faktura (jedna)” (albo „Bez faktury”). Wiersz ma już rzeczywiste, więc zduplikuj go '
                  'i zmień podstawę w kopii na kolejne miesiące.')
    if int(w.get('rodzaj') or 0) == -1 and pod.startswith('Faktura') and not w.get('w_cashflow', True):
        dodaj('cf_off_koszt', 'Faktura kosztowa ma wyłączone „W cash flow”, więc nie ma jej w prognozie płynności.',
              'Jeśli to koszt opłacony prywatnie (zwrot jest w osobnym wierszu), wszystko gra. Inaczej włącz „W cash flow”.')
    if stawka == 23:
        zero = [p for p in rzecz if stawka_proc(p.get('stawka')) == 0]
        powod = ('dokumenty tego wiersza są w rejestrze zagranicznym biura' if zagraniczny_rejestr
                 else f'{len(zero)} z {len(rzecz)} faktur tego wiersza ma 0%' if rzecz and len(zero) * 2 >= len(rzecz)
                 else 'nazwa wygląda na firmę z zagranicy' if zagraniczna_nazwa(w.get('kontrahent')) else None)
        if powod:
            dodaj('vat_zagranica', f'Wiersz ma stawkę 23%, a {powod}. Plan VAT zawyża wtedy prognozę VAT i kwoty brutto w cash flow.',
                  'Przy imporcie usług (Google, Meta, narzędzia z UE i USA) stawka w planie to 0%. Zmień stawkę VAT w wierszu.')
    if pod not in plan.WOREK and not plan.jest_umowa(pod) and pod not in plan.PODATKI:
        pary = []   # (dzień miesiąca faktury, różnica w dniach od daty z reguły, przesunięcie miesiąca faktury od miesiąca budżetu)
        for p in sorted(rzecz, key=lambda x: x.get('wystawienie') or '')[-6:]:   # ostatnie faktury mówią najwięcej
            if not p.get('wystawienie') or not p.get('miesiac'):
                continue
            try:
                oczekiwana, _ = plan.wystawienie_z_reguly(p['miesiac'], w.get('dzien_wystawienia'))
            except ValueError:
                return wynik
            wyst = p['wystawienie'][:10]
            przes = (int(wyst[:4]) - int(p['miesiac'][:4])) * 12 + int(wyst[5:7]) - int(p['miesiac'][5:7])
            pary.append((int(wyst[8:10]), _dni(wyst, oczekiwana), przes))
        inne = [x for x in pary if abs(x[1]) > ODCHYLKA_DNI]
        if len(pary) >= MIN_FAKTUR and len(inne) * 3 >= len(pary) * 2:
            srodek = len(pary) // 2
            dzien = sorted(x[0] for x in pary)[srodek]
            roznica = sorted(x[1] for x in pary)[srodek]
            przes = sorted(x[2] for x in pary)[srodek]
            kiedy = {0: 'w miesiącu budżetu', 1: 'miesiąc po miesiącu budżetu', -1: 'miesiąc przed miesiącem budżetu'}.get(
                przes, f'{abs(przes)} mies. {"po" if przes > 0 else "przed"} miesiącu budżetu')
            propozycja = f'{dzien}.' + (f' {przes:+d}' if przes else '')
            dodaj('dzien_historia', f'Faktury tego wiersza są wystawiane zwykle ok. {dzien}. dnia, {kiedy}, a reguła wiersza to '
                  f'„{plan.regula_opis(w.get("dzien_wystawienia"))}”. Plany wypadają średnio {abs(roznica)} dni '
                  f'{"za wcześnie" if roznica > 0 else "za późno"}.',
                  f'Popraw dzień wystawienia w ustawieniach wiersza (kolumna Dzień wystaw.), np. na „{propozycja}”.')
    return wynik


def policz(con, arkusz: str | None = None) -> dict:
    """Ostrzeżenia dla wierszy jednego arkusza albo całego budżetu (bez arkusza systemowego)."""
    warunek, params = "COALESCE(a.zrodlo, '') != 'system'", []
    if arkusz:
        warunek += ' AND a.id = ?'
        params.append(arkusz)
    wiersze = [dict(r) for r in con.execute(
        'SELECT w.id, w.arkusz, w.rodzaj, w.podstawa, w.kontrahent, w.przedmiot, w.stawka_vat, w.dzien_wystawienia, w.w_cashflow,'
        f' a.nazwa AS arkusz_nazwa, a.folder FROM bud_wiersz w JOIN bud_arkusz a ON a.id = w.arkusz WHERE {warunek}', params)]
    ids = {w['id'] for w in wiersze}
    platnosci = {}
    for r in con.execute('SELECT p.wiersz, p.typ, p.miesiac, p.wystawienie, p.stawka FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz'
                         f' JOIN bud_arkusz a ON a.id = w.arkusz WHERE p.aktualna = 1 AND {warunek}', params):
        platnosci.setdefault(r['wiersz'], []).append(dict(r))
    zagr = {r[0] for r in con.execute(
        "SELECT DISTINCT p.wiersz FROM bud_platnosc p JOIN bud_powiazanie b ON b.platnosc = p.id AND b.typ = 'dokument'"
        " JOIN zakupy z ON z.nr_ewid = b.ref WHERE z.rejestr = 'zagraniczne'")} & ids
    lista = []
    for w in wiersze:
        for o in dla_wiersza({**w, 'w_cashflow': bool(w['w_cashflow']) if w['w_cashflow'] is not None else True},
                             platnosci.get(w['id'], []), w['id'] in zagr):
            lista.append({**o, 'wiersz': w['id'], 'arkusz': w['arkusz'], 'arkusz_nazwa': w['arkusz_nazwa'], 'folder': w['folder'],
                          'kontrahent': w['kontrahent'] or '', 'przedmiot': w['przedmiot'] or ''})
    lista.sort(key=lambda x: (x['folder'], x['arkusz_nazwa'], x['kontrahent'], x['rodzaj']))
    return {'ostrzezenia': lista, 'ile': len(lista), 'wierszy': len({x['wiersz'] for x in lista})}
