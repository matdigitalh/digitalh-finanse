"""Pakiet 11 (BL-02, część formalna): karta klienta z umową, lista klientów z kolumnami umowy, alerty umów na pulpit.

Klient = nazwa z faktur (APK-KLI-01), która zwykle jest też nazwą folderu w budżecie (folder BS po numerze faktury).
Umowa = wpis „umowa” (rejestr umów, finanse/umowy.py). Karta czyta umowy tą samą funkcją co GET /api/umowy (umowy.lista)
i nic w nich nie zmienia; zapis z karty idzie istniejącym wpisem „umowa”.

Punkt podpięcia pakietu 9 (POLA_P9): po pakiecie 9 umowy.lista() ma przy umowie powiązanie z budżetem (folder, arkusze)
i terminy (ostatni dzień wypowiedzenia, termin odejścia, plany po końcu umowy). Pole obecne w umowie wygrywa; gdy go nie ma,
karta liczy wartość zastępczą:
- folder = folder budżetu o nazwie klienta (bez wielkości liter), arkusze = arkusze tego folderu,
- ostatni dzień na wypowiedzenie (nasza i ich strona, ten sam okres z umowy) i termin odejścia z umowy.termin(),
- plany po końcu umowy = plany wpływów z arkuszy klienta po miesiącu końca umowy na czas określony bez przedłużenia.

„Dziś” = dzień stanu (ostatnia data księgowania ING), jak w całej apce."""
import calendar
from collections import defaultdict
from datetime import date, timedelta

from . import rentownosc, umowy as rejestr, wynik, zapytania
from .zapytania_budzet import _dzien_stanu

# Nazwy pól, które dokłada pakiet 9 w umowy.lista() (u nas: wartości zastępcze). Zmiana nazwy po stronie p9 = jedna linijka tu.
POLA_P9 = {
    'folder': 'folder',                                         # folder budżetu klienta
    'arkusze': 'arkusze',                                       # lista ID arkuszy klienta
    'ostatni_dzien_wypowiedzenia': 'ostatni_dzien_wypowiedzenia',   # data albo {'nasza': data, 'ich': data}
    'termin_odejscia': 'termin_odejscia',                       # data końca współpracy przy wypowiedzeniu dziś
    'plany_po_koncu': 'plany_po_koncu',                         # {'ile', 'kwota', 'od'} albo lista płatności
}
# Pola umowy liczone przez apkę (nie są częścią wpisu, więc nie wracają w formularzu karty). Folder i arkusze p9 zapisze
# we wpisie, więc zostają w „dane”: zapis z karty ich nie gubi.
POCHODNE = {'data', 'co', 'dni', 'stan', 'koniec', 'wpis', 'czas', POLA_P9['ostatni_dzien_wypowiedzenia'],
            POLA_P9['termin_odejscia'], POLA_P9['plany_po_koncu']}
KOLEJNOSC_STANU = {'minął': 0, 'alert': 1, 'brak umowy': 2, 'ok': 3}
# Foldery, które nie są klientami (bez alertu „brak umowy”); inne nazwy w ustawienia.json, klucz „foldery_bez_umowy”
FOLDERY_BEZ_UMOWY = ('DigitalH', 'Projekty dodatkowe')


def _klucz(nazwa) -> str:
    return ' '.join(str(nazwa or '').split()).casefold()


def _z_p9(u: dict, pole: str):
    v = u.get(POLA_P9[pole])
    return None if v in (None, '', [], {}) else v


def _plus_miesiace(d: date, n: int) -> date:
    m = d.month - 1 + n
    r, m = d.year + m // 12, m % 12 + 1
    return date(r, m, min(d.day, calendar.monthrange(r, m)[1]))


def _foldery_bez_umowy() -> set:
    lista = wynik.ustawienia().get('foldery_bez_umowy')
    return {_klucz(x) for x in (lista if isinstance(lista, list) else FOLDERY_BEZ_UMOWY)}


def _arkusze(con) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT id, nazwa, folder, kategoria, od, do FROM bud_arkusz"
                                         " WHERE COALESCE(zrodlo, '') != 'system' ORDER BY folder, kategoria, nazwa")]


def _plany_wplywow(con, od_miesiaca: str) -> dict:
    """Plany wpływów (nie rzeczywiste) od miesiąca: arkusz → {miesiąc: netto}."""
    t = defaultdict(lambda: defaultdict(int))
    for r in con.execute("SELECT w.arkusz, p.miesiac, SUM(p.netto) FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz"
                         " WHERE p.typ = 'plan' AND p.rodzaj = 1 AND p.aktualna = 1 AND p.netto > 0 AND p.miesiac >= ?"
                         " AND COALESCE(p.decyzja, '') != 'anulowane' GROUP BY w.arkusz, p.miesiac", (od_miesiaca,)):
        t[r[0]][r[1]] += r[2]
    return t


def _data_pl(iso) -> str:
    return f'{iso[8:10]}.{iso[5:7]}.{iso[:4]}' if iso and len(iso) >= 10 else (f'{iso[5:7]}.{iso[:4]}' if iso else '')


def _miesiac_plus(m: str, n: int) -> str:
    r, mm = int(m[:4]), int(m[5:7]) - 1 + n
    return f'{r + mm // 12}-{mm % 12 + 1:02d}'


def opis_umowy(u: dict, dzis: str, arkusze_klienta: list[str], plany: dict) -> dict:
    """Umowa z rejestru (już z umowy.termin) uzupełniona o to, czego potrzebuje karta: stan wg BL-02, typ i wypowiedzenie
    po ludzku, ostatni dzień na wypowiedzenie (nasza i ich strona), termin odejścia, plany po końcu umowy."""
    d = date.fromisoformat(dzis)
    stan = u.get('stan') if u.get('stan') in ('ok', 'alert', 'minął') else 'ok'   # „bez terminu” (nieokreślony) = ok
    okreslony = u.get('rodzaj') == 'okreslony' and bool(u.get('do'))
    okres = int(u.get('wypowiedzenie_mies') or 0)
    if okreslony:
        typ = f"określony do {_data_pl(u['do'])}" + (', przedłuża się' if u.get('przedluzenie') else '')
    else:
        typ = 'nieokreślony'
    wyp =f"{okres} mies." + (', na koniec miesiąca' if u.get('koniec_miesiaca', True) and okres else '') if okres else 'bez okresu wypowiedzenia'
    # ostatni dzień na wypowiedzenie: tylko gdy umowa sama się przedłuża (inaczej wygasa albo można wypowiedzieć w każdej chwili)
    ost = _z_p9(u, 'ostatni_dzien_wypowiedzenia')
    if ost is None and okreslony and u.get('przedluzenie'):
        ost = u.get('data')
    if isinstance(ost, str):
        ost = {'nasza': ost, 'ich': ost}
    odejscie = _z_p9(u, 'termin_odejscia')
    if odejscie is None:
        if not okreslony:
            odejscie = u.get('koniec')
        elif not u.get('przedluzenie') or (ost and dzis <= ost['ich']):
            odejscie = u['do']
        elif u.get('zawarta'):   # termin na wypowiedzenie minął: umowa przedłużyła się o ten sam okres (może kilka razy)
            koniec = date.fromisoformat(u['do'])
            start = date.fromisoformat(u['zawarta'])
            po = koniec + timedelta(days=1)   # umowa 1.11.2025 do 31.10.2026 trwa 12 miesięcy
            dl = max(1, (po.year - start.year) * 12 + po.month - start.month)
            while _plus_miesiace(koniec, -okres) < d:
                koniec = _plus_miesiace(koniec, dl)
            odejscie = koniec.isoformat()
    po_koncu = _z_p9(u, 'plany_po_koncu')
    if isinstance(po_koncu, list):
        po_koncu = {'ile': len(po_koncu), 'kwota': sum(int(x.get('netto') or x.get('kwota') or 0) for x in po_koncu),
                    'od': min((str(x.get('miesiac') or '') for x in po_koncu), default='')}
    if po_koncu is None and okreslony and not u.get('przedluzenie'):
        koniec_m = u['do'][:7]
        mies = defaultdict(int)
        for aid in arkusze_klienta:
            for m, kw in plany.get(aid, {}).items():
                if m > koniec_m:
                    mies[m] += kw
        if mies:
            po_koncu = {'ile': len(mies), 'kwota': sum(mies.values()), 'od': min(mies)}
    return {'id': u['id'], 'klient': u.get('klient'), 'stan': stan, 'typ': typ, 'wypowiedzenie': wyp,
            'termin': u.get('data'), 'co': u.get('co'), 'dni': u.get('dni'), 'koniec': u.get('koniec'),
            'ostatni_dzien_wypowiedzenia': ost, 'termin_odejscia': odejscie, 'plany_po_koncu': po_koncu,
            'wartosc_mies': int(u.get('wartosc_mies') or 0), 'okreslony': okreslony,
            'dane': {k: v for k, v in u.items() if k not in POCHODNE}}


def _kontekst(con) -> dict:
    """Wspólne dane listy, karty i alertów: dzień stanu, arkusze klientów, plany wpływów, umowy wg klienta."""
    dzis = _dzien_stanu(con)
    ark = _arkusze(con)
    plany = _plany_wplywow(con, dzis[:7])
    um = defaultdict(list)
    for u in rejestr.lista(con, date.fromisoformat(dzis))['umowy']:
        um[_klucz(u.get('klient'))].append(u)
    foldery = defaultdict(list)
    for a in ark:
        foldery[_klucz(a['folder'])].append(a)
    return {'dzis': dzis, 'arkusze': ark, 'ark_po_id': {a['id']: a for a in ark}, 'plany': plany, 'umowy': um, 'foldery': foldery,
            'bez_umowy': _foldery_bez_umowy()}


def _klient(k: dict, nazwa: str) -> dict:
    """Jeden klient: folder i arkusze (p9 albo folder o nazwie klienta), umowa główna (najpilniejsza), plany, ostrzeżenia."""
    klucz = _klucz(nazwa)
    us = k['umowy'].get(klucz, [])
    folder = next((_z_p9(u, 'folder') for u in us if _z_p9(u, 'folder')), None)
    arkusze_p9 = next((_z_p9(u, 'arkusze') for u in us if _z_p9(u, 'arkusze')), None)
    if arkusze_p9:
        ark = [k['ark_po_id'][i] for i in arkusze_p9 if i in k['ark_po_id']]
    else:
        ark = k['foldery'].get(_klucz(folder) if folder else klucz, [])
    folder = folder or (ark[0]['folder'] if ark else None)
    ids = [a['id'] for a in ark]
    opisy = sorted((opis_umowy(u, k['dzis'], ids, k['plany']) for u in us),
                   key=lambda o: (KOLEJNOSC_STANU[o['stan']], o['termin'] or '9999'))
    glowna = opisy[0] if opisy else None
    plany_12 = defaultdict(int)
    koniec_12 = _miesiac_plus(k['dzis'][:7], 11)
    for aid in ids:
        for m, kw in k['plany'].get(aid, {}).items():
            if m <= koniec_12:
                plany_12[m] += kw
    ostatni_plan = max((m for aid in ids for m in k['plany'].get(aid, {})), default=None)
    stan = glowna['stan'] if glowna else 'brak umowy'
    ostrz = []
    if not glowna and plany_12 and klucz not in k['bez_umowy']:
        ostrz.append({'rodzaj': 'brak_umowy', 'tekst': 'Klient ma plany wpływów w budżecie, a w rejestrze nie ma jego umowy.'})
    for o in opisy:
        if o['plany_po_koncu']:
            pk = o['plany_po_koncu']
            ostrz.append({'rodzaj': 'plany_po_koncu', 'kwota': pk['kwota'],
                          'tekst': f"Umowa na czas określony kończy się {_data_pl(o['dane'].get('do'))}, a budżet ma plany wpływów "
                                   f"po tej dacie ({pk['ile']} mies. od {_data_pl(pk['od'])}). W cash flow zostają; sprawdź, "
                                   'czy umowa będzie przedłużona.'})
    return {'klient': nazwa, 'folder': folder, 'arkusze': [{'id': a['id'], 'nazwa': a['nazwa'], 'kategoria': a['kategoria'],
                                                            'od': a['od'], 'do': a['do']} for a in ark],
            'umowa': glowna, 'umowy': opisy, 'stan': stan, 'plany_12m': sum(plany_12.values()), 'plany_mies': dict(plany_12),
            'ostatni_plan': ostatni_plan, 'ostrzezenia': ostrz, 'bez_umowy_ok': klucz in k['bez_umowy']}


def _nazwy_klientow(con, k: dict) -> dict:
    """Klucz → nazwa: klienci z faktur, z umów i foldery budżetu z planami wpływów (klient bez faktur, np. nowy)."""
    nazwy = {}
    for r in con.execute('SELECT DISTINCT klient FROM faktury_klient ORDER BY klient'):
        nazwy.setdefault(_klucz(r[0]), r[0])
    for kl, us in k['umowy'].items():
        nazwy.setdefault(kl, us[0]['klient'])
    for kl, ark in k['foldery'].items():
        if kl not in k['bez_umowy'] and any(k['plany'].get(a['id']) for a in ark):
            nazwy.setdefault(kl, ark[0]['folder'])
    return nazwy


def lista(con) -> dict:
    """Kolumny umowy do listy klientów (łączone w interfejsie z GET /api/klienci po nazwie klienta)."""
    k = _kontekst(con)
    klienci = [_klient(k, n) for n in _nazwy_klientow(con, k).values()]
    klienci.sort(key=lambda x: (KOLEJNOSC_STANU[x['stan']], _klucz(x['klient'])))
    return {'dzien_stanu': k['dzis'], 'klienci': klienci,
            'liczniki': {s: sum(1 for x in klienci if x['stan'] == s) for s in KOLEJNOSC_STANU}}


def alerty(con, klienci: list[dict] | None = None) -> list[dict]:
    """Alerty umów na pulpit (APK-BRAK-03): zbliża się albo minął termin, plany wpływów po końcu umowy, brak umowy u klienta
    z planami wpływów. Od najpilniejszego. klienci: wynik lista()['klienci'], gdy już policzony."""
    wynik_ = []
    for x in (klienci if klienci is not None else lista(con)['klienci']):
        n = x['klient']
        for o in x['umowy']:
            if o['stan'] in ('alert', 'minął'):
                wynik_.append({'klient': n, 'rodzaj': o['stan'], 'data': o['termin'], 'dni': o['dni'], 'co': o['co'], 'umowa': o['id']})
        for o in x['ostrzezenia']:
            if o['rodzaj'] == 'brak_umowy':
                wynik_.append({'klient': n, 'rodzaj': 'brak umowy', 'kwota': x['plany_12m'], 'co': o['tekst']})
            else:
                wynik_.append({'klient': n, 'rodzaj': 'plany po końcu', 'kwota': o.get('kwota'), 'co': o['tekst']})
    kolej = {'minął': 0, 'alert': 1, 'plany po końcu': 2, 'brak umowy': 3}
    wynik_.sort(key=lambda a: (kolej[a['rodzaj']], a.get('data') or '', _klucz(a['klient'])))
    return wynik_


def karta(con, nazwa: str, rok=None) -> dict:
    """Karta klienta: dane (NIP, nabywcy, folder i arkusze), umowa, obroty i należności, rentowność, plany w budżecie."""
    nazwa = str(nazwa or '').strip()
    if not nazwa:
        raise ValueError('brak nazwy klienta')
    k = _kontekst(con)
    x = _klient(k, nazwa)
    rok_ = rok if rok and len(str(rok)) == 4 and str(rok).isdigit() else None
    szczeg = zapytania.klient(con, nazwa, rok_)
    lista_fin = zapytania.klienci_lista(con, rok_)
    fin = next((r for r in lista_fin['klienci'] if _klucz(r['klient']) == _klucz(nazwa)), None)
    nab = [dict(r) for r in con.execute('SELECT f.nabywca, f.nip, COUNT(*) AS faktur FROM faktury f JOIN faktury_klient fk USING(numer)'
                                        ' WHERE fk.klient = ? GROUP BY f.nabywca, f.nip ORDER BY faktur DESC', (nazwa,))]
    rok_rent = rok_ or wynik._rok_domyslny(con)
    rent = next((r for r in rentownosc.klienci(con, rok_rent)['klienci'] if _klucz(r['klient']) == _klucz(nazwa)), None)
    budzet = None
    if x['folder']:
        from .przestawna import policz
        p = policz(con, rok_rent, ['folder'], folder=x['folder'])
        budzet = p['razem']
    # plany i wykonanie w arkuszach klienta: 12 miesięcy od miesiąca dnia stanu
    ids = [a['id'] for a in x['arkusze']]
    od_m = k['dzis'][:7]
    mies = [_miesiac_plus(od_m, i) for i in range(12)]
    tab = {m: {'plan_wplywy': 0, 'rzecz_wplywy': 0, 'obciazenia': 0} for m in mies}
    if ids:
        znaki = ','.join('?' * len(ids))
        for r in con.execute(f'SELECT p.miesiac, p.typ, p.rodzaj, SUM(p.netto) FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz'
                             f' WHERE w.arkusz IN ({znaki}) AND p.aktualna = 1 AND p.miesiac BETWEEN ? AND ?'
                             ' GROUP BY p.miesiac, p.typ, p.rodzaj', [*ids, mies[0], mies[-1]]):
            t = tab[r[0]]
            if r[2] == 1:
                t['plan_wplywy' if r[1] == 'plan' else 'rzecz_wplywy'] += r[3]
            else:
                t['obciazenia'] += r[3]
    return {**x, 'rok': rok_, 'rok_rentownosci': rok_rent, 'lata': lista_fin['lata'], 'dzien_stanu': k['dzis'],
            'nabywcy': nab, 'nip': sorted({n['nip'] for n in nab if n['nip']}),
            'obroty': fin or {'klient': nazwa, 'faktur': 0, 'przychod': 0, 'wplaty': 0, 'naleznosc': 0, 'po_terminie': 0, 'koszty': 0,
                              'marza': 0, 'marza_proc': None},
            'miesiace': szczeg['miesiace'], 'faktury': szczeg['faktury'], 'koszty': szczeg['koszty'],
            'rentownosc': rent, 'budzet': budzet, 'plany': [{'miesiac': m, **tab[m]} for m in mies],
            'umowa_nowa': {'klient': nazwa, 'rodzaj': 'nieokreslony', 'wypowiedzenie_mies': 1, 'koniec_miesiaca': True, 'alert_dni': 30}}
