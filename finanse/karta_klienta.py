"""Pakiet 11 (BL-02, część formalna): karta klienta z umową, lista klientów z kolumnami umowy, alerty umów na pulpit.

Klient = nazwa z faktur (APK-KLI-01), która zwykle jest też nazwą folderu w budżecie (folder BS po numerze faktury).
Umowa = wpis „umowa” (rejestr umów, finanse/umowy.py). Karta czyta umowy tą samą funkcją co GET /api/umowy (umowy.lista)
i nic w nich nie zmienia; zapis z karty idzie istniejącym wpisem „umowa”.

Pola z pakietu 9 (umowy.rozwiazane, przez umowy.lista): folder klienta (z wpisu albo dopasowany po nazwie), arkusze
umowy, ostatni dzień na wypowiedzenie i odejście przy wypowiedzeniu dziś z obu stron (umowy.termin), plany po końcu
umowy (umowy.plany_po_koncu). Karta ich nie liczy drugi raz, tylko zmienia kształt na swój (_strony, _po_koncu).
Klient bez umowy: folder budżetu o nazwie klienta (bez wielkości liter). Arkusze na karcie: wskazane w umowie, a bez
wskazania wszystkie arkusze folderu (karta pokazuje też koszty klienta).

„Dziś” = dzień stanu (ostatnia data księgowania ING), jak w całej apce."""
from collections import defaultdict
from datetime import date

from . import rentownosc, umowy as rejestr, wynik, zapytania
from .zapytania_budzet import _dzien_stanu

# Pola umowy liczone przez apkę (umowy.termin i umowy.rozwiazane), nie są częścią wpisu. Formularz karty odsyła „dane”,
# czyli surowy wpis (z folderem i arkuszami tak, jak je zapisano), więc zapis z karty nie utrwala wartości wyliczonych.
POCHODNE = {'data', 'co', 'dni', 'stan', 'koniec', 'wpis', 'czas', 'ostatni_dzien_wypowiedzenia', 'odejscie_przy_wypowiedzeniu_dzis',
            'koniec_umowy', 'folder_zrodlo', 'arkusze_zrodlo', 'arkusze_ids', 'plany_po_koncu', 'brak_powiazania', 'termin_odejscia'}
KOLEJNOSC_STANU = {'minął': 0, 'alert': 1, 'brak umowy': 2, 'ok': 3}
# Foldery, które nie są klientami (bez alertu „brak umowy”); inne nazwy w ustawienia.json, klucz „foldery_bez_umowy”
FOLDERY_BEZ_UMOWY = ('DigitalH', 'Projekty dodatkowe')


def _klucz(nazwa) -> str:
    return ' '.join(str(nazwa or '').split()).casefold()


def _strony(v):
    """Ostatni dzień na wypowiedzenie z pakietu 9 ({klient, my}) w kształcie karty ({nasza, ich}); brak terminu: None."""
    if isinstance(v, str):
        return {'nasza': v, 'ich': v}
    if isinstance(v, dict):
        nasza, ich = v.get('nasza', v.get('my')), v.get('ich', v.get('klient'))
        if nasza or ich:
            return {'nasza': nasza or ich, 'ich': ich or nasza}
    return None


def _po_koncu(v):
    """Plany po końcu umowy z pakietu 9 ({ile, netto, od_miesiaca}) w kształcie karty ({ile, kwota, od}); brak: None."""
    if not isinstance(v, dict) or not v.get('ile'):
        return None
    return {'ile': v['ile'], 'kwota': v.get('netto', v.get('kwota', 0)), 'od': v.get('od_miesiaca', v.get('od'))}


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


def opis_umowy(u: dict, dzis: str, surowe: dict | None = None) -> dict:
    """Umowa z rejestru (umowy.rozwiazane: terminy i powiązanie z budżetem z pakietu 9) uzupełniona o to, czego potrzebuje
    karta: stan wg BL-02, typ i wypowiedzenie po ludzku. surowe: wpis umowy bez pól wyliczonych (do formularza karty)."""
    stan = u.get('stan') if u.get('stan') in ('ok', 'alert', 'minął') else 'ok'   # „bez terminu” (nieokreślony) = ok
    okreslony = u.get('rodzaj') == 'okreslony' and bool(u.get('do'))
    okres = int(u.get('wypowiedzenie_mies') or 0)
    if okreslony:
        typ = f"określony do {_data_pl(u['do'])}" + (', przedłuża się' if u.get('przedluzenie') else '')
    else:
        typ = 'nieokreślony'
    wyp = f"{okres} mies." + (', na koniec miesiąca' if u.get('koniec_miesiaca', True) and okres else '') if okres else 'bez okresu wypowiedzenia'
    odejscie = u.get('odejscie_przy_wypowiedzeniu_dzis')
    odejscie = odejscie.get('klient') if isinstance(odejscie, dict) else (odejscie or u.get('termin_odejscia'))
    zrodlo = surowe if surowe is not None else u
    return {'id': u['id'], 'klient': u.get('klient'), 'stan': stan, 'typ': typ, 'wypowiedzenie': wyp,
            'termin': u.get('data'), 'co': u.get('co'), 'dni': u.get('dni'), 'koniec': u.get('koniec'),
            'ostatni_dzien_wypowiedzenia': _strony(u.get('ostatni_dzien_wypowiedzenia')), 'termin_odejscia': odejscie,
            'plany_po_koncu': _po_koncu(u.get('plany_po_koncu')),
            'wartosc_mies': int(u.get('wartosc_mies') or 0), 'okreslony': okreslony,
            'dane': {k: v for k, v in zrodlo.items() if k not in POCHODNE}}


def _kontekst(con) -> dict:
    """Wspólne dane listy, karty i alertów: dzień stanu, arkusze klientów, plany wpływów, umowy wg klienta."""
    dzis = _dzien_stanu(con)
    ark = _arkusze(con)
    plany = _plany_wplywow(con, dzis[:7])
    um = defaultdict(list)
    surowe = {u['id']: u for u in rejestr._umowy(con)}   # wpisy bez pól wyliczonych (formularz karty)
    for u in rejestr.lista(con, date.fromisoformat(dzis))['umowy']:
        um[_klucz(u.get('klient'))].append(u)
    foldery = defaultdict(list)
    for a in ark:
        foldery[_klucz(a['folder'])].append(a)
    return {'dzis': dzis, 'arkusze': ark, 'ark_po_id': {a['id']: a for a in ark}, 'plany': plany, 'umowy': um, 'foldery': foldery,
            'surowe': surowe,
            'bez_umowy': _foldery_bez_umowy()}


def _klient(k: dict, nazwa: str) -> dict:
    """Jeden klient: folder i arkusze (z umowy, pakiet 9, albo folder o nazwie klienta), umowa główna (najpilniejsza), plany,
    ostrzeżenia."""
    klucz = _klucz(nazwa)
    us = k['umowy'].get(klucz, [])
    folder = next((u['folder'] for u in us if u.get('folder')), None)
    arkusze_umowy = next((u['arkusze_ids'] for u in us if u.get('arkusze_zrodlo') == 'wpis' and u.get('arkusze_ids')), None)
    if arkusze_umowy:
        ark = [k['ark_po_id'][i] for i in arkusze_umowy if i in k['ark_po_id']]
    else:
        ark = k['foldery'].get(_klucz(folder) if folder else klucz, [])
    folder = folder or (ark[0]['folder'] if ark else None)
    ids = [a['id'] for a in ark]
    opisy = sorted((opis_umowy(u, k['dzis'], k['surowe'].get(u['id'])) for u in us),
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
                                   f"po tej dacie (planów: {pk['ile']}, od {_data_pl(pk['od'])}). W cash flow zostają; sprawdź, "
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
