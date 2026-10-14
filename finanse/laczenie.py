"""Łączenie budżetu z rzeczywistością (wymagania 1–3 z zadania nocnego) i rozjazdy BS ↔ bank ↔ Fakturownia.

Przychód (wiersz „wpływy”): płatność ↔ faktura sprzedażowa (numer dokumentu albo klient + kwota + miesiąc),
  etap z banku przez stan faktury (etap 2).
Koszt („obciążenia”): płatność ↔ dokument z rejestru biura (numer) ↔ wydatek z banku, albo wprost wydatek z banku
  (kwota brutto, data ±5 dni przy karcie, ±3 przy przelewie, nazwa pomocniczo).
Etap: „Opłacona” tylko z banku. Plan bez zapłaty po terminie: „Po terminie” na czerwono, dopóki Mat nie zdecyduje
  (przesuń, zapłacone, anuluj); nie znika z cash flow jak w BS.
"""
import re
from collections import defaultdict
from datetime import date, timedelta

from .dopasowanie import klucz_fv, tokeny


def _d(s):
    return date.fromisoformat(s[:10]) if s else None


def _alnum(s):
    return re.sub(r'[^0-9A-Z]', '', (s or '').upper())


def _koniec_miesiaca(m: str) -> str:
    r, mm = int(m[:4]), int(m[5:7])
    nastepny = date(r + (mm == 12), 1 if mm == 12 else mm + 1, 1)
    return (nastepny - timedelta(days=1)).isoformat()


def policz(con) -> dict:
    dzien_stanu = (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0]
    dzis = _d(dzien_stanu) if dzien_stanu else date.today()
    platnosci = [dict(r) for r in con.execute(
        'SELECT p.*, w.kontrahent AS w_kontrahent, w.podstawa, a.folder, a.nazwa AS arkusz_nazwa, a.id AS arkusz_id'
        ' FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz')]
    faktury = {r['numer']: dict(r) for r in con.execute(
        'SELECT f.numer, f.netto, f.brutto, f.data_sprzedazy, f.data_wystawienia, fk.klient, s.stan, s.pozostalo, s.ostatnia_wplata,'
        ' s.dni_po_terminie FROM faktury f LEFT JOIN faktury_klient fk USING(numer) LEFT JOIN faktury_stan s USING(numer) WHERE f.korekta = 0')}
    po_kluczu = {klucz_fv(n): n for n in faktury if klucz_fv(n)}
    zakupy = {_alnum(r['nr_dok']): dict(r) for r in con.execute(
        'SELECT z.nr_ewid, z.nr_dok, z.podmiot, z.brutto, z.netto, s.operacja_id FROM zakupy z LEFT JOIN zakupy_stan s USING(nr_ewid)')
        if len(_alnum(r['nr_dok'])) >= 4}
    wydatki = [dict(r) for r in con.execute(
        'SELECT o.id, o.data_ksiegowania, o.kwota, o.kontrahent, o.opis, o.tytul FROM operacje o JOIN wydatki w ON w.operacja_id = o.id')]
    for x in wydatki:
        x['_tok'] = tokeny(x['kontrahent'] or x['opis'])
        x['_d'] = _d(x['data_ksiegowania'])
        x['_karta'] = 'kart' in f"{x['opis']} {x['tytul']}".lower()

    powiazania, stany, rozjazdy_grup = [], {}, []
    zajete_fv, zajete_op = set(), set()

    # 1. Przychody ↔ faktury: najpierw numer dokumentu, potem klient + kwota netto + miesiąc ±1
    przychody = [p for p in platnosci if p['rodzaj'] == 1]
    for p in przychody:
        n = po_kluczu.get(klucz_fv(p['nr_dok'])) if p['nr_dok'] else None
        if n:
            powiazania.append((p['id'], 'faktura', n, faktury[n]['netto'], 'numer dokumentu', 'pewne'))
            zajete_fv.add(n)
    polaczone = {x[0] for x in powiazania}
    for p in przychody:
        if p['id'] in polaczone or not p['aktualna']:
            continue
        m = _d(p['miesiac'] + '-01')
        kand = [n for n, f in faktury.items() if n not in zajete_fv and f['klient'] == p['folder'] and f['netto'] == p['netto']
                and abs(((_d((f['data_sprzedazy'] or f['data_wystawienia'])[:7] + '-01')) - m).days) <= 31]
        if kand:
            n = min(kand, key=lambda n: abs((_d((faktury[n]['data_sprzedazy'] or faktury[n]['data_wystawienia'])[:7] + '-01') - m).days))
            powiazania.append((p['id'], 'faktura', n, faktury[n]['netto'], 'klient, kwota i miesiąc', 'prawdopodobne'))
            zajete_fv.add(n)

    # 2. Koszty ↔ dokument z rejestru (numer) ↔ bank; potem wprost bank (kwota brutto i okno dat)
    koszty = [p for p in platnosci if p['rodzaj'] == -1]
    for p in koszty:
        z = zakupy.get(_alnum(p['nr_dok'])) if p['nr_dok'] else None
        if z:
            powiazania.append((p['id'], 'dokument', z['nr_ewid'], z['netto'] or 0, 'numer dokumentu', 'pewne'))
            if z['operacja_id']:
                powiazania.append((p['id'], 'bank', str(z['operacja_id']), p['brutto'], 'przez dokument', 'pewne'))
                zajete_op.add(z['operacja_id'])
    z_bankiem = {x[0] for x in powiazania if x[1] == 'bank'}
    kandydaci = []
    for p in koszty:
        if p['id'] in z_bankiem:
            continue
        dp = _d(p['realny'] or p['termin'] or _koniec_miesiaca(p['miesiac']))
        tok = tokeny(p['w_kontrahent'])
        for x in wydatki:
            if -x['kwota'] != p['brutto'] or x['id'] in zajete_op:
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
    wbudowane = {r[0]: r[1] for r in con.execute("SELECT operacja_id, rodzaj FROM wydatki WHERE zrodlo = 'reguła wbudowana'")}
    def grupa_bs(p):
        if p['podstawa'].startswith('Umowa o pracę') or ('pracownic' in p['arkusz_nazwa'].lower() and p['podstawa'].startswith('Bez faktury')):
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
                for x in ops:
                    powiazania.append((p['id'], 'bank', str(x['id']), None, f'suma w miesiącu ({klucz_g[0]} {klucz_g[1]})', 'prawdopodobne'))
                z_bankiem.add(p['id'])
            zajete_op.update(x['id'] for x in ops)
        else:
            nazwa = {"praca": "koszty pracy", "vat": "VAT", "podatki": "podatek dochodowy"}[klucz_g[0]]
            rozjazdy_grup.append((f'Suma w BS inna niż w banku ({nazwa})', f'{klucz_g[0]}:{klucz_g[1]}', suma_bs - suma_bank,
                                  f'płatności w {klucz_g[1]}: BS {suma_bs} gr ({len(ps)} pozycji), bank {suma_bank} gr ({len(ops)} przelewów)'))

    # 3. Etap z danych
    data_op = {x['id']: x['data_ksiegowania'] for x in wydatki}
    po_platnosci = defaultdict(list)
    for x in powiazania:
        po_platnosci[x[0]].append(x)
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
        elif p['rodzaj'] == 1 and p['typ'] == 'rzeczywista' and p['etap_bs'] == 'Opłacona':
            etap, uwaga = 'Opłacona wg BS', 'brak faktury w eksporcie Fakturowni albo wpłaty w banku'
        elif p['rodzaj'] == -1 and p['etap_bs'] in ('Opłacona', 'Niewymagana'):
            etap, uwaga = 'Opłacona wg BS', 'nie znaleziono płatności w banku'
        elif _d(termin) < dzis:
            etap = 'Po terminie'
        else:
            etap = 'Planowana'
        stany[p['id']] = (etap, zaplacono, data_z, termin, uwaga)

    con.executemany('INSERT INTO bud_powiazanie (platnosc, typ, ref, kwota, metoda, pewnosc) VALUES (?,?,?,?,?,?)', powiazania)
    con.executemany('INSERT INTO bud_stan (platnosc, etap, zaplacono, data_zaplaty, termin_efektywny, uwaga) VALUES (?,?,?,?,?,?)',
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
        suma = sum(netto_p.get(i, 0) for i in ids)
        if not any(i in aktualne for i in ids):
            rozjazdy.append(('Faktura przy pozycji nieaktualnej w BS', ids[0], faktury[n]['netto'],
                             f"faktura {n} (netto {faktury[n]['netto']} gr) jest w BS przy pozycji oznaczonej jako nieaktualna"))
        elif abs(suma - faktury[n]['netto']) > 100:
            rozjazdy.append(('Kwota w BS inna niż na fakturze', ids[0], suma - faktury[n]['netto'],
                             f"faktura {n}: netto {faktury[n]['netto']} gr, w BS {suma} gr ({len(ids)} pozycji)"))
    for n, f in faktury.items():
        if n not in zajete_fv and (f['data_wystawienia'] or '') >= '2026-01-01':
            rozjazdy.append(('Faktura bez pozycji w BS', n, f['netto'], f"klient {f['klient'] or '?'}; propozycja wiersza w arkuszu klienta"))
    duze = [x for x in wydatki if x['id'] not in zajete_op and -x['kwota'] >= 20000]
    for x in duze:
        rozjazdy.append(('Wydatek z banku bez pozycji w BS', str(x['id']), -x['kwota'], f"{x['data_ksiegowania']} {x['kontrahent'] or x['opis']}"))
    con.executemany('INSERT INTO bud_rozjazd (rodzaj, ref, kwota, opis) VALUES (?,?,?,?)', rozjazdy)
    return {'powiazan': len(powiazania), 'rozjazdow': len(rozjazdy)}
