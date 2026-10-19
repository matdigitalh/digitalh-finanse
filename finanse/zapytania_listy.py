"""Listy płatności jak w Budget Studio (pakiet 7): jedna droga dla wszystkich list (GET /api/lista/<ekran>), filtry
podręczne i szczegółowe, filtry dat w trybach BS, sortowanie po stronie serwera z białej listy, podsumowanie wszystkich
wyników, zapisane widoki (startowe + zdarzenia „widok”) i liczniki pozycji do menu.

Parametry z adresu: wielokrotny wybór rozdzielony „|”, daty jako d_<typ>=<tryb> (filtry.py), sortuj + kolejnosc
(rosnaco, malejaco), q (wyszukiwarka), strona, ile, wszystkie=1 (cała lista naraz, do zaznaczenia wszystkich wyników)."""
import json

from . import filtry, zapytania
from . import plan as reguly
from .zapytania_budzet import LISTY, _dzien_stanu, _warunki_list, planowanie

# Podstawa płatności z nazwą składowej umowy (PIT, ZUS), do filtra i sortowania (B-POD-22)
PODSTAWA_SQL = 'CASE ' + ' '.join(f"WHEN w.podstawa = '{pod}' AND p.skladowa = '{s}' THEN '{et}'"
                                  for pod, m in reguly.ETYKIETY_SKLADOWYCH.items() for s, et in m.items()) + ' ELSE w.podstawa END'
KONTRAHENT_SQL = "COALESCE(NULLIF(p.kontrahent, ''), w.kontrahent)"
METODA_SQL = "COALESCE(NULLIF(p.metoda, ''), w.metoda)"
REALNY_SQL = 'COALESCE(p.realny, s.termin_efektywny)'
KSIEGOWANIE_SQL = "COALESCE(p.ksiegowanie, p.wystawienie, p.miesiac || '-01')"

KOL_PLATNOSCI = {
    'rodzaj': ('p.rodzaj', False), 'typ': ('p.typ', True), 'etap': ('s.etap', True), 'aktualnosc': ('s.aktualnosc', True),
    'podstawa': (PODSTAWA_SQL, True), 'kontrahent': (KONTRAHENT_SQL, True), 'tytul': ('p.tytul', True), 'nr_dok': ('p.nr_dok', True),
    'netto': ('p.netto * p.rodzaj', False), 'brutto': ('p.brutto * p.rodzaj', False), 'vat': ('COALESCE(p.vat, 0) * p.rodzaj', False),
    'stawka': ('p.stawka', False), 'wystawienie': ('p.wystawienie', False), 'termin': ('s.termin_efektywny', False),
    'realny': (REALNY_SQL, False), 'przesuniecie': (f'julianday({REALNY_SQL}) - julianday(s.termin_efektywny)', False),
    'ksiegowanie': (f'substr({KSIEGOWANIE_SQL}, 1, 7)', False), 'miesiac': ('p.miesiac', False), 'arkusz': ('a.nazwa', True),
    'folder': ('a.folder', True), 'kategoria': ('a.kategoria', True), 'sekcja': ('w.sekcja', True), 'przedmiot': ('w.przedmiot', True),
    'metoda': (METODA_SQL, True), 'ksiegowane': ('p.ksiegowane', False), 'w_cashflow': ('p.w_cashflow', False),
    'komentarz': ('p.komentarz', True), 'uwagi': ("COALESCE(NULLIF(s.uwaga, ''), p.decyzja)", True),
}
DATY_PLATNOSCI = {'wystawienie': ('p.wystawienie', False), 'termin': ('s.termin_efektywny', False), 'realny': (REALNY_SQL, False),
                  'ksiegowanie': (KSIEGOWANIE_SQL, True), 'miesiac': ("p.miesiac || '-01'", True)}
# filtr wielokrotnego wyboru → wyrażenie SQL
WIELE_PLATNOSCI = {'podstawa': PODSTAWA_SQL, 'etap': 's.etap', 'kontrahent': KONTRAHENT_SQL, 'folder': 'a.folder', 'kategoria': 'a.kategoria',
                   'arkusz': 'a.id', 'sekcja': 'w.sekcja', 'przedmiot': 'w.przedmiot', 'metoda': METODA_SQL}


def _daty_z(q: dict, typy) -> dict:
    return {t: q[f'd_{t}'] for t in typy if q.get(f'd_{t}')}


def platnosci(con, q: dict) -> dict:
    """Płatności połączone z budżetem: plany i rzeczywiste (B-LIS-02) z filtrami jak w BS (B-LIS-05, B-LIS-06)."""
    dzien = _dzien_stanu(con)
    nazwa = q.get('lista') or 'wszystkie'
    warunki, params = [f'({_warunki_list(dzien)[nazwa if nazwa in LISTY else "wszystkie"]})'], []
    if q.get('rodzaj') in ('1', '-1'):
        warunki.append('p.rodzaj = ?')
        params.append(int(q['rodzaj']))
    if q.get('typ') == 'plan':
        warunki.append("p.typ = 'plan'")
    elif q.get('typ') == 'rzeczywista':
        warunki.append("p.typ != 'plan'")
    if q.get('aktualnosc') in ('Aktualna', 'Nieaktualna'):
        warunki.append('s.aktualnosc = ?')
        params.append(q['aktualnosc'])
    for k in ('ksiegowane', 'w_cashflow'):
        if q.get(k) in ('0', '1'):
            warunki.append(f'p.{k} = ?')
            params.append(int(q[k]))
    for k, wyr in WIELE_PLATNOSCI.items():
        wart = filtry.lista_wartosci(q.get(k))
        if wart:
            warunki.append(f"COALESCE({wyr}, '') IN ({','.join('?' * len(wart))})")
            params.extend(wart)
    zapytania._daty(con, _daty_z(q, DATY_PLATNOSCI), DATY_PLATNOSCI, warunki, params)
    if q.get('q'):
        warunki.append(f"({KONTRAHENT_SQL} || ' ' || COALESCE(p.tytul, '') || ' ' || COALESCE(p.nr_dok, '') || ' ' || COALESCE(p.nr_wewn, '')"
                       " || ' ' || COALESCE(a.nazwa, '') || ' ' || COALESCE(p.komentarz, '')) LIKE ?")
        params.append(f"%{q['q']}%")
    sql = ('SELECT p.*, s.etap, s.termin_efektywny, s.data_zaplaty, s.uwaga AS uwaga_stanu, s.etap_wg_bs, s.aktualnosc,'
           f' {KONTRAHENT_SQL} AS w_kontrahent, w.podstawa, w.sekcja, w.przedmiot, {METODA_SQL} AS metoda_ef,'
           f' {REALNY_SQL} AS realny_ef, substr({KSIEGOWANIE_SQL}, 1, 7) AS ksiegowanie_mies, {PODSTAWA_SQL} AS podstawa_platnosci,'
           ' a.nazwa AS arkusz, a.folder, a.kategoria, a.id AS arkusz_id'
           ' FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz'
           ' JOIN bud_stan s ON s.platnosc = p.id WHERE ' + ' AND '.join(warunki))
    ile, maks = zapytania._ile(q.get('ile'), q.get('wszystkie') == '1')
    wynik = zapytania._strona(sql, params, q.get('strona'), ile, con,
                              filtry.porzadek(q.get('sortuj'), q.get('kolejnosc'), KOL_PLATNOSCI, 's.termin_efektywny DESC', 'p.id'), maks)
    wynik['podsumowanie'] = zapytania._podsumowanie(con, sql, params, 'rodzaj', 'netto * rodzaj', 'COALESCE(vat, 0) * rodzaj',
                                                    'brutto * rodzaj')
    wynik.update(suma=wynik['podsumowanie']['razem']['brutto'], lista=nazwa, nazwa=LISTY.get(nazwa, LISTY['wszystkie']),
                 dzien_stanu=dzien, listy=LISTY, planowanie=planowanie(con))
    if q.get('opcje') == '1':
        wynik['opcje'] = opcje_platnosci(con)
    return wynik


def opcje_platnosci(con) -> dict:
    """Wartości do filtrów wielokrotnego wyboru (cała lista, nie bieżący wynik), po polsku alfabetycznie."""
    baza = (' FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz'
            ' JOIN bud_stan s ON s.platnosc = p.id')
    wynik = {}
    for k, wyr in WIELE_PLATNOSCI.items():
        if k == 'arkusz':
            continue
        wart = [r[0] for r in con.execute(f"SELECT DISTINCT COALESCE({wyr}, ''){baza}") if r[0] not in (None, '')]
        wynik[k] = sorted(wart, key=filtry.klucz_pl)
    wynik['arkusz'] = [[r['id'], f"{r['nazwa']} ({r['folder']})"] for r in con.execute('SELECT id, nazwa, folder FROM bud_arkusz')]
    wynik['arkusz'].sort(key=lambda x: filtry.klucz_pl(x[1]))
    return wynik


def do_weryfikacji(con, q: dict) -> dict:
    """Do weryfikacji jako lista: grupa (rodzaj), wyszukiwarka, filtr daty, sortowanie i strony liczone w Pythonie
    (pozycje powstają z kilku źródeł), podsumowanie wszystkich wyników."""
    lista = zapytania.do_weryfikacji(con)
    grupy = {}
    for x in lista:
        grupy.setdefault(x['rodzaj'], x['tytul'])
    if q.get('grupa'):
        wybrane = set(filtry.lista_wartosci(q['grupa']))
        lista = [x for x in lista if x['rodzaj'] in wybrane]
    if q.get('q'):
        f = q['q'].casefold()
        lista = [x for x in lista if f in f"{x.get('kontrahent') or ''} {x.get('faktury') or ''} {x.get('opis') or ''}".casefold()]
    if q.get('d_data'):
        z = filtry.zakres(q['d_data'], zapytania.dzis(con), False, zapytania._pierwszy_dzien_tyg())
        if z:
            od, do = (x.isoformat() if x else None for x in z)
            lista = [x for x in lista if x.get('data') and (not od or x['data'][:10] >= od) and (not do or x['data'][:10] <= do)]
    kol = {'data': (lambda x: x.get('data') or '', False), 'kontrahent': (lambda x: x.get('kontrahent') or '', True),
           'faktury': (lambda x: x.get('faktury') or '', True), 'kwota': (lambda x: x.get('kwota') or 0, False),
           'grupa': (lambda x: x.get('tytul') or '', True), 'opis': (lambda x: x.get('opis') or '', True)}
    sortuj = q.get('sortuj') if q.get('sortuj') in kol else 'data'
    f, tekst = kol[sortuj]
    malejaco = (q.get('kolejnosc') or ('malejaco' if sortuj == 'data' else 'rosnaco')) == 'malejaco'
    lista.sort(key=lambda x: (filtry.klucz_pl(f(x)) if tekst else f(x)), reverse=malejaco)
    ile, maks = zapytania._ile(q.get('ile'), q.get('wszystkie') == '1')
    ile = max(1, min(int(ile or zapytania.STRONA), maks))
    strona = max(1, int(q.get('strona') or 1))
    podsumowanie = filtry.podsumuj([{'rodzaj': 1 if (x.get('kwota') or 0) >= 0 else -1, 'brutto': x.get('kwota') or 0} for x in lista])
    for g in ('wplywy', 'obciazenia', 'razem'):
        podsumowanie[g]['netto'] = podsumowanie[g]['vat'] = None
    return {'razem': len(lista), 'strona': strona, 'ile': ile, 'wiersze': lista[(strona - 1) * ile:strona * ile],
            'podsumowanie': podsumowanie, 'grupy': grupy, 'dzien_stanu': _dzien_stanu(con)}


def _wiele(q, k):
    return '|'.join(filtry.lista_wartosci(q.get(k))) or None


def lista(con, ekran: str, q: dict) -> dict:
    """Jedna droga do wszystkich list; parametry jak w adresie ekranu."""
    wsp = {'sortuj': q.get('sortuj'), 'kolejnosc': q.get('kolejnosc'), 'wszystkie': q.get('wszystkie') == '1',
           'strona': q.get('strona'), 'ile': q.get('ile'), 'q': q.get('q')}
    if ekran == 'platnosci':
        return platnosci(con, q)
    if ekran == 'bank':
        w = zapytania.operacje(con, rachunek=q.get('rachunek'), kierunek=q.get('kierunek'), wewnetrzne=q.get('wewnetrzne'), od=q.get('od'),
                               do=q.get('do'), daty=_daty_z(q, zapytania.DATY_OPERACJI), **{**wsp, 'sortuj': wsp['sortuj'] or 'data_ksiegowania',
                                                                                              'kolejnosc': wsp['kolejnosc'] or 'malejaco'})
    elif ekran == 'faktury':
        w = zapytania.faktury(con, status=q.get('status'), bank=q.get('bank'), od=q.get('od'), do=q.get('do'), klient=_wiele(q, 'klient'),
                              daty=_daty_z(q, zapytania.DATY_FAKTUR), **wsp)
    elif ekran == 'naleznosci':
        w = zapytania.naleznosci(con, przedzial=q.get('przedzial'), po_terminie=q.get('po_terminie'),
                                 daty=_daty_z(q, zapytania.DATY_NALEZNOSCI), **wsp)
    elif ekran == 'zakupy':
        w = zapytania.zakupy(con, rejestr=q.get('rejestr'), stan=q.get('stan'), od=q.get('od'), do=q.get('do'),
                             daty=_daty_z(q, zapytania.DATY_ZAKUPOW), **wsp)
    elif ekran == 'wplaty':
        w = zapytania.wplaty(con, stan=q.get('stan') or 'nieznana', daty=_daty_z(q, zapytania.DATY_WPLAT), **wsp)
    elif ekran == 'do_weryfikacji':
        return do_weryfikacji(con, q)
    elif ekran == 'do_polaczenia':   # pakiet 5: dokumenty rzeczywiste niepołączone z budżetem (laczenie.py)
        from . import laczenie
        return laczenie.lista(con, q)
    elif ekran == 'wydatki':
        w = zapytania.wydatki(con, rodzaj=q.get('rodzaj'), klient=q.get('klient'), dokument=q.get('dokument'), zrodlo=q.get('zrodlo'),
                              od=q.get('od'), do=q.get('do'), daty=_daty_z(q, zapytania.DATY_WYDATKOW), **wsp)
    else:
        raise ValueError('nieznana lista')
    w['dzien_stanu'] = _dzien_stanu(con)
    return w


# ---------- Zapisane widoki ----------

# Widoki startowe (B-LIS-03): dzisiejsze listy menu Płatności jako widoki, plus dwa z bazy wiedzy BS (B-LIS-06).
# Parametry jak w adresie listy; daty względne liczone przy każdym otwarciu od dnia stanu.
WIDOKI_STARTOWE = {
    'platnosci': [
        {'id': 'wszystkie', 'nazwa': 'Wszystkie płatności', 'ik': 'fale', 'parametry': {}},
        {'id': 'nieoplacone', 'nazwa': 'Nadal nieopłacone', 'ik': 'kalendarzX', 'parametry': {'lista': 'nieoplacone'}},
        {'id': 'niewystawione', 'nazwa': 'Nadal niewystawione', 'ik': 'kalendarzK', 'parametry': {'lista': 'niewystawione'}},
        {'id': 'po_terminie', 'nazwa': 'Po terminie płatności', 'ik': 'przekreslony', 'parametry': {'lista': 'po_terminie'}},
        {'id': 'do_wystawienia', 'nazwa': 'Do wystawienia (najbliższe 2 tyg.)', 'ik': 'plusKolko', 'parametry': {'lista': 'do_wystawienia'}},
        {'id': 'do_zaplacenia', 'nazwa': 'Do zapłacenia (najbliższe 2 tyg.)', 'ik': 'przelew', 'parametry': {'lista': 'do_zaplacenia'}},
        {'id': 'zaplacone', 'nazwa': 'Zapłacone (ostatnie 2 tyg.)', 'ik': 'ptaszek', 'parametry': {'lista': 'zaplacone'}},
        {'id': 'do_wystawienia_mies', 'nazwa': 'Do wystawienia do końca miesiąca', 'ik': 'plusKolko',
         'parametry': {'rodzaj': '1', 'etap': 'Planowana', 'd_wystawienie': 'dokonca:miesiac'}},
        {'id': 'najwieksze_koszty', 'nazwa': 'Największe koszty miesiąca', 'ik': 'dol',
         'parametry': {'rodzaj': '-1', 'podstawa': 'Faktura (jedna)|Faktura (w worku)', 'd_wystawienie': 'biezacy:miesiac',
                       'sortuj': 'netto', 'kolejnosc': 'rosnaco'}},
    ],
    'bank': [
        {'id': 'wszystkie', 'nazwa': 'Wszystkie operacje', 'ik': 'bank', 'parametry': {}},
        {'id': 'wplywy', 'nazwa': 'Wpływy', 'ik': 'gora', 'parametry': {'kierunek': 'wplywy', 'wewnetrzne': 'bez'}},
        {'id': 'obciazenia', 'nazwa': 'Obciążenia', 'ik': 'dol', 'parametry': {'kierunek': 'obciazenia', 'wewnetrzne': 'bez'}},
        {'id': 'wewnetrzne', 'nazwa': 'Ruch wewnętrzny i VAT', 'ik': 'przelew', 'parametry': {'wewnetrzne': 'tylko'}},
    ],
    'faktury': [{'id': 'wszystkie', 'nazwa': 'Faktury sprzedażowe', 'ik': 'dokument', 'parametry': {}}],
    'naleznosci': [
        {'id': 'nieoplacone', 'nazwa': 'Należności nieopłacone', 'ik': 'kalendarzX', 'parametry': {}},
        {'id': 'po_terminie', 'nazwa': 'Należności po terminie', 'ik': 'przekreslony', 'parametry': {'po_terminie': '1'}},
    ],
    'zakupy': [
        {'id': 'wszystkie', 'nazwa': 'Rejestr zakupów (biuro)', 'ik': 'dokument', 'parametry': {}},
        {'id': 'bez_platnosci', 'nazwa': 'Dokumenty bez płatności', 'ik': 'dokument', 'parametry': {'stan': 'bez płatności w banku'}},
    ],
    'wplaty': [{'id': 'do_polaczenia', 'nazwa': 'Do połączenia', 'ik': 'rozlacz', 'parametry': {}}],
    'do_polaczenia': [   # pakiet 5: rzeczywiste do połączenia z budżetem
        {'id': 'wszystkie', 'nazwa': 'Do połączenia', 'ik': 'rozlacz', 'parametry': {}},
        {'id': 'pewne', 'nazwa': 'Z pewną podpowiedzią', 'ik': 'ptaszek', 'parametry': {'pewnosc': 'wysoka'}},
        {'id': 'bez_podpowiedzi', 'nazwa': 'Bez podpowiedzi', 'ik': 'przekreslony', 'parametry': {'pewnosc': 'brak'}}],
    'do_weryfikacji': [{'id': 'wszystkie', 'nazwa': 'Do weryfikacji', 'ik': 'weryfikuj', 'parametry': {}}],
    'wydatki': [
        {'id': 'wszystkie', 'nazwa': 'Wszystkie wydatki', 'ik': 'dol', 'parametry': {}},
        {'id': 'nieprzypisane', 'nazwa': 'Nieprzypisane', 'ik': 'przekreslony', 'parametry': {'rodzaj': 'nieprzypisany'}},
        {'id': 'koszty_klientow', 'nazwa': 'Koszty klientów', 'ik': 'folder', 'parametry': {'rodzaj': 'przenoszony'}},
        {'id': 'bez_dokumentu', 'nazwa': 'Bez dokumentu w rejestrze', 'ik': 'plik', 'parametry': {'dokument': 'bez dokumentu'}},
    ],
}


def widoki(con, ekran: str) -> list[dict]:
    """Widoki listy: startowe w stałej kolejności (zmienione przez Mata mają jego parametry), potem własne wg czasu.
    Widok usunięty znika; pierwszy startowy jest domyślny i nie znika."""
    if ekran not in WIDOKI_STARTOWE:
        raise ValueError('nieznana lista')
    start = WIDOKI_STARTOWE[ekran]
    startowe = {v['id']: {**v, 'startowy': True, 'zmieniony': False, 'domyslny': i == 0} for i, v in enumerate(start)}
    wlasne = []
    for r in con.execute('SELECT * FROM widoki WHERE ekran = ? ORDER BY czas, id', (ekran,)):
        if r['usuniety']:
            if r['id'] in startowe and not startowe[r['id']]['domyslny']:
                startowe.pop(r['id'])
            wlasne = [w for w in wlasne if w['id'] != r['id']]
            continue
        v = {'id': r['id'], 'nazwa': r['nazwa'], 'parametry': json.loads(r['parametry'] or '{}'), 'kolumny': json.loads(r['kolumny'] or '[]'),
             'wpis': r['wpis']}
        if r['id'] in startowe:
            startowe[r['id']].update(v, zmieniony=True)
        else:
            wlasne = [w for w in wlasne if w['id'] != r['id']] + [{**v, 'ik': 'oko', 'startowy': False, 'zmieniony': False, 'domyslny': False}]
    return [startowe[v['id']] for v in start if v['id'] in startowe] + wlasne


def menu(con) -> dict:
    """Menu Płatności i Budżetu jak w BS: widoki każdej listy z liczbą pozycji (licznik w menu)."""
    wynik = {}
    stan = zapytania.podsumowanie_naleznosci(con)
    for ekran in WIDOKI_STARTOWE:
        pozycje = []
        for v in widoki(con, ekran):
            if ekran == 'wplaty':
                ile = stan['do_polaczenia']
            elif ekran == 'do_weryfikacji':
                ile = stan['do_weryfikacji']
            else:
                ile = lista(con, ekran, {**v['parametry'], 'ile': '1'})['razem']
            pozycje.append({'id': v['id'], 'nazwa': v['nazwa'], 'ik': v.get('ik', 'oko'), 'ile': ile, 'startowy': v['startowy']})
        wynik[ekran] = pozycje
    return {'ekrany': wynik, 'do_polaczenia': stan['do_polaczenia'], 'do_weryfikacji': stan['do_weryfikacji']}


def podglad_zakresu(con, spec: str, miesieczny: bool) -> dict:
    return filtry.podglad(spec, zapytania.dzis(con), miesieczny, zapytania._pierwszy_dzien_tyg())
