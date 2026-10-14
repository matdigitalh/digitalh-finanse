"""Budżet jak w Budget Studio: folder → kategoria → arkusz → wiersz → płatność (plan albo rzeczywista).

Źródła, w kolejności nakładania:
  1. plik importu Finanse/Aplikacja/import_bs.json, generowany deterministycznie z najnowszego eksportu BS
     (Raporty/Dane/Budget Studio) i listy arkuszy ze zwiadu (Aplikacja/arkusze_bs.json); ID z BS zachowane,
  2. zdarzenia „bud” z pliku zmian (plany Mata, od 2027): dodaj/zmień/usuń arkusz, wiersz, płatność,
     akcje na wierszach; każde ma czas, Maca i stan „było”, cofnięcie przez „cofnij”.
Model żyje w tabelach bud_* odbudowywanych przy każdym starcie, jak reszta bazy.
"""
import calendar
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
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

def generuj_import(csv_path: Path, arkusze_json: Path | None) -> dict:
    """Plik importu z eksportu BS. Deterministyczny: ten sam eksport daje ten sam plik."""
    with open(csv_path, encoding='utf-8-sig', newline='') as f:
        bs = list(csv.DictReader(f, delimiter='\t'))
    zakresy = {}
    if arkusze_json and arkusze_json.exists():
        for a in json.loads(arkusze_json.read_text(encoding='utf-8'))['arkusze']:
            zakresy[(a['folder'], a['kategoria'], a['nazwa'])] = (a['od'], a['do'])
    arkusze, wiersze, platnosci = {}, {}, []
    po_wierszu = defaultdict(list)
    powtorzenia = Counter()
    for nr, x in enumerate(bs, start=2):
        if x['Rodzaj'] not in ('1', '-1'):
            continue
        folder, kategoria, nazwa = x['Folder'].strip(), x['Kategoria'].strip(), x['Arkusz'].strip()
        aid = _slug('arkusz', folder, kategoria, nazwa)
        arkusze.setdefault(aid, {'id': aid, 'folder': folder, 'kategoria': kategoria, 'nazwa': nazwa, 'miesiace': set()})
        miesiac = (_data(x['Miesiąc budżetowy']) or '')[:7]
        arkusze[aid]['miesiace'].add(miesiac)
        podstawa = _podstawa(x['Podstawa płatności'])
        klucz = (aid, x['Rodzaj'], podstawa, x['Kontrahent'].strip(), x['Komentarz w arkuszu'].strip(),
                 x['Przedmiot transakcji'].strip(), x['Sekcja'].strip())
        wid = _slug('wiersz', *klucz)
        if wid not in wiersze:
            wiersze[wid] = {'id': wid, 'arkusz': aid, 'rodzaj': int(x['Rodzaj']), 'podstawa': podstawa, 'kontrahent': klucz[3],
                            'komentarz': klucz[4], 'przedmiot': '' if klucz[5] == 'Przedmiot transakcji' else klucz[5],
                            'sekcja': '' if klucz[6] == '-' else klucz[6], 'zrodlo': 'Budget Studio'}
        rzeczywista = bool(x['Numer wewnętrzny'].strip() or x['Numer dokumentu'].strip()) or x['Etap płatności'] in ('Opłacona', 'Niewymagana')
        pid = f"bs:{x['ID']}:{wid}"
        powtorzenia[pid] += 1
        if powtorzenia[pid] > 1:   # to samo ID w tym samym wierszu (eksport z separateBudgets): kolejny numer
            pid += f":{powtorzenia[pid]}"
        p = {'id': pid, 'bs_id': x['ID'], 'wiersz': wid, 'miesiac': miesiac,
             'typ': 'rzeczywista' if rzeczywista else 'plan', 'etap_bs': x['Etap płatności'], 'aktualna': x['Status aktualności'] == 'Aktualne',
             'netto': abs(grosze(x['Netto (wartość)'])), 'brutto': abs(grosze(x['Brutto (wartość)'])), 'vat': abs(grosze(x['VAT'] or '0')),
             'stawka': x['Stawka VAT'], 'nr_dok': x['Numer dokumentu'].strip(), 'nr_wewn': x['Numer wewnętrzny'].strip(),
             'tytul': x['Tytuł'].strip(), 'wystawienie': _data(x['Dzień wystawienia']), 'termin': _data(x['Dzień płatności']),
             'realny': _data(x['Dzień płatności - realny']), 'ksiegowanie': _data(x['Miesiąc księgowania']),
             'metoda': x['Metoda płatności'].strip(), 'ksiegowane': x['Księgowane'] == 'Tak', 'w_cashflow': x['W cash flow'] == 'Tak',
             'komentarz': x['Komentarz'].strip(), 'zmodyfikowano': x['Data modyfikacji'], 'wiersz_pliku': nr}
        platnosci.append(p)
        po_wierszu[wid].append(p)
    for wid, w in wiersze.items():
        ps = po_wierszu[wid]
        w['stawka_vat'] = Counter(p['stawka'] for p in ps).most_common(1)[0][0]
        w['dzien_wystawienia'] = _dzien_wystawienia([p['wystawienie'] for p in ps])
        w['dni_na_platnosc'] = _dni_na_platnosc([(p['wystawienie'], p['termin']) for p in ps])
        w['metoda'] = Counter(p['metoda'] for p in ps).most_common(1)[0][0]
        w['ksiegowane'] = all(p['ksiegowane'] for p in ps)
        w['w_cashflow'] = all(p['w_cashflow'] for p in ps)
        w['cykl'] = 'miesiac' if len({p['miesiac'] for p in ps}) >= 3 else 'brak'
    lista_ark = []
    for a in arkusze.values():
        od, do = zakresy.get((a['folder'], a['kategoria'], a['nazwa']), (min(a['miesiace']), max(a['miesiace'])))
        lista_ark.append({'id': a['id'], 'folder': a['folder'], 'kategoria': a['kategoria'], 'nazwa': a['nazwa'], 'od': od, 'do': do,
                          'zrodlo': 'Budget Studio'})
    # arkusze ze zwiadu bez płatności (np. nowy, pusty arkusz) też istnieją
    for (folder, kategoria, nazwa), (od, do) in zakresy.items():
        aid = _slug('arkusz', folder, kategoria, nazwa)
        if aid not in arkusze:
            lista_ark.append({'id': aid, 'folder': folder, 'kategoria': kategoria, 'nazwa': nazwa, 'od': od, 'do': do, 'zrodlo': 'Budget Studio'})
    lista_ark.sort(key=lambda a: (a['folder'], a['kategoria'], a['nazwa']))
    sha = hashlib.sha256(Path(csv_path).read_bytes()).hexdigest()
    return {'zrodlo': {'plik': Path(csv_path).name, 'sha256': sha, 'wierszy': len(platnosci),
                       'najnowsza_modyfikacja': max((p['zmodyfikowano'] for p in platnosci), default='')},
            'arkusze': lista_ark, 'wiersze': sorted(wiersze.values(), key=lambda w: w['id']),
            'platnosci': sorted(platnosci, key=lambda p: p['id'])}


def plik_importu() -> Path:
    return konfig.katalog_finanse() / 'Aplikacja' / 'import_bs.json'


def odswiez_import() -> dict | None:
    """Generuje plik importu z najnowszego eksportu BS. Zapis tylko przy zmianie treści (dwa Maki, iCloud)."""
    from .importy.wspolne import pliki
    lista = pliki(konfig.katalog_dane(), 'Budget Studio/budget_studio_*.csv')
    cel = plik_importu()
    if not lista:
        return json.loads(cel.read_text(encoding='utf-8')) if cel.exists() else None
    nowy = generuj_import(lista[0], konfig.katalog_finanse() / 'Aplikacja' / 'arkusze_bs.json')
    tekst = json.dumps(nowy, ensure_ascii=False, indent=0, sort_keys=True)
    if not cel.exists() or cel.read_text(encoding='utf-8') != tekst:
        konfig.katalog_prywatny(cel.parent)
        tmp = cel.with_suffix('.tmp')
        tmp.write_text(tekst, encoding='utf-8')
        tmp.chmod(0o600)
        tmp.replace(cel)
    return nowy


# ---------- Zdarzenia Mata na budżecie (D) ----------

def zastosuj_zdarzenia(model: dict, wpisy: list[dict]) -> list[dict]:
    """Nakłada zdarzenia „bud” na model z importu. Zwraca historię (kto, kiedy, co, było, jest)."""
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    ark = {a['id']: a for a in model['arkusze']}
    wie = {w['id']: w for w in model['wiersze']}
    pla = {p['id']: p for p in model['platnosci']}
    historia = []
    for w in wpisy:
        if w.get('typ') != 'bud' or w.get('id') in cofniete:
            continue
        d = w['dane']
        op, obiekt = d['op'], d.get('obiekt', {})
        bylo = None
        if op in ('arkusz', 'wiersz', 'platnosc'):
            zbior = {'arkusz': ark, 'wiersz': wie, 'platnosc': pla}[op]
            oid = obiekt['id']
            bylo = dict(zbior[oid]) if oid in zbior else None
            if d.get('usun'):
                zbior.pop(oid, None)
                if op == 'wiersz':
                    for pid in [p for p, x in pla.items() if x['wiersz'] == oid]:
                        pla.pop(pid)
            else:
                zbior[oid] = {**(bylo or {}), **obiekt, 'zrodlo': 'apka'}
        elif op == 'przenies':
            for wid in d['wiersze']:
                if wid in wie:
                    wie[wid] = {**wie[wid], 'arkusz': d['do_arkusza']}
        elif op == 'decyzja_planu':   # po terminie: przesuń / zapłacone / anuluj (wymaganie 1)
            p = pla.get(d['platnosc'])
            if p:
                bylo = dict(p)
                if d['decyzja'] == 'przesun':
                    pla[p['id']] = {**p, 'termin': d['termin'], 'miesiac': d['termin'][:7], 'decyzja': 'przesunięte'}
                elif d['decyzja'] == 'anuluj':
                    pla[p['id']] = {**p, 'aktualna': False, 'decyzja': 'anulowane'}
                elif d['decyzja'] == 'zaplacone':
                    pla[p['id']] = {**p, 'decyzja': 'zapłacone (Mat)', 'realny': d.get('data')}
        historia.append({'wpis': w['id'], 'czas': w['czas'], 'mac': w.get('mac', ''), 'op': op,
                         'obiekt': d.get('obiekt', {}).get('id') or d.get('platnosc') or ','.join(d.get('wiersze', [])),
                         'bylo': bylo, 'jest': (ark | wie | pla).get(d.get('obiekt', {}).get('id') or d.get('platnosc') or '')})
    model['arkusze'], model['wiersze'], model['platnosci'] = list(ark.values()), list(wie.values()), list(pla.values())
    return historia


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
                    vat = round(netto * float(plan.get('stawka_vat') or 0) / 100)
                    model['platnosci'].append({'id': f"plan:{w['id']}:{m}:{czesc.get('nazwa', '')}", 'wiersz': w['id'], 'miesiac': m,
                                               'typ': 'plan', 'etap_bs': 'Planowana', 'aktualna': True, 'netto': netto, 'vat': vat,
                                               'brutto': netto + vat, 'wystawienie': wyst, 'termin': termin, 'tytul': czesc.get('nazwa') or w.get('komentarz', ''),
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
        con.execute('INSERT INTO bud_platnosc (id, bs_id, wiersz, miesiac, typ, etap_bs, aktualna, netto, vat, brutto, rodzaj, nr_dok, nr_wewn,'
                    ' tytul, wystawienie, termin, realny, ksiegowanie, metoda, w_cashflow, komentarz, decyzja, zrodlo, wiersz_pliku)'
                    ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (p['id'], p.get('bs_id'), p['wiersz'], p['miesiac'], p['typ'], p.get('etap_bs', ''), int(bool(p.get('aktualna', True))),
                     p['netto'], p.get('vat', 0), p.get('brutto', p['netto']), znak[p['wiersz']], p.get('nr_dok', ''), p.get('nr_wewn', ''),
                     p.get('tytul', ''), p.get('wystawienie'), p.get('termin'), p.get('realny'), p.get('ksiegowanie'), p.get('metoda', ''),
                     int(bool(p.get('w_cashflow', True))), p.get('komentarz', ''), p.get('decyzja', ''), p.get('zrodlo', 'Budget Studio'),
                     p.get('wiersz_pliku')))
    con.executemany('INSERT INTO bud_historia (wpis, czas, mac, op, obiekt, bylo, jest) VALUES (?,?,?,?,?,?,?)',
                    [(h['wpis'], h['czas'], h['mac'], h['op'], h['obiekt'], json.dumps(h['bylo'], ensure_ascii=False),
                      json.dumps(h['jest'], ensure_ascii=False)) for h in historia])
    con.execute("INSERT OR REPLACE INTO meta VALUES ('import_bs', ?)", (json.dumps(model['zrodlo'], ensure_ascii=False),))
    return {'arkuszy': len(model['arkusze']), 'wierszy': len(model['wiersze']), 'platnosci': len(model['platnosci'])}
