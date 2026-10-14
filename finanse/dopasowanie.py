"""Etap 2: dopasowanie wpłat z banku do faktur sprzedażowych i stan należności.

Liczone przy każdej odbudowie bazy, od zera: z operacji ING, faktur z Fakturowni i wpisów Mata (zmiany/*.jsonl).
Kolejność metod (od najpewniejszej):
  1. ręczne połączenie Mata,
  2. numer faktury w tytule przelewu (pewne),
  3. numer KSeF w tytule, bez sumy kontrolnej (pewne),
  4. dokładna kwota jednej faktury + nazwa nabywcy (prawdopodobne),
  5. dokładna suma 2–6 faktur tego samego nabywcy (prawdopodobne),
  6. dokładna kwota jednej faktury + data, bez nazwy, tylko gdy kandydat jest jeden (prawdopodobne).
„Prawdopodobne” trafia do ekranu Do weryfikacji; Mat zatwierdza albo odrzuca jednym kliknięciem.
Korekty pomniejszają należność faktury pierwotnej. Kwoty w groszach.
"""
import re
from datetime import date
from itertools import combinations

from .format import norm

# Numer faktury odporny na zapisy z banku: „FV20 26_09_13”, „F V2026/09/1”, „fv2026/09/19”, „FV2 026/09/10”,
# „/FV/2025/12/21” i podzielona płatność bez „FV”: „/INV/202 5/12/16”.
WZOR_FV = re.compile(r'(?:F\s*V\s*[/_\-]?|/INV/)\s*((?:\d\s*){4})[/_\-]\s*(\d\s*\d?)\s*[/_\-]\s*(\d{1,3})(?!\d)', re.I)
# Skrót kolejnej faktury z tego samego miesiąca: „fv2026/03/18 i 19”, „FV2026/05/3, 4”.
WZOR_DALEJ = re.compile(r'\s*(?:i|oraz|,|\+|&)\s*(\d{1,3})(?![\d/_\-.,])', re.I)

PEWNE, PRAWDOPODOBNE = 'pewne', 'prawdopodobne'
STOP = {'sp', 'z', 'o', 'oo', 'spolka', 'spolki', 'ograniczona', 'ograniczonej', 'odpowiedzialnoscia', 'odpowiedzialnosci',
        'odp', 'sa', 'sc', 'komandytowa', 'jawna', 'akcyjna', 'ul', 'al', 'pl', 'polska', 'poland', 'group', 'grupa', 'the',
        'and', 'ltd', 'inc', 'gmbh', 'llc', 'co', 'fv', 'za', 'do', 'na', 'od', 'nr', 'ip', 'ii', 'ue', 'mp'}
OKNO_PRZED = 5      # wpłata może przyjść kilka dni przed datą wystawienia (zaliczka, przelew z wyprzedzeniem)
OKNO_PO = 200       # dni po wystawieniu, w których szukamy wpłaty bez numeru
MAKS_W_SUMIE = 6
MAKS_KANDYDATOW = 14


def klucz_fv(tekst: str) -> tuple | None:
    """'FV2026/09/1' -> (2026, 9, 1)."""
    m = WZOR_FV.search(tekst or '')
    return _krotka(m) if m else None


def _krotka(m):
    return int(re.sub(r'\s', '', m.group(1))), int(re.sub(r'\s', '', m.group(2))), int(m.group(3))


def numery_w_tytule(tekst: str) -> list[tuple]:
    wynik = []
    tekst = tekst or ''
    for m in WZOR_FV.finditer(tekst):
        k = _krotka(m)
        kolejne = [k]
        poz = m.end()
        while (d := WZOR_DALEJ.match(tekst, poz)):
            kolejne.append((k[0], k[1], int(d.group(1))))
            poz = d.end()
        for x in kolejne:
            if x not in wynik:
                wynik.append(x)
    return wynik


def rdzen_ksef(ksef: str) -> str:
    """Środek numeru KSeF: data i identyfikator („20260722-9F73C4C00002”). Bez NIP-u z przodu i sumy kontrolnej
    na końcu, bo klienci płacący za kilka faktur podają kolejne numery w skrócie."""
    czesci = re.sub(r'\s', '', (ksef or '').upper()).split('-')
    return f'{czesci[1]}-{czesci[2]}' if len(czesci) >= 4 else '-'.join(czesci)


def tokeny(nazwa: str) -> set:
    return {t for t in norm(nazwa).split() if len(t) >= 2 and not t.isdigit() and t not in STOP}  # nazwy firm bywają dwuliterowe


def _dzien(s):
    return date.fromisoformat(s[:10]) if s else None


class Stan:
    """Pomocnik: ile z każdej faktury zostało do zapłaty i co już przydzielono."""

    def __init__(self, faktury):
        self.faktury = faktury
        self.pozostalo = {n: f['naleznosc'] for n, f in faktury.items()}
        self.dopasowania = []      # (operacja_id, numer, kwota, metoda, pewnosc, zrodlo)

    def przydziel(self, op, numery, metoda, pewnosc, zrodlo):
        """Rozkłada wpłatę na faktury od najstarszej. Zwraca nadpłatę (to, czego nie było na co przydzielić)."""
        zostalo = op['kwota']
        numery = sorted(numery, key=lambda n: (self.faktury[n]['data_wystawienia'] or '', n))
        for i, n in enumerate(numery):
            kwota = min(zostalo, max(self.pozostalo[n], 0))
            self.pozostalo[n] -= kwota
            zostalo -= kwota
            self.dopasowania.append((op['id'], n, kwota, metoda, pewnosc, zrodlo))
        return zostalo


def wczytaj_reczne(wpisy: list[dict]) -> dict:
    """Składa wpisy Mata w stan. 'cofnij' unieważnia wskazany wpis. Późniejszy wpis o tej samej wpłacie wygrywa."""
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    r = {'polacz': {}, 'bez_faktury': {}, 'zatwierdz': set(), 'odrzuc': set(), 'poza_bankiem': {}, 'wpis_op': {}, 'wpis_fv': {}}
    for w in wpisy:
        if w.get('id') in cofniete:
            continue
        typ, d = w.get('typ'), w.get('dane', {})
        if typ == 'polacz':
            r['polacz'][d['operacja']] = list(d['faktury'])
            r['bez_faktury'].pop(d['operacja'], None)
            r['wpis_op'][d['operacja']] = w.get('id')
        elif typ == 'bez_faktury':
            r['bez_faktury'][d['operacja']] = d.get('powod', '')
            r['polacz'].pop(d['operacja'], None)
            r['wpis_op'][d['operacja']] = w.get('id')
        elif typ == 'zatwierdz':
            r['zatwierdz'].add((d['operacja'], d['faktura']))
            r['odrzuc'].discard((d['operacja'], d['faktura']))
        elif typ == 'odrzuc':
            r['odrzuc'].add((d['operacja'], d['faktura']))
            r['zatwierdz'].discard((d['operacja'], d['faktura']))
        elif typ == 'poza_bankiem':
            r['poza_bankiem'][d['faktura']] = d.get('powod', '')
            r['wpis_fv'][d['faktura']] = w.get('id')
    return r


def policz(con, wpisy: list[dict]) -> dict:
    """Wypełnia tabele dopasowania, wplaty, faktury_stan. Zwraca krótkie podsumowanie."""
    reczne = wczytaj_reczne(wpisy)
    dzien_stanu = con.execute('SELECT MAX(data_ksiegowania) FROM operacje').fetchone()[0]

    faktury = {}
    for f in con.execute('SELECT * FROM faktury WHERE korekta = 0'):
        faktury[f['numer']] = dict(f)
    for f in faktury.values():
        f['korekty'] = 0
    for k in con.execute('SELECT oryginal, brutto FROM faktury WHERE korekta = 1'):
        if k['oryginal'] in faktury:
            faktury[k['oryginal']]['korekty'] += k['brutto']
    for f in faktury.values():
        f['naleznosc'] = f['brutto'] + f['korekty']
        f['_tok'] = tokeny(f['nabywca'])
        f['_dzien'] = _dzien(f['data_wystawienia'])
    po_kluczu = {}
    for n in faktury:
        k = klucz_fv(n)
        if k:
            po_kluczu[k] = n
    po_ksef = {rdzen_ksef(f['ksef']): n for n, f in faktury.items() if f['ksef']}
    najstarsza = min((f['data_wystawienia'] for f in faktury.values() if f['data_wystawienia']), default=None)

    ops = [dict(o) for o in con.execute(
        'SELECT id, klucz, data_ksiegowania, kwota, kontrahent, tytul, opis FROM operacje'
        ' WHERE kwota > 0 AND wewnetrzna = 0 ORDER BY data_ksiegowania, id')]
    for o in ops:
        o['_tekst'] = f"{o['tytul'] or ''} {o['opis'] or ''}"
        o['_tok'] = tokeny(o['kontrahent'])
        o['_dzien'] = _dzien(o['data_ksiegowania'])

    s = Stan(faktury)
    wynik = {}   # operacja_id -> dict(stan, nadplata, uwaga, podpowiedz)

    def zapisz(o, stan, nadplata=0, uwaga='', podpowiedz=''):
        wynik[o['id']] = {'stan': stan, 'nadplata': nadplata, 'uwaga': uwaga, 'podpowiedz': podpowiedz}

    def pewnosc_auto(o, numery, pewnosc):
        if pewnosc == PRAWDOPODOBNE and all((o['klucz'], n) in reczne['zatwierdz'] for n in numery):
            return PEWNE, 'zatwierdzone'
        return pewnosc, 'automat'

    # 1. Ręczne decyzje Mata
    for o in ops:
        if o['klucz'] in reczne['bez_faktury']:
            zapisz(o, 'bez_faktury', uwaga=reczne['bez_faktury'][o['klucz']] or 'oznaczone: nie dotyczy faktury')
        elif o['klucz'] in reczne['polacz']:
            numery = [n for n in reczne['polacz'][o['klucz']] if n in faktury]
            if numery:
                nad = s.przydziel(o, numery, 'połączone ręcznie', PEWNE, 'ręcznie')
                zapisz(o, 'dopasowana', nad)

    def wolna(o):
        return o['id'] not in wynik

    def dozwolone(o, numery):
        return [n for n in numery if (o['klucz'], n) not in reczne['odrzuc']]

    def kandydaci(o, z_nazwa):
        lista = []
        for n, f in faktury.items():
            if s.pozostalo[n] <= 0 or not f['_dzien'] or (o['klucz'], n) in reczne['odrzuc']:
                continue
            roznica = (o['_dzien'] - f['_dzien']).days
            if -OKNO_PRZED <= roznica <= OKNO_PO and (not z_nazwa or (o['_tok'] & f['_tok'])):
                lista.append(n)
        return lista

    # 2. Numer faktury w tytule
    for o in filter(wolna, ops):
        klucze = numery_w_tytule(o['_tekst'])
        if not klucze:
            continue
        znane = dozwolone(o, [po_kluczu[k] for k in klucze if k in po_kluczu])
        nieznane = [k for k in klucze if k not in po_kluczu]
        # Numer cudzej, już opłaconej faktury to pomyłka w tytule (klient wpisał numer faktury innego nabywcy):
        # pomijamy go, a wpłatę dopasowujemy dalej po kwocie.
        obce = [n for n in znane if not (o['_tok'] & faktury[n]['_tok']) and s.pozostalo[n] <= 0]
        znane = [n for n in znane if n not in obce]
        uwagi = []
        if obce:
            uwagi.append('w tytule numer faktury innego nabywcy, już opłaconej: ' + ', '.join(obce))
        if nieznane:
            uwagi.append('w tytule także ' + ', '.join(f'FV{a}/{b:02d}/{c}' for a, b, c in nieznane))
        if znane:
            cudze = [n for n in znane if not (o['_tok'] & faktury[n]['_tok'])]
            pewnosc, zrodlo = pewnosc_auto(o, cudze, PRAWDOPODOBNE) if cudze else (PEWNE, 'automat')
            if cudze:
                uwagi.append('płaci ktoś inny niż nabywca faktury')
            nad = s.przydziel(o, znane, 'numer faktury w tytule', pewnosc, zrodlo)
            zapisz(o, 'dopasowana', nad, uwaga='; '.join(uwagi))
        elif obce:
            o['_uwaga'] = '; '.join(uwagi)
        elif nieznane and najstarsza and all(1 <= b <= 12 and f'{a}-{b:02d}' < najstarsza[:7] for a, b, c in nieznane):
            zapisz(o, 'sprzed_eksportu', podpowiedz='faktura sprzed eksportu Fakturowni: '
                   + ', '.join(f'FV{a}/{b:02d}/{c}' for a, b, c in nieznane))

    # 3. Numer KSeF w tytule
    if po_ksef:
        for o in filter(wolna, ops):
            tekst = re.sub(r'\s', '', o['_tekst'].upper())
            znane = dozwolone(o, [n for r, n in po_ksef.items() if r and r in tekst])
            if znane:
                nad = s.przydziel(o, znane, 'numer KSeF w tytule', PEWNE, 'automat')
                zapisz(o, 'dopasowana', nad)

    # 3a. Reszta wpłaty po numerze lub KSeF równa kwocie innej faktury tego nabywcy (pomyłka w numerze)
    for o in ops:
        w = wynik.get(o['id'])
        if not w or w['stan'] != 'dopasowana' or w['nadplata'] <= 0:
            continue
        trafione = [n for n in kandydaci(o, True) if s.pozostalo[n] == w['nadplata']]
        if len(trafione) == 1:
            p, z = pewnosc_auto(o, trafione, PRAWDOPODOBNE)
            reszta = dict(o, kwota=w['nadplata'])
            w['nadplata'] = s.przydziel(reszta, trafione, 'reszta wpłaty = kwota faktury', p, z)

    # 4. Kwota jednej faktury + nazwa
    for o in filter(wolna, ops):
        trafione = [n for n in kandydaci(o, True) if s.pozostalo[n] == o['kwota']]
        if trafione:
            n = min(trafione, key=lambda n: abs((o['_dzien'] - faktury[n]['_dzien']).days))
            p, z = pewnosc_auto(o, [n], PRAWDOPODOBNE)
            s.przydziel(o, [n], 'kwota i nazwa nabywcy', p, z)
            zapisz(o, 'dopasowana', uwaga=o.get('_uwaga', ''))

    # 5. Suma kilku faktur tego samego nabywcy
    for o in filter(wolna, ops):
        kand = sorted(kandydaci(o, True), key=lambda n: abs((o['_dzien'] - faktury[n]['_dzien']).days))[:MAKS_KANDYDATOW]
        znalezione = None
        for ile in range(2, min(MAKS_W_SUMIE, len(kand)) + 1):
            for c in combinations(kand, ile):
                if sum(s.pozostalo[n] for n in c) == o['kwota'] and len({faktury[n]['nip'] or faktury[n]['nabywca'] for n in c}) == 1:
                    znalezione = list(c)
                    break
            if znalezione:
                break
        if znalezione:
            p, z = pewnosc_auto(o, znalezione, PRAWDOPODOBNE)
            s.przydziel(o, znalezione, f'suma {len(znalezione)} faktur nabywcy', p, z)
            zapisz(o, 'dopasowana', uwaga=o.get('_uwaga', ''))

    # 6. Kwota + data, bez nazwy: tylko jeden kandydat w 60 dniach
    for o in filter(wolna, ops):
        trafione = [n for n in kandydaci(o, False) if s.pozostalo[n] == o['kwota']
                    and 0 <= (o['_dzien'] - faktury[n]['_dzien']).days <= 60]
        if len(trafione) == 1:
            p, z = pewnosc_auto(o, trafione, PRAWDOPODOBNE)
            s.przydziel(o, trafione, 'kwota i data', p, z)
            zapisz(o, 'dopasowana', uwaga=o.get('_uwaga', ''))

    # Reszta: bez dopasowania, z podpowiedzią (ta sama nazwa nabywcy, faktury z saldem)
    for o in filter(wolna, ops):
        podobne = sorted(kandydaci(o, True), key=lambda n: abs((o['_dzien'] - faktury[n]['_dzien']).days))[:3]
        zapisz(o, 'nieznana', uwaga=o.get('_uwaga', ''), podpowiedz=('może: ' + ', '.join(podobne)) if podobne else '')

    # Zapis do bazy
    con.executemany('INSERT INTO dopasowania (operacja_id, numer, kwota, metoda, pewnosc, zrodlo) VALUES (?,?,?,?,?,?)',
                    s.dopasowania)
    pewnosci = {}
    for op_id, _, _, _, p, _ in s.dopasowania:
        pewnosci[op_id] = PRAWDOPODOBNE if PRAWDOPODOBNE in (p, pewnosci.get(op_id)) else PEWNE
    for o in ops:
        w = wynik[o['id']]
        con.execute('INSERT INTO wplaty (operacja_id, stan, pewnosc, nadplata, uwaga, podpowiedz, wpis) VALUES (?,?,?,?,?,?,?)',
                    (o['id'], w['stan'], pewnosci.get(o['id'], ''), w['nadplata'], w['uwaga'], w['podpowiedz'],
                     reczne['wpis_op'].get(o['klucz'], '') if o['klucz'] in reczne['polacz'] or o['klucz'] in reczne['bez_faktury'] else ''))

    ostatnia = {}
    for op_id, n, kwota, *_ in s.dopasowania:
        d = next(o['data_ksiegowania'] for o in ops if o['id'] == op_id)
        ostatnia[n] = max(ostatnia.get(n, ''), d)
    for n, f in faktury.items():
        zaplacono = f['naleznosc'] - s.pozostalo[n]
        if n in reczne['poza_bankiem'] and s.pozostalo[n] > 0:
            stan, pozostalo = 'opłacona poza bankiem', 0
        elif f['naleznosc'] <= 0 or s.pozostalo[n] <= 0:
            stan, pozostalo = 'opłacona', 0
        elif zaplacono > 0:
            stan, pozostalo = 'częściowo', s.pozostalo[n]
        else:
            stan, pozostalo = 'nieopłacona', s.pozostalo[n]
        dni = (_dzien(dzien_stanu) - _dzien(f['termin'])).days if pozostalo and f['termin'] and dzien_stanu else 0
        con.execute('INSERT INTO faktury_stan (numer, naleznosc, korekty, zaplacono, pozostalo, stan, dni_po_terminie,'
                    ' przedzial, ostatnia_wplata, uwaga, wpis) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (n, f['naleznosc'], f['korekty'], zaplacono, pozostalo, stan, max(dni, 0), przedzial(dni) if pozostalo else '',
                     ostatnia.get(n, ''), reczne['poza_bankiem'].get(n, ''), reczne['wpis_fv'].get(n, '') if n in reczne['poza_bankiem'] else ''))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('dzien_stanu', ?)", (dzien_stanu or '',))
    return {'wplat': len(ops), 'dopasowanych': sum(1 for w in wynik.values() if w['stan'] == 'dopasowana')}


def przedzial(dni: int) -> str:
    if dni <= 0:
        return 'przed terminem'
    if dni <= 30:
        return '1–30 dni'
    if dni <= 60:
        return '31–60 dni'
    if dni <= 90:
        return '61–90 dni'
    return 'ponad 90 dni'
