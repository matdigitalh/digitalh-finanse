"""Etap 3: mapa klientów, rodzaje kosztów i dopasowanie wydatków z banku do rejestru zakupów biura.

Liczone przy każdej odbudowie, od zera. Kolejność źródeł przypisania (pierwsze wygrywa):
  1. reguła Mata z aplikacji (zmiany/*.jsonl),
  2. reguła wbudowana (ZUS, urząd skarbowy, wynagrodzenia, podział zysku),
  3. podpowiedź z Budget Studio (jak Mat skategoryzował tego kontrahenta albo tę fakturę),
  4. brak: „nieprzypisany” albo nazwa nabywcy z faktury.
Każde przypisanie ma zapisane źródło, żeby było widać, skąd się wzięło.
"""
import re
from collections import Counter, defaultdict
from datetime import date, timedelta
from itertools import combinations

from .dopasowanie import klucz_fv, tokeny
from .format import norm

RODZAJE = {
    'przenoszony': 'koszt klienta',          # media, druk, podwykonawcy pod konkretnego klienta
    'staly': 'koszt stały',                  # narzędzia, biuro, księgowość, new business
    'praca': 'koszty pracy',                 # wynagrodzenia, ZUS, PIT-4, PPK
    'podatki': 'podatki',                    # CIT, opłaty urzędowe
    'vat': 'VAT',                            # poza wynikiem
    'dywidenda': 'podział zysku',            # nie koszt
    'zwrot': 'zwrot dla klienta',            # oddana nadpłata, nie koszt
    'zwrocony': 'zakup zwrócony',            # zakup, za który przyszedł zwrot na tę samą kwotę; poza wynikiem
    'nieprzypisany': 'nieprzypisany',
}
BEZ_DOKUMENTU_OK = {'praca', 'podatki', 'vat', 'dywidenda', 'zwrot', 'zwrocony'}
FOLDERY_NIE_KLIENCI = {'DigitalH', 'Zobowiązania fiskalne', 'Projekty dodatkowe', ''}
FORMY = re.compile(r'\b(sp(ółka|olka)?\.?\s*z\s*o\.?\s*o\.?|spółka z ograniczoną odpowiedzialnością.*|spółka akcyjna|'
                   r'prosta spółka akcyjna|s\.a\.|sp\. ?k\.|spółka komandytowa|spółka jawna)\b.*$', re.I)
KSEF_DATA = re.compile(r'\d{10}-(\d{8})-[0-9A-F]{6,}', re.I)
TOLERANCJA_KURS = 0.06
OKNO_DNI = 40


def klucz_kontrahenta(nazwa: str) -> str:
    """Stały klucz kontrahenta z banku: dwa pierwsze słowa bez cyfr, posortowane.
    'GOOGLE *ADS1112223333 DUBLIN' -> 'ads google'; 'KOWALSKI JAN UL.' i 'Jan Kowalski' -> 'jan kowalski'."""
    slowa = []
    if '*' in (nazwa or ''):
        # karta: „FACEBK *WNGQGHVA” (losowy kod po gwiazdce) albo „GOOGLE *ADS1112223333” (prefiks z numerem)
        przed, po = nazwa.split('*', 1)
        pierwszy = (po.split() or [''])[0]
        nazwa = przed + (' ' + re.sub(r'\d+', '', pierwszy) if re.search(r'\d', pierwszy) else '')
    for t in norm(nazwa).split():
        t = re.sub(r'\d+', '', t)
        if len(t) >= 2 and t not in {'sp', 'oo', 'ul', 'al', 'pl', 'z', 'o', 'sa', 'nip', 'pko', 'spolka'}:
            slowa.append(t)
    return ' '.join(sorted(slowa[:2]))


def krotka_nazwa(nabywca: str) -> str:
    s = re.sub(r'["„”]', '', nabywca or '').strip()
    s = FORMY.sub('', s).strip(' ,.-')
    return s.title() if s.isupper() else s


def _dzien(s):
    return date.fromisoformat(s[:10]) if s else None


def wczytaj_reczne(wpisy):
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    r = {'klient_nip': {}, 'klient_faktura': {}, 'koszt_regula': {}, 'koszt_operacja': {}, 'wpis': {}, 'cele': {}, 'konta': {}}
    for w in wpisy:
        if w.get('id') in cofniete:
            continue
        typ, d = w.get('typ'), w.get('dane', {})
        if typ == 'klient_nip':
            r['klient_nip'][d['nabywca']] = d['klient']
            r['wpis'][('klient_nip', d['nabywca'])] = w.get('id')
        elif typ == 'konto_reklamowe':
            r['konta'][d['konto']] = d.get('klient', '')
            r['wpis'][('konto_reklamowe', d['konto'])] = w.get('id')
        elif typ == 'cel':
            r['cele'][d['klucz']] = d['wartosc']
        elif typ == 'klient_faktura':
            r['klient_faktura'][d['faktura']] = d['klient']
            r['wpis'][('klient_faktura', d['faktura'])] = w.get('id')
        elif typ == 'koszt_regula':
            r['koszt_regula'][d['kontrahent']] = (d['rodzaj'], d.get('klient', ''))
            r['wpis'][('koszt_regula', d['kontrahent'])] = w.get('id')
        elif typ == 'koszt_operacja':
            r['koszt_operacja'][d['operacja']] = (d['rodzaj'], d.get('klient', ''))
            r['wpis'][('koszt_operacja', d['operacja'])] = w.get('id')
    return r


def klucz_nabywcy(f) -> str:
    return f['nip'] or norm(f['nabywca'])


def policz(con, wpisy) -> dict:
    reczne = wczytaj_reczne(wpisy)
    import json
    con.execute("INSERT OR REPLACE INTO meta VALUES ('cele', ?)", (json.dumps(reczne['cele']),))
    wiersze = [('klient_nip', k, v, reczne['wpis'].get(('klient_nip', k), '')) for k, v in reczne['klient_nip'].items()]
    wiersze += [('klient_faktura', k, v, reczne['wpis'].get(('klient_faktura', k), '')) for k, v in reczne['klient_faktura'].items()]
    wiersze += [('koszt_regula', k, f'{RODZAJE[a]}{", " + b if b else ""}', reczne['wpis'].get(('koszt_regula', k), ''))
                for k, (a, b) in reczne['koszt_regula'].items()]
    wiersze += [('koszt_operacja', k, f'{RODZAJE[a]}{", " + b if b else ""}', reczne['wpis'].get(('koszt_operacja', k), ''))
                for k, (a, b) in reczne['koszt_operacja'].items()]
    wiersze += [('konto_reklamowe', k, v or '(bez klienta)', reczne['wpis'].get(('konto_reklamowe', k), '')) for k, v in reczne['konta'].items()]
    con.executemany('INSERT INTO reguly (typ, klucz, wartosc, wpis) VALUES (?,?,?,?)', wiersze)
    _klienci_faktur(con, reczne)
    _rodzaje_wydatkow(con, reczne)
    return _wydatki_a_rejestr(con)


# ---------- 1. Klient każdej faktury ----------

def _klienci_faktur(con, reczne):
    faktury = [dict(f) for f in con.execute('SELECT numer, nip, nabywca FROM faktury')]
    bs_po_numerze = {}
    for r in con.execute("SELECT numer, folder FROM bs WHERE rodzaj = 1 AND numer != ''"):
        k = klucz_fv(r['numer'])
        if k and r['folder'] not in FOLDERY_NIE_KLIENCI:
            bs_po_numerze[k] = r['folder']
    wynik = {}
    for f in faktury:
        kn = klucz_nabywcy(f)
        if f['numer'] in reczne['klient_faktura']:
            wynik[f['numer']] = (reczne['klient_faktura'][f['numer']], 'decyzja Mata (ta faktura)',
                                 reczne['wpis'].get(('klient_faktura', f['numer']), ''))
        elif kn in reczne['klient_nip']:
            wynik[f['numer']] = (reczne['klient_nip'][kn], 'reguła Mata', reczne['wpis'].get(('klient_nip', kn), ''))
        elif klucz_fv(f['numer']) in bs_po_numerze:
            wynik[f['numer']] = (bs_po_numerze[klucz_fv(f['numer'])], 'Budget Studio', '')
    # Ten sam nabywca co faktury już przypisane: najczęstszy klient
    po_nabywcy = defaultdict(Counter)
    for f in faktury:
        if f['numer'] in wynik:
            po_nabywcy[klucz_nabywcy(f)][wynik[f['numer']][0]] += 1
    for f in faktury:
        if f['numer'] in wynik:
            continue
        c = po_nabywcy.get(klucz_nabywcy(f))
        if c:
            wynik[f['numer']] = (c.most_common(1)[0][0], 'ten sam nabywca', '')
        else:
            wynik[f['numer']] = (krotka_nazwa(f['nabywca']), 'nazwa nabywcy', '')
    con.executemany('INSERT INTO faktury_klient (numer, klient, zrodlo, wpis) VALUES (?,?,?,?)',
                    [(n, k, z, w) for n, (k, z, w) in wynik.items()])


# ---------- 2. Rodzaj i klient każdego wydatku ----------

def _wbudowana(o) -> str | None:
    kontr, tekst = norm(o['kontrahent']), norm(f"{o['tytul']} {o['opis']}")
    if kontr.startswith('zus') or 'zaklad ubezpieczen' in kontr or 'emerytura' in kontr:
        return 'praca'
    if 'urzad skarbowy' in kontr:
        if re.search(r'\bpit ?8ar\b|dywidend', tekst):
            return 'dywidenda'
        if re.search(r'\bpit ?4|\bpit ?4r\b|umowa o prace', tekst):
            return 'praca'
        if re.search(r'\bvat\b|vat ?7|jpk', tekst):
            return 'vat'
        return 'podatki'
    if 'wynagrodzenie' in tekst:
        return 'praca'
    if 'zwrot nadplaty' in tekst or 'zwrot naplaty' in tekst:
        return 'zwrot'
    if kontr.startswith('ing bank') and ('oplata' in tekst or 'prowizja' in tekst):
        return 'staly'
    if 'dywidend' in tekst or 'podzial zysku' in tekst or 'wyplata zysku' in tekst:
        return 'dywidenda'
    return None


def _para_bs(folder, arkusz):
    if folder == 'Zobowiązania fiskalne':
        return ('podatki', '')
    if folder == 'DigitalH':
        return ('praca', '') if 'pracownicy' in arkusz.lower() else ('staly', '')
    if folder == 'Projekty dodatkowe':
        return ('przenoszony', '')
    return ('przenoszony', folder)


def _z_budget_studio(con, ops) -> tuple[dict, dict]:
    """Podpowiedzi z Budget Studio. Każdą płatność z banku łączymy z wpisem kosztowym Budget Studio po kwocie
    i dacie (nazwy w obu miejscach są zapisane różnie), potem rodzaj i klient przechodzą na całego kontrahenta.
    Zwraca (operacja_id -> para, klucz kontrahenta -> para)."""
    wpisy = []
    for r in con.execute('SELECT kontrahent, folder, arkusz, brutto, dzien FROM bs WHERE rodzaj = -1 AND dzien IS NOT NULL'):
        wpisy.append({'para': _para_bs(r['folder'], r['arkusz']), 'kwota': abs(r['brutto']), 'dzien': _dzien(r['dzien']),
                      'tok': tokeny(r['kontrahent'])})
    kandydaci = []
    for o in ops:
        for i, w in enumerate(wpisy):
            dd = abs((o['_dzien'] - w['dzien']).days)
            if dd > 20:
                continue
            nazwa = bool(o['_tok'] & w['tok'])
            roznica = abs(o['cel'] - w['kwota'])
            # karta: ING księguje 1–3 dni po dacie w BS, więc okno ±5 dni; waluta: różnica kursu do 6%
            okno = 5 if o['_karta'] else 3
            if roznica == 0 and (nazwa or dd <= okno):
                kandydaci.append((dd / 100 + (0 if nazwa else 1), o['id'], i))
            elif roznica <= w['kwota'] * 0.06 and (nazwa or (o['_waluta'] and dd <= 5)):
                kandydaci.append((2 + roznica / max(w['kwota'], 1) + dd / 100 + (0 if nazwa else 1), o['id'], i))
    kandydaci.sort()
    po_op, zajete = {}, set()
    for _, oid, i in kandydaci:
        if oid in po_op or i in zajete:
            continue
        po_op[oid] = wpisy[i]['para']
        zajete.add(i)
    glosy = defaultdict(Counter)
    for o in ops:
        if o['id'] in po_op:
            glosy[o['kk']][po_op[o['id']]] += 1
    return po_op, {k: c.most_common(1)[0][0] for k, c in glosy.items() if k}


def _rodzaje_wydatkow(con, reczne):
    ops = []
    zwrocone = {r[0] for r in con.execute('SELECT wydatek_id FROM zwroty_zakupow')}
    konta_op = _konta_reklamowe(con)
    for o in con.execute('SELECT id, klucz, kwota, data_ksiegowania, kontrahent, tytul, opis, waluta_oryg FROM operacje'
                         ' WHERE kwota < 0 AND wewnetrzna = 0'):
        o = dict(o)
        o['_karta'] = 'kart' in (o['opis'] or '').lower() or 'kart' in (o['tytul'] or '').lower()
        o['_waluta'] = bool(o['waluta_oryg']) and o['waluta_oryg'] != 'PLN'
        o['kk'] = klucz_kontrahenta(o['kontrahent'] or o['opis'])
        o['cel'] = -o['kwota']
        o['_dzien'] = _dzien(o['data_ksiegowania'])
        o['_tok'] = tokeny(o['kontrahent'] or o['opis'])
        ops.append(o)
    bs_op, bs_kontr = _z_budget_studio(con, ops)
    wiersze = []
    for o in ops:
        kk = o['kk']
        konto = konta_op.get(o['id'], '')
        if o['id'] in zwrocone:
            rodzaj, klient, zrodlo, wpis = 'zwrocony', '', 'zwrot na tę samą kwotę', ''
        elif o['klucz'] in reczne['koszt_operacja']:
            (rodzaj, klient), zrodlo, wpis = reczne['koszt_operacja'][o['klucz']], 'decyzja Mata (ta płatność)', \
                reczne['wpis'].get(('koszt_operacja', o['klucz']), '')
        elif konto and konto in reczne['konta']:
            rodzaj, klient, zrodlo, wpis = 'przenoszony', reczne['konta'][konto], f'konto reklamowe {konto}', \
                reczne['wpis'].get(('konto_reklamowe', konto), '')
        elif kk in reczne['koszt_regula']:
            (rodzaj, klient), zrodlo, wpis = reczne['koszt_regula'][kk], 'reguła Mata', reczne['wpis'].get(('koszt_regula', kk), '')
        elif (w := _wbudowana(o)):
            rodzaj, klient, zrodlo, wpis = w, '', 'reguła wbudowana', ''
        elif o['id'] in bs_op:
            (rodzaj, klient), zrodlo, wpis = bs_op[o['id']], 'Budget Studio (ta płatność)', ''
        elif kk in bs_kontr:
            (rodzaj, klient), zrodlo, wpis = bs_kontr[kk], 'Budget Studio (ten kontrahent)', ''
        else:
            rodzaj, klient, zrodlo, wpis = 'nieprzypisany', '', '', ''
        wiersze.append((o['id'], kk, rodzaj, klient, zrodlo, wpis, konto))
    con.executemany('INSERT INTO wydatki (operacja_id, kontrahent_klucz, rodzaj, klient, zrodlo, wpis, konto) VALUES (?,?,?,?,?,?,?)',
                    wiersze)
    _lista_kont(con, reczne)


ADS = re.compile(r'ADS(\d{10})(?!\d)', re.I)


def _konta_reklamowe(con) -> dict:
    """operacja_id -> konto reklamowe. Google Ads: numer z nazwy kontrahenta (ADS1234567890 = 123-456-7890).
    Meta: płatność kartą FACEBK łączona z fakturą Meta z folderu Faktury po kwocie i dacie (±5 dni)."""
    wynik = {}
    meta = [dict(r) for r in con.execute("SELECT kwota, data, konto FROM dokumenty WHERE konto LIKE 'Meta %' AND waluta = 'PLN'")]
    for o in con.execute('SELECT id, kontrahent, kwota, data_ksiegowania FROM operacje WHERE kwota < 0 AND wewnetrzna = 0'):
        k = o['kontrahent'] or ''
        if (m := ADS.search(k)):
            n = m.group(1)
            wynik[o['id']] = f'Google Ads {n[:3]}-{n[3:6]}-{n[6:]}'
        elif k.upper().startswith('FACEBK'):
            d = _dzien(o['data_ksiegowania'])
            trafione = [x for x in meta if x['kwota'] == -o['kwota'] and abs((d - _dzien(x['data'])).days) <= 5]
            if trafione:
                wynik[o['id']] = min(trafione, key=lambda x: abs((d - _dzien(x['data'])).days))['konto']
    return wynik


def _lista_kont(con, reczne):
    """Konta reklamowe z banku i z folderu faktur, z przypisaniem Mata i podpowiedzią (wykazy faktur, nazwa konta)."""
    from .importy.faktury_dysk import podpowiedzi_kont
    podp = podpowiedzi_kont()
    klienci = [r[0] for r in con.execute('SELECT DISTINCT klient FROM faktury_klient')]
    def dopasuj_klienta(nazwa):
        n = norm(nazwa).split()
        return next((k for k in klienci if n and norm(k).split()[:1] == n[:1]), '')
    konta = {}
    for r in con.execute("SELECT w.konto, COUNT(*), -SUM(o.kwota), MAX(o.data_ksiegowania) FROM wydatki w JOIN operacje o"
                         " ON o.id = w.operacja_id WHERE w.konto != '' GROUP BY w.konto"):
        konta[r[0]] = [r[1], r[2], r[3]]
    for r in con.execute("SELECT DISTINCT konto FROM dokumenty WHERE konto != ''"):
        konta.setdefault(r[0], [0, 0, ''])
    for k, (ile, suma, ostatnia) in konta.items():
        nazwa = podp.get(k) or (k.split(' ', 1)[1] if k.startswith('Meta ') and not k.startswith('Meta FBADS') else '')
        con.execute('INSERT INTO konta_reklamowe (konto, platnosci, suma, ostatnia, klient, podpowiedz, klient_podpowiedz, wpis)'
                    ' VALUES (?,?,?,?,?,?,?,?)', (k, ile, suma, ostatnia, reczne['konta'].get(k), nazwa,
                                                  dopasuj_klienta(nazwa) if nazwa else '', reczne['wpis'].get(('konto_reklamowe', k), '')))


# ---------- 3. Wydatki z banku a rejestr zakupów ----------

def _alnum(s):
    return re.sub(r'[^0-9A-Z]', '', (s or '').upper())


def _wydatki_a_rejestr(con) -> dict:
    zakupy = {}
    for z in con.execute('SELECT * FROM zakupy'):
        z = dict(z)
        z['cel'] = z['brutto'] if z['rejestr'] == 'krajowe' and z['brutto'] is not None else z['netto']
        z['_tok'] = tokeny(z['podmiot'])
        z['_dzien'] = _dzien(z['data'])
        z['_nr'] = _alnum(z['nr_dok'])
        if z['cel'] and z['cel'] > 0:
            zakupy[z['nr_ewid']] = z
    koniec_rejestru = max((z['data'] for z in zakupy.values()), default=None)
    # Po końcu rejestru biura: faktury z folderu Faktury/<miesiąc>/Zweryfikowane (nazwa pliku: kwota i data).
    for r in con.execute('SELECT rowid, * FROM dokumenty WHERE data > ?', (koniec_rejestru or '',)):
        z = {'nr_ewid': f"plik:{r['plik']}", 'nr_dok': r['numer'], 'data': r['data'], 'podmiot': r['wystawca'],
             'rejestr': 'folder Faktury', 'netto': None, 'cel': r['kwota'], 'waluta': r['waluta'], 'plik': r['plik']}
        z['_tok'] = tokeny(re.sub(r'([a-z])([A-Z])', r'\1 \2', r['wystawca']))
        z['_dzien'] = _dzien(z['data'])
        z['_nr'] = _alnum(r['numer'])
        if z['cel'] > 0:
            zakupy[z['nr_ewid']] = z
    ops = []
    for o in con.execute('SELECT o.id, o.data_ksiegowania, o.kwota, o.kontrahent, o.tytul, o.opis, o.kwota_oryg, o.waluta_oryg,'
                         ' w.rodzaj FROM operacje o JOIN wydatki w ON w.operacja_id = o.id ORDER BY o.data_ksiegowania, o.id'):
        o = dict(o)
        o['cel'] = -o['kwota']
        o['_tok'] = tokeny(f"{o['kontrahent']} {o['opis'] if not o['kontrahent'] else ''}")
        o['_dzien'] = _dzien(o['data_ksiegowania'])
        o['_tytul'] = _alnum(o['tytul'])
        m = KSEF_DATA.search(o['tytul'] or '')
        o['_ksef_data'] = f'{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}' if m else None
        ops.append(o)

    kandydaci = []
    for oi, o in enumerate(ops):
        for n, z in zakupy.items():
            if z['rejestr'] == 'folder Faktury':
                # plik z folderu: kwota w walucie faktury; porównujemy z kwotą oryginalną płatności kartą albo z PLN
                cel = -(o['kwota_oryg'] or 0) if z['waluta'] != 'PLN' and o['waluta_oryg'] == z['waluta'] else o['cel'] if z['waluta'] == 'PLN' else None
                dd = (o['_dzien'] - z['_dzien']).days
                if cel is None or not -5 <= dd <= OKNO_DNI or not (o['_tok'] & z['_tok']):
                    continue
                if abs(abs(cel) - z['cel']) <= max(1, z['cel'] // 100):
                    kandydaci.append((3 + abs(dd) / 100, oi, n, 'plik w folderze Faktury'))
                continue
            dd = (o['_dzien'] - z['_dzien']).days
            if not -10 <= dd <= OKNO_DNI + 60:
                continue
            nazwa = bool(o['_tok'] & z['_tok'])
            rowna = o['cel'] == z['cel']
            numer = len(z['_nr']) >= 4 and z['_nr'] in o['_tytul']
            if numer and abs(o['cel'] - z['cel']) <= max(1, z['cel'] // 100):
                wynik, metoda = 0, 'numer dokumentu w tytule'
            elif rowna and o['_ksef_data'] == z['data']:
                wynik, metoda = 1, 'numer KSeF (data i kwota)'
            elif rowna and nazwa and dd <= OKNO_DNI:
                wynik, metoda = 2 + abs(dd) / 100, 'kwota i nazwa'
            elif (z['rejestr'] == 'zagraniczne' and nazwa and -5 <= dd <= OKNO_DNI
                  and abs(o['cel'] - z['cel']) <= z['cel'] * TOLERANCJA_KURS):
                wynik, metoda = 4 + abs(o['cel'] - z['cel']) / max(z['cel'], 1) + abs(dd) / 100, 'kwota po kursie i nazwa'
            else:
                continue
            kandydaci.append((wynik, oi, n, metoda))
    kandydaci.sort(key=lambda k: k[:3])
    para_op, para_z = {}, {}
    for wynik, oi, n, metoda in kandydaci:
        if oi in para_op or n in para_z:
            continue
        para_op[oi] = [(n, metoda)]
        para_z[n] = oi

    # Jeden przelew za kilka dokumentów tego samego dostawcy (2–4, dokładnie co do grosza)
    for oi, o in enumerate(ops):
        if oi in para_op or o['rodzaj'] in BEZ_DOKUMENTU_OK:
            continue
        kand = [n for n, z in zakupy.items() if n not in para_z and o['_tok'] & z['_tok'] and z.get('waluta', 'PLN') == 'PLN'
                and 0 <= (o['_dzien'] - z['_dzien']).days <= OKNO_DNI + 30][:12]
        for ile in range(2, min(4, len(kand)) + 1):
            trafione = next((c for c in combinations(kand, ile) if sum(zakupy[n]['cel'] for n in c) == o['cel']), None)
            if trafione:
                para_op[oi] = [(n, 'suma dokumentów dostawcy') for n in trafione]
                for n in trafione:
                    para_z[n] = oi
                break

    # Faktura zbiorcza za miesiąc (Google Ads, Meta, narzędzia) = suma wielu płatności kartą tego dostawcy
    # w miesiącu dokumentu albo miesiąc wcześniej, z tolerancją kursową.
    for n, z in sorted(zakupy.items(), key=lambda x: x[1]['data']):
        if n in para_z:
            continue
        miesiace = {z['data'][:7], (z['_dzien'].replace(day=1) - timedelta(days=1)).isoformat()[:7]}
        for m in sorted(miesiace, reverse=True):
            if z.get('waluta', 'PLN') != 'PLN':
                break
            grupa = [oi for oi, o in enumerate(ops) if oi not in para_op and o['data_ksiegowania'][:7] == m
                     and o['_tok'] & z['_tok'] and o['rodzaj'] not in BEZ_DOKUMENTU_OK]
            if len(grupa) >= 2 and abs(sum(ops[oi]['cel'] for oi in grupa) - z['cel']) <= z['cel'] * TOLERANCJA_KURS:
                for oi in grupa:
                    para_op[oi] = [(n, 'suma płatności kartą w miesiącu')]
                para_z[n] = grupa[0]
                break

    wiersze_dok, stan_op = [], {}
    for oi, o in enumerate(ops):
        if oi in para_op:
            netto = 0
            for n, metoda in para_op[oi]:
                wiersze_dok.append((o['id'], n, metoda))
                if metoda == 'suma płatności kartą w miesiącu':   # udział tej płatności w netto faktury
                    netto += round((zakupy[n]['netto'] or 0) * o['cel'] / max(zakupy[n]['cel'], 1))
                elif zakupy[n]['rejestr'] == 'folder Faktury':     # z nazwy pliku nie znamy VAT: kwota z banku
                    netto += o['cel']
                else:
                    netto += zakupy[n]['netto'] or 0
            stan_op[o['id']] = ('dokument', netto)
        elif o['rodzaj'] in BEZ_DOKUMENTU_OK:
            stan_op[o['id']] = ('nie wymaga', None)
        elif koniec_rejestru and o['data_ksiegowania'] > koniec_rejestru:
            stan_op[o['id']] = ('po okresie rejestru', None)
        else:
            stan_op[o['id']] = ('bez dokumentu', None)
    con.executemany('INSERT INTO wydatki_dok (operacja_id, nr_ewid, metoda) VALUES (?,?,?)', wiersze_dok)
    con.executemany('UPDATE wydatki SET dokument = ?, netto_dok = ? WHERE operacja_id = ?',
                    [(s, n, i) for i, (s, n) in stan_op.items()])
    con.executemany('INSERT INTO zakupy_stan (nr_ewid, stan, operacja_id) VALUES (?,?,?)',
                    [(n, 'opłacony' if n in para_z else 'bez płatności w banku', ops[para_z[n]]['id'] if n in para_z else None)
                     for n in zakupy if not n.startswith('plik:')])
    con.execute("INSERT OR REPLACE INTO meta VALUES ('koniec_rejestru', ?)", (koniec_rejestru or '',))
    return {'wydatkow': len(ops), 'z_dokumentem': sum(1 for s, _ in stan_op.values() if s == 'dokument'),
            'dokumentow': len(zakupy), 'oplaconych': len(para_z)}
