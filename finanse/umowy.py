"""Rejestr umów z klientami (brief, MVP pkt 8). Dane wpisuje Mat (wpisy „umowa” w pliku zmian), apka liczy terminy.

Rodzaje:
- określony bez przedłużenia: umowa wygasa w dniu „do”; alert przed końcem,
- określony z automatycznym przedłużeniem: ostatni dzień na wypowiedzenie = koniec minus okres wypowiedzenia,
- nieokreślony: najwcześniejszy koniec przy wypowiedzeniu dziś (okres wypowiedzenia, opcjonalnie na koniec miesiąca).
Alert na ekranie X dni przed terminem (domyślnie 30). Kanał zewnętrzny później, za zgodą.

Pakiet 9 (decyzje Mata 9 do 11, umowy w cash flow): umowa wskazuje folder klienta w budżecie i jego arkusze przychodowe
(domyślnie wszystkie arkusze folderu z wierszami wpływów). Stary wpis z samym klientem jako tekstem dopasowujemy do folderu
po nazwie przy odczycie, bez przepisywania pliku zmian. Z tego cash flow wie, czyje plany wpływów kończą się w którym
miesiącu (pozycje „z umowy”), kiedy klient odchodzi przy wypowiedzeniu dziś (scenariusz „klienci odchodzą”) i które plany
leżą po końcu umowy na czas określony (ostrzeżenie, plany zostają jak w BS).
"""
import calendar
import json
import re
from datetime import date

# Foldery budżetu, które nie są klientami (bez flagi „brak umowy”). Zmiana: Finanse/Aplikacja/ustawienia.json,
# klucz "foldery_nieklienckie" (lista nazw).
FOLDERY_NIEKLIENCKIE = ('System', 'DigitalH', 'Projekty dodatkowe')
DNI_DOMYSLNIE = 7          # termin pozycji „z umowy”, gdy klient nie ma wiersza wpływów (decyzja 9)
STAWKA_DOMYSLNIE = 23


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


def _odejscie(dzis: date, okres: int, na_koniec: bool) -> date:
    """Koniec współpracy przy wypowiedzeniu złożonym dziś: dziś + okres, przy „na koniec miesiąca” ostatni dzień miesiąca."""
    k = _plus_miesiace(dzis, okres)
    return _koniec_miesiaca(k) if na_koniec else k


def _strona(u: dict, okres: int, dzis: date) -> dict:
    """Dla jednej strony umowy: ostatni dzień na wypowiedzenie (gdy jest) i dzień odejścia przy wypowiedzeniu dziś."""
    na_koniec = bool(u.get('koniec_miesiaca', True))
    teraz = _odejscie(dzis, okres, na_koniec)
    if u.get('rodzaj') == 'okreslony' and u.get('do'):
        koniec = date.fromisoformat(u['do'])
        if u.get('przedluzenie'):
            ostatni = _plus_miesiace(koniec, -okres)
            if na_koniec:
                ostatni = _koniec_miesiaca(ostatni)
            # wypowiedzenie w terminie kończy umowę z jej końcem; spóźnione: umowa się przedłuża, liczymy okres od dziś
            odejscie = koniec if dzis <= ostatni else max(koniec, teraz)
        else:
            ostatni = None
            odejscie = min(koniec, teraz) if okres else koniec
    else:
        ostatni, odejscie = None, teraz
    return {'okres_mies': okres, 'ostatni_dzien': ostatni.isoformat() if ostatni else None, 'odejscie_dzis': odejscie.isoformat()}


def termin(u: dict, dzis: date) -> dict:
    """Wylicza, co i kiedy trzeba zrobić z umową."""
    okres = int(u.get('wypowiedzenie_mies') or 0)
    na_koniec = bool(u.get('koniec_miesiaca', True))
    alert = int(u.get('alert_dni') or 30)
    if u.get('rodzaj') == 'okreslony' and u.get('do'):
        koniec = date.fromisoformat(u['do'])
        if u.get('przedluzenie'):
            ostatni = _plus_miesiace(koniec, -okres)
            if na_koniec:
                ostatni = _koniec_miesiaca(ostatni)
            co = 'ostatni dzień na wypowiedzenie (inaczej umowa się przedłuży)'
        else:
            ostatni = koniec
            co = 'umowa wygasa'
    else:
        koniec = _odejscie(dzis, okres, na_koniec)
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
    okres_my = u.get('wypowiedzenie_mies_my')
    okres_my = okres if okres_my in (None, '') else int(okres_my)
    klient, my = _strona(u, okres, dzis), _strona(u, okres_my, dzis)
    return {'data': data.isoformat(), 'co': co, 'dni': dni, 'stan': stan, 'koniec': koniec.isoformat(),
            # pakiet 9: obie strony umowy (gdy nasz okres wypowiedzenia jest inny, wpis ma „wypowiedzenie_mies_my”)
            'ostatni_dzien_wypowiedzenia': {'klient': klient['ostatni_dzien'], 'my': my['ostatni_dzien']},
            'odejscie_przy_wypowiedzeniu_dzis': {'klient': klient['odejscie_dzis'], 'my': my['odejscie_dzis']},
            'koniec_umowy': u['do'] if u.get('rodzaj') == 'okreslony' and u.get('do') and not u.get('przedluzenie') else None}


def dzien_stanu(con) -> date:
    """„Dziś” w logice = dzień stanu (ostatnia data księgowania ING), jak w reszcie apki; bez banku: data systemowa."""
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone()
    return date.fromisoformat(r[0]) if r and r[0] else date.today()


# ---------- Powiązanie z budżetem (pakiet 9) ----------

def _norm(s) -> str:
    return re.sub(r'[^0-9a-ząćęłńóśźż]', '', str(s or '').casefold())


def foldery_nieklienckie() -> set:
    from .wynik import ustawienia
    z = ustawienia().get('foldery_nieklienckie')
    return set(z) if isinstance(z, list) else set(FOLDERY_NIEKLIENCKIE)


def foldery(con) -> dict:
    """Folder budżetu → jego arkusze (id, nazwa, czy ma wiersze wpływów), po polsku alfabetycznie. Bez arkusza systemowego."""
    from .filtry import klucz_pl
    wynik = {}
    for r in con.execute('SELECT a.id, a.nazwa, a.folder, a.zrodlo, COALESCE(SUM(w.rodzaj = 1), 0) AS wplywy FROM bud_arkusz a'
                         ' LEFT JOIN bud_wiersz w ON w.arkusz = a.id GROUP BY a.id'):
        if r['zrodlo'] == 'system':
            continue
        wynik.setdefault(r['folder'], []).append({'id': r['id'], 'nazwa': r['nazwa'], 'wplywy': bool(r['wplywy'])})
    for v in wynik.values():
        v.sort(key=lambda a: klucz_pl(a['nazwa']))
    return dict(sorted(wynik.items(), key=lambda kv: klucz_pl(kv[0])))


def dopasuj_folder(klient: str, nazwy) -> str | None:
    """Stary wpis „umowa” z klientem jako tekstem: folder o tej samej nazwie (bez wielkości liter, spacji i znaków), a gdy
    takiego nie ma, jedyny folder, którego nazwa zawiera się w nazwie klienta albo odwrotnie."""
    n = _norm(klient)
    if not n:
        return None
    rowne = [f for f in nazwy if _norm(f) == n]
    if rowne:
        return rowne[0]
    czesc = [f for f in nazwy if len(_norm(f)) >= 3 and (_norm(f) in n or n in _norm(f))]
    return czesc[0] if len(czesc) == 1 else None


def rozwiaz(u: dict, fold: dict) -> dict:
    """Folder i arkusze przychodowe umowy: z wpisu, a dla starych wpisów z dopasowania po nazwie i arkuszy folderu."""
    folder, zrodlo = None, None
    if u.get('folder'):
        if u['folder'] in fold:
            folder, zrodlo = u['folder'], 'wpis'
        else:
            zrodlo = 'folderu z wpisu nie ma w budżecie'
    if not folder:
        folder = dopasuj_folder(u.get('klient'), list(fold))
        if folder:
            zrodlo = 'dopasowanie po nazwie klienta'
    ark_folderu = fold.get(folder, [])
    if isinstance(u.get('arkusze'), list) and u['arkusze']:
        wszystkie = {a['id']: a for v in fold.values() for a in v}
        arkusze = [wszystkie[i] for i in u['arkusze'] if i in wszystkie]
        ark_zrodlo = 'wpis'
    else:
        arkusze = [a for a in ark_folderu if a['wplywy']]
        ark_zrodlo = 'domyślnie: arkusze folderu z wierszami wpływów'
    return {'folder': folder, 'folder_zrodlo': zrodlo, 'arkusze': [{'id': a['id'], 'nazwa': a['nazwa']} for a in arkusze],
            'arkusze_zrodlo': ark_zrodlo}


def _umowy(con) -> list[dict]:
    return [json.loads(r[0]) for r in con.execute('SELECT dane FROM umowy ORDER BY id')]


def wiersz_klienta(con, arkusze: list[str]) -> dict:
    """Wiersz wpływów klienta, z którego pozycja „z umowy” bierze stawkę VAT i dni na płatność: ten z najpóźniejszym
    zaplanowanym miesiącem (przy remisie większa suma). Bez wiersza: 23% i 7 dni (decyzja 9)."""
    from .budzet import stawka_proc
    from .plan import dni_na_platnosc, ma_vat
    brak = {'stawka': STAWKA_DOMYSLNIE, 'dni': DNI_DOMYSLNIE, 'arkusz_id': arkusze[0] if arkusze else '', 'arkusz': '',
            'kontrahent': '', 'metoda': '', 'wiersz': None, 'podstawa': ''}
    if not arkusze:
        return brak
    znaki = ','.join('?' * len(arkusze))
    r = con.execute(
        f'SELECT w.id, w.podstawa, w.stawka_vat, w.dni_na_platnosc, w.kontrahent, w.metoda, a.id AS arkusz_id, a.nazwa,'
        f' MAX(p.miesiac) AS ostatni, SUM(p.netto) AS suma FROM bud_wiersz w JOIN bud_arkusz a ON a.id = w.arkusz'
        f' LEFT JOIN bud_platnosc p ON p.wiersz = w.id WHERE w.rodzaj = 1 AND a.id IN ({znaki})'
        f' GROUP BY w.id ORDER BY ostatni IS NULL, ostatni DESC, suma DESC, w.id LIMIT 1', arkusze).fetchone()
    if not r:
        return brak
    if ma_vat(r['podstawa'] or ''):
        stawka = stawka_proc(r['stawka_vat'])
        stawka = STAWKA_DOMYSLNIE if stawka is None else stawka
    else:
        stawka = 0
    dni = DNI_DOMYSLNIE if r['dni_na_platnosc'] in (None, '') else dni_na_platnosc(r['dni_na_platnosc'])
    return {'stawka': stawka, 'dni': dni, 'arkusz_id': r['arkusz_id'], 'arkusz': r['nazwa'], 'kontrahent': r['kontrahent'] or '',
            'metoda': r['metoda'] or '', 'wiersz': r['id'], 'podstawa': r['podstawa'] or ''}


def plany_po_koncu(con, koniec: str | None, arkusze: list[str]) -> dict:
    """Plany wpływów w miesiącach po końcu umowy na czas określony (bez przedłużenia). Zostają w cash flow jak w BS,
    apka tylko ostrzega (decyzja 10). Per arkusz liczba planów i suma netto."""
    if not koniec or not arkusze:
        return {'ile': 0, 'netto': 0, 'od_miesiaca': None, 'arkusze': {}}
    znaki = ','.join('?' * len(arkusze))
    po = {}
    for r in con.execute(f"SELECT w.arkusz, COUNT(*) AS ile, SUM(p.netto) AS netto, MIN(p.miesiac) AS od FROM bud_platnosc p"
                         f" JOIN bud_wiersz w ON w.id = p.wiersz WHERE w.arkusz IN ({znaki}) AND p.rodzaj = 1 AND p.typ = 'plan'"
                         f" AND COALESCE(p.decyzja, '') != 'anulowane' AND COALESCE(p.ukryty, 0) = 0 AND p.miesiac > ?"
                         f" GROUP BY w.arkusz", (*arkusze, koniec[:7])):
        po[r['arkusz']] = {'ile': r['ile'], 'netto': r['netto'] or 0, 'od_miesiaca': r['od']}
    return {'ile': sum(x['ile'] for x in po.values()), 'netto': sum(x['netto'] for x in po.values()),
            'od_miesiaca': min((x['od_miesiaca'] for x in po.values()), default=None), 'arkusze': po}


def rozwiazane(con, dzis: date | None = None) -> list[dict]:
    """Umowy z terminami i powiązaniem z budżetem: dla listy, karty klienta, arkusza i cash flow."""
    dzis = dzis or dzien_stanu(con)
    fold = foldery(con)
    wynik = []
    for u in _umowy(con):
        r = rozwiaz(u, fold)
        t = termin(u, dzis)
        ids = [a['id'] for a in r['arkusze']]
        wynik.append({**u, **t, **r, 'arkusze_ids': ids, 'plany_po_koncu': plany_po_koncu(con, t['koniec_umowy'], ids),
                      'brak_powiazania': not r['folder'] and not ids})
    return wynik


def klienci(con, umowy: list[dict], fold: dict | None = None) -> list[dict]:
    """Foldery klientów z wierszami wpływów i ich umowy; bez umowy: flaga „brak umowy” (cash flow liczy ich tylko z planów)."""
    fold = foldery(con) if fold is None else fold
    pomin = foldery_nieklienckie()
    po_folderze = {}
    for u in umowy:
        if u.get('folder'):
            po_folderze.setdefault(u['folder'], []).append(u['id'])
    return [{'folder': f, 'arkusze': [{'id': a['id'], 'nazwa': a['nazwa']} for a in ark if a['wplywy']],
             'umowy': po_folderze.get(f, []), 'brak_umowy': f not in po_folderze}
            for f, ark in fold.items() if f not in pomin and any(a['wplywy'] for a in ark)]


def lista(con, dzis: date | None = None) -> dict:
    dzis = dzis or dzien_stanu(con)
    fold = foldery(con)
    umowy = rozwiazane(con, dzis)
    kolej = {'minął': 0, 'alert': 1, 'ok': 2, 'bez terminu': 3}
    umowy.sort(key=lambda u: (kolej[u['stan']], u['data']))
    kl = klienci(con, umowy, fold)
    return {'umowy': umowy, 'dzis': dzis.isoformat(), 'wartosc_mies': sum(int(u.get('wartosc_mies') or 0) for u in umowy),
            'alerty': sum(1 for u in umowy if u['stan'] in ('alert', 'minął')),
            'klienci': kl, 'bez_umowy': sum(1 for k in kl if k['brak_umowy']),
            'plany_po_koncu': sum(u['plany_po_koncu']['ile'] for u in umowy),
            'foldery': [{'folder': f, 'arkusze': ark} for f, ark in fold.items()]}


def dla_arkusza(con, aid: str, dzis: date | None = None) -> dict:
    """Pole „umowa” arkusza: która umowa obejmuje arkusz, stan, koniec i plany po końcu umowy; brak umowy dla arkusza klienta."""
    a = con.execute('SELECT folder, zrodlo FROM bud_arkusz WHERE id = ?', (aid,)).fetchone()
    if not a or a['zrodlo'] == 'system':
        return {'umowa': None, 'brak_umowy': False}
    for u in rozwiazane(con, dzis):
        if aid in u['arkusze_ids']:
            po = u['plany_po_koncu']['arkusze'].get(aid, {'ile': 0, 'netto': 0, 'od_miesiaca': None})
            return {'umowa': u['id'], 'klient': u.get('klient'), 'folder': u['folder'], 'rodzaj': u.get('rodzaj'), 'stan': u['stan'],
                    'koniec_umowy': u['koniec_umowy'], 'odejscie_przy_wypowiedzeniu_dzis': u['odejscie_przy_wypowiedzeniu_dzis'],
                    'plany_po_koncu': po, 'brak_umowy': False}
    return {'umowa': None, 'folder': a['folder'], 'brak_umowy': a['folder'] not in foldery_nieklienckie()}


def sprawdz_odwolania(con, dane: dict):
    """Wpis „umowa”: folder i arkusze muszą istnieć w budżecie (stare wpisy bez nich przechodzą jak dotąd)."""
    if dane.get('usun'):
        return
    fold = foldery(con)
    if dane.get('folder') and dane['folder'] not in fold:
        raise ValueError(f"nie ma folderu {dane['folder']} w budżecie")
    znane = {a['id'] for v in fold.values() for a in v}
    for i in dane.get('arkusze') or []:
        if i not in znane:
            raise ValueError(f'nie ma arkusza {i} w budżecie')
