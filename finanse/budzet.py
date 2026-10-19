"""Budżet jak w Budget Studio: folder → kategoria → arkusz → wiersz → płatność (plan albo rzeczywista).

Źródła, w kolejności nakładania:
  1. plik importu Finanse/Aplikacja/import_bs.json, generowany deterministycznie z najnowszego eksportu BS
     (Raporty/Dane/Budget Studio) i listy arkuszy ze zwiadu (Aplikacja/arkusze_bs.json); ID z BS zachowane,
  2. zdarzenia „bud” z pliku zmian (plany Mata, od 2027): dodaj/zmień/usuń arkusz, wiersz, płatność,
     akcje na wierszach (seria = kilka operacji w jednym wpisie, wszystkie albo żadna); każde ma czas, Maca
     i stan „było”, cofnięcie przez „cofnij”.
Stabilne ID: Aplikacja/mapa_id.json pamięta, do którego wiersza należy płatność BS i do którego arkusza wiersz,
więc zmiana kontrahenta, komentarza czy folderu w kolejnym eksporcie nie zmienia ID, a zmiany Mata nie giną.
Zdarzenie, które nie ma do czego się odnieść, nie znika po cichu: trafia do bud_osierocone (ekran Historia zmian).
Model żyje w tabelach bud_* odbudowywanych przy każdym starcie, jak reszta bazy.
"""
import calendar
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from . import konfig
from .format import data_iso, grosze, norm

PODSTAWY = ['Faktura (jedna)', 'Faktura (w worku)', 'Bez faktury', 'Bez faktury (w worku)', 'Umowa o pracę - dla wykonawcy',
            'Umowa o pracę - PIT', 'Umowa o pracę - ZUS', 'Podatek VAT', 'Podatek dochodowy']
ETAPY = ['Planowana', 'Niewymagana', 'Opłacona', 'Po terminie']
CYKLE = {'brak': 0, 'miesiac': 1, 'kwartal': 3, 'rok': 12}


def _slug(*czesci) -> str:
    return hashlib.sha1('|'.join(czesci).encode('utf-8')).hexdigest()[:12]


def _podstawa(s: str) -> str:
    s = (s or '').strip()
    return {'Faktura': 'Faktura (jedna)', 'Bez faktury': 'Bez faktury'}.get(s, s)


STAWKI = (23, 8, 5, 0)


def stawka_proc(s, scisle=False) -> int | None:
    """Stawka VAT w procentach z zapisu BS (0,23; BS eksportuje stawkę efektywną, np. 0,2299), apki (23, '23 %')
    albo None dla braku, zw i np. Wartość w odległości do 0,1 pkt proc. od 23, 8, 5 to ta stawka (zaokrąglenia BS), 0 tylko dokładnie;
    inna (faktura z kilkoma stawkami, np. 0,138) to None, a scisle=True: błąd (walidacja wpisów)."""
    if s is None or isinstance(s, bool):
        return None
    t = str(s).replace('%', '').replace(',', '.').strip().lower()
    if t in ('', 'zw', 'np', 'oo', 'none', 'null', '-'):
        return None
    try:
        v = Decimal(t)
    except InvalidOperation:
        v = None
    if v is not None:
        if 0 < v < 1:   # BS zapisuje ułamek
            v *= 100
        trafiona = next((x for x in STAWKI if abs(v - x) <= (Decimal('0.1') if x else 0)), None)
        if trafiona is not None:
            return trafiona
    if scisle:
        raise ValueError('stawka VAT: 23, 8, 5 albo 0')
    return None


def ma_vat(podstawa: str) -> bool:
    """VAT tylko przy fakturze; bez faktury, umowy i daniny: VAT 0, brutto = netto."""
    return (podstawa or '').startswith('Faktura')


def vat_od_netto(netto: int, stawka, podstawa: str = 'Faktura (jedna)') -> int:
    """VAT w groszach: netto × stawka / 100, zaokrąglone połówkami w górę (bez float)."""
    st = stawka_proc(stawka)
    if not st or not ma_vat(podstawa):
        return 0
    return int((Decimal(int(netto)) * st / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _przelicz_vat(p: dict, w: dict | None, wzor: dict | None = None):
    """VAT i brutto płatności z jej netto. Stawka z płatności, a gdy brak, z wiersza. Płatność z BS z kilkoma stawkami
    (stawka efektywna spoza 23, 8, 5, 0) zachowuje proporcję VAT do netto ze wzoru (oryginału albo stanu sprzed zmiany)."""
    w = w or {}
    s = p.get('stawka')
    if s in (None, ''):
        s = w.get('stawka_vat')
    if (wzor and stawka_proc(s) is None and str(s or '').strip() and wzor.get('netto') and wzor.get('vat')
            and ma_vat(w.get('podstawa', ''))):
        p['vat'] = int((Decimal(int(p['netto'])) * int(wzor['vat']) / int(wzor['netto'])).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    else:
        p['vat'] = vat_od_netto(p['netto'], s, w.get('podstawa', ''))
    p['brutto'] = p['netto'] + p['vat']


def _data(s):
    try:
        return data_iso(s)
    except ValueError:
        return None


def _dzien_wystawienia(daty: list[str]) -> str:
    """Z dat wystawienia płatności: „Ostatni”, „15-ty”, „2-gi” albo „(auto)”."""
    dni = []
    for d in daty:
        if d:
            r, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
            dni.append('ostatni' if dd == calendar.monthrange(r, m)[1] else dd)
    if not dni:
        return '(auto)'
    najczestszy, ile = Counter(dni).most_common(1)[0]
    if ile < max(2, len(dni) // 2):
        return '(auto)'
    return 'Ostatni' if najczestszy == 'ostatni' else f'{najczestszy}.'


def _dni_na_platnosc(pary) -> str:
    roznice = [(date.fromisoformat(t) - date.fromisoformat(w)).days for w, t in pary if w and t]
    if not roznice:
        return 'Natychmiast'
    d = Counter(roznice).most_common(1)[0][0]
    return 'Natychmiast' if d <= 0 else str(d) if d in (7, 14, 21, 30, 60) else f'{d} (nietypowe)'


# ---------- Import z Budget Studio (B) ----------

def nowa_mapa() -> dict:
    """Mapa stałych ID: płatność BS → wiersz, wiersz → arkusz, klucz arkusza → arkusz, klucz atrybutów wiersza → wiersz,
    stare ID płatności (sprzed mapy) → nowe. ID nadawane raz (z klucza w chwili pierwszego pojawienia się, więc dwa Maki
    nadają te same), potem tylko odczytywane."""
    return {'wersja': 1, 'arkusze': {}, 'wiersze': {}, 'klucze_wierszy': {}, 'platnosci': {}, 'stare': {}}


def _bs_id(pid: str) -> str:
    return pid.split(':')[1]


def _wolne(baza: str, zajete) -> str:
    """ID z klucza; przy kolizji z istniejącym ID kolejny numer."""
    i, kand = 1, baza
    while kand in zajete:
        i += 1
        kand = f'{baza}:{i}'
    return kand


def generuj_import(csv_path: Path, arkusze_json: Path | None, mapa: dict | None = None) -> dict:
    """Plik importu z eksportu BS. Deterministyczny: ten sam eksport i ta sama mapa dają ten sam plik.
    Mapa (nowa_mapa) jest uzupełniana w miejscu: nowe płatności, wiersze i arkusze dostają ID, znane zachowują swoje."""
    mapa = mapa if mapa is not None else nowa_mapa()
    with open(csv_path, encoding='utf-8-sig', newline='') as f:
        bs = list(csv.DictReader(f, delimiter='\t'))
    zakresy = {}
    if arkusze_json and arkusze_json.exists():
        for a in json.loads(arkusze_json.read_text(encoding='utf-8'))['arkusze']:
            zakresy[(a['folder'], a['kategoria'], a['nazwa'])] = (a['od'], a['do'])
    czesci = []   # jedna część = jeden wiersz eksportu (ID BS bywa w kilku: faktura na kilka komórek)
    for nr, x in enumerate(bs, start=2):
        if x['Rodzaj'] not in ('1', '-1'):
            continue
        ark = (x['Folder'].strip(), x['Kategoria'].strip(), x['Arkusz'].strip())
        podstawa = _podstawa(x['Podstawa płatności'])
        atrybuty = (x['Rodzaj'], podstawa, x['Kontrahent'].strip(), x['Komentarz w arkuszu'].strip(),
                    x['Przedmiot transakcji'].strip(), x['Sekcja'].strip())
        # klucz atrybutów = dawne ID wiersza (hash); z nim szukamy wiersza dla nowej płatności
        klucz_wiersza = _slug('wiersz', _slug('arkusz', *ark), *atrybuty)
        czesci.append({'x': x, 'nr': nr, 'ark': ark, 'klucz_ark': '|'.join(ark), 'atrybuty': atrybuty, 'klucz': klucz_wiersza})

    # 1. ID płatności: znane z mapy zostają (najpierw ta, której wiersz się zgadza), nowe: bs:<ID>, potem bs:<ID>:2...
    po_bs = defaultdict(list)
    for pid in mapa['platnosci']:
        po_bs[_bs_id(pid)].append(pid)
    grupy = defaultdict(list)
    for c in czesci:
        grupy[c['x']['ID']].append(c)
    for bid, cz in grupy.items():
        wolne = sorted(po_bs.get(bid, []))
        for c in cz:
            kand = mapa['klucze_wierszy'].get(c['klucz'])
            trafienie = next((pid for pid in wolne if mapa['platnosci'][pid] == kand), None)
            if trafienie:
                c['pid'], c['znana'] = trafienie, True
                wolne.remove(trafienie)
        for c in cz:
            if 'pid' not in c and wolne:
                c['pid'], c['znana'] = wolne.pop(0), True
        zajete = set(po_bs.get(bid, [])) | {c['pid'] for c in cz if 'pid' in c}
        for c in cz:
            if 'pid' not in c:
                c['pid'], c['znana'] = _wolne(f'bs:{bid}', zajete), False
                zajete.add(c['pid'])

    # 2. Wiersz: płatność znana z mapy trafia do swojego wiersza (nawet gdy zmienił się kontrahent, komentarz, folder);
    # nowa do wiersza o tym samym kluczu atrybutów, a gdy brak, do nowego wiersza.
    wszystkie_w = set(mapa['wiersze']) | set(mapa['klucze_wierszy'].values())
    for c in czesci:
        if c['znana']:
            c['wid'] = mapa['platnosci'][c['pid']]
            mapa['klucze_wierszy'].setdefault(c['klucz'], c['wid'])
    for c in czesci:
        if not c['znana']:
            wid = mapa['klucze_wierszy'].get(c['klucz'])
            if not wid:
                wid = _wolne(c['klucz'], wszystkie_w)
                mapa['klucze_wierszy'][c['klucz']] = wid
                wszystkie_w.add(wid)
            c['wid'] = wid
        mapa['platnosci'][c['pid']] = c['wid']

    # 3. Arkusz: znany klucz (folder, kategoria, nazwa) zostaje; nowy klucz, pod którym są wiersze znanego arkusza,
    # którego dawnego klucza nie ma już w eksporcie, to zmiana nazwy albo folderu (to samo ID); inaczej nowy arkusz.
    # (lista arkuszy ze zwiadu jest statyczna, więc jej stara nazwa nie blokuje zmiany nazwy widocznej w eksporcie)
    w_eksporcie = {c['klucz_ark'] for c in czesci}
    obecne = w_eksporcie | {'|'.join(k) for k in zakresy}
    zajete_ark = {mapa['arkusze'][k] for k in w_eksporcie if k in mapa['arkusze']}
    for k in sorted(w_eksporcie - set(mapa['arkusze'])) + sorted(obecne - w_eksporcie - set(mapa['arkusze'])):
        stare = Counter(mapa['wiersze'].get(c['wid']) for c in czesci if c['klucz_ark'] == k and c['wid'] in mapa['wiersze'])
        aid = next((a for a, _ in stare.most_common() if a and a not in zajete_ark), None)
        if not aid:
            aid = _wolne(_slug('arkusz', *k.split('|')), set(mapa['arkusze'].values()))
        mapa['arkusze'][k] = aid
        zajete_ark.add(aid)
    ark_po_kluczu = {k: mapa['arkusze'][k] for k in obecne}

    # 4. Atrybuty wiersza: najczęstsze wśród jego płatności (ten sam układ co w BS); arkusz: najczęstszy arkusz płatności.
    po_wierszu = defaultdict(list)
    for c in czesci:
        po_wierszu[c['wid']].append(c)
    wiersze, platnosci, nazwy_ark = {}, [], {}
    for wid, cz in po_wierszu.items():
        atr = Counter(c['atrybuty'] for c in cz).most_common(1)[0][0]
        klucz_ark = Counter(c['klucz_ark'] for c in cz).most_common(1)[0][0]
        aid = ark_po_kluczu[klucz_ark]
        mapa['wiersze'][wid] = aid
        nazwy_ark[aid] = klucz_ark
        wiersze[wid] = {'id': wid, 'arkusz': aid, 'rodzaj': int(atr[0]), 'podstawa': atr[1], 'kontrahent': atr[2], 'komentarz': atr[3],
                        'przedmiot': '' if atr[4] == 'Przedmiot transakcji' else atr[4], 'sekcja': '' if atr[5] == '-' else atr[5],
                        'zrodlo': 'Budget Studio'}
    miesiace_ark = defaultdict(set)
    powtorzenia = Counter()
    for c in czesci:
        x, wid = c['x'], c['wid']
        miesiac = (_data(x['Miesiąc budżetowy']) or '')[:7]
        miesiace_ark[mapa['wiersze'][wid]].add(miesiac)
        stary = f"bs:{x['ID']}:{c['klucz']}"   # format ID sprzed mapy: zdarzenia z tamtego czasu tłumaczymy przy odczycie
        powtorzenia[stary] += 1
        if powtorzenia[stary] > 1:
            stary += f':{powtorzenia[stary]}'
        if stary != c['pid']:
            mapa['stare'][stary] = c['pid']
        p = {'id': c['pid'], 'bs_id': x['ID'], 'wiersz': wid, 'miesiac': miesiac,
             'typ': 'rzeczywista' if (bool(x['Numer wewnętrzny'].strip() or x['Numer dokumentu'].strip())
                                      or x['Etap płatności'] in ('Opłacona', 'Niewymagana')) else 'plan',
             'etap_bs': x['Etap płatności'], 'aktualna': x['Status aktualności'] == 'Aktualne',
             'netto': abs(grosze(x['Netto (wartość)'])), 'brutto': abs(grosze(x['Brutto (wartość)'])), 'vat': abs(grosze(x['VAT'] or '0')),
             'stawka': x['Stawka VAT'], 'nr_dok': x['Numer dokumentu'].strip(), 'nr_wewn': x['Numer wewnętrzny'].strip(),
             'tytul': x['Tytuł'].strip(), 'wystawienie': _data(x['Dzień wystawienia']), 'termin': _data(x['Dzień płatności']),
             'realny': _data(x['Dzień płatności - realny']), 'ksiegowanie': _data(x['Miesiąc księgowania']),
             'metoda': x['Metoda płatności'].strip(), 'ksiegowane': x['Księgowane'] == 'Tak', 'w_cashflow': x['W cash flow'] == 'Tak',
             'komentarz': x['Komentarz'].strip(), 'zmodyfikowano': x['Data modyfikacji'], 'wiersz_pliku': c['nr']}
        platnosci.append(p)
    for wid, w in wiersze.items():
        ps = [p for p in platnosci if p['wiersz'] == wid]
        w['stawka_vat'] = Counter(p['stawka'] for p in ps).most_common(1)[0][0]
        w['dzien_wystawienia'] = _dzien_wystawienia([p['wystawienie'] for p in ps])
        w['dni_na_platnosc'] = _dni_na_platnosc([(p['wystawienie'], p['termin']) for p in ps])
        w['metoda'] = Counter(p['metoda'] for p in ps).most_common(1)[0][0]
        w['ksiegowane'] = all(p['ksiegowane'] for p in ps)
        w['w_cashflow'] = all(p['w_cashflow'] for p in ps)
        w['cykl'] = 'miesiac' if len({p['miesiac'] for p in ps}) >= 3 else 'brak'
    zakres_ark = {}   # zakres ze zwiadu po dowolnej nazwie, pod którą arkusz kiedyś był (zmiana nazwy w BS)
    for k, aid in sorted(mapa['arkusze'].items()):
        if tuple(k.split('|')) in zakresy:
            zakres_ark.setdefault(aid, zakresy[tuple(k.split('|'))])
    lista_ark = []
    for aid, k in sorted(nazwy_ark.items()):
        folder, kategoria, nazwa = k.split('|')
        od, do = zakresy.get((folder, kategoria, nazwa)) or zakres_ark.get(aid) or (min(miesiace_ark[aid]), max(miesiace_ark[aid]))
        lista_ark.append({'id': aid, 'folder': folder, 'kategoria': kategoria, 'nazwa': nazwa, 'od': od, 'do': do, 'zrodlo': 'Budget Studio'})
    # arkusze ze zwiadu bez płatności (np. nowy, pusty arkusz) też istnieją
    for (folder, kategoria, nazwa), (od, do) in zakresy.items():
        aid = ark_po_kluczu['|'.join((folder, kategoria, nazwa))]
        if aid not in nazwy_ark and aid not in {x['id'] for x in lista_ark}:
            lista_ark.append({'id': aid, 'folder': folder, 'kategoria': kategoria, 'nazwa': nazwa, 'od': od, 'do': do, 'zrodlo': 'Budget Studio'})
    lista_ark.sort(key=lambda a: (a['folder'], a['kategoria'], a['nazwa']))
    sha = hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()
    return {'zrodlo': {'plik': Path(csv_path).name, 'sha256': sha, 'wierszy': len(platnosci),
                       'najnowsza_modyfikacja': max((p['zmodyfikowano'] for p in platnosci), default='')},
            'arkusze': lista_ark, 'wiersze': sorted(wiersze.values(), key=lambda w: w['id']),
            'platnosci': sorted(platnosci, key=lambda p: p['id']), 'stare_id': dict(sorted(mapa['stare'].items()))}


def plik_importu() -> Path:
    return konfig.katalog_finanse() / 'Aplikacja' / 'import_bs.json'


def plik_mapy() -> Path:
    return konfig.katalog_finanse() / 'Aplikacja' / 'mapa_id.json'


def _zapisz_jesli_inny(cel: Path, tekst: str):
    """Zapis tylko przy zmianie treści (dwa Maki, iCloud), atomowo, plik 600."""
    if not cel.exists() or cel.read_text(encoding='utf-8') != tekst:
        konfig.katalog_prywatny(cel.parent)
        tmp = cel.with_suffix('.tmp')
        tmp.write_text(tekst, encoding='utf-8')
        tmp.chmod(0o600)
        tmp.replace(cel)


def wczytaj_mape() -> dict:
    p = plik_mapy()
    if not p.exists():
        return nowa_mapa()
    return {**nowa_mapa(), **json.loads(p.read_text(encoding='utf-8'))}


def odswiez_import() -> dict | None:
    """Generuje plik importu z najnowszego eksportu BS i uzupełnia mapę stałych ID. Zapis tylko przy zmianie treści."""
    from .importy.wspolne import pliki
    lista = pliki(konfig.katalog_dane(), 'Budget Studio/budget_studio_*.csv')
    cel = plik_importu()
    if not lista:
        return json.loads(cel.read_text(encoding='utf-8')) if cel.exists() else None
    mapa = wczytaj_mape()
    nowy = generuj_import(lista[0], konfig.katalog_finanse() / 'Aplikacja' / 'arkusze_bs.json', mapa)
    _zapisz_jesli_inny(plik_mapy(), json.dumps(mapa, ensure_ascii=False, indent=0, sort_keys=True))
    _zapisz_jesli_inny(cel, json.dumps(nowy, ensure_ascii=False, indent=0, sort_keys=True))
    return nowy


# ---------- Zdarzenia Mata na budżecie (D) ----------

POLA_KOPII = ('stawka', 'wystawienie', 'termin', 'realny', 'ksiegowanie', 'metoda', 'ksiegowane', 'w_cashflow', 'komentarz', 'tytul', 'netto')


def _przesun_date(d: str | None, o: int) -> str | None:
    """Data przesunięta o o miesięcy; dzień ponad koniec miesiąca = ostatni dzień."""
    if not d or not o:
        return d
    r, m, dd = int(d[:4]), int(d[5:7]) - 1 + o, int(d[8:10])
    r, m = r + m // 12, m % 12 + 1
    return f'{r}-{m:02d}-{min(dd, calendar.monthrange(r, m)[1]):02d}'


def _roznica_mies(z: str, na: str) -> int:
    return (int(na[:4]) - int(z[:4])) * 12 + int(na[5:7]) - int(z[5:7])


def _zastosuj_op(st: dict, d: dict, stare: dict):
    """Jedna operacja na stanie modelu. Zwraca (powód osierocenia albo None, było, id obiektu). Przy osieroceniu nic nie zmienia."""
    ark, wie, pla = st['arkusz'], st['wiersz'], st['platnosc']
    op = d['op']
    if op in ('arkusz', 'wiersz', 'platnosc'):
        obiekt = dict(d.get('obiekt', {}))
        if op == 'platnosc':
            obiekt['id'] = stare.get(obiekt['id'], obiekt['id'])
            if obiekt.get('wzor'):
                obiekt['wzor'] = stare.get(obiekt['wzor'], obiekt['wzor'])
        zbior = {'arkusz': ark, 'wiersz': wie, 'platnosc': pla}[op]
        oid = obiekt['id']
        bylo = dict(zbior[oid]) if oid in zbior else None
        nazwa = {'arkusz': 'arkusza', 'wiersz': 'wiersza', 'platnosc': 'płatności'}[op]
        if d.get('usun'):
            if bylo is None:
                return f'nie ma {nazwa} do usunięcia', None, oid
            zbior.pop(oid)
            if op == 'wiersz':
                for pid in [p for p, x in pla.items() if x['wiersz'] == oid]:
                    pla.pop(pid)
            return None, bylo, oid
        if op == 'arkusz':
            if bylo is None and not all(obiekt.get(k) for k in ('nazwa', 'folder', 'kategoria', 'od', 'do')):
                return 'nie ma takiego arkusza', None, oid
            ark[oid] = {**(bylo or {}), **obiekt, 'zrodlo': 'apka'}
            return None, bylo, oid
        if op == 'wiersz':
            if 'arkusz' in obiekt and obiekt['arkusz'] not in ark:
                return 'nie ma arkusza tego wiersza', None, oid
            if bylo is None and not ('arkusz' in obiekt and obiekt.get('rodzaj') in (1, -1) and obiekt.get('podstawa')):
                return 'nie ma takiego wiersza', None, oid
            wie[oid] = {**(bylo or {}), **obiekt, 'zrodlo': 'apka'}
            return None, bylo, oid
        # płatność
        if 'wiersz' in obiekt and obiekt['wiersz'] not in wie:
            return 'nie ma wiersza tej płatności', None, oid
        wzor = obiekt.pop('wzor', None)
        if bylo is None:
            if wzor:   # kopia (duplikuj, scal, podziel): stawka i daty z oryginału przesunięte o różnicę miesięcy
                if wzor not in pla:
                    return 'nie ma płatności, z której robiona jest kopia', None, oid
                z = pla[wzor]
                o = _roznica_mies(z['miesiac'], obiekt.get('miesiac') or z['miesiac'])
                baza_ = {k: z.get(k) for k in POLA_KOPII}
                for k in ('wystawienie', 'termin', 'realny', 'ksiegowanie'):
                    baza_[k] = _przesun_date(baza_[k], o)
                obiekt = {**baza_, 'wiersz': z['wiersz'], 'miesiac': z['miesiac'], **obiekt}
            if not (obiekt.get('wiersz') in wie and obiekt.get('miesiac') and 'netto' in obiekt):
                return 'nie ma takiej płatności', None, oid
            obiekt = {'typ': 'plan', 'etap_bs': 'Planowana', 'aktualna': True, 'nr_dok': '', 'nr_wewn': '', **obiekt}
        nowa = {**(bylo or {}), **{k: v for k, v in obiekt.items() if k not in ('vat', 'brutto')}, 'zrodlo': 'apka'}
        if bylo is None or 'netto' in obiekt or 'stawka' in obiekt:
            _przelicz_vat(nowa, wie.get(nowa['wiersz']), None if 'stawka' in obiekt else (bylo or (pla.get(wzor) if wzor else None)))
        pla[oid] = nowa
        return None, bylo, oid
    if op == 'przenies':
        brak = [w for w in d['wiersze'] if w not in wie]
        if d['do_arkusza'] not in ark or brak:
            return 'nie ma arkusza docelowego' if d['do_arkusza'] not in ark else f'nie ma wierszy: {", ".join(brak)}', None, ','.join(d['wiersze'])
        for wid in d['wiersze']:
            wie[wid] = {**wie[wid], 'arkusz': d['do_arkusza']}
        return None, None, ','.join(d['wiersze'])
    if op == 'decyzja_planu':   # po terminie: przesuń / zapłacone / anuluj (wymaganie 1)
        pid = stare.get(d['platnosc'], d['platnosc'])
        p = pla.get(pid)
        if not p:
            return 'nie ma takiej płatności', None, pid
        bylo = dict(p)
        if d['decyzja'] == 'przesun':
            pla[pid] = {**p, 'termin': d['termin'], 'miesiac': d['termin'][:7], 'decyzja': 'przesunięte'}
        elif d['decyzja'] == 'anuluj':
            pla[pid] = {**p, 'aktualna': False, 'decyzja': 'anulowane'}
        elif d['decyzja'] == 'zaplacone':
            pla[pid] = {**p, 'decyzja': 'zapłacone (Mat)', 'realny': d.get('data')}
        return None, bylo, pid
    return 'nieznana operacja', None, ''


def _zastosuj_wpis(st: dict, w: dict, stare: dict):
    """Wpis „bud” w całości albo wcale: seria na kopii stanu, podmiana dopiero, gdy wszystkie operacje się udały.
    Zwraca (powód osierocenia albo None, lista (operacja, było, id))."""
    d = w['dane']
    ops = d['operacje'] if d['op'] == 'seria' else [d]
    roboczy = {k: dict(v) for k, v in st.items()} if len(ops) > 1 else st
    wykonane = []
    for i, o in enumerate(ops, start=1):
        powod, bylo, oid = _zastosuj_op(roboczy, o, stare)
        if powod:
            return (f'operacja {i} z {len(ops)}: {powod}' if len(ops) > 1 else powod), []
        wykonane.append((o, bylo, oid))
    if roboczy is not st:
        st.update(roboczy)
    return None, wykonane


def zastosuj_zdarzenia(model: dict, wpisy: list[dict]) -> list[dict]:
    """Nakłada zdarzenia „bud” na model z importu. Zwraca historię (kto, kiedy, co, było, jest); zdarzenia bez obiektu
    (np. płatność, której już nie ma w eksporcie BS) zapisuje w model['osierocone'] zamiast gubić je po cichu."""
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    stare = model.get('stare_id', {})
    st = {'arkusz': {a['id']: a for a in model['arkusze']}, 'wiersz': {w['id']: w for w in model['wiersze']},
          'platnosc': {p['id']: p for p in model['platnosci']}}
    historia, osierocone = [], []
    for w in wpisy:
        if w.get('typ') != 'bud' or w.get('id') in cofniete:
            continue
        powod, wykonane = _zastosuj_wpis(st, w, stare)
        if powod:
            d = w['dane']
            obiekt = (d.get('obiekt') or {}).get('id') or d.get('platnosc') or ','.join(d.get('wiersze', [])) or f"{len(d.get('operacje', []))} operacji"
            osierocone.append({'wpis': w['id'], 'czas': w['czas'], 'mac': w.get('mac', ''), 'op': d['op'], 'obiekt': obiekt, 'powod': powod})
            continue
        for o, bylo, oid in wykonane:
            jest = st['arkusz'].get(oid) or st['wiersz'].get(oid) or st['platnosc'].get(oid)
            historia.append({'wpis': w['id'], 'czas': w['czas'], 'mac': w.get('mac', ''),
                             'op': o['op'] if w['dane']['op'] != 'seria' else f"seria: {o['op']}", 'obiekt': oid, 'bylo': bylo, 'jest': jest})
    model['arkusze'], model['wiersze'], model['platnosci'] = list(st['arkusz'].values()), list(st['wiersz'].values()), list(st['platnosc'].values())
    model['osierocone'] = osierocone
    return historia


def wczytaj_model() -> dict | None:
    """Model z pliku importu (bez generowania i zapisu), do sprawdzenia wpisu przed zapisem."""
    p = plik_importu()
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def sprawdz_wpis(dane: dict, wpisy: list[dict], model: dict | None = None):
    """Próba wpisu „bud” na bieżącym stanie (import + dotychczasowe zmiany), bez zapisu. ValueError z powodem, gdy
    którakolwiek operacja nie ma do czego się odnieść: wtedy do pliku zmian nie trafia nic (seria w całości albo wcale)."""
    model = model or wczytaj_model()
    if not model:
        raise ValueError('brak budżetu: nie ma pliku importu z Budget Studio')
    zastosuj_zdarzenia(model, wpisy)
    st = {'arkusz': {a['id']: a for a in model['arkusze']}, 'wiersz': {w['id']: w for w in model['wiersze']},
          'platnosc': {p['id']: p for p in model['platnosci']}}
    powod, _ = _zastosuj_wpis(st, {'dane': dane}, model.get('stare_id', {}))
    if powod:
        raise ValueError(f'zmiana odrzucona, nic nie zapisano ({powod})')


def generuj_cykliczne(model: dict):
    """Wiersz z planem cyklicznym (dodany w apce) tworzy płatności planowane w zakresie arkusza:
    co miesiąc, co kwartał albo co rok, z dniem wystawienia, dniami na płatność i częściami (wynagrodzenia)."""
    ark = {a['id']: a for a in model['arkusze']}
    jest = {(p['wiersz'], p['miesiac']) for p in model['platnosci']}
    for w in model['wiersze']:
        plan = w.get('plan')
        if not plan or w.get('zrodlo') != 'apka':
            continue
        a = ark.get(w['arkusz'])
        if not a:
            continue
        krok = CYKLE.get(plan.get('cykl', 'miesiac'), 1) or 1
        m = plan.get('od') or a['od']
        koniec = min(plan.get('do') or a['do'], a['do'])
        i = 0
        while m <= koniec:
            if i % krok == 0 and (w['id'], m) not in jest:
                for czesc in plan.get('czesci') or [{'nazwa': '', 'kwota': plan['netto'], 'dzien_platnosci': None}]:
                    wyst = _dzien_w_miesiacu(m, plan.get('dzien_wystawienia', 'Ostatni'))
                    termin = (_dzien_w_miesiacu(_nastepny(m), czesc['dzien_platnosci']) if czesc.get('dzien_platnosci')
                              else (date.fromisoformat(wyst) + timedelta(days=int(plan.get('dni_na_platnosc') or 0))).isoformat())
                    netto = int(czesc['kwota'])
                    vat = vat_od_netto(netto, plan.get('stawka_vat'), w.get('podstawa', ''))
                    model['platnosci'].append({'id': f"plan:{w['id']}:{m}:{czesc.get('nazwa', '')}", 'wiersz': w['id'], 'miesiac': m,
                                               'typ': 'plan', 'etap_bs': 'Planowana', 'aktualna': True, 'netto': netto, 'vat': vat,
                                               'brutto': netto + vat, 'stawka': plan.get('stawka_vat'), 'wystawienie': wyst, 'termin': termin, 'tytul': czesc.get('nazwa') or w.get('komentarz', ''),
                                               'nr_dok': '', 'nr_wewn': '', 'zrodlo': 'plan cykliczny', 'w_cashflow': w.get('w_cashflow', True)})
            m = _nastepny(m)
            i += 1


def _nastepny(m: str) -> str:
    r, mm = int(m[:4]), int(m[5:7])
    return f'{r + (mm == 12)}-{1 if mm == 12 else mm + 1:02d}'


def _dzien_w_miesiacu(m: str, dzien) -> str:
    r, mm = int(m[:4]), int(m[5:7])
    ost = calendar.monthrange(r, mm)[1]
    if dzien in (None, '', '(auto)', 'Ostatni', 'ostatni'):
        return f'{m}-{ost:02d}'
    d = int(re.sub(r'\D', '', str(dzien)) or ost)
    return f'{m}-{min(d, ost):02d}'


# ---------- Zapis modelu do bazy ----------

def ustawienia_z_wpisow(con, wpisy: list[dict]):
    """Ustawienia (planowanie w apce) i estymaty czasu zespołu: ostatni wpis wygrywa, cofnięte pomijamy."""
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    planowanie, estymaty = 'nie', {}
    for w in wpisy:
        if w.get('id') in cofniete:
            continue
        if w.get('typ') == 'ustawienie' and w['dane'].get('klucz') == 'planowanie':
            planowanie = w['dane']['wartosc']
        elif w.get('typ') == 'estymata':
            estymaty[w['dane']['klient']] = {'udzial': w['dane']['udzial'], 'od': w['dane'].get('od', ''), 'wpis': w['id']}
    con.execute("INSERT OR REPLACE INTO meta VALUES ('planowanie', ?)", (planowanie,))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('estymaty', ?)", (json.dumps(estymaty, ensure_ascii=False),))


def zbuduj(con, wpisy: list[dict]) -> dict:
    ustawienia_z_wpisow(con, wpisy)
    from . import umowy
    umowy.zapisz_do_bazy(con, wpisy)
    model = odswiez_import()
    if not model:
        return {'arkuszy': 0}
    model = json.loads(json.dumps(model))   # kopia, plik zostaje nietknięty
    historia = zastosuj_zdarzenia(model, wpisy)
    generuj_cykliczne(model)
    for a in model['arkusze']:
        con.execute('INSERT INTO bud_arkusz (id, folder, kategoria, nazwa, od, do, zrodlo) VALUES (?,?,?,?,?,?,?)',
                    (a['id'], a['folder'], a['kategoria'], a['nazwa'], a['od'], a['do'], a.get('zrodlo', '')))
    for w in model['wiersze']:
        con.execute('INSERT INTO bud_wiersz (id, arkusz, rodzaj, podstawa, kontrahent, komentarz, przedmiot, sekcja, stawka_vat,'
                    ' dzien_wystawienia, dni_na_platnosc, metoda, ksiegowane, w_cashflow, cykl, plan, zrodlo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (w['id'], w['arkusz'], w['rodzaj'], w['podstawa'], w.get('kontrahent', ''), w.get('komentarz', ''), w.get('przedmiot', ''),
                     w.get('sekcja', ''), str(w.get('stawka_vat', '')), w.get('dzien_wystawienia', ''), w.get('dni_na_platnosc', ''),
                     w.get('metoda', ''), int(bool(w.get('ksiegowane', True))), int(bool(w.get('w_cashflow', True))), w.get('cykl', 'brak'),
                     json.dumps(w.get('plan')) if w.get('plan') else None, w.get('zrodlo', '')))
    znak = {w['id']: w['rodzaj'] for w in model['wiersze']}
    for p in model['platnosci']:
        if p['wiersz'] not in znak:
            continue
        st = stawka_proc(p.get('stawka'))
        con.execute('INSERT INTO bud_platnosc (id, bs_id, wiersz, miesiac, typ, etap_bs, aktualna, netto, vat, brutto, stawka, rodzaj, nr_dok, nr_wewn,'
                    ' tytul, wystawienie, termin, realny, ksiegowanie, metoda, w_cashflow, komentarz, decyzja, zrodlo, wiersz_pliku)'
                    ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (p['id'], p.get('bs_id'), p['wiersz'], p['miesiac'], p['typ'], p.get('etap_bs', ''), int(bool(p.get('aktualna', True))),
                     p['netto'], p.get('vat', 0), p.get('brutto', p['netto']), st, znak[p['wiersz']], p.get('nr_dok', ''), p.get('nr_wewn', ''),
                     p.get('tytul', ''), p.get('wystawienie'), p.get('termin'), p.get('realny'), p.get('ksiegowanie'), p.get('metoda', ''),
                     int(bool(p.get('w_cashflow', True))), p.get('komentarz', ''), p.get('decyzja', ''), p.get('zrodlo', 'Budget Studio'),
                     p.get('wiersz_pliku')))
    con.executemany('INSERT INTO bud_historia (wpis, czas, mac, op, obiekt, bylo, jest) VALUES (?,?,?,?,?,?,?)',
                    [(h['wpis'], h['czas'], h['mac'], h['op'], h['obiekt'], json.dumps(h['bylo'], ensure_ascii=False),
                      json.dumps(h['jest'], ensure_ascii=False)) for h in historia])
    con.executemany('INSERT INTO bud_osierocone (wpis, czas, mac, op, obiekt, powod) VALUES (?,?,?,?,?,?)',
                    [(o['wpis'], o['czas'], o['mac'], o['op'], o['obiekt'], o['powod']) for o in model['osierocone']])
    con.execute("INSERT OR REPLACE INTO meta VALUES ('import_bs', ?)", (json.dumps(model['zrodlo'], ensure_ascii=False),))
    wynik = {'arkuszy': len(model['arkusze']), 'wierszy': len(model['wiersze']), 'platnosci': len(model['platnosci'])}
    if model['osierocone']:
        wynik['osierocone'] = len(model['osierocone'])
    return wynik
