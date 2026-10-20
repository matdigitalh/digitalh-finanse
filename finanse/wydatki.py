"""Analiza wydatków: kategoria (drugi poziom pod rodzajem), cel wydatku per kontrahent, koszty stałe (cykliczne).

Rodzaj wydatku (klienci.py) zostaje bez zmian: od niego zależy wynik zarządczy, rezerwa i cash flow. Kategoria to drugi poziom,
tylko do analizy „na co ile wydajemy”. Liczona przy każdej odbudowie, z polem źródła, w kolejności (pierwsze wygrywa):
  1. decyzja Mata dla płatności (wpis „kategoria_operacja”),
  2. reguła Mata dla kontrahenta (wpis „kategoria_regula”),
  3. reguły wbudowane (REGULY_NAZW i kolejność w kategoria_wbudowana),
  4. kategoria domyślna dla rodzaju (Inne albo Nieprzypisane).
Kategoria niezgodna z rodzajem (np. Narzędzia przy rodzaju „koszty pracy”) nie poprawia rodzaju: ekran pokazuje ją w „Do decyzji”.

Kontrahent w analizie to `kontrahent_grupa`: klucz kontrahenta z klienci.py, poza płatnościami kartą z losowym kodem w nazwie
(FACEBK *W9NGQGHVA2, IPR* VXTGK, Microsoft-G1860…), które klucz z klienci.py rozbija na osobne „kontrahenty”.
Kwoty z banku są brutto (grosze, dodatnie = wydatek)."""
import json
import re
from collections import Counter, defaultdict
from datetime import date

from .format import norm

KATEGORIE = (
    ('pensje', 'Pensje (etat, powołanie)'),
    ('wspolpracownicy', 'Współpracownicy (B2B, dzieło)'),
    ('zus', 'ZUS'),
    ('pit4', 'PIT-4 od pensji'),
    ('ppk', 'PPK'),
    ('benefity', 'Benefity'),
    ('vat', 'Podatki: VAT'),
    ('cit', 'Podatki: CIT i opłaty'),
    ('ksiegowosc', 'Księgowość i prawne'),
    ('narzedzia', 'Narzędzia i subskrypcje'),
    ('reklama', 'Reklama własna DigitalH'),
    ('sprzet', 'Sprzęt i wyposażenie'),
    ('podroze', 'Podróże i dojazdy'),
    ('reprezentacja', 'Reprezentacja i gastronomia'),
    ('rekrutacja', 'Rekrutacja'),
    ('klienci_media', 'Koszty klientów: media'),
    ('klienci_druk', 'Koszty klientów: druk i produkcja'),
    ('klienci_podwykonawcy', 'Koszty klientów: podwykonawcy'),
    ('podzial_zysku', 'Podział zysku'),
    ('zwroty', 'Zwroty'),
    ('inne', 'Inne'),
    ('nieprzypisane', 'Nieprzypisane'),
)
NAZWY = dict(KATEGORIE)
KOSZT_PRACY = ('pensje', 'wspolpracownicy', 'zus', 'pit4', 'ppk', 'benefity')
PODATKI = ('vat', 'cit')
KLIENCI = ('klienci_media', 'klienci_druk', 'klienci_podwykonawcy')
# Rodzaje, z którymi kategoria jest zgodna. Brak klucza = zgodna z każdym rodzajem (Inne, Nieprzypisane).
ZGODNE = {
    'pensje': {'praca'}, 'wspolpracownicy': {'praca'}, 'zus': {'praca'}, 'pit4': {'praca'}, 'ppk': {'praca'}, 'benefity': {'praca', 'staly'},
    'vat': {'vat'}, 'cit': {'podatki'},
    'ksiegowosc': {'staly'}, 'narzedzia': {'staly'}, 'reklama': {'staly'}, 'sprzet': {'staly'},
    'podroze': {'staly', 'praca'}, 'reprezentacja': {'staly', 'praca'}, 'rekrutacja': {'staly', 'praca'},
    'klienci_media': {'przenoszony'}, 'klienci_druk': {'przenoszony'}, 'klienci_podwykonawcy': {'przenoszony'},
    'podzial_zysku': {'dywidenda'}, 'zwroty': {'zwrot', 'zwrocony'},
}
OBSZARY_DOMYSLNE = ('Działalność spółki', 'New Business', 'Realizacja dla klientów', 'Zespół', 'Rozwój')
OCENY = {'zasadny': 'zasadny', 'do_sprawdzenia': 'do sprawdzenia', 'do_wypowiedzenia': 'do wypowiedzenia'}
POLA_CELU = ('obszar', 'kto', 'uzasadnienie', 'ocena', 'staly', 'roczna')
POZA_STALYMI = {'vat', 'dywidenda', 'zwrot', 'zwrocony', 'przenoszony'}   # rodzaje, które nie są kosztem stałym
# Kategorie nieregularne z natury: nie wykrywamy ich jako kosztu stałego (zwroty za wyjazdy, przejazdy, kolacje, zakupy sprzętu).
# Mat może oznaczyć kontrahenta jako stałego ręcznie.
POZA_STALYMI_KAT = {'podroze', 'reprezentacja', 'sprzet', 'zwroty', 'podzial_zysku', 'vat', 'klienci_media', 'klienci_druk',
                    'klienci_podwykonawcy'}
PROG_ROCZNEJ = 30000   # grosze: pojedyncza płatność narzędzia od 300 zł bez płatności w innych miesiącach = opłata roczna

# ---------- reguły wbudowane (jedno miejsce; wzorce na nazwie po norm(): małe litery, bez polskich znaków i interpunkcji) ----------

_ZUS = re.compile(r'^zus\b|zaklad ubezpieczen')
_US = re.compile(r'urzad skarbowy')
_PPK = re.compile(r'emerytur|\bppk\b')
_REKLAMA = re.compile(r'^facebk\b|google ads|^google ads|\bads\d{10}\b|^ads\d|tiktok ads|meta platforms')
_DRUK = re.compile(r'drukomat|\bdruk|print|naklej|digicolor|poligraf|gadzet|gifts?\b|promotion|plotter|banner|\bdpd\b|inpost|poczta polska')
_WYJAZD = re.compile(r'wyjazd|delegac|podroz sluzb')
_BENEFIT_TYTUL = re.compile(r'medycyny pracy|pakiet medyczny|multisport')
_FIRMA = re.compile(r'\b(sp z o ?o|spolka|s a|sa|sp k|s c|ltd|inc|gmbh|llc|bv|kancelaria|urzad|bank)\b')
# (kategoria, wzorzec nazwy kontrahenta). Kolejność ma znaczenie: pierwszy pasujący wygrywa.
REGULY_NAZW = (
    ('ksiegowosc', r'brixen|kancelaria|radc[ay] prawn|notariu|adwokat|\bsad rejonowy|\bsad okregowy|komornik'),
    ('benefity', r'mediccentre|medicover|luxmed|lux med|multisport|medycyna pracy'),
    ('rekrutacja', r'just join|justjoin|pracuj pl|no fluff|nofluff|rocketjobs|olx praca'),
    ('narzedzia', r'google workspace|google cloud|cloud google|google.*\bcloud\b|figma|budget studio|adobe|clickup|linkedin|'
                  r'cyber folks|cyberfolks|nazwa pl|\binstantly\b|anthropic|claude|openai|chatgpt|trello|atlassian|wispr|apify|canva|'
                  r'hubspot|clickmeeting|jitter|\bklap\b|envato|microsoft|planable|capcut|artlist|elevenlabs|iproyal|^ipr\b|lastpass|'
                  r'\bmake com\b|fakturownia|\baz pl\b|imagify|addcal|linktree|brand24|\bwix\b|vercom|linkedhelper|notion|zapier|'
                  r'dropbox|slack|zoom us|calendly|semrush|ahrefs|t mobile|polkomtel|\bplus pl\b|orange polska|\bplay\b'),
    ('podroze', r'^bolt\b|\buber\b|^ubr\b|bilet|intercity|\bpkp\b|koleje|hotel|booking com|airbnb|\borlen\b|\bshell\b|circle k|'
                r'\bbp\b|parking|skycash|jakdojade|flixbus|ryanair|wizz|\blot\b|plaza recepcja|recepcja'),
    ('reprezentacja', r'restaur|ristorante|trattoria|pizz|bistro|\bcaf+e\b|coffee|costa coffee|starbucks|\bsbx\b|mcdonald|\bkfc\b|'
                      r'burger|^bk mop|sushi|kebab|pyszne|glovo|wolt|uber eats|kuchnia|kredens|piekarni|cukierni|\bbar\b|grill'),
    ('sprzet', r'allegro|media ?expert|x kom|morele|euro rtv|ikea|leroy merlin|castorama|bricomarche|obi\b|empik|'
               r'paperconcept|moleskine|apple com|apple store|supersound|komputronik'),
)
_REGULY = tuple((k, re.compile(w)) for k, w in REGULY_NAZW)
# Płatności kartą z losowym kodem w nazwie: jeden kontrahent w analizie (prefiks nazwy po norm() → klucz grupy).
GRUPY_KART = (('facebk', 'facebk'), ('ipr ', 'iproyal'), ('iproyal', 'iproyal'), ('microsoft', 'microsoft'), ('bolt', 'bolt'),
              ('uber', 'uber'), ('ubr ', 'uber'), ('openai', 'openai'), ('anthropic', 'anthropic'), ('claude ai', 'anthropic'),
              ('linkedinprec', 'linkedin premium'), ('zaklad ubezpieczen', 'zus'))


def klucz_grupy(nazwa: str, kk: str) -> str:
    n = norm(nazwa)
    for prefiks, grupa in GRUPY_KART:
        if n.startswith(prefiks):
            return grupa
    if kk:
        return kk
    return ' '.join(re.sub(r'\d+', '', n).split()[:2]) or '(bez nazwy)'


def _osoba(n: str) -> bool:
    """Nazwa wygląda na osobę fizyczną (brak formy prawnej i słów firmowych)."""
    return bool(n) and not _FIRMA.search(n)


def kategoria_wbudowana(o: dict, osoby: set = frozenset()) -> tuple[str, str]:
    """(kategoria, opis reguły). o: rodzaj, kontrahent, tytul, opis, konto, karta (bool), kk (klucz kontrahenta)."""
    rodzaj = o.get('rodzaj') or 'nieprzypisany'
    nazwa = norm(o.get('kontrahent') or o.get('opis') or '')
    tytul = norm(f"{o.get('tytul') or ''} {o.get('opis') or ''}")
    if rodzaj == 'vat':
        return 'vat', 'rodzaj VAT'
    if rodzaj == 'dywidenda':
        return 'podzial_zysku', 'rodzaj podział zysku'
    if rodzaj in ('zwrot', 'zwrocony'):
        return 'zwroty', 'rodzaj zwrot'
    if _ZUS.search(nazwa):
        return 'zus', 'kontrahent ZUS'
    if _PPK.search(nazwa):
        return 'ppk', 'fundusz PPK'
    if _US.search(nazwa):
        if rodzaj == 'praca' or re.search(r'\bpit ?4', tytul):
            return 'pit4', 'urząd skarbowy przy kosztach pracy'
        return 'cit', 'urząd skarbowy'
    konto = o.get('konto') or ''
    if _REKLAMA.search(nazwa) or konto:
        if rodzaj == 'przenoszony':
            return 'klienci_media', 'konto reklamowe, koszt klienta'
        if konto and 'digitalh' not in konto.lower() and rodzaj == 'nieprzypisany':
            return 'klienci_media', f'konto reklamowe {konto}'
        return 'reklama', 'reklama bez klienta'
    if rodzaj == 'przenoszony':
        if _DRUK.search(nazwa) or _DRUK.search(tytul):
            return 'klienci_druk', 'koszt klienta: druk, gadżety, wysyłka'
        return 'klienci_podwykonawcy', 'koszt klienta'
    if _WYJAZD.search(tytul):
        return 'podroze', 'zwrot za wyjazd służbowy'
    if _BENEFIT_TYTUL.search(tytul):
        return 'benefity', 'tytuł: medycyna pracy, pakiet'
    for kat, wz in _REGULY:
        if wz.search(nazwa):
            return kat, f'nazwa kontrahenta ({NAZWY[kat].lower()})'
    if rodzaj == 'praca' and not o.get('karta'):
        if 'wynagrodz' in tytul or (o.get('kk') and o['kk'] in osoby):
            return 'pensje', 'wynagrodzenie z listy płac'
        if _osoba(nazwa):
            return 'wspolpracownicy', 'przelew do osoby bez listy płac (faktura, umowa o dzieło)'
    if rodzaj == 'podatki':
        return 'cit', 'rodzaj podatki'
    if rodzaj == 'nieprzypisany':
        return 'nieprzypisane', 'brak reguły i rodzaju'
    return 'inne', 'brak reguły'


def zgodna(kategoria: str, rodzaj: str) -> bool:
    z = ZGODNE.get(kategoria)
    return z is None or rodzaj in z


# ---------- wpisy Mata (odczyt w klienci.wczytaj_reczne) ----------

def sprawdz_kategorie(typ: str, d: dict) -> dict:
    """Wpis „kategoria_regula” (kontrahent, kategoria) albo „kategoria_operacja” (operacja, kategoria)."""
    pole = 'kontrahent' if typ == 'kategoria_regula' else 'operacja'
    if not isinstance(d, dict) or set(d) - {pole, 'kategoria'}:
        raise ValueError('kategoria wydatku: nieznane pole')
    v = d.get(pole)
    if not isinstance(v, str) or not v.strip() or len(v) > 300:
        raise ValueError(f'kategoria wydatku: brak pola {pole}')
    if d.get('kategoria') not in NAZWY:
        raise ValueError('kategoria wydatku: nieznana kategoria')
    return {pole: v.strip() if pole == 'kontrahent' else v, 'kategoria': d['kategoria']}


def sprawdz_cel(d: dict) -> dict:
    """Wpis „cel_wydatku”: kontrahent plus tylko zmieniane pola (obszar, kto, uzasadnienie, ocena, stały). Kolejne wpisy
    nakładają się po czasie; cofnięcie przywraca stan sprzed wpisu. Pusty tekst = wyczyść pole; stały null = wykrywanie auto."""
    if not isinstance(d, dict) or set(d) - {'kontrahent', *POLA_CELU}:
        raise ValueError('cel wydatku: nieznane pole')
    k = d.get('kontrahent')
    if not isinstance(k, str) or not k.strip() or len(k) > 300:
        raise ValueError('cel wydatku: brak kontrahenta')
    wynik = {'kontrahent': k.strip()}
    for pole, maks in (('obszar', 60), ('kto', 80), ('uzasadnienie', 500)):
        if pole in d:
            v = d[pole]
            if v is not None and not isinstance(v, str):
                raise ValueError(f'cel wydatku: {pole} jako tekst')
            v = (v or '').strip()
            if len(v) > maks:
                raise ValueError(f'cel wydatku: {pole} najwyżej {maks} znaków')
            wynik[pole] = v
    if 'ocena' in d:
        if d['ocena'] not in ('', None, *OCENY):
            raise ValueError('cel wydatku: ocena zasadny, do sprawdzenia albo do wypowiedzenia')
        wynik['ocena'] = d['ocena'] or ''
    if 'staly' in d:
        if d['staly'] not in (True, False, None):
            raise ValueError('cel wydatku: koszt stały tak, nie albo automatycznie')
        wynik['staly'] = d['staly']
    if 'roczna' in d:
        if d['roczna'] not in (True, False, None):
            raise ValueError('cel wydatku: opłata roczna tak, nie albo automatycznie')
        wynik['roczna'] = d['roczna']
    if len(wynik) == 1:
        raise ValueError('cel wydatku: brak zmian')
    return wynik


def sprawdz_obszary(v) -> list:
    if not isinstance(v, list) or len(v) > 30 or not all(isinstance(x, str) and 0 < len(x.strip()) <= 60 for x in v):
        raise ValueError('obszary wydatków: lista nazw (najwyżej 30, do 60 znaków)')
    return list(dict.fromkeys(x.strip() for x in v))


def wczytaj(wpisy, cofniete) -> dict:
    """Decyzje Mata z pliku zmian: kategorie (płatność, kontrahent), cele per kontrahent, dodatkowe obszary."""
    r = {'kat_regula': {}, 'kat_operacja': {}, 'cel': {}, 'obszary': None}
    for w in wpisy:
        if w.get('id') in cofniete:
            continue
        typ, d = w.get('typ'), w.get('dane') or {}
        if typ == 'kategoria_regula':
            r['kat_regula'][d['kontrahent']] = (d['kategoria'], w.get('id', ''))
        elif typ == 'kategoria_operacja':
            r['kat_operacja'][d['operacja']] = (d['kategoria'], w.get('id', ''))
        elif typ == 'cel_wydatku':
            c = r['cel'].setdefault(d['kontrahent'], {})
            c.update({p: d[p] for p in POLA_CELU if p in d})
            if 'ocena' in d:
                c['data_oceny'] = (w.get('czas') or '')[:10]
            c['data_wpisu'] = (w.get('czas') or '')[:10]
            c['wpis'] = w.get('id', '')
        elif typ == 'ustawienie' and d.get('klucz') == 'obszary_wydatkow':
            r['obszary'] = d.get('wartosc')
    return r


def obszary(con=None) -> list:
    """Lista obszarów: domyślne, plus klucz „obszary_wydatkow” w ustawienia.json, plus wpis „ustawienie” z apki."""
    from .wynik import ustawienia
    lista = list(OBSZARY_DOMYSLNE)
    z_pliku = ustawienia().get('obszary_wydatkow')
    if isinstance(z_pliku, list):
        lista += [str(x) for x in z_pliku]
    if con is not None:
        r = con.execute("SELECT wartosc FROM meta WHERE klucz = 'obszary_wydatkow'").fetchone()
        if r and r[0]:
            lista += json.loads(r[0])
    return list(dict.fromkeys(x for x in lista if x))


# ---------- przypisanie przy odbudowie (woła klienci.policz) ----------

def _osoby_z_listy_plac(con) -> set:
    from .klienci import klucz_kontrahenta
    wynik = set()
    for r in con.execute("SELECT DISTINCT kontrahent FROM bud_wiersz WHERE podstawa LIKE 'Umowa%' OR lista_plac = 1"):
        if r[0]:
            wynik.add(klucz_kontrahenta(r[0]))
    return wynik


def przypisz(con, reczne: dict):
    w = reczne['wydatki']
    try:
        osoby = _osoby_z_listy_plac(con)
    except Exception:   # budżet liczy się później; przy pierwszym przebiegu tabela jest pusta
        osoby = set()
    zmiany = []
    for o in con.execute('SELECT o.id, o.klucz, o.kontrahent, o.tytul, o.opis, x.rodzaj, x.kontrahent_klucz, x.konto FROM wydatki x'
                         ' JOIN operacje o ON o.id = x.operacja_id'):
        o = dict(o)
        o['kk'] = o['kontrahent_klucz']
        o['karta'] = 'kart' in f"{o['tytul'] or ''} {o['opis'] or ''}".lower()
        grupa = klucz_grupy(o['kontrahent'] or o['opis'], o['kk'])
        if o['klucz'] in w['kat_operacja']:
            kat, wpis = w['kat_operacja'][o['klucz']]
            zrodlo = 'decyzja Mata (ta płatność)'
        elif grupa in w['kat_regula']:
            kat, wpis = w['kat_regula'][grupa]
            zrodlo = 'reguła Mata (kontrahent)'
        else:
            kat, opis = kategoria_wbudowana(o, osoby)
            wpis = ''
            zrodlo = f'reguła wbudowana: {opis}'
        zmiany.append((kat, zrodlo, wpis, grupa, o['id']))
    con.executemany('UPDATE wydatki SET kategoria = ?, kategoria_zrodlo = ?, kategoria_wpis = ?, kontrahent_grupa = ? WHERE operacja_id = ?',
                    zmiany)
    con.executemany('INSERT INTO wydatki_cel (kontrahent, obszar, kto, uzasadnienie, ocena, data_oceny, staly, roczna, wpis)'
                    ' VALUES (?,?,?,?,?,?,?,?,?)',
                    [(k, c.get('obszar', ''), c.get('kto', ''), c.get('uzasadnienie', ''), c.get('ocena', ''), c.get('data_oceny', ''),
                      None if c.get('staly') is None else int(c['staly']), None if c.get('roczna') is None else int(c['roczna']),
                      c.get('wpis', '')) for k, c in w['cel'].items()])
    if w['obszary'] is not None:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('obszary_wydatkow', ?)", (json.dumps(w['obszary'], ensure_ascii=False),))


# ---------- odczyty ekranu ----------

def _dzien_stanu(con) -> str:
    r = con.execute("SELECT wartosc FROM meta WHERE klucz = 'dzien_stanu'").fetchone()
    return (r[0] if r and r[0] else '') or date.today().isoformat()


def _ostatni_dzien(m: str) -> str:
    r, mm = int(m[:4]), int(m[5:7])
    nast = date(r + mm // 12, mm % 12 + 1, 1)
    return date.fromordinal(nast.toordinal() - 1).isoformat()


def _miesiace(od: str, do: str) -> list:
    wynik, r, m = [], int(od[:4]), int(od[5:7])
    while f'{r:04d}-{m:02d}' <= do[:7]:
        wynik.append(f'{r:04d}-{m:02d}')
        r, m = (r + 1, 1) if m == 12 else (r, m + 1)
    return wynik


def _przesun(m: str, o: int) -> str:
    i = int(m[:4]) * 12 + int(m[5:7]) - 1 + o
    return f'{i // 12:04d}-{i % 12 + 1:02d}'


def _platnosci(con, od=None, do=None, grupa=None) -> list:
    warunki, par = [], []
    if od:
        warunki.append('o.data_ksiegowania >= ?'); par.append(od)
    if do:
        warunki.append('o.data_ksiegowania <= ?'); par.append(do)
    if grupa is not None:
        warunki.append('w.kontrahent_grupa = ?'); par.append(grupa)
    sql = ('SELECT o.id, o.klucz, o.data_ksiegowania AS data, -o.kwota AS kwota, o.kontrahent, o.tytul, o.opis, o.rachunek, o.kwota_oryg,'
           ' o.waluta_oryg, o.plik, o.wiersz, w.rodzaj, w.klient, w.zrodlo, w.dokument, w.netto_dok, w.konto, w.kategoria,'
           ' w.kategoria_zrodlo, w.kategoria_wpis, w.kontrahent_grupa AS grupa, w.kontrahent_klucz'
           ' FROM wydatki w JOIN operacje o ON o.id = w.operacja_id' + (' WHERE ' + ' AND '.join(warunki) if warunki else '')
           + ' ORDER BY o.data_ksiegowania, o.id')
    return [dict(r) for r in con.execute(sql, par)]


def _cele(con) -> dict:
    return {r['kontrahent']: dict(r) for r in con.execute('SELECT * FROM wydatki_cel')}


def _nazwa_grupy(platnosci) -> str:
    c = Counter((p['kontrahent'] or p['opis'] or '').strip() for p in platnosci)
    n = c.most_common(1)[0][0] if c else ''
    return re.sub(r'\s{2,}.*$', '', n)[:60] or '(bez nazwy)'


def okres(con, od=None, do=None) -> dict:
    dzien = _dzien_stanu(con)
    od = od if od and re.fullmatch(r'\d{4}-\d{2}-\d{2}', od) else f'{dzien[:4]}-01-01'
    do = do if do and re.fullmatch(r'\d{4}-\d{2}-\d{2}', do) else dzien
    if do > dzien:
        do = dzien
    if od > do:
        od = do[:8] + '01'
    miesiace = _miesiace(od, do)
    niepelne = [m for m in miesiace if (m == od[:7] and od[8:] != '01') or (m == do[:7] and do != _ostatni_dzien(m))]
    return {'od': od, 'do': do, 'dzien_stanu': dzien, 'miesiace': miesiace, 'niepelne': niepelne,
            'pelne': [m for m in miesiace if m not in niepelne]}


def _srednia(miesiace: dict, pelne: list):
    return (sum(miesiace.get(m, 0) for m in pelne) + len(pelne) // 2) // len(pelne) if pelne else None


def analiza(con, od=None, do=None) -> dict:
    """Ekran Wydatki: kafle, kategorie z kontrahentami, miesiące (do wykresu), liczba spraw do decyzji."""
    ok = okres(con, od, do)
    pl = _platnosci(con, ok['od'], ok['do'])
    razem = sum(p['kwota'] for p in pl)
    kat = {k: {'klucz': k, 'nazwa': n, 'suma': 0, 'ile': 0, 'miesiace': defaultdict(int), 'kontr': defaultdict(list)} for k, n in KATEGORIE}
    for p in pl:
        x = kat[p['kategoria'] if p['kategoria'] in kat else 'nieprzypisane']
        x['suma'] += p['kwota']
        x['ile'] += 1
        x['miesiace'][p['data'][:7]] += p['kwota']
        x['kontr'][p['grupa']].append(p)
    kategorie = []
    for k, _ in KATEGORIE:
        x = kat[k]
        if not x['ile']:
            continue
        kontrahenci = sorted(({'klucz': g, 'nazwa': _nazwa_grupy(ps), 'suma': sum(p['kwota'] for p in ps), 'ile': len(ps),
                               'ostatnia': ps[-1]['data'], 'ostrzezenie': any(not zgodna(p['kategoria'], p['rodzaj']) for p in ps)}
                              for g, ps in x['kontr'].items()), key=lambda y: -y['suma'])
        kategorie.append({'klucz': k, 'nazwa': x['nazwa'], 'suma': x['suma'], 'ile': x['ile'], 'miesiace': dict(x['miesiace']),
                          'srednia': _srednia(x['miesiace'], ok['pelne']),
                          'udzial': round(100 * x['suma'] / razem, 1) if razem else None, 'kontrahenci': kontrahenci})
    po_kat = {x['klucz']: x for x in kategorie}
    suma = lambda klucze: sum(po_kat[k]['suma'] for k in klucze if k in po_kat)
    stale = koszty_stale(con)
    kafle = {
        'koszt_pracy': {'suma': suma(KOSZT_PRACY), 'srednia': _srednia(_sumuj_mies(kategorie, KOSZT_PRACY), ok['pelne']),
                        'rozbicie': [{'klucz': k, 'nazwa': NAZWY[k], 'suma': suma([k])} for k in KOSZT_PRACY]},
        'podatki': {'suma': suma(PODATKI), 'rozbicie': [{'klucz': k, 'nazwa': NAZWY[k], 'suma': suma([k])} for k in PODATKI],
                    'w_koszcie_pracy': [{'klucz': k, 'nazwa': NAZWY[k], 'suma': suma([k])} for k in ('zus', 'pit4')]},
        'narzedzia': _narzedzia_mies(con, pl, ok),
        'stale': {'miesiecznie': stale['razem']['miesiecznie'], 'rocznie': stale['razem']['rocznie'], 'ile': len(stale['pozycje'])},
    }
    dd = do_decyzji(con, ok['od'], ok['do'])
    return {**ok, 'razem': razem, 'ile': len(pl), 'kategorie': kategorie, 'kafle': kafle,
            'bez_klientow_vat': razem - suma(KLIENCI + ('vat',)),
            'do_decyzji': len(dd['nieprzypisane']) + len(dd['niezgodne']),
            'lista_kategorii': [{'klucz': k, 'nazwa': n} for k, n in KATEGORIE]}


def _narzedzia_mies(con, pl, ok) -> dict:
    """Narzędzia miesięcznie: płatności bieżące = suma z pełnych miesięcy okresu podzielona przez ich liczbę; opłaty roczne
    (wydatki._roczne) zapłacone w okresie liczone jako 1/12 kwoty, niezależnie od miesiąca zapłaty. Ten sam podział co w kosztach stałych."""
    roczne = _roczne(con, _dzien_stanu(con))
    biezace = sum(p['kwota'] for p in pl if p['kategoria'] == 'narzedzia' and p['grupa'] not in roczne and p['data'][:7] in ok['pelne'])
    rocz = [p for p in pl if p['kategoria'] == 'narzedzia' and p['grupa'] in roczne]
    suma_roczne = sum(p['kwota'] for p in rocz)
    n = len(ok['pelne'])
    sr_biez = (biezace + n // 2) // n if n else None
    return {'srednia': None if sr_biez is None else sr_biez + (suma_roczne + 6) // 12, 'biezace_mies': sr_biez,
            'roczne': suma_roczne, 'roczne_mies': (suma_roczne + 6) // 12, 'roczne_ile': len(rocz),
            'suma': sum(p['kwota'] for p in pl if p['kategoria'] == 'narzedzia'), 'miesiecy': n,
            'od_miesiaca': ok['pelne'][0] if n else None, 'do_miesiaca': ok['pelne'][-1] if n else None}


def _sumuj_mies(kategorie, klucze) -> dict:
    m = defaultdict(int)
    for x in kategorie:
        if x['klucz'] in klucze:
            for k, v in x['miesiace'].items():
                m[k] += v
    return m


def okno_stalych(dzien: str) -> list:
    """4 ostatnie pełne miesiące przed dniem stanu (miesiąc stanu pełny tylko, gdy dzień stanu to jego ostatni dzień)."""
    m = dzien[:7]
    ost = m if dzien == _ostatni_dzien(m) else _przesun(m, -1)
    return [_przesun(ost, -i) for i in (3, 2, 1, 0)]


def _roczne(con, dzien: str, cele: dict | None = None) -> dict:
    """Opłaty roczne: grupa -> płatność. Ręcznie (cel „roczna” tak/nie) albo automatycznie: narzędzie z jedną płatnością
    w ostatnich 12 miesiącach, co najmniej PROG_ROCZNEJ, a w pozostałych miesiącach nic; albo ta sama kwota (±10%) rok wcześniej."""
    cele = _cele(con) if cele is None else cele
    od12 = _przesun(dzien[:7], -11)
    grupy = defaultdict(list)
    for p in _platnosci(con, do=dzien):
        if p['rodzaj'] not in POZA_STALYMI:
            grupy[p['grupa']].append(p)
    wynik = {}
    for g, ps in grupy.items():
        recznie = cele.get(g, {}).get('roczna')
        ostatnie = [p for p in ps if p['data'][:7] >= od12]
        if recznie is not None:
            if recznie and ostatnie:
                wynik[g] = max(ostatnie, key=lambda p: p['kwota'])
            continue
        if not ostatnie:
            continue
        p = ostatnie[-1]
        jedna = len({x['data'][:7] for x in ostatnie}) == 1 and len(ostatnie) == 1
        if jedna and p['kategoria'] == 'narzedzia' and p['kwota'] >= PROG_ROCZNEJ:
            wynik[g] = p
            continue
        if jedna:   # ta sama kwota ±10% 11 do 13 miesięcy wcześniej
            for q in ps:
                if _przesun(p['data'][:7], -13) <= q['data'][:7] <= _przesun(p['data'][:7], -11) and abs(q['kwota'] - p['kwota']) * 10 <= p['kwota']:
                    wynik[g] = p
    return wynik


def _dzien_cyklu(ps) -> int | None:
    dni = sorted(int(p['data'][8:10]) for p in ps)
    return dni[len(dni) // 2] if dni else None


def koszty_stale(con) -> dict:
    """Koszty stałe (cykliczne), decyzja Mata 2026-10-20 po kontroli liczb:
    - wykrycie: kontrahent × kategoria z płatnością w co najmniej 3 z 4 ostatnich pełnych miesięcy, bez VAT, podziału zysku,
      zwrotów i kosztów klientów oraz bez kategorii nieregularnych z natury (podróże, reprezentacja, sprzęt);
    - aktywny tylko z płatnością w ostatnim pełnym miesiącu albo w bieżącym; pozostali to „wygasłe” (data ostatniej płatności);
    - koszt miesięczny = suma z ostatniego pełnego miesiąca (gdy wtedy nic, z bieżącego), roczny = × 12;
    - opłata roczna (_roczne): miesięcznie 1/12 kwoty;
    - ostatnia płatność = data ostatniej i suma jej miesiąca (wszystkie karty i zapisy kontrahenta w tej kategorii);
    - flagi: zmiana kwoty ponad 50% (miesiąc z płatnością kontra poprzedni) i płatność poza zwykłym dniem cyklu (ponad 3 dni).
    Decyzja Mata (stały tak/nie, roczna tak/nie) wygrywa z wykrywaniem."""
    dzien = _dzien_stanu(con)
    okno = okno_stalych(dzien)
    ost_pelny, biezacy = okno[-1], dzien[:7]
    cele = _cele(con)
    roczne = _roczne(con, dzien, cele)
    grupy = defaultdict(list)
    for p in _platnosci(con, do=dzien):
        if p['rodzaj'] not in POZA_STALYMI and p['kategoria'] not in POZA_STALYMI_KAT:
            grupy[(p['grupa'], p['kategoria'])].append(p)
    pozycje, wygasle = [], []
    ile_kat = Counter(g for g, _ in grupy)
    for (g, kat), ps in grupy.items():
        cel = cele.get(g, {})
        staly = cel.get('staly')
        mies = defaultdict(int)
        ile_mies = Counter()
        for p in ps:
            mies[p['data'][:7]] += p['kwota']
            ile_mies[p['data'][:7]] += 1
        w_oknie = [m for m in okno if mies.get(m)]
        roczna = roczne.get(g)
        if roczna is not None and roczna['kategoria'] != kat:
            roczna = None
        auto = len(w_oknie) >= 3 or roczna is not None
        if not (auto if staly is None else bool(staly)):
            continue
        ost = ps[-1]
        m_ost = ost['data'][:7]
        wspolne = {'klucz': g if ile_kat[g] == 1 else f'{g}|{kat}', 'kontrahent': g,
                   'nazwa': _nazwa_grupy(ps), 'kategoria': kat, 'kategoria_nazwa': NAZWY.get(kat, kat),
                   'ostatnia_data': ost['data'], 'ostatnia_kwota': mies[m_ost], 'ostatnia_ile': ile_mies[m_ost],
                   'obszar': cel.get('obszar') or '', 'kto': cel.get('kto') or '', 'uzasadnienie': cel.get('uzasadnienie') or '',
                   'ocena': cel.get('ocena') or '', 'data_oceny': cel.get('data_oceny') or '',
                   'staly_decyzja': None if staly is None else bool(staly), 'roczna_decyzja': cel.get('roczna')}
        if roczna is not None:
            pozycje.append({**wspolne, 'miesiecznie': (roczna['kwota'] + 6) // 12, 'rocznie': roczna['kwota'], 'roczna': True,
                            'sposob': 'opłata roczna, 1/12' + (' (decyzja Mata)' if cel.get('roczna') else ''),
                            'zmiana_ceny': None, 'flagi': [], 'miesiace_w_oknie': len(w_oknie)})
            continue
        if not (mies.get(ost_pelny) or mies.get(biezacy)):
            wygasle.append({**wspolne, 'ostatni_koszt_mies': mies[m_ost],
                            'powod': f'brak płatności w {ost_pelny} i {biezacy}' if ost_pelny != biezacy else f'brak płatności w {ost_pelny}'})
            continue
        miesiecznie = mies[ost_pelny] if mies.get(ost_pelny) else mies[biezacy]
        sposob = f"{len(w_oknie)} z 4 mies., kwota z {ost_pelny if mies.get(ost_pelny) else biezacy}"
        if staly is not None:
            sposob = 'decyzja Mata' + ('' if auto else ' (wykrywanie: nie)') + f", kwota z {ost_pelny if mies.get(ost_pelny) else biezacy}"
        # zmiana kwoty: ostatni miesiąc z płatnością kontra poprzedni (sumy miesięcy, więc kilka kart naraz się nie myli)
        mm = sorted(m for m in mies if m <= biezacy)
        poprzednia = mies[mm[-2]] if len(mm) > 1 else None
        zmiana, flagi = None, []
        if poprzednia:
            proc = round(100 * (mies[mm[-1]] - poprzednia) / poprzednia, 1)
            if abs(mies[mm[-1]] - poprzednia) * 10 > poprzednia:
                zmiana = {'poprzednia': poprzednia, 'ostatnia': mies[mm[-1]], 'proc': proc, 'miesiac': mm[-1], 'poprzedni_miesiac': mm[-2]}
            if abs(mies[mm[-1]] - poprzednia) * 2 > poprzednia:
                flagi.append('zmiana kwoty')
        typowo = sorted(ile_mies[m] for m in w_oknie)
        if typowo and typowo[len(typowo) // 2] <= 1 and len(ps) > 1:   # cykl liczymy tylko przy jednej płatności w miesiącu
            dzien_c = _dzien_cyklu(ps[:-1][-6:])
            if dzien_c is not None and abs(int(ost['data'][8:10]) - dzien_c) > 3:
                flagi.append('poza cyklem')
        pozycje.append({**wspolne, 'miesiecznie': miesiecznie, 'rocznie': miesiecznie * 12, 'roczna': False, 'sposob': sposob,
                        'zmiana_ceny': zmiana, 'flagi': flagi, 'miesiace_w_oknie': len(w_oknie)})
    pozycje.sort(key=lambda x: -x['miesiecznie'])
    wygasle.sort(key=lambda x: x['ostatnia_data'], reverse=True)

    def wg(pole):
        s = defaultdict(lambda: [0, 0, 0])
        for x in pozycje:
            k = x[pole] or ''
            s[k][0] += x['miesiecznie']; s[k][1] += x['rocznie']; s[k][2] += 1
        return sorted(({'nazwa': k, 'miesiecznie': a, 'rocznie': b, 'ile': c} for k, (a, b, c) in s.items()), key=lambda y: -y['miesiecznie'])
    return {'dzien_stanu': dzien, 'okno': okno, 'ostatni_pelny': ost_pelny, 'pozycje': pozycje, 'wygasle': wygasle,
            'wg_obszaru': wg('obszar'), 'wg_osoby': wg('kto'),
            'razem': {'miesiecznie': sum(x['miesiecznie'] for x in pozycje), 'rocznie': sum(x['rocznie'] for x in pozycje)},
            'obszary': obszary(con), 'oceny': OCENY}


def do_decyzji(con, od=None, do=None) -> dict:
    """Kontrahenci z kategorią Nieprzypisane i płatności z kategorią niezgodną z rodzajem (grupy kontrahent × kategoria × rodzaj)."""
    if od is None or do is None:
        ok = okres(con)
        od, do = ok['od'], ok['do']
    nie, niezg = defaultdict(list), defaultdict(list)
    for p in _platnosci(con, od, do):
        if p['kategoria'] == 'nieprzypisane':
            nie[p['grupa']].append(p)
        elif not zgodna(p['kategoria'], p['rodzaj']):
            niezg[(p['grupa'], p['kategoria'], p['rodzaj'])].append(p)
    from .klienci import RODZAJE
    return {'od': od, 'do': do,
            'nieprzypisane': sorted(({'klucz': g, 'nazwa': _nazwa_grupy(ps), 'suma': sum(p['kwota'] for p in ps), 'ile': len(ps),
                                      'ostatnia': ps[-1]['data']} for g, ps in nie.items()), key=lambda y: -y['suma']),
            'niezgodne': sorted(({'klucz': g, 'nazwa': _nazwa_grupy(ps), 'kategoria': k, 'kategoria_nazwa': NAZWY.get(k, k),
                                  'rodzaj': r, 'rodzaj_nazwa': RODZAJE.get(r, r), 'suma': sum(p['kwota'] for p in ps), 'ile': len(ps),
                                  'zrodlo': ps[-1]['kategoria_zrodlo'], 'od_mata': any(p['kategoria_wpis'] for p in ps),
                                  'zgodne_rodzaje': [RODZAJE[x] for x in sorted(ZGODNE.get(k, ()))],
                                  'typ': 'bez_rodzaju' if r == 'nieprzypisany' else 'niezgodna',
                                  'rodzaj_podpowiedz': _podpowiedz_rodzaju(k), 'klucze': sorted({p['kontrahent_klucz'] for p in ps})}
                                 for (g, k, r), ps in niezg.items()), key=lambda y: (not y['od_mata'], -y['suma']))}


def _podpowiedz_rodzaju(kategoria: str) -> str | None:
    """Rodzaj, który pasuje do kategorii (do jednego kliknięcia w Do decyzji). Koszt klienta wymaga klienta, więc bez podpowiedzi."""
    z = ZGODNE.get(kategoria) or set()
    for r in ('praca', 'staly', 'podatki', 'vat', 'dywidenda', 'zwrot'):
        if r in z and 'przenoszony' not in z:
            return r
    return None


def kontrahent(con, klucz: str, od=None, do=None) -> dict:
    """Karta kontrahenta: płatności w okresie (data, rachunek, kwota, tytuł, źródło przypisania), cel, kategoria, stały."""
    ok = okres(con, od, do)
    pl = _platnosci(con, ok['od'], ok['do'], klucz)
    wszystkie = _platnosci(con, grupa=klucz)
    if not wszystkie:
        raise ValueError('nie ma takiego kontrahenta w wydatkach')
    from .klienci import RODZAJE
    cel = _cele(con).get(klucz, {})
    ks = koszty_stale(con)
    stale = sorted((x for x in ks['pozycje'] if x['kontrahent'] == klucz), key=lambda x: -x['miesiecznie'])
    wygasly = next((x for x in ks['wygasle'] if x['kontrahent'] == klucz), None)
    kat = Counter(p['kategoria'] for p in wszystkie).most_common(1)[0][0]
    regula = con.execute('SELECT 1 FROM wydatki WHERE kontrahent_grupa = ? AND kategoria_zrodlo LIKE ?', (klucz, 'reguła Mata%')).fetchone()
    return {**ok, 'klucz': klucz, 'nazwa': _nazwa_grupy(wszystkie), 'kategoria': kat,
            'regula_mata': bool(regula), 'regula_wpis': next((p['kategoria_wpis'] for p in wszystkie
                                                              if p['kategoria_zrodlo'].startswith('reguła Mata')), ''),
            'suma': sum(p['kwota'] for p in pl), 'ile': len(pl), 'ile_wszystkich': len(wszystkie),
            'platnosci': [{**{k: p[k] for k in ('klucz', 'data', 'kwota', 'tytul', 'opis', 'rachunek', 'kwota_oryg', 'waluta_oryg', 'rodzaj',
                                                 'klient', 'zrodlo', 'dokument', 'netto_dok', 'kategoria', 'kategoria_zrodlo', 'kategoria_wpis',
                                                 'plik', 'wiersz', 'kontrahent')},
                           'rodzaj_nazwa': RODZAJE.get(p['rodzaj'], p['rodzaj']), 'kategoria_nazwa': NAZWY.get(p['kategoria'], p['kategoria']),
                           'zgodna': zgodna(p['kategoria'], p['rodzaj'])} for p in reversed(pl)],
            'cel': {k: cel.get(k) for k in ('obszar', 'kto', 'uzasadnienie', 'ocena', 'data_oceny', 'staly', 'roczna', 'wpis')},
            'staly': stale[0] if stale else None, 'wygasly': wygasly, 'obszary': obszary(con), 'oceny': OCENY, 'osoby': osoby(con),
            'lista_kategorii': [{'klucz': k, 'nazwa': n} for k, n in KATEGORIE]}


def osoby(con) -> list:
    """Podpowiedzi pola „kto”: osoby z listy płac (wiersze umów w budżecie) i wcześniej wpisane."""
    wynik = [r[0] for r in con.execute("SELECT DISTINCT kontrahent FROM bud_wiersz WHERE (podstawa LIKE 'Umowa%' OR lista_plac = 1)"
                                       " AND kontrahent != ''")]
    wynik += [r[0] for r in con.execute("SELECT DISTINCT kto FROM wydatki_cel WHERE kto != ''")]
    return sorted(dict.fromkeys(wynik), key=str.lower)


def sprawdz_odwolania(con, typ: str, dane: dict):
    """Kontrahent i obszar wpisu muszą istnieć (nic zmyślonego nie trafia do pliku zmian)."""
    if typ in ('kategoria_regula', 'cel_wydatku') and not con.execute(
            'SELECT 1 FROM wydatki WHERE kontrahent_grupa = ?', (dane['kontrahent'],)).fetchone():
        raise ValueError(f"nie ma kontrahenta „{dane['kontrahent']}” w wydatkach z banku")
    if typ == 'cel_wydatku' and dane.get('obszar') and dane['obszar'] not in obszary(con):
        raise ValueError(f"nieznany obszar „{dane['obszar']}”: dodaj go najpierw do listy obszarów")


ODCZYTY = {
    'wydatki/analiza': lambda con, q: analiza(con, q.get('od'), q.get('do')),
    'wydatki/stale': lambda con, q: koszty_stale(con),
    'wydatki/do-decyzji': lambda con, q: do_decyzji(con, *(lambda o: (o['od'], o['do']))(okres(con, q.get('od'), q.get('do')))),
    'wydatki/kontrahent': lambda con, q: kontrahent(con, q.get('klucz', ''), q.get('od'), q.get('do')),
}
