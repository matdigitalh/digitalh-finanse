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

from . import konfig, plan
from .format import data_iso, grosze, norm, zl

PODSTAWY = plan.PODSTAWY_WIERSZA + plan.PODSTAWY_SKLADOWE_BS
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


def _stan(model: dict) -> dict:
    """Stan roboczy modelu: obiekty po ID, kwoty komórek {(wiersz, miesiąc): grosze} i ręczne zmiany planów z komórek."""
    from . import biblioteka
    return {'arkusz': {a['id']: a for a in model['arkusze']}, 'wiersz': {w['id']: w for w in model['wiersze']},
            'platnosc': {p['id']: p for p in model['platnosci']},
            'komorka': {(k['wiersz'], k['miesiac']): k['kwota'] for k in model.get('komorki', [])},
            'nadpisane': dict(model.get('nadpisane', {})), 'parametry': dict(model.get('parametry') or parametry_planu()),
            'podzialy': dict(model.get('podzialy', {})),   # podział komórki z kopii BS (pakiet 6): '<wiersz>:<miesiąc>'
            # pakiet 5: połączenia dokumentów z komórkami (ref → zapis połączenia), stan komórki po połączeniu
            # ((wiersz, miesiąc) → 'zamknieta': bez planu, 'otwarta': plan na resztę) i płatności dodane ręcznie (id → dane)
            'polaczenia': dict(model.get('polaczenia', {})),
            'realizacja': {(r[0], r[1]): r[2] for r in model.get('realizacja', [])},
            'reczne': dict(model.get('reczne', {})),
            'listy': dict(model.get('listy', {})),   # listy płac za miesiąc (wpis „lista_plac”): uwaga, PPK, osoby
            **biblioteka.stan(model)}   # pakiet 4: słowniki i struktura folderów (Biblioteka)


def parametry_planu() -> dict:
    """Parametry techniczne generatora (DOMYSŁ do sprawdzenia na eksporcie BS), z Finanse/Aplikacja/ustawienia.json."""
    from .wynik import ustawienia
    try:
        tydzien = int(ustawienia().get('worek_pierwszy_dzien_tygodnia', plan.PIERWSZY_DZIEN_TYGODNIA))
    except (TypeError, ValueError):
        tydzien = plan.PIERWSZY_DZIEN_TYGODNIA
    return {'tydzien': tydzien if 0 <= tydzien <= 6 else plan.PIERWSZY_DZIEN_TYGODNIA}


def _odswiez(st: dict, wid: str, miesiace=None):
    """Plany z komórek wiersza liczone na nowo z kwoty, ustawień wiersza i ręcznych zmian (pakiet 2: plan = pochodna komórki).
    Worek z rzeczywistymi: plany tylko na resztę kwoty ponad sumę rzeczywistych."""
    pla, kom = st['platnosc'], st['komorka']
    if miesiace is None:
        miesiace = {m for (w, m) in kom if w == wid} | {p['miesiac'] for p in pla.values() if p['wiersz'] == wid and p.get('generowany')}
    for pid in [pid for pid, p in pla.items() if p.get('generowany') and p['wiersz'] == wid and p['miesiac'] in miesiace]:
        pla.pop(pid)
    w = st['wiersz'].get(wid)
    if not w:
        return
    realizacja = st.get('realizacja', {})
    for m in sorted(miesiace):
        kwota = kom.get((wid, m))
        if kwota is None or realizacja.get((wid, m)) == 'zamknieta':   # pakiet 5: plan zastąpiony rzeczywistą
            continue
        if w.get('podstawa') in plan.WOREK or realizacja.get((wid, m)) == 'otwarta':
            kwota = max(0, kwota - sum(p['netto'] for p in pla.values() if p['wiersz'] == wid and p['miesiac'] == m and p['typ'] != 'plan'))
        for p in plan.generuj_komorke(w, m, kwota, st['nadpisane'], st['parametry']['tydzien'], st['podzialy'].get(f'{wid}:{m}')):
            pla[p['id']] = p


def _ma_rzeczywiste(st: dict, wid: str) -> bool:
    return any(p['wiersz'] == wid and p['typ'] != 'plan' for p in st['platnosc'].values())


# ---------- Pakiet 3: akcje na wierszach i arkuszu (reguły BS w jednym miejscu, zawsze jedną serią) ----------

LIMIT_WIERSZY = 1000   # wierszy na arkusz (A-ARK-09)
MIESIACE_PL = ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień', 'wrzesień', 'październik',
               'listopad', 'grudzień']
WOREK_DLA = {'Faktura (jedna)': 'Faktura (w worku)', 'Bez faktury': 'Bez faktury (w worku)'}


def _mies_pl(m: str) -> str:
    return f'{MIESIACE_PL[int(m[5:7]) - 1]} {m[:4]}'


def _lista_mies(ms) -> str:
    ms = sorted(ms)
    t = ', '.join(_mies_pl(m) for m in ms[:4])
    return t + (f' i {len(ms) - 4} innych' if len(ms) > 4 else '')


def _rodzina(podstawa: str) -> str:
    """Faktura z fakturą w worku to ta sama rodzina (scalanie dozwolone, A-OPS-12); tak samo bez faktury."""
    return {'Faktura (w worku)': 'Faktura (jedna)', 'Bez faktury (w worku)': 'Bez faktury'}.get(podstawa, podstawa)


def _usun_podzialy(st: dict, wid: str, miesiace=None):
    """Podział komórki z kopii BS (pakiet 6) znika razem z komórką: przeniesiona albo przesunięta kwota liczy się z reguły."""
    for k in [k for k in st['podzialy'] if k.startswith(f'{wid}:') and (miesiace is None or k.split(':', 1)[1] in miesiace)]:
        st['podzialy'].pop(k)


def _usun_wiersz(st: dict, wid: str):
    st['wiersz'].pop(wid, None)
    for pid in [p for p, x in st['platnosc'].items() if x['wiersz'] == wid]:
        st['platnosc'].pop(pid)
    for k in [k for k in st['komorka'] if k[0] == wid]:
        st['komorka'].pop(k)
    for k in [k for k in st['nadpisane'] if k.startswith(f'plan:{wid}:')]:
        st['nadpisane'].pop(k)
    _usun_podzialy(st, wid)


def _utrwal(st: dict, wid: str, cel: str | None = None) -> dict:
    """Plany liczone z komórek wiersza stają się zwykłymi planami (jak plany z BS): kwota, daty i cechy (razem z ręcznymi
    zmianami) zostają, komórka znika. Potrzebne przy scalaniu i dzieleniu, bo płatności przechodzą wtedy do innego wiersza
    bez przeliczania („wszystkie płatności, nie suma kwot”). Nowe ID, bo ID planu z komórki należy do komórki.
    Zwraca mapę stare ID → nowe. Słowniki stanu podmieniamy, nie zmieniamy w miejscu (seria musi dać się odrzucić)."""
    cel = cel or wid
    pla = st['platnosc']
    mapa = {}
    for pid in sorted(pid for pid, p in pla.items() if p['wiersz'] == wid and p.get('generowany')):
        p = pla.pop(pid)
        nid = _wolne(f'p-{_slug(pid, cel)}', pla)
        mapa[pid] = nid
        pla[nid] = {**{k: v for k, v in p.items() if k not in ('generowany', 'nadpisane')}, 'id': nid, 'wiersz': cel, 'zrodlo': 'apka'}
    for nid in mapa.values():
        if pla[nid].get('spinacz') in mapa:
            pla[nid] = {**pla[nid], 'spinacz': mapa[pla[nid]['spinacz']]}
    for k in [k for k in st['komorka'] if k[0] == wid]:
        st['komorka'].pop(k)
    for k in [k for k in st['nadpisane'] if k.startswith(f'plan:{wid}:')]:
        st['nadpisane'].pop(k)
    _usun_podzialy(st, wid)
    return mapa


def wartosci_komorek(st: dict, wid: str, tylko_plany: bool = False) -> dict:
    """Wartość każdej komórki wiersza tak, jak widać ją w arkuszu: kwota wpisana w apce, a gdy jej brak, suma netto
    aktualnych płatności (plany z BS i rzeczywiste). Worek z rzeczywistymi: większa z kwoty i sumy rzeczywistych (A-KOM-04).
    Używane przy duplikowaniu (rzeczywiste stają się planami z ustawień wiersza) i przesuwaniu arkusza."""
    wynik = {m: k for (w, m), k in st['komorka'].items() if w == wid}
    suma, rz, jest = defaultdict(int), defaultdict(int), set()
    for p in st['platnosc'].values():
        if p['wiersz'] != wid or not p.get('aktualna', True) or (tylko_plany and p['typ'] != 'plan'):
            continue
        jest.add(p['miesiac'])
        if p.get('generowany'):
            continue
        suma[p['miesiac']] += p['netto']
        if p['typ'] != 'plan':
            rz[p['miesiac']] += p['netto']
    for m in jest:
        wynik[m] = max(wynik[m], rz[m]) if m in wynik else suma[m]
    return wynik


def _wiersze_ark(st: dict, aid: str) -> list[str]:
    return [x for x, w in st['wiersz'].items() if w['arkusz'] == aid]


def _za_duzo_wierszy(st: dict, aid: str, dochodzi: int) -> str | None:
    ile = len(_wiersze_ark(st, aid))
    if ile + dochodzi > LIMIT_WIERSZY:
        return (f'Arkusz może mieć najwyżej {LIMIT_WIERSZY} wierszy (ma {ile}, dochodzi {dochodzi}). '
                'Przenieś część wierszy do nowego arkusza tematycznego.')
    return None


def _scal(st: dict, d: dict, scisle: bool):
    """A-OPS-12: ten sam rodzaj i ta sama podstawa (faktura z fakturą w worku wolno). Wynik: pierwszy zaznaczony wiersz
    (opis i ustawienia z niego) ze WSZYSTKIMI płatnościami; gdy w miesiącu jest kilka płatności, podstawa w worku."""
    wie, pla = st['wiersz'], st['platnosc']
    ids = d['wiersze']
    oid = ids[0]
    brak = [x for x in ids if x not in wie]
    if brak:
        return f'nie ma wierszy: {", ".join(brak)}', None, oid
    ws = [wie[x] for x in ids]
    if len({w['rodzaj'] for w in ws}) > 1:
        return 'Scalić można tylko wiersze tego samego rodzaju: same wpływy albo same obciążenia. Odznacz wiersze drugiego rodzaju.', None, oid
    if len({_rodzina(w.get('podstawa', '')) for w in ws}) > 1:
        return ('Scalić można tylko wiersze o tej samej podstawie płatności (wyjątek: faktura z fakturą w worku). '
                'Zmień podstawę jednego z wierszy albo scal je w osobnych grupach.'), None, oid
    pod = ws[0].get('podstawa', '')
    if _rodzina(pod) not in WOREK_DLA:   # umowy i podatki nie mają wersji w worku: miesiące nie mogą się pokrywać
        mies = [{p['miesiac'] for p in pla.values() if p['wiersz'] == x and not p.get('ukryty')} for x in ids]
        wspolne = sorted({m for s in mies for m in s if sum(m in t for t in mies) > 1})
        if wspolne and scisle:
            return (f'Wiersze mają płatności w tych samych miesiącach ({_lista_mies(wspolne)}), a podstawa „{pod}” nie ma wersji '
                    'w worku. Scal wiersze bez wspólnych miesięcy albo zostaw je osobno.'), None, oid
    bylo = {'wiersze': [dict(w) for w in ws]}
    for x in ids:
        _utrwal(st, x, oid)
    for pid, p in list(pla.items()):
        if p['wiersz'] in ids[1:]:
            pla[pid] = {**p, 'wiersz': oid}
    for x in ids[1:]:
        wie.pop(x)
    nowy = {**wie[oid], 'zrodlo': 'apka'}
    widoczne = Counter(p['miesiac'] for p in pla.values() if p['wiersz'] == oid and not p.get('ukryty'))
    for pid, p in list(pla.items()):   # plan zerowy był tylko miejscem na płatność; obok innej płatności jest zbędny
        if p['wiersz'] == oid and p.get('ukryty') and widoczne[p['miesiac']]:
            pla.pop(pid)
    if pod in WOREK_DLA and any(n > 1 for n in widoczne.values()):
        nowy['podstawa'] = WOREK_DLA[pod]
    wie[oid] = nowy
    return None, bylo, oid


def _podziel(st: dict, d: dict, scisle: bool):
    """A-OPS-13: tylko wiersz z co najmniej dwiema płatnościami; tyle wierszy, ile płatności, każdy z jedną płatnością
    i tymi samymi cechami. Pierwsza płatność (najwcześniejsza) zostaje w oryginale."""
    wie, pla = st['wiersz'], st['platnosc']
    wid = d['wiersz']
    if wid not in wie:
        return 'nie ma wiersza do podziału', None, wid
    w = wie[wid]
    if plan.jest_umowa(w.get('podstawa', '')):
        return ('Wiersza umowy nie podzielisz: wypłata, PIT i ZUS z jednej komórki muszą zostać razem. '
                'Zduplikuj wiersz i rozdziel kwoty w komórkach.'), None, wid
    ile = sum(1 for p in pla.values() if p['wiersz'] == wid and not p.get('ukryty'))
    if ile < 2:
        return (f'Podzielić można tylko wiersz z co najmniej dwiema płatnościami (ten ma {ile}). '
                'Żeby rozbić kwotę, użyj „Podziel procentem” albo wpisz kwoty w nowym wierszu.'), None, wid
    if scisle and (powod := _za_duzo_wierszy(st, w['arkusz'], ile - 1)):
        return powod, None, wid
    bylo = dict(w)
    _utrwal(st, wid)
    ps = sorted((p for p in pla.values() if p['wiersz'] == wid and not p.get('ukryty')),
                key=lambda p: (p['miesiac'], p.get('wystawienie') or '', p['id']))
    for i, p in enumerate(ps[1:], start=2):
        nid = _wolne(f'{wid[:70]}-{i}', wie)
        wie[nid] = {**w, 'id': nid, 'zrodlo': 'apka'}
        pla[p['id']] = {**p, 'wiersz': nid}
    return None, bylo, wid


def _duplikuj(st: dict, d: dict, scisle: bool):
    """A-OPS-10: kopia wiersza z ustawieniami i wartościami komórek; rzeczywiste oryginału stają się w kopii planami
    z ustawień wiersza (wartość komórki = kwota, plany liczy generator)."""
    wie, ark = st['wiersz'], st['arkusz']
    oid = ','.join(d['nowe'])
    brak = [x for x in d['wiersze'] if x not in wie]
    if brak:
        return f'nie ma wierszy: {", ".join(brak)}', None, oid
    cel = d.get('do_arkusza')
    if cel and cel not in ark:
        return 'nie ma arkusza docelowego', None, oid
    if any(x in wie for x in d['nowe']):
        return 'wiersz o tym identyfikatorze już jest', None, oid
    if scisle:
        for aid, n in Counter(cel or wie[x]['arkusz'] for x in d['wiersze']).items():
            if powod := _za_duzo_wierszy(st, aid, n):
                return powod, None, oid
    for src, nid in zip(d['wiersze'], d['nowe']):
        w = wie[src]
        wie[nid] = {**w, 'id': nid, 'zrodlo': 'apka', **({'arkusz': cel} if cel else {})}
        a = ark.get(wie[nid]['arkusz']) or {}
        for m, k in wartosci_komorek(st, src).items():
            if not a or a['od'] <= m <= a['do']:
                st['komorka'][(nid, m)] = k
        _odswiez(st, nid)
    return None, None, oid


def _przesun_arkusz(st: dict, d: dict, scisle: bool):
    """A-OPS-05: cały arkusz o N miesięcy bez zmiany długości; tylko bez płatności rzeczywistych. Plany powstają na nowo
    z ustawień wierszy (ręczne zmiany pojedynczych planów przepadają)."""
    ark, wie, pla = st['arkusz'], st['wiersz'], st['platnosc']
    aid, o = d['arkusz'], d['o']
    a = ark.get(aid)
    if not a:
        return 'nie ma takiego arkusza', None, aid
    ids = set(_wiersze_ark(st, aid))
    if scisle and any(p['wiersz'] in ids and p['typ'] != 'plan' for p in pla.values()):
        return ('Arkusz ma płatności rzeczywiste, więc jego startu nie przesuniesz. Zmień zakres miesięcy (Zmodyfikuj czas trwania) '
                'albo zduplikuj arkusz z przesunięciem startu.'), None, aid
    bylo = dict(a)
    for wid in ids:
        wart = wartosci_komorek(st, wid, tylko_plany=True)
        for pid in [pid for pid, p in pla.items() if p['wiersz'] == wid and p['typ'] == 'plan']:
            pla.pop(pid)
        for k in [k for k in st['komorka'] if k[0] == wid]:
            st['komorka'].pop(k)
        for k in [k for k in st['nadpisane'] if k.startswith(f'plan:{wid}:')]:
            st['nadpisane'].pop(k)
        _usun_podzialy(st, wid)
        for m, k in wart.items():
            st['komorka'][(wid, plan.przesun_miesiac(m, o))] = k
        _odswiez(st, wid)
    ark[aid] = {**a, 'od': plan.przesun_miesiac(a['od'], o), 'do': plan.przesun_miesiac(a['do'], o), 'zrodlo': 'apka'}
    return None, bylo, aid


def _duplikuj_arkusz(st: dict, d: dict, scisle: bool):
    """A-OPS-06: kopia struktury (wiersze, sekcje, ustawienia), a z „Duplikuj wartości” także kwot komórek, przesuniętych
    o N miesięcy i przyciętych do zakresu kopii. Wszystkie płatności oryginału stają się w kopii nowymi planami z ustawień
    wiersza (bez ręcznych zmian pojedynczych planów)."""
    ark, wie = st['arkusz'], st['wiersz']
    src, o = d['arkusz'], d['obiekt']
    nid = o['id']
    if src not in ark:
        return 'nie ma arkusza do zduplikowania', None, nid
    if nid in ark:
        return 'arkusz o tym identyfikatorze już jest', None, nid
    ark[nid] = {'przypiety': True, **o, 'zrodlo': 'apka'}   # A-OPS-06: kopia przypięta
    zrodlowe = sorted((wie[x] for x in _wiersze_ark(st, src)),
                      key=lambda w: (-w['rodzaj'], w.get('kontrahent') or '', w.get('komentarz') or '', w['id']))
    for w in zrodlowe:
        wid = _wolne(f"w-{_slug(nid, w['id'])}", wie)
        wie[wid] = {**w, 'id': wid, 'arkusz': nid, 'zrodlo': 'apka'}
        if d['wartosci']:
            for m, k in wartosci_komorek(st, w['id']).items():
                m2 = plan.przesun_miesiac(m, d['przesuniecie'])
                if o['od'] <= m2 <= o['do']:
                    st['komorka'][(wid, m2)] = k
            _odswiez(st, wid)
    return None, None, nid


def _zmien_zakres(st: dict, a: dict, nowy: dict, scisle: bool) -> str | None:
    """A-OPS-04: miesiąc z płatnością rzeczywistą musi zostać w zakresie (🔒); plany z wyciętych miesięcy znikają (💲)."""
    od, do = nowy['od'], nowy['do']
    if od > do:
        return 'Początek zakresu jest po końcu. Wybierz najpierw miesiąc startu, potem miesiąc końca.'
    ile = _roznica_mies(od, do) + 1
    if ile > 240:
        return f'Arkusz może mieć najwyżej 20 lat (240 miesięcy), a wybrany zakres ma {ile}. Podziel plan na kilka arkuszy.'
    if (od, do) == (a.get('od'), a.get('do')):
        return None
    ids = set(_wiersze_ark(st, a['id']))
    poza = [p for p in st['platnosc'].values() if p['wiersz'] in ids and not od <= p['miesiac'] <= do]
    rz = {p['miesiac'] for p in poza if p['typ'] != 'plan'}
    if scisle and rz:
        return (f'W miesiącach: {_lista_mies(rz)} są płatności rzeczywiste, więc te miesiące muszą zostać w zakresie arkusza. '
                'Wybierz zakres, który je obejmuje.')
    for p in poza:
        if p['typ'] == 'plan':
            st['platnosc'].pop(p['id'])
            st['nadpisane'].pop(p['id'], None)
    for k in [k for k in st['komorka'] if k[0] in ids and not od <= k[1] <= do]:
        st['komorka'].pop(k)
        _usun_podzialy(st, k[0], {k[1]})
    return None


def _rowne(pole: str, a, b) -> bool:
    """Porównanie wartości cechy wiersza po normalizacji (stawka 0,23 = 23, „14” = 14, „10” = „10.”)."""
    try:
        if pole == 'stawka_vat':
            return stawka_proc(a) == stawka_proc(b)
        if pole == 'dni_na_platnosc':
            return plan.dni_na_platnosc(a) == plan.dni_na_platnosc(b)
        if pole == 'dzien_wystawienia':
            return plan.regula_tekst(plan.regula(a)) == plan.regula_tekst(plan.regula(b))
        if pole in ('ksiegowane', 'w_cashflow'):
            return bool(a if a is not None else True) == bool(b if b is not None else True)
    except ValueError:
        pass
    return (a or '') == (b or '') if pole in ('kontrahent', 'komentarz', 'metoda') else a == b


def _blokady_wiersza(st: dict, oid: str, bylo: dict | None, nowy: dict, obiekt: dict) -> str | None:
    """Reguły BS przy zapisie wiersza z interfejsu (A-KOL-08, 09, B-POD-02, 06). Przy odtwarzaniu historii nie sprawdzamy:
    zmiana zapisana, gdy była dozwolona, zostaje, nawet jeśli eksport BS dołożył potem rzeczywistą."""
    pod = nowy.get('podstawa', '')
    if bylo and _ma_rzeczywiste(st, oid):
        if pod != bylo.get('podstawa'):
            return 'Wiersz ma już płatność rzeczywistą, więc podstawy nie zmienisz. Zduplikuj wiersz i ustaw nową podstawę w kopii.'
        if nowy.get('rodzaj') != bylo.get('rodzaj'):
            return 'Wiersz ma już płatność rzeczywistą, więc rodzaju (wpływ albo obciążenie) nie zmienisz. Zduplikuj wiersz i zmień rodzaj w kopii.'
        if pod in ('Umowa zlecenie', 'Umowa o pracę') and 'proporcje' in obiekt and obiekt['proporcje'] != bylo.get('proporcje'):
            return 'Wiersz ma już wypłatę rzeczywistą, więc proporcji nie zmienisz. Zduplikuj wiersz i podaj nowe kwoty w kopii.'
    if pod in plan.PODSTAWY_SKLADOWE_BS and pod != (bylo or {}).get('podstawa'):
        return 'Ta podstawa jest tylko w imporcie z Budget Studio. Wybierz umowę o pracę, zlecenie albo o dzieło.'
    if plan.jest_umowa(pod):
        if nowy.get('rodzaj') != -1:
            return 'Umowa to zawsze obciążenie (koszt). Ustaw rodzaj: obciążenia.'
        prop = nowy.get('proporcje') or {}
        if pod == 'Umowa o dzieło' and prop.get('zus'):
            return 'Umowa o dzieło nie ma ZUS: podaj tylko kwotę dla wykonawcy i PIT.'
        if not sum(int(prop.get(k) or 0) for k in plan.UMOWY[pod]):
            return 'Podaj kwoty od księgowej (dla osoby, PIT i ZUS); z nich apka liczy proporcje podziału każdej komórki.'
    return None


def _po_zmianie_wiersza(st: dict, wid: str, zmienione: set, przelicz: bool):
    """Reguła nadpisań: zmieniona cecha-generator przechodzi do WSZYSTKICH planów wiersza (ręczny wyjątek ginie),
    rzeczywistych nie rusza. Zmiana podstawy albo proporcji: plany spoza komórek stają się komórkami i liczą się od nowa."""
    w = st['wiersz'][wid]
    pola_planu = set().union(*(plan.GENERATORY[k] for k in zmienione)) if zmienione else set()
    prefiks = f'plan:{wid}:'
    if przelicz:   # nowa podstawa albo proporcje: podział z kopii BS przestaje obowiązywać
        for k in [k for k in st['podzialy'] if k.startswith(f'{wid}:')]:
            st['podzialy'].pop(k)
    if pola_planu:
        for pid in [k for k in st['nadpisane'] if k.startswith(prefiks)]:
            st['nadpisane'][pid] = {k: v for k, v in st['nadpisane'][pid].items() if k not in pola_planu}
    for pid, p in list(st['platnosc'].items()):
        if p['wiersz'] != wid or p['typ'] != 'plan' or p.get('generowany'):
            continue
        if przelicz:
            klucz = (wid, p['miesiac'])
            st['komorka'][klucz] = st['komorka'].get(klucz, 0) + p['netto']
            st['platnosc'].pop(pid)
        elif zmienione:
            st['platnosc'][pid] = plan.przelicz_jawny(p, w, zmienione)
    _odswiez(st, wid)


def _zmien_plan_z_komorki(st: dict, d: dict, obiekt: dict, p: dict, scisle: bool, dzis: str | None):
    """Zmiana pojedynczego planu z komórki = ręczny wyjątek zapisany przy planie (nadpisanie), plan liczony od nowa.
    Kwota planu jednej faktury albo bez faktury to kwota komórki. Worek: tylko kontrahent i komentarz; PIT i ZUS umowy:
    nic (daty idą za składową dla osoby); stawka tylko w fakturze jednej."""
    wid, m, pid = p['wiersz'], p['miesiac'], p['id']
    w = st['wiersz'][wid]
    pod = w.get('podstawa', '')
    bylo = dict(p)
    pojedynczy = pod not in plan.WOREK and not plan.jest_umowa(pod)
    if d.get('usun'):
        if not pojedynczy:
            return 'Pojedynczego planu z worka ani składowej umowy nie usuniesz. Wyczyść kwotę w komórce.', None, pid
        st['komorka'].pop((wid, m), None)
        _usun_podzialy(st, wid, {m})
        for k in [k for k in st['nadpisane'] if k.startswith(f'plan:{wid}:{m}:')]:
            st['nadpisane'].pop(k)
        _odswiez(st, wid, {m})
        return None, bylo, pid
    pola = {k: v for k, v in obiekt.items() if k not in ('id', 'vat', 'brutto')}
    if pola.get('wiersz', wid) != wid or pola.get('miesiac', m) != m:
        if scisle:
            return 'Plan należy do swojej komórki. Żeby przenieść kwotę na inny miesiąc, zmień kwoty w komórkach.', None, pid
    pola.pop('wiersz', None)
    pola.pop('miesiac', None)
    if scisle:
        if pod in plan.WOREK:
            dozwolone = plan.NADPISANIA_WOREK
        elif p.get('skladowa') in ('us', 'zus'):
            dozwolone = set()
        else:
            dozwolone = plan.NADPISANIA_ZWYKLE | ({'netto'} if pojedynczy else set())
        if 'stawka' in pola and pod != 'Faktura (jedna)':
            return 'Stawkę VAT zmienisz na pojedynczym planie tylko przy fakturze jednej; dla reszty zmień ją w wierszu.', None, pid
        if 'netto' in pola and not pojedynczy:
            return 'Kwotę worka i umowy zmieniasz w komórce miesiąca, nie na pojedynczym planie.', None, pid
        zle = sorted(set(pola) - dozwolone)
        if zle:
            return ('W worku na pojedynczym planie zmienisz tylko kontrahenta i komentarz.' if pod in plan.WOREK else
                    'PIT i ZUS umowy idą za składową dla osoby; zmień ją albo ustawienia wiersza.' if p.get('skladowa') in ('us', 'zus')
                    else f'Tego pola nie zmienisz na planie: {", ".join(zle)}.'), None, pid
        for k in ('wystawienie', 'termin', 'realny', 'ksiegowanie'):
            if pola.get(k) and dzis:
                plan.zakres_daty_planu(pola[k], dzis)
    if 'netto' in pola:
        st['komorka'][(wid, m)] = pola.pop('netto')
    n = {**st['nadpisane'].get(pid, {}), **pola}
    if pola.get('wystawienie') and 'termin' not in pola:
        n.pop('termin', None)
    if (pola.get('wystawienie') or pola.get('termin')) and 'realny' not in pola:
        n.pop('realny', None)   # zmiana dnia płatności ustawia dzień realny = dzień płatności
    st['nadpisane'][pid] = n
    _odswiez(st, wid, {m})
    return None, bylo, pid


# ---------- Pakiet 5: rzeczywista zastępuje plan (połącz, odłącz, płatność ręczna, zamiana planu, lista płac) ----------
# Rzeczywista płatność budżetu powstaje wyłącznie z decyzji Mata (kliknięcie „Połącz”, formularz, lista płac): dokument
# (faktura z Fakturowni, dokument z rejestru biura, przelew ING bez dokumentu, płatność dodana ręcznie) dzielony na części,
# każda część w swojej komórce. Plan komórki znika (A-INN-03, B-LACZ-04): plan z kwoty komórki przestaje się generować
# („zamknięta”) albo liczy się tylko na resztę („otwarta”, worek), plan jawny (z kopii BS) czeka w zapisie połączenia, żeby
# odłączenie mogło go przywrócić. Dane dokumentu czytamy przy każdej odbudowie z plików (Fakturownia, rejestr, ING), więc
# poprawka w źródle od razu widać na płatności; płatność ręczna żyje w zdarzeniu „rzeczywista”.

ZRODLO_DOKUMENTU = {'faktura': 'Fakturownia', 'zakup': 'rejestr biura', 'operacja': 'bank ING', 'reczna': 'dodana ręcznie',
                    'zamiana': 'zamiana planu', 'lista': 'lista płac'}


def id_rzeczywistej(ref: str, i: int = 1, ile: int = 1) -> str:
    """Stałe ID płatności rzeczywistej z dokumentu (krótkie, bo ID przelewu bywa długie); części: :2, :3."""
    baza = f"rz:{_slug('dokument', ref)}"
    return baza if ile == 1 else f'{baza}:{i}'


def rodzina_wiersza(podstawa: str) -> str | None:
    """Faktura z fakturą w worku i bez faktury z bez faktury w worku łączą się ze sobą (B-POD-04); umowy i daniny nie."""
    return {'Faktura (jedna)': 'Faktura', 'Faktura (w worku)': 'Faktura', 'Bez faktury': 'Bez faktury',
            'Bez faktury (w worku)': 'Bez faktury'}.get(podstawa or '')


def wynagrodzenie(w: dict) -> bool:
    """Wiersz wynagrodzenia: umowa (praca, zlecenie, dzieło), wiersz jednej składowej umowy z kopii BS („Umowa o pracę -
    PIT”) albo wiersz oznaczony do listy płac (np. powołanie prezesa)."""
    p = w.get('podstawa', '')
    return plan.jest_umowa(p) or bool(plan.skladowa_umowy(p)) or bool(w.get('lista_plac'))


def rodzenstwo_umowy(wiersze: dict, w: dict) -> dict | None:
    """Wiersze składowych tej samej umowy tej samej osoby w arkuszu (kopia BS: osobny wiersz na wypłatę, PIT i ZUS):
    {składowa: id wiersza}. None, gdy wiersz nie jest składową umowy."""
    su = plan.skladowa_umowy(w.get('podstawa', ''))
    if not su:
        return None
    osoba = (w.get('kontrahent') or '').strip().casefold()
    wynik = {}
    for x in sorted(wiersze.values(), key=lambda x: x['id']):
        t = plan.skladowa_umowy(x.get('podstawa', ''))
        if t and t[0] == su[0] and x['arkusz'] == w['arkusz'] and (x.get('kontrahent') or '').strip().casefold() == osoba:
            wynik.setdefault(t[1], x['id'])
    return wynik


def _dzis_wpisu(dzis: str | None) -> str:
    """„Dziś” przy sprawdzaniu daty dokumentu: dzień stanu, ale nie wcześniej niż kalendarz (faktura z wczoraj nie jest
    „z przyszłości” tylko dlatego, że wyciąg ING jest starszy)."""
    return max(dzis or '', date.today().isoformat())


def _plus_lat(d: str, n: int) -> str:
    return f'{int(d[:4]) + n}{d[4:]}' if d[5:] != '02-29' else f'{int(d[:4]) + n}-02-28'


def dokument_reczny(o: dict) -> dict:
    """Płatność dodana ręcznie (formularz jak „Dodaj płatność” w BS) w kształcie dokumentu do łączenia."""
    fakt = o.get('podstawa') == 'Faktura'
    st_ = stawka_proc(o.get('stawka')) if fakt else None
    vat = (int(o['vat']) if (fakt and o.get('vat') is not None) else vat_od_netto(o['netto'], st_, 'Faktura (jedna)') if fakt else 0)
    wyst = o['wystawienie']
    sprz = o.get('sprzedaz') or wyst
    termin = o.get('termin') or wyst
    return {'ref': f"reczna:{o['id']}", 'typ': 'reczna', 'rodzaj': o['rodzaj'], 'rodzina': o['podstawa'], 'kontrahent': o['kontrahent'],
            'nip': '', 'nr_dok': o.get('nr_dok') or '', 'nr_wewn': o.get('nr_wewn') or '', 'netto': int(o['netto']), 'vat': vat,
            'brutto': int(o['netto']) + vat, 'kwota': int(o['netto']), 'stawka': st_, 'wystawienie': wyst, 'sprzedaz': sprz,
            'termin': termin, 'realny': o.get('oplacona') or o.get('realny') or termin,
            'ksiegowanie': f"{o.get('ksiegowanie') or sprz[:7]}-01", 'tytul': '', 'komentarz': o.get('komentarz') or '',
            'metoda': o.get('metoda') or '', 'ksiegowane': o.get('ksiegowane', True), 'w_cashflow': o.get('w_cashflow', True),
            'oplacona': o.get('oplacona'), 'zrodlo': ZRODLO_DOKUMENTU['reczna'], 'data': wyst}


def _dokument(st: dict, ref: str, dok) -> dict | None:
    if ref.startswith('reczna:'):
        o = st['reczne'].get(ref[7:])
        return dokument_reczny(o) if o else None
    return dok(ref) if dok else None


def _plany_komorki(st: dict, wid: str, m: str) -> list[dict]:
    return [p for p in st['platnosc'].values() if p['wiersz'] == wid and p['miesiac'] == m and p['typ'] == 'plan']


def _klucz(wid: str, m: str) -> str:
    return f'{wid}|{m}'


def _przelicz_realizacje(st: dict, komorki):
    """Stan komórki z połączeń w kolejności zapisu: ostatnie połączenie tej komórki decyduje (zamknięta albo otwarta)."""
    for k in komorki:
        wid, m = k.split('|', 1)
        stan = None
        for rek in st['polaczenia'].values():
            if rek['komorki'].get(k):
                stan = rek['komorki'][k]
        if stan:
            st['realizacja'][(wid, m)] = stan
        else:
            st['realizacja'].pop((wid, m), None)
        _odswiez(st, wid, {m})


def _zastap_plany(st: dict, wid: str, m: str, netto_rz: int, reszta: str | None):
    """Plany komórki ustępują rzeczywistej. Zwraca (stan komórki z kwotą, plany jawne zastąpione, plany dodane: reszta).
    Nie worek: plan znika w całości (BS), chyba że Mat zostawi resztę, gdy rzeczywista jest mniejsza od planu. Worek:
    przyjmuje kolejne rzeczywiste, plany tygodniowe liczą się na resztę, „usuń resztę” zamyka worek."""
    pla, w = st['platnosc'], st['wiersz'][wid]
    worek = w.get('podstawa') in plan.WOREK
    plany = _plany_komorki(st, wid, m)
    jawne = sorted((p for p in plany if not p.get('generowany')), key=lambda p: (p.get('wystawienie') or '', p['id']))
    stan = None
    if (wid, m) in st['komorka']:
        rz_w_komorce = netto_rz + sum(p['netto'] for p in pla.values() if p['wiersz'] == wid and p['miesiac'] == m and p['typ'] != 'plan')
        if worek:
            stan = 'zamknieta' if reszta == 'usun' else None
        else:
            stan = 'otwarta' if reszta == 'zostaw' and st['komorka'][(wid, m)] > rz_w_komorce else 'zamknieta'
    zastapione, dodane = [], []
    if jawne:
        if worek and reszta != 'usun':   # plany tygodniowe zużywane od najwcześniejszego
            zostalo = netto_rz
            for p in jawne:
                if zostalo <= 0:
                    break
                zastapione.append(dict(p))
                pla.pop(p['id'])
                if p['netto'] > zostalo:
                    nowy = {**p, 'netto': p['netto'] - zostalo}
                    _przelicz_vat(nowy, w, p)
                    pla[p['id']] = nowy
                    dodane.append(p['id'])
                zostalo -= min(zostalo, p['netto'])
        else:
            suma = sum(p['netto'] for p in jawne)
            for p in jawne:
                zastapione.append(dict(p))
                pla.pop(p['id'])
            if reszta == 'zostaw' and suma > netto_rz and not worek:
                r = {**jawne[0], 'id': f"{jawne[0]['id']}:reszta", 'netto': suma - netto_rz, 'zrodlo': 'reszta planu'}
                _przelicz_vat(r, w, jawne[0])
                pla[r['id']] = r
                dodane.append(r['id'])
    return stan, zastapione, dodane


def _cechy_z_planu(plany: list[dict], w: dict) -> dict:
    """Cechy zarządcze płatności z dokumentu importowanego: z planu, który zastępuje (ustawienia wiersza z ręcznymi
    wyjątkami), a gdy brak, z wiersza."""
    p = plany[0] if plany else {}
    return {'metoda': p.get('metoda') or w.get('metoda', ''), 'ksiegowane': bool(p.get('ksiegowane', w.get('ksiegowane', True))),
            'w_cashflow': bool(p.get('w_cashflow', w.get('w_cashflow', True)))}


def _platnosci_z_dokumentu(x: dict, czesci: list[dict], st: dict, plany_czesci: list[list[dict]]) -> list[dict]:
    """Płatności rzeczywiste z części dokumentu. Faktura i dokument z rejestru: część = netto, VAT dzielony proporcjonalnie
    (reszta grosza w ostatniej części). Przelew bez dokumentu: część = kwota z banku (brutto); w wierszu z fakturą netto
    i VAT liczone ze stawki wiersza (brak dokumentu, więc VAT jest szacunkiem), w wierszu bez faktury VAT 0."""
    wynik, vat_zost = [], x['vat']
    for i, (c, plany) in enumerate(zip(czesci, plany_czesci), start=1):
        w = st['wiersz'][c['wiersz']]
        kw = c['kwota']
        if x['rodzina'] == 'bank':
            if rodzina_wiersza(w.get('podstawa')) == 'Faktura':
                st_ = stawka_proc(w.get('stawka_vat')) or 0
                netto = int((Decimal(kw) * 100 / (100 + st_)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
                vat, stawka = kw - netto, st_
            else:
                netto, vat, stawka = kw, 0, None
        else:
            netto, stawka = kw, x.get('stawka')
            if i == len(czesci):
                vat = vat_zost
            else:
                vat = int((Decimal(x['vat']) * kw / x['netto']).quantize(Decimal(1), rounding=ROUND_HALF_UP)) if x['netto'] else 0
                vat_zost -= vat
        cechy = _cechy_z_planu(plany, w)
        if x['typ'] == 'reczna':
            cechy = {'metoda': x.get('metoda') or cechy['metoda'], 'ksiegowane': bool(x.get('ksiegowane', True)),
                     'w_cashflow': bool(x.get('w_cashflow', True))}
        termin = x.get('termin') or plan.plus_dni(x['wystawienie'], plan.dni_na_platnosc(w.get('dni_na_platnosc')))
        p = {'id': id_rzeczywistej(x['ref'], i, len(czesci)), 'wiersz': c['wiersz'], 'miesiac': c['miesiac'], 'typ': 'rzeczywista',
             'etap_bs': '', 'aktualna': True, 'netto': netto, 'vat': vat, 'brutto': netto + vat, 'stawka': stawka,
             'nr_dok': x.get('nr_dok') or '', 'nr_wewn': x.get('nr_wewn') or '', 'tytul': x.get('tytul') or '',
             'wystawienie': x['wystawienie'], 'termin': termin, 'realny': x.get('realny') or termin,
             'ksiegowanie': x.get('ksiegowanie'), 'komentarz': x.get('komentarz') or '', 'kontrahent': x.get('kontrahent') or '',
             'zrodlo': x['zrodlo'], 'dokument': x['ref'], **cechy}
        if x.get('oplacona'):   # wyjątek poza bankiem z datą przelewu (decyzja 3), data = dzień realnej płatności
            p.update(decyzja='zapłacone (Mat)', realny=x['oplacona'])
        wynik.append(p)
    return wynik


def _polacz(st: dict, d: dict, scisle: bool, dzis: str | None, dok):
    """B-LACZ-01 do 04: dokument rzeczywisty w komórkach budżetu. Warunki BS: tylko do komórki z planem (choćby 0), ten sam
    rodzaj, zgodna podstawa (stawka VAT wiersza bez znaczenia), cała kwota dokumentu rozdzielona (Do rozliczenia 0,00)."""
    ark, wie = st['arkusz'], st['wiersz']
    ref, czesci = d['dokument'], d['czesci']
    if ref in st['polaczenia']:
        return 'Ten dokument jest już połączony z budżetem. Odłącz go, zanim połączysz go inaczej.', None, ref
    x = _dokument(st, ref, dok)
    if not x:
        return 'nie ma takiego dokumentu w danych (Fakturownia, rejestr biura, ING albo płatności dodane ręcznie)', None, ref
    roznica = x['kwota'] - sum(c['kwota'] for c in czesci)
    if roznica:
        return (f"Do rozliczenia zostało {zl(roznica)}: rozdziel całą kwotę dokumentu ({zl(x['kwota'])}) na komórki tak, "
                'żeby zostało 0,00 zł.'), None, ref
    plany_czesci = []
    for c in czesci:
        w = wie.get(c['wiersz'])
        if not w:
            return 'nie ma wiersza wybranej komórki', None, ref
        a = ark.get(w['arkusz']) or {}
        miejsce = f"„{a.get('nazwa', '')}”, {w.get('kontrahent') or 'wiersz'}, {_mies_pl(c['miesiac'])}"
        if str(w['id']).startswith('sys:') or a.get('zrodlo') == 'system':
            return 'Daniny z arkusza Opłaty urzędowe łączą się same: kwotę od biura wpiszesz w Budżet, Podatki.', None, ref
        if scisle and a and not a['od'] <= c['miesiac'] <= a['do']:
            return f'Miesiąc {_mies_pl(c["miesiac"])} jest poza zakresem arkusza „{a["nazwa"]}”. Najpierw wydłuż arkusz.', None, ref
        if w['rodzaj'] != x['rodzaj']:
            return (f"Nie połączysz {'wpływu' if x['rodzaj'] == 1 else 'obciążenia'} z wierszem "
                    f"{'wpływów' if w['rodzaj'] == 1 else 'obciążeń'} ({miejsce}). Wybierz wiersz tego samego rodzaju."), None, ref
        if wynagrodzenie(w):
            return f'To wiersz wynagrodzenia ({miejsce}): kwoty z listy płac wpiszesz w Budżet, Lista płac.', None, ref
        rw = rodzina_wiersza(w.get('podstawa'))
        if rw is None or (x['rodzina'] != 'bank' and rw != x['rodzina']):
            return (f"Podstawa się nie zgadza: dokument to {x['rodzina'].lower()}, a wiersz ({miejsce}) ma podstawę "
                    f"„{w.get('podstawa')}”. Wybierz wiersz z tą samą podstawą albo dodaj nowy."), None, ref
        plany = _plany_komorki(st, c['wiersz'], c['miesiac'])
        if not plany and w.get('podstawa') in plan.WOREK and st['realizacja'].get((c['wiersz'], c['miesiac'])) == 'zamknieta':
            return (f'Worek {miejsce} jest zamknięty. Otwórz go na karcie komórki (Otwórz worek) albo zwiększ jego kwotę, '
                    'potem połącz.'), None, ref
        if not plany and any(p['wiersz'] == c['wiersz'] and p['miesiac'] == c['miesiac'] for p in st['platnosc'].values()):
            return (f'Komórka {miejsce} ma już płatność rzeczywistą, a jej plan jest zrealizowany. Wybierz inną komórkę '
                    'albo wpisz plan w innym miesiącu tego wiersza.'), None, ref
        if not plany:
            return (f'Komórka {miejsce} jest pusta: nie ma planu, który rzeczywista mogłaby zastąpić. Wpisz w niej kwotę '
                    'planu (choćby 0), potem połącz.'), None, ref
        plany_czesci.append(plany)
    nowe = _platnosci_z_dokumentu(x, czesci, st, plany_czesci)
    rek = {'czesci': [dict(c) for c in czesci], 'platnosci': [], 'komorki': {}, 'zastapione': [], 'dodane': [],
           'reszta': d.get('reszta') or '', 'zrodlo': x['zrodlo']}
    for c, p in zip(czesci, nowe):
        stan, zast, dod = _zastap_plany(st, c['wiersz'], c['miesiac'], p['netto'], d.get('reszta'))
        st['platnosc'][p['id']] = p
        rek['platnosci'].append(p['id'])
        rek['komorki'][_klucz(c['wiersz'], c['miesiac'])] = stan
        rek['zastapione'] += zast
        rek['dodane'] += dod
    st['polaczenia'][ref] = rek
    _przelicz_realizacje(st, rek['komorki'])
    return None, None, ref


def _odlacz(st: dict, ref: str, scisle: bool):
    """B-LACZ-05: rzeczywista wraca do „Do połączenia”, w komórce wraca plan (z kwoty komórki i ustawień wiersza albo plan
    jawny sprzed połączenia). Zamiana planu i lista płac: płatności rzeczywiste znikają, wraca plan."""
    rek = st['polaczenia'].get(ref)
    if not rek:
        return 'Ten dokument nie jest połączony z budżetem.', None, ref
    if scisle:
        kolejne = list(st['polaczenia'])[list(st['polaczenia']).index(ref) + 1:]
        for r in kolejne:
            wspolne = [k for k in st['polaczenia'][r]['komorki'] if k in rek['komorki']
                       and st['wiersz'].get(k.split('|', 1)[0], {}).get('podstawa') not in plan.WOREK]
            if wspolne:
                return (f'W tej samej komórce jest płatność połączona później ({r.split(":", 1)[-1]}). Odłącz najpierw ją, '
                        'potem tę.'), None, ref
    for pid in rek['platnosci'] + rek['dodane']:
        st['platnosc'].pop(pid, None)
    for p in rek['zastapione']:
        st['platnosc'][p['id']] = p
    st['polaczenia'].pop(ref)
    _przelicz_realizacje(st, rek['komorki'])
    return None, rek, ref


def _reczna(st: dict, d: dict, scisle: bool, dzis: str | None):
    """B-DOD-02, B-DOD-03: płatność rzeczywista z formularza (faktura albo bez faktury). Trafia do „Do połączenia”;
    walidacje BS: dzień wystawienia nie z przyszłości i najwyżej 5 lat wstecz, dzień realnej płatności faktury najwcześniej
    45 dni przed wystawieniem (bez faktury: od wystawienia), najwyżej 5 lat w przód."""
    o = d['obiekt']
    rid = o['id']
    ref = f'reczna:{rid}'
    bylo = st['reczne'].get(rid)
    if d.get('usun'):
        if not bylo:
            return 'nie ma takiej płatności dodanej ręcznie', None, ref
        if ref in st['polaczenia']:
            return 'Ta płatność jest połączona z budżetem: odłącz ją, zanim ją usuniesz.', None, ref
        st['reczne'].pop(rid)
        return None, bylo, ref
    nowy = {**(bylo or {}), **o}
    nowy['ksiegowane'] = nowy.get('ksiegowane', True)
    nowy['w_cashflow'] = nowy.get('w_cashflow', True)
    if nowy.get('podstawa') != 'Faktura':
        nowy.pop('stawka', None)
        nowy.pop('vat', None)
    elif nowy.get('stawka') is None and nowy.get('vat') is None:
        return 'Faktura: podaj stawkę VAT (23, 8, 5, 0) albo kwotę VAT.', None, ref
    if scisle:
        dz = _dzis_wpisu(dzis)
        wyst = nowy['wystawienie']
        if wyst > dz:
            return (f'Dzień wystawienia płatności rzeczywistej nie może być z przyszłości (dziś {dz}). Przyszłą płatność '
                    'zaplanuj w arkuszu budżetu.'), None, ref
        if wyst < _plus_lat(dz, -5):
            return 'Dzień wystawienia najwyżej 5 lat wstecz.', None, ref
        fakt = nowy['podstawa'] == 'Faktura'
        od = plan.plus_dni(wyst, -45) if fakt else wyst
        for pole, nazwa in (('realny', 'Dzień realnej płatności'), ('termin', 'Dzień płatności'), ('oplacona', 'Data zapłaty')):
            v = nowy.get(pole)
            if not v:
                continue
            if v < od:
                return (f'{nazwa} {"faktury może być najwcześniej 45 dni przed" if fakt else "nie może być wcześniej niż dzień"} '
                        f'wystawienia ({wyst}).'), None, ref
            if v > _plus_lat(dz, 5):
                return f'{nazwa}: najwyżej 5 lat od dziś.', None, ref
        if nowy.get('oplacona') and nowy['oplacona'] > dz:
            return 'Data zapłaty nie może być z przyszłości.', None, ref
        if bylo and ref in st['polaczenia'] and any(nowy.get(k) != bylo.get(k) for k in ('netto', 'rodzaj', 'podstawa')):
            return 'Płatność jest połączona z budżetem: odłącz ją, zanim zmienisz kwotę, rodzaj albo podstawę.', None, ref
    st['reczne'][rid] = nowy
    if ref in st['polaczenia']:   # poprawione dane (kontrahent, daty, komentarz) od razu na połączonych płatnościach
        rek = st['polaczenia'][ref]
        x = dokument_reczny(nowy)
        if x['kwota'] == sum(c['kwota'] for c in rek['czesci']):
            for p in _platnosci_z_dokumentu(x, rek['czesci'], st, [_plany_komorki(st, c['wiersz'], c['miesiac']) for c in rek['czesci']]):
                if p['id'] in st['platnosc']:
                    st['platnosc'][p['id']] = p
    return None, bylo, ref


def _zamien(st: dict, d: dict, stare: dict, scisle: bool, dzis: str | None):
    """B-LACZ-06, B-POD-11: plan → rzeczywista w tej samej komórce. Tylko plan z dniem wystawienia nie później niż dziś,
    1:1 (bez podziału), nie worek; wynagrodzenia idą listą płac. Komentarz planu przechodzi na rzeczywistą."""
    pid = stare.get(d['plan'], d['plan'])
    p = st['platnosc'].get(pid)
    ref = f'zamiana:{pid}'
    if not p:
        return 'nie ma takiego planu', None, ref
    if p['typ'] != 'plan':
        return 'To już płatność rzeczywista.', None, ref
    w = st['wiersz'][p['wiersz']]
    pod = w.get('podstawa', '')
    if str(w['id']).startswith('sys:'):
        return 'Daniny: kwotę od biura wpiszesz w Budżet, Podatki.', None, ref
    if pod in plan.WOREK:
        return ('Worka nie zmienisz na rzeczywistą: połącz z nim płatności z listy Do połączenia (worek przyjmuje ich wiele) '
                'albo dodaj płatność ręcznie.'), None, ref
    if wynagrodzenie(w):
        return 'Wynagrodzenia zamieniasz na rzeczywiste listą płac (Budżet, Lista płac): kwoty z listy płac od biura.', None, ref
    o = dict(d.get('obiekt') or {})
    if 'stawka' in o and pod != 'Faktura (jedna)':
        return 'Stawkę VAT zmienisz tylko w fakturze.', None, ref
    if pod.startswith('Faktura') and not (o.get('nr_dok') or p.get('nr_dok')):
        return 'Podaj numer faktury (z dokumentu).', None, ref
    wyst = o.get('wystawienie') or p.get('wystawienie')
    if scisle and wyst and wyst > _dzis_wpisu(dzis):
        return (f'Na rzeczywistą zmienisz plan dopiero od dnia jego wystawienia ({wyst}). Dokument już jest? Popraw dzień '
                'wystawienia na karcie zamiany.'), None, ref
    if o.get('ksiegowanie'):
        o['ksiegowanie'] = f"{o['ksiegowanie']}-01"
    if o.get('wystawienie') and 'termin' not in o:
        o['termin'] = plan.plus_dni(o['wystawienie'], plan.dni_na_platnosc(w.get('dni_na_platnosc')))
    if (o.get('wystawienie') or o.get('termin')) and 'realny' not in o:
        o['realny'] = o.get('termin') or p.get('termin')
    netto_rz = o.get('netto', p['netto'])
    stan, zast, dod = _zastap_plany(st, p['wiersz'], p['miesiac'], netto_rz, 'usun')
    rz = {**{k: v for k, v in p.items() if k not in ('generowany', 'nadpisane', 'ukryty', 'decyzja')}, **o,
          'id': id_rzeczywistej(ref), 'typ': 'rzeczywista', 'etap_bs': '', 'aktualna': True, 'zrodlo': ZRODLO_DOKUMENTU['zamiana'],
          'dokument': ref, 'kontrahent': o.get('kontrahent') or p.get('kontrahent') or w.get('kontrahent', '')}
    _przelicz_vat(rz, w, None if 'stawka' in o else p)
    st['platnosc'][rz['id']] = rz
    k = _klucz(p['wiersz'], p['miesiac'])
    st['polaczenia'][ref] = {'czesci': [{'wiersz': p['wiersz'], 'miesiac': p['miesiac'], 'kwota': rz['netto']}], 'platnosci': [rz['id']],
                             'komorki': {k: stan}, 'zastapione': zast, 'dodane': dod, 'reszta': 'usun', 'zrodlo': rz['zrodlo']}
    _przelicz_realizacje(st, [k])
    return None, dict(p), ref


def _zamknij_worek(st: dict, d: dict, scisle: bool):
    """Ręczne „zamknięcie worka” (BS): worek przyjmuje kolejne rzeczywiste, dopóki Mat go nie zamknie. Zamknięcie usuwa
    niezrealizowane plany tygodniowe (komórka = suma rzeczywistych), otwarcie to odłączenie „worek:<wiersz>:<miesiąc>”."""
    wid, m = d['wiersz'], d['miesiac']
    ref = f'worek:{wid}:{m}'
    w = st['wiersz'].get(wid)
    if not w:
        return 'nie ma wiersza tej komórki', None, ref
    if w.get('podstawa') not in plan.WOREK:
        return 'Zamknąć można tylko worek (podstawa „w worku”). Plan pojedynczy zamyka się sam po połączeniu.', None, ref
    if st['realizacja'].get((wid, m)) == 'zamknieta' or ref in st['polaczenia']:
        return 'Ten worek jest już zamknięty.', None, ref
    if scisle and not any(p['wiersz'] == wid and p['miesiac'] == m and p['typ'] != 'plan' for p in st['platnosc'].values()):
        return ('Worek nie ma jeszcze żadnej płatności rzeczywistej. Pusty worek zmniejszysz albo usuniesz, zmieniając kwotę '
                'komórki.'), None, ref
    jawne = [p for p in _plany_komorki(st, wid, m) if not p.get('generowany')]
    for p in jawne:
        st['platnosc'].pop(p['id'])
    k = _klucz(wid, m)
    st['polaczenia'][ref] = {'czesci': [], 'platnosci': [], 'komorki': {k: 'zamknieta'}, 'zastapione': [dict(p) for p in jawne],
                             'dodane': [], 'reszta': 'usun', 'zrodlo': 'zamknięcie worka'}
    _przelicz_realizacje(st, [k])
    return None, None, ref


def _lista_plac(st: dict, d: dict, scisle: bool):
    """Dawne zdarzenie „bud” lista_plac (sprzed wpisu „lista_plac”): to samo działanie co wpis listy płac za miesiąc."""
    from . import lista_plac
    powod = lista_plac.zastosuj(st, d, scisle)
    return powod, None, f"lista:{d['miesiac']}"


def _zastosuj_op(st: dict, d: dict, stare: dict, scisle: bool = False, dzis: str | None = None, dok=None):
    """Jedna operacja na stanie modelu. Zwraca (powód odrzucenia albo osierocenia, było, id obiektu); przy powodzie nic
    nie zmienia. scisle=True przy sprawdzaniu nowego wpisu z interfejsu: wtedy obowiązują też blokady BS."""
    ark, wie, pla = st['arkusz'], st['wiersz'], st['platnosc']
    op = d['op']
    akcje = {'scal': _scal, 'podziel': _podziel, 'duplikuj': _duplikuj, 'przesun_arkusz': _przesun_arkusz,
             'duplikuj_arkusz': _duplikuj_arkusz}
    # pakiet 4: Biblioteka (słowniki, foldery i kategorie) i miejsce arkusza w strukturze (biblioteka.py)
    from . import biblioteka
    if op in ('slownik', 'struktura'):
        return biblioteka.zastosuj(st, d, scisle)
    if scisle and op in ('arkusz', 'duplikuj_arkusz') and not d.get('usun') and (powod := biblioteka.sprawdz_miejsce(st, d['obiekt'])):
        return powod, None, d['obiekt']['id']
    if op == 'wiersz' and d.get('domyslne') and d['obiekt']['id'] not in wie:
        # nowy wiersz z „Dodaj +”: brakujące pola z ustawień kontrahenta albo kontrahenta domyślnego (A-KOL-04, 05);
        # przy zapisie wpis dostaje pełny wiersz, więc historia nie zależy od późniejszych zmian w Bibliotece
        d_pelny = {**d, 'obiekt': biblioteka.uzupelnij_wiersz(st, d['obiekt'])}
        d_pelny.pop('domyslne')
        if scisle:
            d.update(d_pelny)
            d.pop('domyslne', None)
        d = d_pelny
    if op in akcje:
        return akcje[op](st, d, scisle)
    if op == 'polacz':
        return _polacz(st, d, scisle, dzis, dok)
    if op == 'odlacz':
        if scisle and d['dokument'].startswith('lista:'):
            return ('Listę płac zmienisz albo usuniesz na ekranie Lista płac (Budżet). Kwoty z listy to dane rzeczywiste, nie '
                    'połączenie z dokumentem.'), None, d['dokument']
        return _odlacz(st, stare.get(d['dokument'], d['dokument']), scisle)
    if op == 'rzeczywista':
        return _reczna(st, d, scisle, dzis)
    if op == 'zamien':
        return _zamien(st, d, stare, scisle, dzis)
    if op == 'lista_plac':
        return _lista_plac(st, d, scisle)
    if op == 'zamknij_worek':
        return _zamknij_worek(st, d, scisle)
    if op == 'komorka':
        wid, m, kwota = d['wiersz'], d['miesiac'], d.get('kwota')
        oid = f'{wid}:{m}'
        if wid not in wie:
            return 'nie ma wiersza tej komórki', None, oid
        w = wie[wid]
        w_komorce = [p for p in pla.values() if p['wiersz'] == wid and p['miesiac'] == m]
        rz = sum(p['netto'] for p in w_komorce if p['typ'] != 'plan')
        ma_rz = any(p['typ'] != 'plan' for p in w_komorce)
        if scisle:
            a = ark.get(w['arkusz'])
            if a and not (a['od'] <= m <= a['do']):
                return f"Miesiąc {m} jest poza zakresem arkusza ({a['od']} do {a['do']}). Najpierw wydłuż arkusz.", None, oid
            if ma_rz and w.get('podstawa') not in plan.WOREK:
                return 'W tej komórce jest już płatność rzeczywista, więc kwoty nie zmienisz. Wpisz plan w innym miesiącu albo zduplikuj wiersz.', None, oid
            if ma_rz and (kwota is None or kwota < rz):
                return f'W worku są już płatności rzeczywiste na {zl(rz)}, więc kwota komórki nie może być mniejsza.', None, oid
        jawne = [p for p in w_komorce if p['typ'] == 'plan' and not p.get('generowany')]
        bylo = {'kwota': st['komorka'].get((wid, m), sum(p['netto'] for p in jawne) if jawne else None)}
        for p in jawne:
            pla.pop(p['id'])
        if kwota is None:
            st['komorka'].pop((wid, m), None)
            st['podzialy'].pop(f'{wid}:{m}', None)
            for k in [k for k in st['nadpisane'] if k.startswith(f'plan:{wid}:{m}:')]:
                st['nadpisane'].pop(k)
        else:
            st['komorka'][(wid, m)] = kwota
            k = _klucz(wid, m)   # A-KOM-05: zwiększenie kwoty zamkniętego worka otwiera go (plany na różnicę)
            if (w.get('podstawa') in plan.WOREK and st['realizacja'].get((wid, m)) == 'zamknieta'
                    and kwota > (bylo['kwota'] or 0)):
                for r, rek in list(st['polaczenia'].items()):
                    if r == f'worek:{wid}:{m}':   # ręczne zamknięcie worka znika razem z zamknięciem
                        st['polaczenia'].pop(r)
                    elif rek['komorki'].get(k):
                        st['polaczenia'][r] = {**rek, 'komorki': {**rek['komorki'], k: None}}
                _przelicz_realizacje(st, [k])
        _odswiez(st, wid, {m})
        return None, bylo, oid
    if op in ('arkusz', 'wiersz', 'platnosc'):
        obiekt = dict(d.get('obiekt', {}))
        if op == 'platnosc':
            obiekt['id'] = stare.get(obiekt['id'], obiekt['id'])
            if obiekt.get('wzor'):
                obiekt['wzor'] = stare.get(obiekt['wzor'], obiekt['wzor'])
            ist = pla.get(obiekt['id'])
            if ist and ist.get('generowany'):
                obiekt.pop('wzor', None)
                return _zmien_plan_z_komorki(st, d, obiekt, ist, scisle, dzis)
        zbior = {'arkusz': ark, 'wiersz': wie, 'platnosc': pla}[op]
        oid = obiekt['id']
        bylo = dict(zbior[oid]) if oid in zbior else None
        nazwa = {'arkusz': 'arkusza', 'wiersz': 'wiersza', 'platnosc': 'płatności'}[op]
        if d.get('usun'):
            if bylo is None:
                return f'nie ma {nazwa} do usunięcia', None, oid
            if op == 'arkusz':
                wiersze_ark = set(_wiersze_ark(st, oid))
                if scisle and any(p['wiersz'] in wiersze_ark and p['typ'] != 'plan' for p in pla.values()):
                    return ('Arkusz ma płatności rzeczywiste, więc go nie usuniesz. Przenieś wiersze z rzeczywistymi do innego '
                            'arkusza albo zostaw arkusz i wyczyść tylko plany.'), None, oid
                zbior.pop(oid)
                for wid in wiersze_ark:
                    _usun_wiersz(st, wid)
                return None, bylo, oid
            if op == 'wiersz':
                if scisle and _ma_rzeczywiste(st, oid):
                    return ('Wiersz ma płatność rzeczywistą, więc go nie usuniesz. Wyczyść kwoty planów w komórkach '
                            'albo przenieś wiersz do innego arkusza.'), None, oid
                _usun_wiersz(st, oid)
                return None, bylo, oid
            if scisle and bylo.get('typ') != 'plan':
                return ('To płatność rzeczywista (dokument albo przelew), więc nie usuniesz jej z budżetu. '
                        'Usunąć możesz tylko płatność planowaną.'), None, oid
            zbior.pop(oid)
            return None, bylo, oid
        if op == 'arkusz':
            if bylo is None and not all(obiekt.get(k) for k in ('nazwa', 'folder', 'kategoria', 'od', 'do')):
                return 'nie ma takiego arkusza', None, oid
            nowy = {**(bylo or {}), **obiekt, 'zrodlo': 'apka'}
            if bylo and set(obiekt) <= {'id', 'przypiety'}:   # przypięcie nie zmienia źródła arkusza (pakiet 4)
                nowy['zrodlo'] = bylo.get('zrodlo', '')
            if bylo:
                powod = _zmien_zakres(st, bylo, nowy, scisle)
                if powod:
                    return powod, None, oid
            ark[oid] = nowy
            return None, bylo, oid
        if op == 'wiersz':
            if 'arkusz' in obiekt and obiekt['arkusz'] not in ark:
                return 'nie ma arkusza tego wiersza', None, oid
            if bylo is None and not ('arkusz' in obiekt and obiekt.get('rodzaj') in (1, -1) and obiekt.get('podstawa')):
                return 'nie ma takiego wiersza', None, oid
            nowy = {**(bylo or {}), **obiekt, 'zrodlo': 'apka'}
            if scisle:
                powod = _blokady_wiersza(st, oid, bylo, nowy, obiekt)
                if not powod and (bylo is None or bylo.get('arkusz') != nowy['arkusz']):
                    powod = _za_duzo_wierszy(st, nowy['arkusz'], 1)
                if powod:
                    return powod, None, oid
            if plan.jest_umowa(nowy.get('podstawa', '')):   # umowa: Księgowane zawsze tak, VAT „-”
                nowy['ksiegowane'], nowy['stawka_vat'] = True, None
            wie[oid] = nowy
            if bylo:
                zmienione = {k for k in plan.GENERATORY if k in nowy and not _rowne(k, bylo.get(k), nowy.get(k))}
                przelicz = nowy.get('podstawa') != bylo.get('podstawa') or nowy.get('proporcje') != bylo.get('proporcje')
                if zmienione or przelicz:
                    _po_zmianie_wiersza(st, oid, zmienione, przelicz)
            return None, bylo, oid
        # płatność (z importu BS, kopia albo dodana w apce, nie z komórki)
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
        elif obiekt.get('miesiac', bylo['miesiac']) != bylo['miesiac'] or obiekt.get('wiersz', bylo['wiersz']) != bylo['wiersz']:
            if bylo.get('typ') != 'plan':
                if scisle:
                    return ('Płatności rzeczywistej nie przeniesiesz ręcznie do innej komórki. '
                            'Przenieś cały wiersz do innego arkusza.'), None, oid
            elif 'miesiac' in obiekt:   # plan na inny miesiąc: wszystkie daty przesuwają się o tyle samo (B-MOD-11)
                o = _roznica_mies(bylo['miesiac'], obiekt['miesiac'])
                obiekt = {**{k: _przesun_date(bylo.get(k), o) for k in ('wystawienie', 'termin', 'realny', 'ksiegowanie')}, **obiekt}
            a = ark.get(wie.get(obiekt.get('wiersz', bylo['wiersz']), {}).get('arkusz'))
            if scisle and a and not a['od'] <= obiekt.get('miesiac', bylo['miesiac']) <= a['do']:
                return f"Miesiąc {_mies_pl(obiekt['miesiac'])} jest poza zakresem arkusza. Najpierw wydłuż arkusz (Zarządzaj).", None, oid
        if scisle and dzis and (bylo or obiekt).get('typ') == 'plan':
            for k in ('wystawienie', 'termin', 'realny', 'ksiegowanie'):
                if obiekt.get(k) and (bylo is None or obiekt[k] != bylo.get(k)):
                    plan.zakres_daty_planu(obiekt[k], dzis)
        nowa = {**(bylo or {}), **{k: v for k, v in obiekt.items() if k not in ('vat', 'brutto')}, 'zrodlo': 'apka'}
        if bylo and bylo.get('typ') == 'plan' and obiekt.get('termin') and 'realny' not in obiekt:
            nowa['realny'] = obiekt['termin']   # zmiana dnia płatności ustawia dzień realny
        if bylo is None or 'netto' in obiekt or 'stawka' in obiekt:
            _przelicz_vat(nowa, wie.get(nowa['wiersz']), None if 'stawka' in obiekt else (bylo or (pla.get(wzor) if wzor else None)))
        pla[oid] = nowa
        return None, bylo, oid
    if op == 'przenies':
        brak = [w for w in d['wiersze'] if w not in wie]
        if d['do_arkusza'] not in ark or brak:
            return 'nie ma arkusza docelowego' if d['do_arkusza'] not in ark else f'nie ma wierszy: {", ".join(brak)}', None, ','.join(d['wiersze'])
        if scisle:
            cel, ids = ark[d['do_arkusza']], set(d['wiersze'])
            poza = {p['miesiac'] for p in pla.values() if p['wiersz'] in ids and not cel['od'] <= p['miesiac'] <= cel['do']}
            if poza:
                return (f"Arkusz „{cel['nazwa']}” obejmuje {_mies_pl(cel['od'])} do {_mies_pl(cel['do'])}, a wiersze mają płatności "
                        f"także w: {_lista_mies(poza)}. Najpierw wydłuż arkusz docelowy (Zarządzaj, Zmodyfikuj czas trwania)."), None, ','.join(d['wiersze'])
            if powod := _za_duzo_wierszy(st, d['do_arkusza'], len([x for x in ids if wie[x]['arkusz'] != d['do_arkusza']])):
                return powod, None, ','.join(d['wiersze'])
        for wid in d['wiersze']:
            wie[wid] = {**wie[wid], 'arkusz': d['do_arkusza']}
        return None, None, ','.join(d['wiersze'])
    if op == 'decyzja_planu':   # po terminie: przesuń / zapłacone / anuluj (wymaganie 1)
        pid = stare.get(d['platnosc'], d['platnosc'])
        p = pla.get(pid)
        if not p:
            return 'nie ma takiej płatności', None, pid
        bylo = dict(p)
        if p.get('generowany'):   # plan z komórki: decyzja jako ręczna zmiana planu, plan zostaje w swojej komórce
            n = dict(st['nadpisane'].get(pid, {}))
            if d['decyzja'] == 'przesun':
                n.update(termin=d['termin'], decyzja='przesunięte')
                n.pop('realny', None)
            elif d['decyzja'] == 'anuluj':
                n.update(aktualna=False, decyzja='anulowane')
            elif d['decyzja'] == 'zaplacone':
                n.update(decyzja='zapłacone (Mat)', **({'realny': d['data']} if d.get('data') else {}))
            st['nadpisane'][pid] = n
            _odswiez(st, p['wiersz'], {p['miesiac']})
            return None, bylo, pid
        if d['decyzja'] == 'przesun':
            pla[pid] = {**p, 'termin': d['termin'], 'realny': d['termin'], 'miesiac': d['termin'][:7], 'decyzja': 'przesunięte'}
        elif d['decyzja'] == 'anuluj':
            pla[pid] = {**p, 'aktualna': False, 'decyzja': 'anulowane'}
        elif d['decyzja'] == 'zaplacone':
            pla[pid] = {**p, 'decyzja': 'zapłacone (Mat)', 'realny': d.get('data')}
        return None, bylo, pid
    return 'nieznana operacja', None, ''


def _zastosuj_wpis(st: dict, w: dict, stare: dict, scisle: bool = False, dzis: str | None = None, dok=None):
    """Wpis „bud” w całości albo wcale: seria na kopii stanu, podmiana dopiero, gdy wszystkie operacje się udały.
    Zwraca (powód osierocenia albo None, lista (operacja, było, id))."""
    d = w['dane']
    ops = d['operacje'] if d['op'] == 'seria' else [d]
    roboczy = {k: dict(v) for k, v in st.items()}
    wykonane = []
    for i, o in enumerate(ops, start=1):
        try:
            powod, bylo, oid = _zastosuj_op(roboczy, o, stare, scisle, dzis, dok)
        except ValueError as e:
            powod = str(e)
        if powod:
            return (f'operacja {i} z {len(ops)}: {powod}' if len(ops) > 1 else powod), []
        wykonane.append((o, bylo, oid))
    from . import biblioteka
    biblioteka.wchlon(roboczy, ops)   # pakiet 4: nowe wartości i foldery z tego wpisu trafiają do Biblioteki
    st.update(roboczy)
    return None, wykonane


def zastosuj_zdarzenia(model: dict, wpisy: list[dict], dokumenty=None) -> list[dict]:
    """Nakłada zdarzenia „bud” na model z importu. Zwraca historię (kto, kiedy, co, było, jest); zdarzenia bez obiektu
    (np. płatność, której już nie ma w eksporcie BS) zapisuje w model['osierocone'] zamiast gubić je po cichu.
    dokumenty: ref → dokument rzeczywisty z bazy (pakiet 5, łączenie), np. laczenie.Dokumenty(con)."""
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    stare = model.get('stare_id', {})
    st = _stan(model)
    historia, osierocone = [], []
    for w in wpisy:
        if w.get('typ') != 'bud' or w.get('id') in cofniete:
            continue
        powod, wykonane = _zastosuj_wpis(st, w, stare, dok=dokumenty)
        if powod:
            d = w['dane']
            obiekt = ((d.get('obiekt') or {}).get('id') or d.get('platnosc') or d.get('dokument') or d.get('plan')
                      or (f"lista płac {d['miesiac']}" if d['op'] == 'lista_plac' else '') or ','.join(d.get('wiersze', []))
                      or (f"{d['wiersz']}:{d['miesiac']}" if d['op'] in ('komorka', 'zamknij_worek') else d.get('wiersz') or d.get('arkusz')
                          or f"{len(d.get('operacje', []))} operacji"))
            osierocone.append({'wpis': w['id'], 'czas': w['czas'], 'mac': w.get('mac', ''), 'op': d['op'], 'obiekt': obiekt, 'powod': powod})
            continue
        for o, bylo, oid in wykonane:
            if o['op'] == 'komorka':
                jest = {'kwota': st['komorka'].get((o['wiersz'], o['miesiac']))}
            elif o['op'] in ('polacz', 'zamien', 'lista_plac', 'odlacz', 'rzeczywista', 'zamknij_worek'):
                rek = st['polaczenia'].get(oid)
                jest = ({'platnosci': rek['platnosci'], 'czesci': rek['czesci']} if rek else
                        st['reczne'].get(oid[7:]) if oid.startswith('reczna:') else None)
            else:
                jest = st['arkusz'].get(oid) or st['wiersz'].get(oid) or st['platnosc'].get(oid)
            historia.append({'wpis': w['id'], 'czas': w['czas'], 'mac': w.get('mac', ''),
                             'op': o['op'] if w['dane']['op'] != 'seria' else f"seria: {o['op']}", 'obiekt': oid, 'bylo': bylo, 'jest': jest})
    _zastosuj_listy(st, wpisy, historia, osierocone)
    model['arkusze'], model['wiersze'], model['platnosci'] = list(st['arkusz'].values()), list(st['wiersz'].values()), list(st['platnosc'].values())
    model['komorki'] = [{'wiersz': w, 'miesiac': m, 'kwota': k} for (w, m), k in sorted(st['komorka'].items())]
    model['nadpisane'] = {k: v for k, v in st['nadpisane'].items() if v}
    model['podzialy'] = st['podzialy']
    model['parametry'] = st['parametry']
    model['polaczenia'], model['reczne'], model['listy'] = st['polaczenia'], st['reczne'], st['listy']
    model['realizacja'] = [[w, m, v] for (w, m), v in sorted(st['realizacja'].items())]
    model['osierocone'] = osierocone
    from . import biblioteka
    biblioteka.odloz(model, st)   # pakiet 4: słowniki i struktura po zdarzeniach
    return historia


def _zastosuj_listy(st: dict, wpisy: list[dict], historia: list[dict], osierocone: list[dict]):
    """Listy płac (wpis „lista_plac”, dane rzeczywiste) po wszystkich zdarzeniach „bud”: obowiązuje ostatni wpis za miesiąc.
    Nie zależą od kopii z BS ani od planowania; pozycja bez wiersza trafia do osieroconych, reszta listy działa."""
    from . import lista_plac
    for m, w in lista_plac.obowiazujace(wpisy).items():
        powod = lista_plac.zastosuj(st, w['dane'])
        if powod:
            osierocone.append({'wpis': w['id'], 'czas': w['czas'], 'mac': w.get('mac', ''), 'op': 'lista_plac',
                               'obiekt': f'lista płac {m}', 'powod': powod})
        if m in st['listy']:
            st['listy'][m]['wpis'] = w['id']
        rek = {r: st['polaczenia'][r]['platnosci'] for r in st['polaczenia'] if r.startswith(f'lista:{m}:')}
        historia.append({'wpis': w['id'], 'czas': w['czas'], 'mac': w.get('mac', ''), 'op': 'lista_plac', 'obiekt': f'lista płac {m}',
                         'bylo': None, 'jest': {'platnosci': [p for ps in rek.values() for p in ps]} if rek else None})


def sprawdz_liste(dane: dict, wpisy: list[dict], dokumenty=None):
    """Próba wpisu listy płac na bieżącym budżecie (kopia z BS albo import, zdarzenia „bud”, wcześniejsze listy), bez zapisu.
    Planowanie nie jest potrzebne: lista płac to dane rzeczywiste od biura."""
    from . import lista_plac
    model, wpisy_modelu, _ = model_bazowy(wpisy, odswiez=False)
    if not model:
        raise ValueError('brak budżetu: nie ma pliku importu z Budget Studio')
    zastosuj_zdarzenia(model, wpisy_modelu, dokumenty)
    powod = lista_plac.zastosuj(_stan(model), dane, scisle=True)
    if powod:
        raise ValueError(f'Nic nie zapisano. {powod}' if powod[:1].isupper() else f'Nic nie zapisano: {powod}')


def wczytaj_model() -> dict | None:
    """Model z pliku importu (bez generowania i zapisu), do sprawdzenia wpisu przed zapisem."""
    p = plik_importu()
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else None


def import_bs_wlaczony(wpisy: list[dict]) -> bool:
    """Przełącznik „import_bs” (APK-FLAG-02, pakiet 6): czy apka czyta eksporty BS. Domyślnie tak; po 1.01.2027 Mat
    wyłącza i apka działa dalej na kopii z BS i własnych planach. Ostatni nie cofnięty wpis wygrywa."""
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    wartosc = 'tak'
    for w in wpisy:
        if w.get('typ') == 'ustawienie' and w['dane'].get('klucz') == 'import_bs' and w.get('id') not in cofniete:
            wartosc = w['dane']['wartosc']
    return wartosc == 'tak'


def model_bazowy(wpisy: list[dict], odswiez: bool = True) -> tuple[dict | None, list[dict], dict]:
    """Model, na który nakładamy zdarzenia „bud”: przyjęta kopia z BS (pakiet 6; zdarzenia sprzed kopii już nie
    obowiązują), a bez niej import z najnowszego eksportu BS. Zwraca (model, wpisy do nałożenia, informacje: wpis kopii,
    import do porównania w okresie równoległym, błąd kopii). odswiez=False: bez generowania pliku importu (próba wpisu)."""
    from . import kopia_bs
    info = {}
    wlaczony = import_bs_wlaczony(wpisy)
    k = kopia_bs.aktywna(wpisy)
    if k:
        try:
            kopia = kopia_bs.wczytaj(k)
            info.update(kopia=k, wiersze_bs=kopia.get('wiersze_bs', {}),
                        imp=odswiez_import() if (odswiez and wlaczony) else None)
            return kopia_bs.rozwin(kopia), kopia_bs.po_kopii(wpisy, k), info
        except ValueError as e:
            info['blad'] = str(e)
    if not wlaczony:
        return None, wpisy, info
    imp = odswiez_import() if odswiez else wczytaj_model()
    return (json.loads(json.dumps(imp)) if imp else None), wpisy, info   # kopia, plik importu zostaje nietknięty


def sprawdz_wpis(dane: dict, wpisy: list[dict], model: dict | None = None, dzis: str | None = None, dokumenty=None):
    """Próba wpisu „bud” na bieżącym stanie (kopia z BS albo import + dotychczasowe zmiany), bez zapisu, z blokadami BS
    (rzeczywiste w wierszu, worek, składowe umowy, zakres miesięcy i dat). ValueError z powodem: wtedy do pliku zmian nie trafia nic."""
    if model is None:
        model, wpisy, _ = model_bazowy(wpisy, odswiez=False)
    if not model:
        raise ValueError('brak budżetu: nie ma pliku importu z Budget Studio')
    zastosuj_zdarzenia(model, wpisy, dokumenty)
    powod, _ = _zastosuj_wpis(_stan(model), {'dane': dane}, model.get('stare_id', {}), scisle=True, dzis=dzis, dok=dokumenty)
    if powod:
        raise ValueError(f'Nic nie zapisano. {powod}' if powod[:1].isupper() else f'Nic nie zapisano: {powod}')


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
    from .zmiany import LACZENIE_OD
    planowanie, estymaty, laczenie_od = 'nie', {}, LACZENIE_OD
    for w in wpisy:
        if w.get('id') in cofniete:
            continue
        if w.get('typ') == 'ustawienie' and w['dane'].get('klucz') == 'planowanie':
            planowanie = w['dane']['wartosc']
        elif w.get('typ') == 'ustawienie' and w['dane'].get('klucz') == 'laczenie_od':
            laczenie_od = w['dane']['wartosc']
        elif w.get('typ') == 'estymata':
            estymaty[w['dane']['klient']] = {'udzial': w['dane']['udzial'], 'od': w['dane'].get('od', ''), 'wpis': w['id']}
    con.execute("INSERT OR REPLACE INTO meta VALUES ('planowanie', ?)", (planowanie,))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('import_bs_wl', ?)", ('tak' if import_bs_wlaczony(wpisy) else 'nie',))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('estymaty', ?)", (json.dumps(estymaty, ensure_ascii=False),))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('laczenie_od', ?)", (laczenie_od,))


def zbuduj(con, wpisy: list[dict]) -> dict:
    ustawienia_z_wpisow(con, wpisy)
    from . import umowy
    umowy.zapisz_do_bazy(con, wpisy)
    model, wpisy_modelu, info = model_bazowy(wpisy)
    if not model:
        return {'arkuszy': 0, **({'blad': info['blad']} if info.get('blad') else {})}
    z_importu = {w['id'] for w in model['wiersze']}   # model_bazowy daje kopię: plik importu i kopii zostają nietknięte
    from . import laczenie   # pakiet 5: dokumenty rzeczywiste (Fakturownia, rejestr, ING) do zdarzeń „polacz”
    historia = zastosuj_zdarzenia(model, wpisy_modelu, laczenie.Dokumenty(con))
    generuj_cykliczne(model)
    ile = {'arkuszy': len(model['arkusze']), 'wierszy': len(model['wiersze']), 'platnosci': len(model['platnosci'])}
    rozjazdy = None
    if info.get('kopia') and info.get('imp'):   # pakiet 6: okres równoległy, nowy eksport BS kontra plany apki (bez danin)
        from . import kopia_bs
        rozjazdy = kopia_bs.porownaj(info['imp'], model, info['wiersze_bs'])
    from . import podatki   # pakiet 8: arkusz systemowy „Opłaty urzędowe” zamiast wierszy podatkowych z BS
    podatki.dolacz(model, wpisy, con)
    # Kolejność wierszy w arkuszu: wiersze z importu jak dotąd (wpływy, potem obciążenia, kontrahent, komentarz), wiersze
    # dodane w apce na końcu w kolejności powstania (nowy wiersz zostaje tam, gdzie go wpisano, jak w BS).
    klucz = {w['id']: ((0, -w['rodzaj'], w.get('kontrahent') or '', w.get('komentarz') or '', w['id']) if w['id'] in z_importu
                       else (1, nr)) for nr, w in enumerate(model['wiersze'])}
    kolejnosc = {wid: i for i, wid in enumerate(sorted(klucz, key=klucz.get))}
    for a in model['arkusze']:
        con.execute('INSERT INTO bud_arkusz (id, folder, kategoria, nazwa, od, do, zrodlo, przypiety) VALUES (?,?,?,?,?,?,?,?)',
                    (a['id'], a['folder'], a['kategoria'], a['nazwa'], a['od'], a['do'], a.get('zrodlo', ''),
                     int(a.get('przypiety', True) is not False)))   # pakiet 4: bez decyzji arkusz jest przypięty
    for w in model['wiersze']:
        con.execute('INSERT INTO bud_wiersz (id, arkusz, rodzaj, podstawa, kontrahent, komentarz, przedmiot, sekcja, stawka_vat,'
                    ' dzien_wystawienia, dni_na_platnosc, metoda, ksiegowane, w_cashflow, cykl, plan, zrodlo, split, proporcje, kup, kolejnosc,'
                    ' lista_plac) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (w['id'], w['arkusz'], w['rodzaj'], w['podstawa'], w.get('kontrahent', ''), w.get('komentarz', ''), w.get('przedmiot', ''),
                     w.get('sekcja', ''), '' if w.get('stawka_vat') is None else str(w['stawka_vat']), w.get('dzien_wystawienia', ''),
                     str(w.get('dni_na_platnosc', '')), w.get('metoda', ''), int(bool(w.get('ksiegowane', True))), int(bool(w.get('w_cashflow', True))),
                     w.get('cykl', 'brak'), json.dumps(w.get('plan')) if w.get('plan') else None, w.get('zrodlo', ''), int(bool(w.get('split'))),
                     json.dumps(w['proporcje'], sort_keys=True) if w.get('proporcje') else None, w.get('kup'), kolejnosc[w['id']],
                     int(bool(w.get('lista_plac')))))
    znak = {w['id']: w['rodzaj'] for w in model['wiersze']}
    kontrahent = {w['id']: w.get('kontrahent', '') for w in model['wiersze']}
    for p in model['platnosci']:
        if p['wiersz'] not in znak:
            continue
        st = stawka_proc(p.get('stawka'))
        con.execute('INSERT INTO bud_platnosc (id, bs_id, wiersz, miesiac, typ, etap_bs, aktualna, netto, vat, brutto, stawka, rodzaj, nr_dok, nr_wewn,'
                    ' tytul, wystawienie, termin, realny, ksiegowanie, metoda, w_cashflow, komentarz, decyzja, zrodlo, wiersz_pliku,'
                    ' kontrahent, ksiegowane, skladowa, spinacz, generowany, nadpisane, ukryty, dokument, skladniki)'
                    ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (p['id'], p.get('bs_id'), p['wiersz'], p['miesiac'], p['typ'], p.get('etap_bs', ''), int(bool(p.get('aktualna', True))),
                     p['netto'], p.get('vat', 0), p.get('brutto', p['netto']), st, znak[p['wiersz']], p.get('nr_dok', ''), p.get('nr_wewn', ''),
                     p.get('tytul', ''), p.get('wystawienie'), p.get('termin'), p.get('realny'), p.get('ksiegowanie'), p.get('metoda', ''),
                     int(bool(p.get('w_cashflow', True))), p.get('komentarz', ''), p.get('decyzja', ''), p.get('zrodlo', 'Budget Studio'),
                     p.get('wiersz_pliku'), p.get('kontrahent') or kontrahent[p['wiersz']], int(bool(p.get('ksiegowane', True))),
                     p.get('skladowa'), p.get('spinacz'), int(bool(p.get('generowany'))),
                     json.dumps(p['nadpisane'], ensure_ascii=False, sort_keys=True) if p.get('nadpisane') else None, int(bool(p.get('ukryty'))),
                     p.get('dokument'), json.dumps(p['skladniki'], sort_keys=True) if p.get('skladniki') else None))
    con.executemany('INSERT INTO bud_komorka (wiersz, miesiac, kwota) VALUES (?,?,?)',
                    [(k['wiersz'], k['miesiac'], k['kwota']) for k in model.get('komorki', []) if k['wiersz'] in znak])
    con.executemany('INSERT INTO bud_historia (wpis, czas, mac, op, obiekt, bylo, jest) VALUES (?,?,?,?,?,?,?)',
                    [(h['wpis'], h['czas'], h['mac'], h['op'], h['obiekt'], json.dumps(h['bylo'], ensure_ascii=False),
                      json.dumps(h['jest'], ensure_ascii=False)) for h in historia])
    wpis_recznej = {}
    for w in wpisy_modelu:
        o = (w.get('dane') or {}).get('obiekt') or {}
        if w.get('typ') == 'bud' and w['dane'].get('op') == 'rzeczywista':
            wpis_recznej[o.get('id')] = w['id']
        for x in (w.get('dane') or {}).get('operacje', []) if w.get('typ') == 'bud' else []:
            if x.get('op') == 'rzeczywista':
                wpis_recznej[(x.get('obiekt') or {}).get('id')] = w['id']
    con.executemany('INSERT INTO bud_reczne (id, dane, wpis) VALUES (?,?,?)',
                    [(rid, json.dumps(o, ensure_ascii=False, sort_keys=True), wpis_recznej.get(rid)) for rid, o in sorted(model.get('reczne', {}).items())])
    lekkie = {r: {k: v for k, v in rek.items() if k in ('czesci', 'platnosci', 'reszta', 'zrodlo', 'kwoty', 'bs', 'plan', 'osoby',
                                                          'data_wyplaty', 'uwaga', 'ppk', 'miesiac_listy', 'komorka_bs')}
              | ({'bs_zastapione': sorted(p['bs_id'] for p in rek.get('zastapione', []) if p.get('bs_id'))}
                 if rek.get('zrodlo') == 'lista płac' else {})
              for r, rek in model.get('polaczenia', {}).items()}   # bez planów zastąpionych (te są tylko do odłączenia); lista płac:
    # ID płatności BS, które zastąpiła (odbiór 1:1 z plikiem BS pomija je jawnie)
    con.execute("INSERT OR REPLACE INTO meta VALUES ('polaczenia', ?)", (json.dumps(lekkie, ensure_ascii=False, sort_keys=True),))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('listy_plac', ?)", (json.dumps(model.get('listy', {}), ensure_ascii=False, sort_keys=True),))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('realizacja', ?)", (json.dumps(model.get('realizacja', []), ensure_ascii=False),))
    con.executemany('INSERT INTO bud_osierocone (wpis, czas, mac, op, obiekt, powod) VALUES (?,?,?,?,?,?)',
                    [(o['wpis'], o['czas'], o['mac'], o['op'], o['obiekt'], o['powod']) for o in model['osierocone']])
    con.execute("INSERT OR REPLACE INTO meta VALUES ('import_bs', ?)", (json.dumps(model['zrodlo'], ensure_ascii=False),))
    from . import biblioteka
    biblioteka.zapisz(con, model)   # pakiet 4: Biblioteka (słowniki, foldery i kategorie)
    wynik = {**ile}   # liczby budżetu z importu (albo kopii) i zmian, bez arkusza systemowego (podatki w meta „podatki”)
    if info.get('kopia'):   # pakiet 6: budżet z kopii; nowy eksport BS tylko porównujemy (okres równoległy)
        k = info['kopia']
        con.execute("INSERT OR REPLACE INTO meta VALUES ('kopia_bs', ?)", (json.dumps(
            {'wpis': k['id'], 'czas': k['czas'], 'plik': k['dane']['plik'], 'eksport': k['dane'].get('eksport', '')}, ensure_ascii=False),))
        if rozjazdy is not None:
            con.executemany('INSERT INTO bud_rozjazd (rodzaj, ref, kwota, opis) VALUES (?,?,?,?)', rozjazdy)
            wynik['rozjazdy_z_bs'] = len(rozjazdy)
    if info.get('blad'):
        wynik['blad'] = info['blad']
    if model['osierocone']:
        wynik['osierocone'] = len(model['osierocone'])
    return wynik
