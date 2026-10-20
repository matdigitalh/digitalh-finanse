"""Łączenie budżetu z rzeczywistością i rozjazdy BS ↔ bank ↔ Fakturownia.

Od pakietu 5 (decyzja Mata 2026-10-19, pkt 2) dokument rzeczywisty (faktura z Fakturowni, dokument z rejestru biura,
przelew ING bez dokumentu, płatność dodana ręcznie) wchodzi do budżetu wyłącznie kliknięciem „Połącz” (zdarzenie „bud”
op „polacz”, budzet.py). Ta warstwa:
  - czyta dokumenty z bazy (Dokumenty, wszystkie_dokumenty) i liczy dla każdego niepołączonego PODPOWIEDŹ planu
    (arkusz, wiersz, miesiąc) z pewnością i uzasadnieniem: lista „Do połączenia” (bud_laczenie),
  - nadaje płatnościom budżetu etap z banku i Fakturowni (jak dotąd): „Opłacona” wyłącznie z banku albo z decyzji Mata
    z datą (wyjątek poza bankiem); etap BS „Niewymagana” NIGDY nie znaczy „opłacona” (poprawka błędu z pakietu 8),
  - nie zamyka sama płatności: dokumenty od dnia „Łączenie w apce od” nie wiążą się z planami automatycznie (plan dostaje
    tylko podpowiedź), a plan wynagrodzenia nigdy nie staje się opłacony z przelewu (decyzja 12, lista płac).

Starsze dokumenty (sprzed startu łączenia w apce) wiążą się jak w zadaniu nocnym: przychód ↔ faktura (numer, potem klient
+ kwota netto + miesiąc ±1), koszt ↔ dokument z rejestru ↔ bank albo wprost bank (kwota brutto, ±5 dni karta, ±3 przelew),
koszty pracy, VAT, podatek dochodowy sumą w miesiącu płatności.
"""
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from . import plan
from .dopasowanie import klucz_fv, tokeny

LACZENIE_OD_DOMYSLNIE = '2026-11-01'


def _d(s):
    return date.fromisoformat(s[:10]) if s else None


def _alnum(s):
    return re.sub(r'[^0-9A-Z]', '', (s or '').upper())


def _koniec_miesiaca(m: str) -> str:
    r, mm = int(m[:4]), int(m[5:7])
    nastepny = date(r + (mm == 12), 1 if mm == 12 else mm + 1, 1)
    return (nastepny - timedelta(days=1)).isoformat()


def laczenie_od(con) -> str:
    """Dzień, od którego dokumenty łączy Mat w apce (ustawienie „laczenie_od”, domyślnie 1.11.2026). Wcześniejsze są
    połączone w Budget Studio i przychodzą z kopii albo eksportu BS."""
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='laczenie_od'").fetchone()
    return r[0] if r and r[0] else LACZENIE_OD_DOMYSLNIE


# ---------- Dokumenty rzeczywiste (źródła płatności rzeczywistych, pakiet 5) ----------

def _stawka(netto, vat):
    from .budzet import stawka_proc
    if not netto:
        return None
    return stawka_proc(str(Decimal(int(vat or 0)) / Decimal(int(netto))))


def _krotko(nazwa):
    from .klienci import krotka_nazwa
    return krotka_nazwa(nazwa or '') or (nazwa or '')


def _z_faktury(r) -> dict:
    oplacono = r['ostatnia_wplata'] if r['stan'] in ('opłacona', 'opłacona poza bankiem') and r['ostatnia_wplata'] else None
    sprzedaz = r['data_sprzedazy'] or r['data_wystawienia'] or ''
    return {'ref': f"faktura:{r['numer']}", 'typ': 'faktura', 'rodzaj': 1, 'rodzina': 'Faktura', 'kontrahent': _krotko(r['nabywca']),
            'nip': r['nip'] or '', 'klient': r['klient'] or '', 'nr_dok': r['numer'], 'nr_wewn': '', 'netto': r['netto'] or 0,
            'vat': r['vat'] or 0, 'brutto': r['brutto'] or 0, 'kwota': r['netto'] or 0, 'stawka': _stawka(r['netto'], r['vat']),
            'wystawienie': r['data_wystawienia'], 'sprzedaz': sprzedaz, 'termin': r['termin'], 'realny': oplacono or r['termin'],
            'oplacono': oplacono, 'ksiegowanie': f'{sprzedaz[:7]}-01', 'tytul': r['pozycje'] or '', 'komentarz': '',
            'zrodlo': 'Fakturownia', 'data': r['data_wystawienia']}


def _z_zakupu(r) -> dict:
    netto = r['netto'] or 0
    vat = r['vat'] if r['vat'] is not None else 0
    brutto = r['brutto'] if r['brutto'] is not None else netto + vat
    oplacono = r['data_op']
    return {'ref': f"zakup:{r['nr_ewid']}", 'typ': 'zakup', 'rodzaj': -1, 'rodzina': 'Faktura', 'kontrahent': _krotko(r['podmiot']),
            'nip': '', 'klient': '', 'nr_dok': r['nr_dok'] or '', 'nr_wewn': r['nr_ewid'], 'netto': netto, 'vat': vat, 'brutto': brutto,
            'kwota': netto, 'stawka': _stawka(netto, vat), 'wystawienie': r['data'], 'sprzedaz': r['data'], 'termin': oplacono,
            'realny': oplacono, 'oplacono': oplacono, 'ksiegowanie': f"{(r['data'] or '')[:7]}-01", 'tytul': f"rejestr {r['rejestr']}",
            'komentarz': '', 'zrodlo': 'rejestr biura', 'data': r['data'], 'operacja_id': r['operacja_id']}


def _z_operacji(r) -> dict:
    kw = abs(r['kwota'])
    d = r['data_ksiegowania']
    return {'ref': f"operacja:{r['klucz']}", 'typ': 'operacja', 'rodzaj': 1 if r['kwota'] > 0 else -1, 'rodzina': 'bank',
            'kontrahent': _krotko(r['kontrahent'] or r['opis']), 'nip': '', 'klient': '', 'nr_dok': '', 'nr_wewn': '',
            'netto': kw, 'vat': 0, 'brutto': kw, 'kwota': kw, 'stawka': None, 'wystawienie': d, 'sprzedaz': d, 'termin': d,
            'realny': d, 'oplacono': d, 'ksiegowanie': f'{d[:7]}-01', 'tytul': r['tytul'] or r['opis'] or '', 'komentarz': '',
            'zrodlo': 'bank ING', 'data': d, 'operacja_id': r['id']}


SQL_FAKTURY = ("SELECT f.numer, f.nabywca, f.nip, f.netto, f.vat, f.brutto, f.data_wystawienia, f.data_sprzedazy, f.termin, fk.klient,"
               " s.stan, s.ostatnia_wplata, (SELECT GROUP_CONCAT(nazwa, ' | ') FROM faktury_pozycje p WHERE p.numer = f.numer) AS pozycje"
               ' FROM faktury f LEFT JOIN faktury_stan s USING(numer) LEFT JOIN faktury_klient fk USING(numer) WHERE f.korekta = 0')
SQL_ZAKUPY = ('SELECT z.*, s.operacja_id, (SELECT data_ksiegowania FROM operacje o WHERE o.id = s.operacja_id) AS data_op'
              ' FROM zakupy z LEFT JOIN zakupy_stan s USING(nr_ewid)')
# Przelew bez dokumentu: wydatek bez dokumentu z rejestru (wynagrodzenia, ZUS, PIT-4, VAT i podatki z reguł wbudowanych
# idą listą płac i arkuszem Opłaty urzędowe) i wpłata, która nie dotyczy faktury (zwrot, cashback).
SQL_OPERACJE = ("SELECT o.* FROM operacje o JOIN wydatki w ON w.operacja_id = o.id WHERE o.wewnetrzna = 0 AND o.kwota < 0"
                " AND NOT EXISTS (SELECT 1 FROM wydatki_dok d WHERE d.operacja_id = o.id) AND w.rodzaj != 'zwrocony'"
                " AND NOT (w.zrodlo = 'reguła wbudowana' AND w.rodzaj IN ('praca', 'vat', 'podatki'))"
                " UNION ALL SELECT o.* FROM operacje o JOIN wplaty p ON p.operacja_id = o.id WHERE o.wewnetrzna = 0 AND p.stan = 'bez_faktury'")


class Dokumenty:
    """ref → dokument rzeczywisty z bazy (dla zdarzeń „polacz” przy odbudowie i przy sprawdzaniu wpisu)."""

    def __init__(self, con):
        self.con = con

    def __call__(self, ref: str) -> dict | None:
        typ, _, klucz = ref.partition(':')
        if typ == 'faktura':
            r = self.con.execute(f'{SQL_FAKTURY} AND f.numer = ?', (klucz,)).fetchone()
            return _z_faktury(r) if r else None
        if typ == 'zakup':
            r = self.con.execute(f'{SQL_ZAKUPY} WHERE z.nr_ewid = ?', (klucz,)).fetchone()
            return _z_zakupu(r) if r else None
        if typ == 'operacja':
            r = self.con.execute(f'SELECT * FROM ({SQL_OPERACJE}) WHERE klucz = ?', (klucz,)).fetchone()
            return _z_operacji(r) if r else None
        return None


def wszystkie_dokumenty(con) -> list[dict]:
    """Każdy dokument rzeczywisty, który może trafić do budżetu (bez ruchu wewnętrznego i bez danin z reguł wbudowanych)."""
    from .budzet import dokument_reczny
    wynik = [_z_faktury(r) for r in con.execute(SQL_FAKTURY)]
    wynik += [_z_zakupu(r) for r in con.execute(SQL_ZAKUPY) if (r['netto'] or r['brutto'])]
    wynik += [_z_operacji(r) for r in con.execute(SQL_OPERACJE)]
    for r in con.execute('SELECT dane FROM bud_reczne'):
        wynik.append(dokument_reczny(json.loads(r[0])))
    return wynik


# ---------- Etap, powiązania z bankiem i Fakturownią, rozjazdy ----------

def _wynagrodzenie(p: dict) -> bool:
    """Płatność wynagrodzenia (umowa, składowa PIT albo ZUS, wiersz listy płac): plan nigdy nie zamyka się sam."""
    return bool(p['skladowa'] or (p['podstawa'] or '').startswith('Umowa') or p.get('lista_plac'))


def policz(con) -> dict:
    dzien_stanu = (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0]
    dzis = _d(dzien_stanu) if dzien_stanu else date.today()
    od = laczenie_od(con)
    platnosci = [dict(r) for r in con.execute(
        "SELECT p.*, COALESCE(NULLIF(p.kontrahent, ''), w.kontrahent) AS w_kontrahent, w.podstawa, w.lista_plac, a.folder,"
        ' a.nazwa AS arkusz_nazwa, a.id AS arkusz_id FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz')]
    faktury = {r['numer']: dict(r) for r in con.execute(
        'SELECT f.numer, f.netto, f.brutto, f.data_sprzedazy, f.data_wystawienia, fk.klient, s.stan, s.pozostalo, s.ostatnia_wplata,'
        ' s.dni_po_terminie FROM faktury f LEFT JOIN faktury_klient fk USING(numer) LEFT JOIN faktury_stan s USING(numer) WHERE f.korekta = 0')}
    po_kluczu = {klucz_fv(n): n for n in faktury if klucz_fv(n)}
    wszystkie_zakupy = [dict(r) for r in con.execute(
        'SELECT z.nr_ewid, z.nr_dok, z.podmiot, z.brutto, z.netto, s.operacja_id FROM zakupy z LEFT JOIN zakupy_stan s USING(nr_ewid)')]
    zakupy = {_alnum(z['nr_dok']): z for z in wszystkie_zakupy if len(_alnum(z['nr_dok'])) >= 4}
    zakup_po_ewid = {z['nr_ewid']: z for z in wszystkie_zakupy}
    wydatki = [dict(r) for r in con.execute(
        'SELECT o.id, o.data_ksiegowania, o.kwota, o.kontrahent, o.opis, o.tytul FROM operacje o JOIN wydatki w ON w.operacja_id = o.id')]
    op_po_kluczu = {r['klucz']: r['id'] for r in con.execute('SELECT id, klucz FROM operacje')}
    for x in wydatki:
        x['_tok'] = tokeny(x['kontrahent'] or x['opis'])
        x['_d'] = _d(x['data_ksiegowania'])
        x['_karta'] = 'kart' in f"{x['opis']} {x['tytul']}".lower()

    powiazania, stany, rozjazdy_grup, podpowiedzi_bank = [], {}, [], {}
    zajete_fv, zajete_op = set(), set()

    # 0. Płatności połączone w apce (pakiet 5): dokument wskazany wprost, bez zgadywania
    for p in platnosci:
        typ, _, ref = (p['dokument'] or '').partition(':')
        if typ == 'faktura' and ref in faktury:
            powiazania.append((p['id'], 'faktura', ref, p['netto'], 'połączone w apce', 'pewne'))
            zajete_fv.add(ref)
        elif typ == 'zakup' and ref in zakup_po_ewid:
            z = zakup_po_ewid[ref]
            powiazania.append((p['id'], 'dokument', ref, p['netto'], 'połączone w apce', 'pewne'))
            if z['operacja_id']:
                powiazania.append((p['id'], 'bank', str(z['operacja_id']), p['brutto'], 'przez dokument', 'pewne'))
                zajete_op.add(z['operacja_id'])
        elif typ == 'operacja' and ref in op_po_kluczu:
            powiazania.append((p['id'], 'bank', str(op_po_kluczu[ref]), p['brutto'], 'połączone w apce', 'pewne'))
            zajete_op.add(op_po_kluczu[ref])
    z_apki = {p['id'] for p in platnosci if p['dokument']}
    fv_z_apki, op_z_apki = set(zajete_fv), set(zajete_op)

    # 1. Przychody ↔ faktury: najpierw numer dokumentu (płatność z BS), potem klient + kwota netto + miesiąc ±1, ale tylko
    #    dla faktur sprzed startu łączenia w apce (nowsze czekają w „Do połączenia” z podpowiedzią)
    przychody = [p for p in platnosci if p['rodzaj'] == 1 and p['id'] not in z_apki]
    for p in przychody:
        n = po_kluczu.get(klucz_fv(p['nr_dok'])) if p['nr_dok'] else None
        if n and n not in fv_z_apki:   # jedna faktura bywa w BS na kilku wierszach (suma porównana niżej)
            powiazania.append((p['id'], 'faktura', n, faktury[n]['netto'], 'numer dokumentu', 'pewne'))
            zajete_fv.add(n)
    polaczone = {x[0] for x in powiazania}
    for p in przychody:
        if p['id'] in polaczone or not p['aktualna']:
            continue
        m = _d(p['miesiac'] + '-01')
        kand = [n for n, f in faktury.items() if n not in zajete_fv and f['klient'] == p['folder'] and f['netto'] == p['netto']
                and (f['data_wystawienia'] or '') < od
                and abs(((_d((f['data_sprzedazy'] or f['data_wystawienia'])[:7] + '-01')) - m).days) <= 31]
        if kand:
            n = min(kand, key=lambda n: abs((_d((faktury[n]['data_sprzedazy'] or faktury[n]['data_wystawienia'])[:7] + '-01') - m).days))
            powiazania.append((p['id'], 'faktura', n, faktury[n]['netto'], 'klient, kwota i miesiąc', 'prawdopodobne'))
            zajete_fv.add(n)

    # 2. Koszty ↔ dokument z rejestru (numer) ↔ bank; potem wprost bank (kwota brutto i okno dat). Plan wiąże się z bankiem
    #    tylko sprzed startu łączenia w apce i nigdy plan wynagrodzenia; rzeczywista (z BS, ręczna, zamiana) zawsze.
    koszty = [p for p in platnosci if p['rodzaj'] == -1]
    for p in koszty:
        if p['id'] in z_apki:
            continue
        z = zakupy.get(_alnum(p['nr_dok'])) if p['nr_dok'] else None
        if z:
            powiazania.append((p['id'], 'dokument', z['nr_ewid'], z['netto'] or 0, 'numer dokumentu', 'pewne'))
            if z['operacja_id'] and z['operacja_id'] not in op_z_apki:
                powiazania.append((p['id'], 'bank', str(z['operacja_id']), p['brutto'], 'przez dokument', 'pewne'))
                zajete_op.add(z['operacja_id'])
    z_bankiem = {x[0] for x in powiazania if x[1] == 'bank'}
    kandydaci = []
    for p in koszty:
        if p['id'] in z_bankiem or (p['typ'] == 'plan' and _wynagrodzenie(p)):
            continue
        dp = _d(p['realny'] or p['termin'] or _koniec_miesiaca(p['miesiac']))
        tok = tokeny(p['w_kontrahent'])
        for x in wydatki:
            if -x['kwota'] != p['brutto'] or x['id'] in zajete_op:
                continue
            if p['typ'] == 'plan' and x['data_ksiegowania'] >= od:
                continue
            dd = abs((x['_d'] - dp).days)
            nazwa = bool(tok & x['_tok'])
            if dd <= (5 if x['_karta'] else 3) or (nazwa and dd <= 20):
                kandydaci.append((dd / 100 + (0 if nazwa else 1), p['id'], x['id'], nazwa))
    kandydaci.sort()
    for _, pid, oid, nazwa in kandydaci:
        if pid in z_bankiem or oid in zajete_op:
            continue
        powiazania.append((pid, 'bank', str(oid), None, 'kwota i data' + (' i nazwa' if nazwa else ''), 'pewne' if nazwa else 'prawdopodobne'))
        z_bankiem.add(pid)
        zajete_op.add(oid)

    # 2b. Koszty pracy, VAT i podatek dochodowy: w BS jedna kwota (koszt pracodawcy, VAT za miesiąc), w banku kilka
    #     przelewów (wypłata, ZUS, PIT-4, PPK; dwie wpłaty VAT). Porównujemy sumy w miesiącu faktycznej płatności:
    #     BS wg dnia płatności (realny, inaczej termin), bank wg daty księgowania, tylko przelewy z reguł wbudowanych.
    #     Plan wynagrodzenia nie staje się opłacony z przelewu (decyzja 12): dostaje tylko podpowiedź „jest przelew”.
    wbudowane = {r[0]: r[1] for r in con.execute("SELECT operacja_id, rodzaj FROM wydatki WHERE zrodlo = 'reguła wbudowana'")}

    def grupa_bs(p):
        if p['podstawa'].startswith(('Umowa o pracę', 'Umowa zlecenie', 'Umowa o dzieło')) or p['lista_plac'] or (
                'pracownic' in p['arkusz_nazwa'].lower() and p['podstawa'].startswith('Bez faktury')):
            return 'praca'
        return {'Podatek VAT': 'vat', 'Podatek dochodowy': 'podatki'}.get(p['podstawa'])
    bs_grupy, bank_grupy = defaultdict(list), defaultdict(list)
    for p in koszty:
        g = grupa_bs(p)
        if g and p['aktualna']:
            bs_grupy[(g, (p['realny'] or p['termin'] or p['miesiac'])[:7])].append(p)
    for x in wydatki:
        g = wbudowane.get(x['id'])
        if g in ('praca', 'vat', 'podatki'):
            bank_grupy[(g, x['data_ksiegowania'][:7])].append(x)
    for klucz_g, ps in bs_grupy.items():
        ops = bank_grupy.get(klucz_g, [])
        suma_bs, suma_bank = sum(p['brutto'] for p in ps), sum(-x['kwota'] for x in ops)
        if klucz_g[1] > (dzien_stanu or '')[:7]:
            continue
        if ops and abs(suma_bs - suma_bank) <= max(100, suma_bs * 5 // 100):
            for p in ps:
                if p['id'] in z_bankiem:
                    continue
                if p['typ'] == 'plan' and klucz_g[0] == 'praca':
                    podpowiedzi_bank[p['id']] = f'jest przelew w {klucz_g[1]} (suma {suma_bank} gr); kwoty wpisz listą płac'
                    continue
                for x in ops:
                    powiazania.append((p['id'], 'bank', str(x['id']), None, f'suma w miesiącu ({klucz_g[0]} {klucz_g[1]})', 'prawdopodobne'))
                z_bankiem.add(p['id'])
            zajete_op.update(x['id'] for x in ops)
        else:
            nazwa = {"praca": "koszty pracy", "vat": "VAT", "podatki": "podatek dochodowy"}[klucz_g[0]]
            rozjazdy_grup.append((f'Suma w BS inna niż w banku ({nazwa})', f'{klucz_g[0]}:{klucz_g[1]}', suma_bs - suma_bank,
                                  f'płatności w {klucz_g[1]}: BS {suma_bs} gr ({len(ps)} pozycji), bank {suma_bank} gr ({len(ops)} przelewów)'))

    # 3. Etap z danych. „Opłacona” wyłącznie z banku (albo faktury opłaconej w banku) i z decyzji Mata z datą (wyjątek
    #    poza bankiem). Etap BS „Niewymagana” to rzeczywista NIEopłacona przed terminem: zostaje w cash flow (poprawka).
    #    „Opłacona wg BS” (słabszy stan, kreska) tylko dla rzeczywistej, którą BS ma jako opłaconą, a w danych nie ma
    #    przelewu; przy wynagrodzeniu tylko z minionym terminem (przyszłe PIT i ZUS zostają w cash flow).
    data_op = {x['id']: x['data_ksiegowania'] for x in wydatki}
    po_platnosci = defaultdict(list)
    for x in powiazania:
        po_platnosci[x[0]].append(x)
    dzis_iso = dzis.isoformat()
    for p in platnosci:
        pow_ = po_platnosci.get(p['id'], [])
        termin = p['termin'] or _koniec_miesiaca(p['miesiac'])
        uwaga, zaplacono, data_z = '', 0, None
        fv = next((x[2] for x in pow_ if x[1] == 'faktura'), None)
        op = next((x[2] for x in pow_ if x[1] == 'bank'), None)
        if not p['aktualna']:
            etap = 'Nieaktualna'
        elif p['decyzja'] == 'zapłacone (Mat)':
            etap, data_z = 'Opłacona', p['realny']
            uwaga = 'oznaczone przez Mata'
        elif fv:
            f = faktury[fv]
            if f['stan'] in ('opłacona', 'opłacona poza bankiem'):
                etap, zaplacono, data_z = 'Opłacona', p['brutto'], f['ostatnia_wplata']
            elif f['stan'] == 'częściowo':
                etap = 'Częściowo opłacona'
            else:
                etap = 'Po terminie' if (f['dni_po_terminie'] or 0) > 0 else 'Wystawiona'
            uwaga = f'faktura {fv}'
        elif op:
            etap, zaplacono, data_z = 'Opłacona', p['brutto'], data_op.get(int(op))
        elif p['typ'] != 'plan' and p['etap_bs'] == 'Opłacona' and (not _wynagrodzenie(p) or (p['realny'] or termin) < dzis_iso):
            etap, uwaga = 'Opłacona wg BS', ('brak faktury w eksporcie Fakturowni albo wpłaty w banku' if p['rodzaj'] == 1
                                             else 'nie znaleziono płatności w banku')
        elif _d(termin) < dzis:
            etap = 'Po terminie'
        else:
            etap = 'Planowana'
        if p['id'] in podpowiedzi_bank and etap != 'Opłacona':
            uwaga = podpowiedzi_bank[p['id']]
        # etap i aktualność wg reguł BS (opłacona = z banku albo decyzja Mata z datą), obok naszego etapu
        oplacona = etap == 'Opłacona'
        etap_bs = plan.etap_wg_bs(p['typ'], oplacona, p['termin'], dzis_iso)
        akt = plan.aktualna_wg_bs(p['typ'], oplacona, p['wystawienie'], p['termin'], p['realny'], dzis_iso)
        stany[p['id']] = (etap, zaplacono, data_z, termin, uwaga, etap_bs, 'Aktualna' if akt else 'Nieaktualna')

    con.executemany('INSERT INTO bud_powiazanie (platnosc, typ, ref, kwota, metoda, pewnosc) VALUES (?,?,?,?,?,?)', powiazania)
    con.executemany('INSERT INTO bud_stan (platnosc, etap, zaplacono, data_zaplaty, termin_efektywny, uwaga, etap_wg_bs, aktualnosc)'
                    ' VALUES (?,?,?,?,?,?,?,?)',
                    [(k, *v) for k, v in stany.items()])

    # 4. Rozjazdy BS ↔ bank ↔ Fakturownia (lista do decyzji Mata)
    rozjazdy = list(rozjazdy_grup)
    for p in platnosci:
        etap = stany[p['id']][0]
        if p.get('bs_id') is None or not p['aktualna']:
            continue
        if p['etap_bs'] == 'Opłacona' and etap == 'Opłacona wg BS':
            rozjazdy.append(('Opłacone w BS, brak w danych', p['id'], p['brutto'], stany[p['id']][4]))
        elif p['etap_bs'] in ('Planowana', 'Po terminie') and etap == 'Opłacona':
            rozjazdy.append(('Zapłacone w banku, w BS nadal planowane', p['id'], p['brutto'], 'zaktualizuj w BS albo zostaw: od 2027 liczy apka'))

    # Jedna faktura bywa na kilka wierszy planu (np. Google Ads + Social + SEO + wideo): porównujemy sumę planu z fakturą.
    na_fakture = defaultdict(list)
    for x in powiazania:
        if x[1] == 'faktura':
            na_fakture[x[2]].append(x[0])
    netto_p = {p['id']: p['netto'] for p in platnosci}
    aktualne = {p['id'] for p in platnosci if p['aktualna']}
    for n, ids in na_fakture.items():
        if all(i in z_apki for i in ids):
            continue   # faktura połączona w apce: części sumują się do kwoty dokumentu z definicji
        suma = sum(netto_p.get(i, 0) for i in ids)
        if not any(i in aktualne for i in ids):
            rozjazdy.append(('Faktura przy pozycji nieaktualnej w BS', ids[0], faktury[n]['netto'],
                             f"faktura {n} (netto {faktury[n]['netto']} gr) jest w BS przy pozycji oznaczonej jako nieaktualna"))
        elif abs(suma - faktury[n]['netto']) > 100:
            rozjazdy.append(('Kwota w BS inna niż na fakturze', ids[0], suma - faktury[n]['netto'],
                             f"faktura {n}: netto {faktury[n]['netto']} gr, w BS {suma} gr ({len(ids)} pozycji)"))
    for n, f in faktury.items():   # od startu łączenia w apce takie faktury są w „Do połączenia”, nie w rozjazdach
        if n not in zajete_fv and '2026-01-01' <= (f['data_wystawienia'] or '') < od:
            rozjazdy.append(('Faktura bez pozycji w BS', n, f['netto'], f"klient {f['klient'] or '?'}; propozycja wiersza w arkuszu klienta"))
    duze = [x for x in wydatki if x['id'] not in zajete_op and -x['kwota'] >= 20000 and x['data_ksiegowania'] < od]
    for x in duze:
        rozjazdy.append(('Wydatek z banku bez pozycji w BS', str(x['id']), -x['kwota'], f"{x['data_ksiegowania']} {x['kontrahent'] or x['opis']}"))
    con.executemany('INSERT INTO bud_rozjazd (rodzaj, ref, kwota, opis) VALUES (?,?,?,?)', rozjazdy)

    # 5. Dokumenty rzeczywiste: stan łączenia i podpowiedź planu (lista „Do połączenia”)
    ile = zbuduj_do_polaczenia(con, powiazania, od, platnosci)
    return {'powiazan': len(powiazania), 'rozjazdow': len(rozjazdy), 'do_polaczenia': ile}


# ---------- „Do połączenia”: stan dokumentu i podpowiedź planu (B-LACZ-01, decyzja Mata pkt 2) ----------

def _w_budzecie(powiazania, platnosci) -> dict:
    """Dokument → płatności rzeczywiste, które go reprezentują w budżecie (z BS po numerze albo przelewie). Powiązanie
    z planem (stary automat sprzed startu łączenia) nie liczy się jako połączenie."""
    typ = {p['id']: p['typ'] for p in platnosci}
    wynik = defaultdict(list)
    for pid, t, ref, *_ in powiazania:
        if typ.get(pid) != 'plan':
            wynik[{'faktura': f'faktura:{ref}', 'dokument': f'zakup:{ref}', 'bank': f'op:{ref}'}[t]].append(pid)
    return wynik


def kandydaci_komorek(con) -> list[dict]:
    """Komórki z planem, do których może trafić rzeczywista: plan w komórce (choćby 0), wiersz faktura albo bez faktury,
    nie wynagrodzenie (lista płac) i nie arkusz systemowy. Kwota planu: netto i brutto planów komórki."""
    wynik = []
    for r in con.execute(
            "SELECT p.wiersz, p.miesiac, SUM(p.netto) AS netto, SUM(p.brutto) AS brutto, COUNT(*) AS planow, MIN(p.id) AS plan,"
            " GROUP_CONCAT(DISTINCT COALESCE(NULLIF(p.kontrahent, ''), w.kontrahent)) AS kontrahenci,"
            " w.rodzaj, w.podstawa, w.kontrahent, w.komentarz, w.przedmiot, a.id AS arkusz, a.nazwa AS arkusz_nazwa, a.folder,"
            " (SELECT COUNT(*) FROM bud_platnosc r WHERE r.wiersz = p.wiersz AND r.miesiac = p.miesiac AND r.typ != 'plan') AS rzeczywistych"
            " FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz"
            " WHERE p.typ = 'plan' AND COALESCE(a.zrodlo, '') != 'system' AND COALESCE(w.lista_plac, 0) = 0"
            " AND w.podstawa IN ('Faktura (jedna)', 'Faktura (w worku)', 'Bez faktury', 'Bez faktury (w worku)')"
            ' GROUP BY p.wiersz, p.miesiac'):
        x = dict(r)
        x['_tok'] = tokeny(' '.join(filter(None, [x['kontrahent'], x['kontrahenci'] or ''])))
        x['worek'] = x['podstawa'] in plan.WOREK
        wynik.append(x)
    return wynik


def _historia_wierszy(con) -> dict:
    """Wiersz → słowa nazw i NIP-y kontrahentów dokumentów połączonych z nim wcześniej (BS i apka)."""
    hist = defaultdict(set)
    for r in con.execute("SELECT p.wiersz, f.nip, f.nabywca FROM bud_powiazanie b JOIN bud_platnosc p ON p.id = b.platnosc"
                         " JOIN faktury f ON f.numer = b.ref WHERE b.typ = 'faktura' AND p.typ != 'plan'"):
        if r['nip']:
            hist[r['wiersz']].add(f"nip:{r['nip']}")
        hist[r['wiersz']].update(tokeny(r['nabywca']))
    for r in con.execute("SELECT p.wiersz, z.podmiot FROM bud_powiazanie b JOIN bud_platnosc p ON p.id = b.platnosc"
                         " JOIN zakupy z ON z.nr_ewid = b.ref WHERE b.typ = 'dokument' AND p.typ != 'plan'"):
        hist[r['wiersz']].update(tokeny(r['podmiot']))
    for r in con.execute("SELECT p.wiersz, o.kontrahent, o.opis FROM bud_powiazanie b JOIN bud_platnosc p ON p.id = b.platnosc"
                         " JOIN operacje o ON o.id = CAST(b.ref AS INTEGER) WHERE b.typ = 'bank' AND p.typ != 'plan'"):
        hist[r['wiersz']].update(tokeny(r['kontrahent'] or r['opis']))
    for r in con.execute("SELECT wiersz, kontrahent FROM bud_platnosc WHERE typ != 'plan' AND COALESCE(dokument, '') != ''"):
        hist[r['wiersz']].update(tokeny(r['kontrahent']))
    return hist


def _rozne_miesiace(a: str, b: str) -> int:
    return abs((int(a[:4]) - int(b[:4])) * 12 + int(a[5:7]) - int(b[5:7]))


def zgodna(x: dict, k: dict) -> bool:
    """Twarde warunki BS: ten sam rodzaj, zgodna podstawa (faktura ↔ faktura i worek faktur, bez faktury ↔ bez faktury;
    przelew bez dokumentu przyjmie podstawę wiersza)."""
    if k['rodzaj'] != x['rodzaj']:
        return False
    rodzina = 'Faktura' if k['podstawa'].startswith('Faktura') else 'Bez faktury'
    return x['rodzina'] == 'bank' or x['rodzina'] == rodzina


def kwota_planu(x: dict, k: dict) -> int:
    """Kwota planu w jednostkach dokumentu: netto, a przy przelewie bez dokumentu do wiersza z fakturą brutto."""
    return k['brutto'] if x['rodzina'] == 'bank' and k['podstawa'].startswith('Faktura') else k['netto']


def ocen(x: dict, k: dict, hist: dict) -> tuple[int, list[str], int]:
    """Punkty podpowiedzi (0 do 100) dla pary dokument × komórka z planem, uzasadnienie po ludzku i różnica kwot
    (plan − dokument). Kolejność kryteriów jak w BS: kontrahent, kwota, miesiąc, historia wcześniejszych połączeń."""
    pkt, why = 0, []
    tok_x = x.get('_tok') if x.get('_tok') is not None else tokeny(x['kontrahent'])
    if x.get('klient') and x['klient'].casefold() == (k['folder'] or '').casefold():
        pkt += 35
        why.append(f"ten sam klient (folder {k['folder']})")
    if tok_x & k['_tok']:
        pkt += 30 if x['typ'] == 'faktura' else 40
        why.append('kontrahent jak w wierszu')
    h = hist.get(k['wiersz'], set())
    if (x.get('nip') and f"nip:{x['nip']}" in h) or (tok_x and tok_x & h):
        pkt += 25
        why.append('wcześniej łączone z tym wierszem')
    plan_kw = kwota_planu(x, k)
    roznica = plan_kw - x['kwota']
    if x['kwota'] and plan_kw:
        r = abs(roznica) / x['kwota']
        if r == 0:
            pkt += 25
            why.append('kwota równa planowi')
        elif r <= 0.02:
            pkt += 20
            why.append('kwota prawie równa planowi')
        elif r <= 0.3:
            pkt += 12 if r <= 0.1 else 5
            why.append(f'kwota różni się o {round(r * 100)}%')
        elif k['worek'] and x['kwota'] <= plan_kw:
            pkt += 10
            why.append('mieści się w worku')
    mies = (x.get('sprzedaz') or x.get('wystawienie') or x.get('data') or '')[:7]
    if mies:
        dm = _rozne_miesiace(mies, k['miesiac'])
        if dm == 0:
            pkt += 15
            why.append('ten sam miesiąc')
        elif dm == 1:
            pkt += 8
            why.append('miesiąc obok')
        elif dm == 2:
            pkt += 2
        else:
            pkt -= 10 * (dm - 2)
    return max(0, min(100, pkt)), why, roznica


PROGI_PEWNOSCI = ((70, 'wysoka'), (45, 'średnia'), (30, 'niska'))


def pewnosc(pkt: int) -> str | None:
    return next((n for prog, n in PROGI_PEWNOSCI if pkt >= prog), None)


def podpowiedzi(con, x: dict, n: int = 8, komorki=None, hist=None, q: str = '') -> list[dict]:
    """Najlepsze komórki z planem dla dokumentu (ekran łączenia: lewa kolumna). q: wyszukiwarka komórek (arkusz, folder,
    kontrahent, komentarz, przedmiot, miesiąc); z frazą pokazujemy też komórki z niskimi punktami."""
    komorki = komorki if komorki is not None else kandydaci_komorek(con)
    hist = hist if hist is not None else _historia_wierszy(con)
    f = q.casefold().strip()
    wynik = []
    for k in komorki:
        if not zgodna(x, k):
            continue
        if f and f not in ' '.join(str(k.get(c) or '') for c in ('arkusz_nazwa', 'folder', 'kontrahent', 'komentarz', 'przedmiot',
                                                                    'miesiac', 'kontrahenci')).casefold():
            continue
        pkt, why, roznica = ocen(x, k, hist)
        wynik.append({'wiersz': k['wiersz'], 'miesiac': k['miesiac'], 'arkusz': k['arkusz'], 'arkusz_nazwa': k['arkusz_nazwa'],
                      'folder': k['folder'], 'kontrahent': k['kontrahent'] or '', 'komentarz': k['komentarz'] or '',
                      'przedmiot': k['przedmiot'] or '', 'podstawa': k['podstawa'], 'plan': kwota_planu(x, k), 'planow': k['planow'],
                      'rzeczywistych': k['rzeczywistych'], 'worek': k['worek'], 'punkty': pkt, 'pewnosc': pewnosc(pkt),
                      'uzasadnienie': ', '.join(why), 'roznica': roznica, 'plan_id': k['plan']})
    wynik.sort(key=lambda c: (-c['punkty'], abs(c['roznica']), c['miesiac'], c['wiersz']))
    return wynik[:n]


def zbuduj_do_polaczenia(con, powiazania, od: str, platnosci) -> int:
    """Każdy dokument z jego stanem: „polaczony” (w apce), „w_budzecie” (płatność z BS po numerze albo przelewie),
    „do_polaczenia” (od dnia startu łączenia albo dodany ręcznie, bez połączenia) albo „sprzed” (starszy, niepołączony:
    zostaje w Budget Studio i w rozjazdach). Dla „do połączenia” najlepsza podpowiedź; komórka nie-worek trafia do jednej
    podpowiedzi (najwyżej punktowanej), żeby „Połącz wg podpowiedzi” na wielu pozycjach nie trafiło dwa razy w ten sam plan."""
    w_bud = _w_budzecie(powiazania, platnosci)
    z_apki = defaultdict(list)
    for p in platnosci:
        if p['dokument']:
            z_apki[p['dokument']].append(p['id'])
    komorki = kandydaci_komorek(con)
    hist = _historia_wierszy(con)
    dokumenty, do_oceny = wszystkie_dokumenty(con), []
    for x in dokumenty:
        ref = x['ref']
        op = f"op:{x.get('operacja_id')}" if x.get('operacja_id') else ''
        if ref in z_apki:
            x['_stan'], x['_ids'] = 'polaczony', z_apki[ref]
        elif w_bud.get(ref) or (op and w_bud.get(op)):
            x['_stan'], x['_ids'] = 'w_budzecie', w_bud.get(ref) or w_bud[op]
        elif (x['data'] or '') >= od or x['typ'] == 'reczna':
            x['_stan'], x['_ids'] = 'do_polaczenia', []
            x['_tok'] = tokeny(x['kontrahent'])
            do_oceny.append(x)
        else:
            x['_stan'], x['_ids'] = 'sprzed', []
    pary = []
    for x in do_oceny:
        for c in podpowiedzi(con, x, n=5, komorki=komorki, hist=hist):
            if c['pewnosc']:
                pary.append((-c['punkty'], abs(c['roznica']), x['ref'], c))
    pary.sort(key=lambda t: t[:3])
    zajete, wybrane = set(), {}
    for _, _, ref, c in pary:
        if ref in wybrane or (not c['worek'] and (c['wiersz'], c['miesiac']) in zajete):
            continue
        wybrane[ref] = c
        zajete.add((c['wiersz'], c['miesiac']))
    wiersze = []
    for x in dokumenty:
        c = wybrane.get(x['ref']) or {}
        wiersze.append((x['ref'], x['typ'], x['rodzaj'], x['rodzina'], x['data'], x['kontrahent'], x['nr_dok'], x['netto'], x['vat'],
                        x['brutto'], x['kwota'], x['tytul'], x['_stan'], json.dumps(x['_ids']), c.get('wiersz'), c.get('miesiac'),
                        c.get('arkusz'), c.get('plan'), c.get('pewnosc'), c.get('punkty'), c.get('uzasadnienie'), x['zrodlo'],
                        x.get('oplacono'), x.get('termin'), x.get('operacja_id')))
    con.executemany('INSERT OR REPLACE INTO bud_laczenie (ref, typ, rodzaj, rodzina, data, kontrahent, nr_dok, netto, vat, brutto, kwota, tytul,'
                    ' stan, platnosci, pod_wiersz, pod_miesiac, pod_arkusz, pod_kwota, pewnosc, punkty, uzasadnienie, zrodlo, oplacono,'
                    ' termin, operacja_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', wiersze)
    return len(do_oceny)


# ---------- Odczyty dla interfejsu: lista „Do połączenia”, karta dokumentu, wyszukiwarka komórek ----------

NAZWA_ZRODLA = {'faktura': 'Fakturownia', 'zakup': 'Rejestr biura', 'operacja': 'Bank ING', 'reczna': 'Dodana ręcznie'}
STANY_LISTY = {'do_polaczenia': 'Do połączenia', 'sprzed': 'Starsze niż start łączenia', 'polaczony': 'Połączone w apce'}
KOL_LISTY = {'data': ('l.data', False), 'kontrahent': ('l.kontrahent', True), 'nr_dok': ('l.nr_dok', True), 'zrodlo': ('l.typ', True),
             'netto': ('l.netto * l.rodzaj', False), 'vat': ('l.vat * l.rodzaj', False), 'brutto': ('l.brutto * l.rodzaj', False),
             'kwota': ('l.kwota * l.rodzaj', False), 'rodzaj': ('l.rodzaj', False), 'podpowiedz': ('a.nazwa', True),
             'pewnosc': ('COALESCE(l.punkty, -1)', False), 'roznica': ('ABS(COALESCE(l.pod_kwota - l.kwota, 0))', False),
             'tytul': ('l.tytul', True)}
_ODCIEK = re.compile(r'\s{2,}.*$|\s+(?:ul\.|al\.)\s.*$|\s+\d{2}-\d{3}\b.*$|\s+\d{4,}.*$|\s+\d{3}\s*$', re.I)


def nazwa_krotka(nazwa: str) -> str:
    """Nazwa kontrahenta z banku bez adresu, numeru karty i kodu kraju („Openai San Francisco 94158 840  2210…” →
    „Openai San Francisco”)."""
    n = (nazwa or '').strip()
    k = _ODCIEK.sub('', n).strip(' ,*')
    return k if len(k) >= 3 else n


def _oznaczone_sql() -> str:
    return "EXISTS (SELECT 1 FROM oznaczone o WHERE o.obiekt || ':' || o.ref = l.ref)"


def lista(con, q: dict) -> dict:
    """GET /api/lista/do-polaczenia: dokumenty rzeczywiste niepołączone z budżetem (B-LIS-10) z podpowiedzią planu.
    Zakładki: do połączenia (od startu łączenia), starsze (w Budget Studio), połączone w apce. Pozycje przeniesione do
    Do weryfikacji nie są tu widoczne, dopóki nie zostaną oznaczone jako sprawdzone."""
    from . import filtry, zapytania
    stan = q.get('stan') if q.get('stan') in STANY_LISTY else 'do_polaczenia'
    warunki, params = ['l.stan = ?', f'NOT {_oznaczone_sql()}'], [stan]
    if q.get('rodzaj') in ('1', '-1'):
        warunki.append('l.rodzaj = ?')
        params.append(int(q['rodzaj']))
    zr = [z for z in filtry.lista_wartosci(q.get('zrodlo')) if z in NAZWA_ZRODLA]
    if zr:
        warunki.append(f"l.typ IN ({','.join('?' * len(zr))})")
        params += zr
    pw = filtry.lista_wartosci(q.get('pewnosc'))
    if pw:
        warunki.append(f"COALESCE(l.pewnosc, 'brak') IN ({','.join('?' * len(pw))})")
        params += pw
    zapytania._daty(con, {'data': q['d_data']} if q.get('d_data') else None, {'data': ('l.data', False)}, warunki, params)
    if q.get('q'):
        warunki.append("(l.kontrahent || ' ' || COALESCE(l.nr_dok, '') || ' ' || COALESCE(l.tytul, '') || ' ' || COALESCE(a.nazwa, '')) LIKE ?")
        params.append(f"%{q['q']}%")
    sql = ('SELECT l.*, a.nazwa AS pod_arkusz_nazwa, a.folder AS pod_folder, w.kontrahent AS pod_kontrahent, w.komentarz AS pod_komentarz,'
           ' w.przedmiot AS pod_przedmiot, w.podstawa AS pod_podstawa FROM bud_laczenie l LEFT JOIN bud_wiersz w ON w.id = l.pod_wiersz'
           ' LEFT JOIN bud_arkusz a ON a.id = w.arkusz WHERE ' + ' AND '.join(warunki))
    ile, maks = zapytania._ile(q.get('ile'), q.get('wszystkie') == '1')
    wynik = zapytania._strona(sql, params, q.get('strona'), ile, con,
                              filtry.porzadek(q.get('sortuj'), q.get('kolejnosc'), KOL_LISTY, 'l.data DESC', 'l.ref'), maks)
    for x in wynik['wiersze']:
        x['kontrahent_krotko'] = nazwa_krotka(x['kontrahent'])
        x['zrodlo_nazwa'] = NAZWA_ZRODLA.get(x['typ'], x['typ'])
        x['roznica'] = (x['pod_kwota'] - x['kwota']) if x['pod_kwota'] is not None else None
    wynik['podsumowanie'] = zapytania._podsumowanie(con, sql, params, 'rodzaj', 'netto * rodzaj', 'vat * rodzaj', 'brutto * rodzaj')
    wynik['liczniki'] = {r[0]: r[1] for r in con.execute(f'SELECT l.stan, COUNT(*) FROM bud_laczenie l WHERE NOT {_oznaczone_sql()} GROUP BY l.stan')}
    from .zapytania_budzet import planowanie
    wynik.update(stan=stan, stany=STANY_LISTY, laczenie_od=laczenie_od(con), planowanie=planowanie(con),
                 dzien_stanu=(con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0])
    return wynik


def ile_do_polaczenia(con) -> int:
    return con.execute(f"SELECT COUNT(*) FROM bud_laczenie l WHERE l.stan = 'do_polaczenia' AND NOT {_oznaczone_sql()}").fetchone()[0]


def _dokument_z_bazy(con, ref: str) -> dict | None:
    if ref.startswith('reczna:'):
        r = con.execute('SELECT dane FROM bud_reczne WHERE id = ?', (ref[7:],)).fetchone()
        if not r:
            return None
        from .budzet import dokument_reczny
        return dokument_reczny(json.loads(r[0]))
    return Dokumenty(con)(ref)


def karta(con, ref: str, q: str = '') -> dict:
    """GET /api/laczenie/dokument: dokument, jego stan, połączenie (części w komórkach) i podpowiedzi planów (ekran łączenia)."""
    from .zapytania_budzet import planowanie
    x = _dokument_z_bazy(con, ref)
    if not x:
        raise ValueError('nie ma takiego dokumentu')
    r = con.execute('SELECT * FROM bud_laczenie WHERE ref = ?', (ref,)).fetchone()
    stan = dict(r) if r else {'stan': 'do_polaczenia', 'platnosci': '[]'}
    oznaczone = con.execute("SELECT powod FROM oznaczone WHERE obiekt || ':' || ref = ?", (ref,)).fetchone()
    platnosci = []
    for pid in json.loads(stan.get('platnosci') or '[]'):
        p = con.execute("SELECT p.id, p.wiersz, p.miesiac, p.netto, p.vat, p.brutto, p.typ, p.zrodlo, p.skladowa, a.nazwa AS arkusz, a.id AS arkusz_id,"
                        " a.folder, w.kontrahent AS w_kontrahent, w.komentarz AS w_komentarz, w.podstawa, s.etap FROM bud_platnosc p"
                        ' JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz LEFT JOIN bud_stan s ON s.platnosc = p.id'
                        ' WHERE p.id = ?', (pid,)).fetchone()
        if p:
            platnosci.append(dict(p))
    x = {k: v for k, v in x.items() if not k.startswith('_')}
    if ref.startswith('reczna:'):   # dane z formularza do edycji
        x['dane'] = json.loads(con.execute('SELECT dane FROM bud_reczne WHERE id = ?', (ref[7:],)).fetchone()[0])
    x['kontrahent_krotko'] = nazwa_krotka(x['kontrahent'])
    x['zrodlo_nazwa'] = NAZWA_ZRODLA.get(x['typ'], x['typ'])
    return {'dokument': x, 'stan': stan['stan'], 'platnosci': platnosci, 'oznaczone': oznaczone[0] if oznaczone else None,
            'podpowiedzi': podpowiedzi(con, x, n=30 if q else 8, q=q) if stan['stan'] != 'polaczony' else [],
            'planowanie': planowanie(con), 'laczenie_od': laczenie_od(con)}


# ---------- Lista płac (decyzja Mata 12) i ostrzeżenia ----------

def _wiersze_wynagrodzen(con) -> list[dict]:
    """Osoby na liście płac: wiersz umowy (składowe w jednym wierszu), wiersz oznaczony do listy płac albo grupa wierszy
    składowych jednej umowy z kopii BS („Umowa o pracę - dla wykonawcy / - PIT / - ZUS” tej samej osoby w arkuszu):
    grupa ma id wiersza wypłaty, podstawę umowy i mapę składowych {składowa: wiersz}."""
    wynik, grupy = [], {}
    for r in con.execute(
            "SELECT w.*, a.nazwa AS arkusz_nazwa, a.folder FROM bud_wiersz w JOIN bud_arkusz a ON a.id = w.arkusz"
            " WHERE w.podstawa IN ('Umowa o pracę', 'Umowa zlecenie', 'Umowa o dzieło') OR COALESCE(w.lista_plac, 0) = 1"
            " OR w.podstawa LIKE 'Umowa o pracę - %' OR w.podstawa LIKE 'Umowa zlecenie - %' OR w.podstawa LIKE 'Umowa o dzieło - %'"
            ' ORDER BY a.nazwa, w.kolejnosc, w.id'):
        w = dict(r)
        su = plan.skladowa_umowy(w['podstawa'])
        if not su:
            if not (w['podstawa'] or '').startswith('Umowa') or plan.jest_umowa(w['podstawa']) or w['lista_plac']:
                wynik.append({**w, 'skladowe_wierszy': None})
            continue
        klucz = (w['arkusz'], (w['kontrahent'] or '').strip().casefold(), su[0])
        g = grupy.get(klucz)
        if not g:
            g = grupy[klucz] = {**w, 'podstawa': su[0], 'skladowe_wierszy': {}}
            wynik.append(g)
        g['skladowe_wierszy'][su[1]] = min(g['skladowe_wierszy'].get(su[1]) or w['id'], w['id'])
        if su[1] == 'osoba':
            g.update(id=g['skladowe_wierszy']['osoba'], komentarz=w['komentarz'])
    for g in grupy.values():   # jak serwer (budzet.rodzenstwo_umowy): wiersz wypłaty, a bez niego pierwszy wiersz składowej
        g['id'] = g['skladowe_wierszy'].get('osoba') or sorted(g['skladowe_wierszy'].values())[0]
    return wynik


def _komorki_wynagrodzen(con, wiersze) -> dict:
    """(osoba, miesiąc) → {'plany': {składowa: płatność}, 'rzeczywiste': {składowa: płatność}}; osoba = id z
    _wiersze_wynagrodzen (przy wierszach składowych z kopii BS płatności wszystkich jej wierszy)."""
    wynik = defaultdict(lambda: {'plany': {}, 'rzeczywiste': {}})
    mapa = {}
    for w in wiersze:
        if w.get('skladowe_wierszy'):
            for s, wid in w['skladowe_wierszy'].items():
                mapa[wid] = (w['id'], s)
        else:
            mapa[w['id']] = (w['id'], None)
    if not mapa:
        return wynik
    for r in con.execute(f"SELECT * FROM bud_platnosc WHERE wiersz IN ({','.join('?' * len(mapa))}) AND aktualna = 1", list(mapa)):
        p = dict(r)
        k = 'plany' if p['typ'] == 'plan' else 'rzeczywiste'
        osoba, s0 = mapa[p['wiersz']]
        p['wiersz'] = osoba
        s = s0 or p['skladowa'] or 'osoba'
        if s in wynik[(p['wiersz'], p['miesiac'])][k]:   # wiersz bez umowy: kilka płatności w miesiącu sumujemy
            stary = wynik[(p['wiersz'], p['miesiac'])][k][s]
            p = {**stary, 'netto': stary['netto'] + p['netto'], 'brutto': stary['brutto'] + p['brutto']}
        wynik[(p['wiersz'], p['miesiac'])][k][s] = p
    return wynik


def _przelewy_wynagrodzen(con) -> dict:
    """Przelewy z banku do porównania z listą płac: wypłaty („wynagrodzenie za MM.RRRR”) wg miesiąca pracy, PIT-4 wg
    okresu z tytułu (miesiąc wypłaty), ZUS wg okresu z tytułu („DRA 01/08” = sierpień)."""
    from .podatki import zaplaty_z_banku
    from .wynik import okres_pracy
    wynik = {'osoba': defaultdict(list), 'us': defaultdict(list), 'zus': defaultdict(list)}
    for o in con.execute("SELECT o.id, o.data_ksiegowania, o.kwota, o.kontrahent, o.tytul, o.opis FROM operacje o JOIN wydatki w ON w.operacja_id = o.id"
                         " WHERE w.rodzaj = 'praca' AND o.kwota < 0"):
        if 'wynagrodzenie' in f"{o['tytul'] or ''} {o['opis'] or ''}".lower():
            wynik['osoba'][okres_pracy(o['tytul'] or '', o['data_ksiegowania'])].append(
                {'data': o['data_ksiegowania'], 'kwota': -o['kwota'], 'kontrahent': o['kontrahent'] or '', 'tytul': o['tytul'] or '',
                 '_tok': tokeny(o['kontrahent'])})
    for z in zaplaty_z_banku(con):
        if z['rodzaj'] == 'pit4':
            wynik['us'][z['okres']].append({'data': z['data'], 'kwota': z['kwota'], 'tytul': z['tytul'] or ''})
        elif z['rodzaj'] == 'zus':
            wynik['zus'][z['okres']].append({'data': z['data'], 'kwota': z['kwota'], 'tytul': z['tytul'] or ''})
    return wynik


def _przelewy_osoby(w: dict, przelewy: list[dict]) -> list[dict]:
    tok = tokeny(w.get('kontrahent'))
    return [x for x in przelewy if tok and tok & x['_tok']]


def lista_plac(con, miesiac: str | None = None) -> dict:
    """GET /api/lista-plac?miesiac=: formularz „Lista płac za miesiąc”: osoby (wiersze umów i wiersze oznaczone do listy
    płac) z planem (estymacja), ostatnią rzeczywistą kwotą, wpisaną listą i przelewami z banku jako podpowiedzią."""
    from .zapytania_budzet import planowanie
    if miesiac and not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', miesiac):
        raise ValueError('miesiąc RRRR-MM')
    wiersze = _wiersze_wynagrodzen(con)
    kom = _komorki_wynagrodzen(con, wiersze)
    miesiace = sorted({m for (_, m) in kom}, reverse=True)
    dzien = (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0] or date.today().isoformat()
    if not miesiac:   # domyślnie najstarszy miesiąc z minioną wypłatą bez listy, inaczej bieżący
        brak = sorted(o['miesiac'] for o in ostrzezenia(con) if o['rodzaj'] == 'lista_niewpisana')
        miesiac = brak[0] if brak else dzien[:7]
    przelewy = _przelewy_wynagrodzen(con)
    osoby = []
    for w in wiersze:
        k = kom.get((w['id'], miesiac), {'plany': {}, 'rzeczywiste': {}})
        skladowe = list(plan.UMOWY.get(w['podstawa'], ('osoba', 'us', 'zus')))
        ostatnia = max((m for (wid, m), v in kom.items() if wid == w['id'] and v['rzeczywiste'] and m < miesiac), default=None)
        rz = k['rzeczywiste']
        z_listy = any(p['zrodlo'] == 'lista płac' for p in rz.values())
        wpisane = {}
        if z_listy:
            if plan.jest_umowa(w['podstawa']):
                wpisane = {s: rz[s]['netto'] for s in skladowe if s in rz}
            else:
                p = rz.get('osoba')
                wpisane = json.loads(p['skladniki']) if p and p['skladniki'] else {'osoba': p['netto'] if p else 0}
        osoba_plan = k['plany'].get('osoba') or {}
        termin = osoba_plan.get('termin') or (rz.get('osoba') or {}).get('termin')
        osoby.append({
            'wiersz': w['id'], 'kontrahent': w['kontrahent'] or '', 'komentarz': w['komentarz'] or '', 'podstawa': w['podstawa'],
            'arkusz': w['arkusz_nazwa'], 'arkusz_id': w['arkusz'], 'umowa': plan.jest_umowa(w['podstawa']), 'skladowe': skladowe,
            'plan': {s: p['netto'] for s, p in k['plany'].items()}, 'plan_razem': sum(p['netto'] for p in k['plany'].values()),
            'rzeczywiste': {s: p['netto'] for s, p in rz.items()}, 'z_listy': z_listy, 'wpisane': wpisane,
            'z_kopii': bool(rz) and not z_listy, 'termin_wyplaty': termin,
            'ostatnia': ({'miesiac': ostatnia, 'razem': sum(p['netto'] for p in kom[(w['id'], ostatnia)]['rzeczywiste'].values()),
                          'kwoty': {s: p['netto'] for s, p in kom[(w['id'], ostatnia)]['rzeczywiste'].items()}} if ostatnia else None),
            'przelewy': [{k2: v for k2, v in x.items() if k2 != '_tok'} for x in _przelewy_osoby(w, przelewy['osoba'].get(miesiac, []))],
            'mozna': bool(k['plany']) and not (rz and not z_listy)})
    termin_m = next((o['termin_wyplaty'] for o in osoby if o['termin_wyplaty']), None)
    bank = {'us': przelewy['us'].get((termin_m or '')[:7], []), 'zus': przelewy['zus'].get(miesiac, [])}
    kandydaci = [dict(r) for r in con.execute(
        "SELECT w.id, w.kontrahent, w.komentarz, a.nazwa AS arkusz FROM bud_wiersz w JOIN bud_arkusz a ON a.id = w.arkusz"
        " WHERE w.rodzaj = -1 AND w.podstawa IN ('Bez faktury', 'Bez faktury (w worku)') AND COALESCE(w.lista_plac, 0) = 0"
        " AND COALESCE(a.zrodlo, '') != 'system' ORDER BY a.nazwa, w.kontrahent")]
    return {'miesiac': miesiac, 'miesiace': miesiace, 'osoby': osoby, 'bank': bank, 'kandydaci': kandydaci, 'dzien_stanu': dzien,
            'planowanie': planowanie(con), 'ostrzezenia': [o for o in ostrzezenia(con) if o.get('miesiac') == miesiac]}


def ostrzezenia(con) -> list[dict]:
    """Ostrzeżenia kosztu pracy (decyzja Mata 12): (a) wypłata za miesiąc minęła, a listy płac nie ma; (b) estymacja na
    przyszły miesiąc niższa niż ostatnia rzeczywista kwota tej osoby (estymacja ma być zawyżona); (c) lista płac różni się
    od przelewów w banku o ponad 1 zł. Każde: rodzaj, poziom, tytuł, opis, wiersz, osoba, miesiąc, kwota."""
    dzien = (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0] or date.today().isoformat()
    wiersze = _wiersze_wynagrodzen(con)
    kom = _komorki_wynagrodzen(con, wiersze)
    przelewy = _przelewy_wynagrodzen(con)
    wynik = []
    po_wierszu = defaultdict(dict)
    for (wid, m), v in kom.items():
        po_wierszu[wid][m] = v
    listy = defaultdict(list)   # miesiąc → wiersze z wpisaną listą płac
    for w in wiersze:
        komorki = po_wierszu.get(w['id'], {})
        osoba = w['kontrahent'] or w['komentarz'] or 'osoba'
        for m, v in sorted(komorki.items()):
            if v['rzeczywiste'] and any(p['zrodlo'] == 'lista płac' for p in v['rzeczywiste'].values()):
                listy[m].append((w, v))
            if v['plany'] and not v['rzeczywiste']:
                o = v['plany'].get('osoba') or next(iter(v['plany'].values()))
                termin = o.get('termin') or f'{m}-28'
                razem = sum(p['netto'] for p in v['plany'].values())
                if termin < dzien and razem > 0:
                    wynik.append({'rodzaj': 'lista_niewpisana', 'poziom': 'uwaga', 'tytul': 'Lista płac niewpisana',
                                  'opis': f'{osoba}: wypłata za {_mies(m)} minęła {_dzien_pl(termin)}, a listy płac nie ma. Plan '
                                          f'(estymacja {_zl(razem)}) nadal liczy się w cash flow.',
                                  'wiersz': w['id'], 'osoba': osoba, 'miesiac': m, 'kwota': -razem, 'data': termin})
        rz_mies = [m for m, v in komorki.items() if v['rzeczywiste']]
        if rz_mies:
            ostatni = max(rz_mies)
            ost = sum(p['netto'] for p in komorki[ostatni]['rzeczywiste'].values())
            nizsze = [(m, sum(p['netto'] for p in v['plany'].values())) for m, v in sorted(komorki.items())
                      if m > ostatni and v['plany'] and not v['rzeczywiste']
                      and ((v['plany'].get('osoba') or {}).get('termin') or f'{m}-28') >= dzien]
            nizsze = [(m, k) for m, k in nizsze if k < ost]
            if nizsze:
                m0, k0 = nizsze[0]
                wynik.append({'rodzaj': 'estymacja_nizsza', 'poziom': 'uwaga', 'tytul': 'Estymacja wynagrodzenia za niska',
                              'opis': f'{osoba}: plan na {_mies(m0)} ({_zl(k0)}) jest niższy niż ostatnia rzeczywista kwota '
                                      f'({_zl(ost)} za {_mies(ostatni)})' + (f', tak samo w {len(nizsze) - 1} kolejnych miesiącach' if len(nizsze) > 1 else '')
                                      + '. Podnieś estymację w arkuszu: koszt pracy w planie ma być zawyżony.',
                              'wiersz': w['id'], 'osoba': osoba, 'miesiac': m0, 'kwota': k0 - ost, 'data': f'{m0}-01',
                              'miesiace': [m for m, _ in nizsze]})
    for m, pozycje in sorted(listy.items()):
        termin_m = None
        sumy = {'osoba': 0, 'us': 0, 'zus': 0}
        for w, v in pozycje:
            rz = v['rzeczywiste']
            if plan.jest_umowa(w['podstawa']):
                for s in sumy:
                    sumy[s] += rz[s]['netto'] if s in rz else 0
            else:
                p = rz.get('osoba') or next(iter(rz.values()))
                skl = json.loads(p['skladniki']) if p.get('skladniki') else {'osoba': p['netto']}
                for s in sumy:
                    sumy[s] += int(skl.get(s) or 0)
            termin_m = termin_m or (rz.get('osoba') or {}).get('termin')
            os_ = _przelewy_osoby(w, przelewy['osoba'].get(m, []))
            wpis = (rz['osoba']['netto'] if plan.jest_umowa(w['podstawa']) and 'osoba' in rz else
                    int((json.loads((rz.get('osoba') or {}).get('skladniki') or '{}') or {}).get('osoba') or 0))
            if os_ and abs(sum(x['kwota'] for x in os_) - wpis) > 100:
                bank = sum(x['kwota'] for x in os_)
                wynik.append({'rodzaj': 'lista_vs_przelew', 'poziom': 'info', 'tytul': 'Lista płac inna niż przelew',
                              'opis': f"{w['kontrahent'] or 'osoba'}: wypłata z listy płac za {_mies(m)} {_zl(wpis)}, przelew w banku "
                                      f'{_zl(bank)} (różnica {_zl(wpis - bank)}). Sprawdź listę płac albo przelew.',
                              'wiersz': w['id'], 'osoba': w['kontrahent'] or '', 'miesiac': m, 'kwota': wpis - bank,
                              'data': os_[0]['data']})
        for s, nazwa, przel in (('us', 'PIT-4', przelewy['us'].get((termin_m or '')[:7], [])), ('zus', 'ZUS', przelewy['zus'].get(m, []))):
            if przel and abs(sum(x['kwota'] for x in przel) - sumy[s]) > 100:
                bank = sum(x['kwota'] for x in przel)
                wynik.append({'rodzaj': 'lista_vs_przelew', 'poziom': 'info', 'tytul': 'Lista płac inna niż przelew',
                              'opis': f'{nazwa} za {_mies(m)}: z list płac {_zl(sumy[s])}, przelew w banku {_zl(bank)} '
                                      f'(różnica {_zl(sumy[s] - bank)}). Sprawdź listę płac albo przelew.',
                              'wiersz': '', 'osoba': nazwa, 'miesiac': m, 'kwota': sumy[s] - bank, 'data': przel[0]['data']})
    for i, o in enumerate(wynik):
        o['id'] = f"{o['rodzaj']}|{o['wiersz']}|{o['miesiac']}|{i}"
        # prosty kształt dla kafla pulpitu (pakiet 11): typ, opis, osoba, miesiąc, kwota w groszach, link do ekranu
        o.update(typ=o['rodzaj'], kwota_gr=o['kwota'], link=f"#/budzet/lista-plac?miesiac={o['miesiac']}")
    return wynik


def polaczone(con) -> dict:
    """GET /api/laczenie/polaczone: płatność budżetu → dokument, z którym połączono ją w apce (dokument z Do połączenia,
    zamiana planu, lista płac). Do masowego odłączenia z list i cash flow."""
    return {r[0]: r[1] for r in con.execute("SELECT id, dokument FROM bud_platnosc WHERE COALESCE(dokument, '') != ''")}


MIES_PL = ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień', 'wrzesień', 'październik', 'listopad', 'grudzień']


def _mies(m: str) -> str:
    return f'{MIES_PL[int(m[5:7]) - 1]} {m[:4]}'


def _dzien_pl(d: str) -> str:
    return f'{int(d[8:10])}.{d[5:7]}.{d[:4]}'


def _zl(gr: int) -> str:
    from .format import zl
    return zl(gr)
