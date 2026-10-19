"""Etap F: prognoza gotówki dzienna i 13-tygodniowa.

Saldo startowe: rachunek główny + online z ostatniej operacji w eksporcie ING (dzień stanu).
Wpływy: faktury nieopłacone w banku, w dniu termin + średnie spóźnienie tego nabywcy (z historii wpłat),
  plus plany przychodów bez faktury (termin planu). Wydatki: plany kosztów niezapłacone (termin planu).
Dwa scenariusze: „ostrożny” bez należności już po terminie, „pełny” z nimi (wpływ za 7 dni).
Plany po terminie bez decyzji Mata: nie znikają, są w osobnej liście i w scenariuszu pełnym (za 7 dni).
VAT z planów BS liczy się jak inne wydatki (płatność z rachunku); rachunek VAT poza saldem.
"""
from collections import defaultdict
from datetime import date, timedelta

DNI = 91


def _d(s):
    return date.fromisoformat(s[:10]) if s else None


def _spoznienia(con) -> dict:
    """Nabywca -> średnia liczba dni od terminu do ostatniej wpłaty (tylko faktury opłacone w banku, min. 0)."""
    s = defaultdict(list)
    for r in con.execute("SELECT f.nip, f.nabywca, f.termin, st.ostatnia_wplata FROM faktury f JOIN faktury_stan st USING(numer)"
                         " WHERE st.stan = 'opłacona' AND st.ostatnia_wplata != '' AND f.termin IS NOT NULL"):
        s[r['nip'] or r['nabywca']].append(max(0, (_d(r['ostatnia_wplata']) - _d(r['termin'])).days))
    return {k: round(sum(v) / len(v)) for k, v in s.items()}


def _saldo_ing(con) -> int:
    """Gotówka na koniec dnia stanu: rachunek główny + online z ostatniej operacji w eksporcie ING (bez rachunku VAT)."""
    return sum(r[0] for r in con.execute(
        "SELECT saldo_po FROM operacje o WHERE rachunek IN ('główny', 'online') AND saldo_po IS NOT NULL AND id = ("
        " SELECT id FROM operacje p WHERE p.rachunek = o.rachunek AND p.saldo_po IS NOT NULL"
        " ORDER BY data_ksiegowania DESC, data_pliku DESC, wiersz ASC LIMIT 1)"))


def _zdarzenie(data, kwota, opis, rodzaj, scenariusz, zrodlo, typ, **szczegoly) -> dict:
    """Jedna pozycja prognozy. typ: plan, faktura (należność z Fakturowni), szacunek, bank (historia z ING)."""
    return {'data': data, 'kwota': kwota, 'opis': opis, 'rodzaj': rodzaj, 'scenariusz': scenariusz, 'zrodlo': zrodlo,
            'typ': typ, **szczegoly}


def _zdarzenia(con, start: date, koniec: date) -> tuple[list[dict], list[dict]]:
    """Pozycje prognozy po dniu stanu (start) do końca horyzontu i lista planów po terminie.
    Logika jak w prognozie 13 tygodni (APK-CF-01 do 03), tylko z szerszym opisem pozycji do listy płatności."""
    spoz = _spoznienia(con)
    zdarzenia = []
    for r in con.execute('SELECT f.numer, f.nip, f.nabywca, f.termin, f.netto, f.vat, f.brutto, f.data_wystawienia, f.waluta,'
                         ' s.pozostalo, s.dni_po_terminie, fk.klient,'
                         " (SELECT a.id || char(9) || a.nazwa || char(9) || p.miesiac FROM bud_powiazanie b JOIN bud_platnosc p ON p.id = b.platnosc"
                         "  JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz"
                         "  WHERE b.typ = 'faktura' AND b.ref = f.numer LIMIT 1) AS ark"
                         ' FROM faktury_stan s JOIN faktury f USING(numer) LEFT JOIN faktury_klient fk USING(numer) WHERE s.pozostalo > 0'):
        ark = (r['ark'] or '').split('\t') if r['ark'] else ['', '', '']
        termin = _d(r['termin'])
        wspolne = dict(kontrahent=r['klient'] or r['nabywca'], tytul='należność z faktury', nr_dok=r['numer'], netto=r['netto'],
                       vat=r['vat'], stawka=None, wystawienie=r['data_wystawienia'], termin=r['termin'], arkusz_id=ark[0],
                       arkusz=ark[1], miesiac=ark[2] or (r['data_wystawienia'] or '')[:7], metoda='Przelew', waluta=r['waluta'] or 'PLN',
                       podstawa='Faktura', etap='Po terminie' if (r['dni_po_terminie'] or 0) > 0 else 'Wystawiona')
        if (r['dni_po_terminie'] or 0) > 0:
            zdarzenia.append(_zdarzenie(start + timedelta(days=7), r['pozostalo'], f"{r['numer']} {r['klient'] or r['nabywca']} (po terminie)",
                                        'należność po terminie', 'pelny', r['numer'], 'faktura', **wspolne))
        else:
            d = max(start + timedelta(days=1), termin + timedelta(days=spoz.get(r['nip'] or r['nabywca'], 0)))
            zdarzenia.append(_zdarzenie(d, r['pozostalo'], f"{r['numer']} {r['klient'] or r['nabywca']}", 'należność', 'oba', r['numer'],
                                        'faktura', **wspolne))
    po_terminie = []
    for r in con.execute("SELECT p.id, p.rodzaj, p.brutto, p.netto, p.vat, p.stawka, p.nr_dok, p.tytul, p.wystawienie, p.termin, p.miesiac,"
                         " p.metoda, s.termin_efektywny, s.etap, COALESCE(NULLIF(p.kontrahent, ''), w.kontrahent) AS kontrahent,"
                         " w.podstawa, a.nazwa, a.id AS arkusz_id FROM bud_platnosc p"
                         ' JOIN bud_stan s ON s.platnosc = p.id JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz'
                         " WHERE p.aktualna = 1 AND p.w_cashflow = 1 AND s.etap IN ('Planowana', 'Po terminie')"
                         " AND NOT EXISTS (SELECT 1 FROM bud_powiazanie b WHERE b.platnosc = p.id AND b.typ = 'faktura')"):
        kwota = r['brutto'] * r['rodzaj']
        opis = f"{r['kontrahent'] or ''} · {r['nazwa']}"
        wspolne = dict(kontrahent=r['kontrahent'] or '', tytul=r['tytul'] or '', nr_dok=r['nr_dok'] or '', netto=r['netto'] * r['rodzaj'],
                       vat=(r['vat'] or 0) * r['rodzaj'], stawka=r['stawka'], wystawienie=r['wystawienie'], termin=r['termin_efektywny'],
                       arkusz_id=r['arkusz_id'], arkusz=r['nazwa'], miesiac=r['miesiac'], metoda=r['metoda'] or '', waluta='PLN',
                       podstawa=r['podstawa'], etap=r['etap'])
        if r['etap'] == 'Po terminie':
            po_terminie.append({'platnosc': r['id'], 'termin': r['termin_efektywny'], 'kwota': kwota, 'opis': opis})
            zdarzenia.append(_zdarzenie(start + timedelta(days=7), kwota, opis + ' (plan po terminie)', 'plan po terminie', 'pelny', r['id'],
                                        'plan', **wspolne))
        else:
            d = _d(r['termin_efektywny'])
            if d and start < d <= koniec:
                zdarzenia.append(_zdarzenie(d, kwota, opis, 'plan przychodu' if kwota > 0 else 'plan wydatku', 'oba', r['id'], 'plan', **wspolne))
    # Miesiące bez planu kosztów (plany BS kończą się zwykle na grudniu): szacunek kosztów pracy i stałych ze średniej
    # z 6 pełnych miesięcy (jak rezerwa na pulpicie), 10. dnia miesiąca, jako wyraźnie opisana pozycja.
    from .controlling import policz as kontrolka
    srednie = kontrolka(con).get('rezerwa', {}).get('srednie_stale', 0)
    plan_kosztow = defaultdict(int)
    for z in zdarzenia:
        if z['kwota'] < 0 and z['rodzaj'] == 'plan wydatku':
            plan_kosztow[z['data'].isoformat()[:7]] += -z['kwota']
    m = start.replace(day=1)
    while m <= koniec:
        klucz = m.isoformat()[:7]
        d10 = m.replace(day=10)
        if srednie and start < d10 <= koniec and plan_kosztow[klucz] < srednie // 2:
            kw = -(srednie - plan_kosztow[klucz])
            zdarzenia.append(_zdarzenie(d10, kw, f'szacunek kosztów pracy i stałych {klucz} (brak planu w budżecie)',
                                        'szacunek kosztów', 'oba', '', 'szacunek', kontrahent='szacunek', tytul='koszty pracy i stałe (średnia 6 mies.)',
                                        nr_dok='', netto=kw, vat=0, stawka=None, wystawienie=None, termin=d10.isoformat(), arkusz_id='',
                                        arkusz='', miesiac=klucz, metoda='', waluta='PLN', podstawa='Szacunek', etap='Szacunek'))
        m = (m + timedelta(days=32)).replace(day=1)
    return zdarzenia, po_terminie


def prognoza(con) -> dict:
    dzien = (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0]
    if not dzien:
        return {'brak_danych': True}
    start = _d(dzien)
    koniec = start + timedelta(days=DNI)
    saldo = _saldo_ing(con)
    zdarzenia, po_terminie = _zdarzenia(con, start, koniec)
    dni = []
    s_ostr, s_peln = saldo, saldo
    po_dniu = defaultdict(list)
    for z in zdarzenia:
        if z['data'] <= koniec:
            po_dniu[z['data']].append(z)
    for i in range(DNI + 1):
        d = start + timedelta(days=i)
        for z in po_dniu.get(d, []):
            s_peln += z['kwota']
            if z['scenariusz'] == 'oba':
                s_ostr += z['kwota']
        dni.append({'data': d.isoformat(), 'ostrozny': s_ostr, 'pelny': s_peln,
                    'wplywy': sum(z['kwota'] for z in po_dniu.get(d, []) if z['kwota'] > 0),
                    'wydatki': sum(z['kwota'] for z in po_dniu.get(d, []) if z['kwota'] < 0)})
    tygodnie = []
    for t in range(13):
        od, do = start + timedelta(days=7 * t + 1), start + timedelta(days=7 * t + 7)
        zt = [z for z in zdarzenia if od <= z['data'] <= do]
        tygodnie.append({'od': od.isoformat(), 'do': do.isoformat(),
                         'wplywy': sum(z['kwota'] for z in zt if z['kwota'] > 0 and z['scenariusz'] == 'oba'),
                         'wydatki': sum(z['kwota'] for z in zt if z['kwota'] < 0 and z['scenariusz'] == 'oba'),
                         'tylko_pelny': sum(z['kwota'] for z in zt if z['scenariusz'] == 'pelny'),
                         'saldo_ostrozny': dni[min(7 * t + 7, DNI)]['ostrozny'], 'saldo_pelny': dni[min(7 * t + 7, DNI)]['pelny'],
                         'pozycje': [{'data': z['data'].isoformat(), 'kwota': z['kwota'], 'opis': z['opis'], 'rodzaj': z['rodzaj'],
                                      'scenariusz': z['scenariusz']} for z in sorted(zt, key=lambda z: z['data'])]})
    minimum = min(dni, key=lambda x: x['ostrozny'])
    return {'dzien_stanu': dzien, 'saldo_start': saldo, 'dni': dni, 'tygodnie': tygodnie, 'po_terminie': po_terminie,
            'minimum_ostrozny': {'data': minimum['data'], 'saldo': minimum['ostrozny']},
            'koniec': {'ostrozny': dni[-1]['ostrozny'], 'pelny': dni[-1]['pelny']}}


# ---------- Cash flow jak w Budget Studio: okresy wg granulacji (dzień, tydzień, miesiąc) ----------

GRANULACJE = ('dzien', 'tydzien', 'miesiac')
# Tydzień w BS (zrzuty 14.10 i 19.10.2026): od wtorku do poniedziałku („13 paź. – 19 paź.”). Parametr w
# Finanse/Aplikacja/ustawienia.json: "cashflow_pierwszy_dzien_tygodnia" (0 = poniedziałek, 1 = wtorek).
PIERWSZY_DZIEN_TYGODNIA = 1
MAKS_DNI = 366 * 5
MIES_KROTKO = ('sty', 'lut', 'mar', 'kwi', 'maj', 'cze', 'lip', 'sie', 'wrz', 'paź', 'lis', 'gru')
MIES_PELNE = ('styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień', 'wrzesień', 'październik',
              'listopad', 'grudzień')


def _dzien_krotko(d: date) -> str:
    return f'{d.day} {MIES_KROTKO[d.month - 1]}'


def okresy_dat(od: date, do: date, granulacja: str, pierwszy: int = PIERWSZY_DZIEN_TYGODNIA) -> list[dict]:
    """Okresy zakresu [od, do] wg granulacji, przycięte do granic zakresu. Tydzień zaczyna się w dniu tygodnia `pierwszy`
    (0 = poniedziałek). Etykiety jak w BS: dzień „13 paź”, tydzień „13 paź – 19 paź”, miesiąc „październik”
    (z rokiem przy styczniu i w pierwszej kolumnie: „styczeń '26”)."""
    if granulacja not in GRANULACJE:
        raise ValueError('granulacja: dzien, tydzien albo miesiac')
    if do < od:
        raise ValueError('koniec zakresu przed początkiem')
    if (do - od).days > MAKS_DNI:
        raise ValueError('zakres dłuższy niż 5 lat')
    wynik, d = [], od
    while d <= do:
        if granulacja == 'dzien':
            k = d
        elif granulacja == 'tydzien':
            k = d + timedelta(days=6 - (d.weekday() - pierwszy) % 7)
        else:
            k = (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        k = min(k, do)
        if granulacja == 'dzien':
            etykieta = _dzien_krotko(d)
        elif granulacja == 'tydzien':
            etykieta = f'{_dzien_krotko(d)} – {_dzien_krotko(k)}'
        else:
            etykieta = MIES_PELNE[d.month - 1] + (f" '{str(d.year)[2:]}" if d.month == 1 or not wynik else '')
        wynik.append({'od': d.isoformat(), 'do': k.isoformat(), 'etykieta': etykieta})
        d = k + timedelta(days=1)
    return wynik


def _historia_banku(con, od: date, do: date) -> list[dict]:
    """Rzeczywiste przepływy gotówki (rachunek główny i online) w dniach [od, do] z eksportu ING. Przelewy między
    głównym a online znoszą się w saldzie, więc pomijamy parę; przelew na rachunek VAT to wypływ z gotówki."""
    ops = [dict(r) for r in con.execute(
        "SELECT id, rachunek, data_ksiegowania, kwota, kontrahent, tytul, opis, wewnetrzna FROM operacje"
        " WHERE rachunek IN ('główny', 'online') AND data_ksiegowania BETWEEN ? AND ? ORDER BY data_ksiegowania, id",
        (od.isoformat(), do.isoformat()))]
    pominiete, wolne = set(), defaultdict(list)
    for o in ops:
        if o['wewnetrzna']:
            klucz = (o['data_ksiegowania'], -o['kwota'], 'online' if o['rachunek'] == 'główny' else 'główny')
            para = next((x for x in wolne[klucz] if x not in pominiete), None)
            if para is not None:
                pominiete.update((para, o['id']))
            else:
                wolne[(o['data_ksiegowania'], o['kwota'], o['rachunek'])].append(o['id'])
    wynik = []
    for o in ops:
        if o['id'] in pominiete:
            continue
        wynik.append(_zdarzenie(_d(o['data_ksiegowania']), o['kwota'], o['kontrahent'] or o['opis'] or '', 'bank', 'oba', f"op:{o['id']}",
                                'bank', kontrahent=o['kontrahent'] or '', tytul=o['tytul'] or o['opis'] or '', nr_dok='', netto=None,
                                vat=None, stawka=None, wystawienie=None, termin=o['data_ksiegowania'], arkusz_id='', arkusz='',
                                miesiac=o['data_ksiegowania'][:7], metoda='Konto firmowe', waluta='PLN',
                                podstawa='Przelew z banku', etap='Opłacona'))
    return wynik


def _saldo_na_koniec_dnia(con, d: date) -> int | None:
    from .zapytania import historia_salda
    h = {x['x']: x['y'] for x in historia_salda(con)}
    if not h:
        return None
    dni = sorted(h)
    if d.isoformat() < dni[0]:
        return h[dni[0]] - sum(r[0] for r in con.execute(
            "SELECT kwota FROM operacje WHERE rachunek IN ('główny', 'online') AND data_ksiegowania = ?", (dni[0],)))
    return h.get(d.isoformat(), h[dni[-1]])


def okresy(con, granulacja='tydzien', od=None, do=None, saldo_start=None, rodzaj=None, scenariusz='ostrozny', arkusz=None,
           pierwszy=None) -> dict:
    """Cash flow jak w BS (A-CF-04, A-CF-07, A-CF-10): kolumny okresów wg granulacji, w każdej wpływy, obciążenia,
    saldo okresu i saldo narastające; SUM, MAX, MIN z okresem; lista pozycji z numerem okresu.

    Oś czasu: dzień płatności w prognozie (jak w prognozie 13 tygodni). Przed dniem stanu i w nim: przepływy z banku
    (rzeczywiste). Po dniu stanu: należności z faktur i plany z budżetu, scenariusz ostrożny bez zaległości,
    pełny z nimi (za 7 dni). Saldo startowe = gotówka na koniec dnia przed zakresem, chyba że podane ręcznie.
    Arkusz: tylko pozycje tego arkusza (plany i faktury z nim połączone), bez banku i szacunku, saldo startowe 0."""
    dzien = (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0]
    if not dzien:
        return {'brak_danych': True}
    from .wynik import ustawienia
    stan = _d(dzien)
    if pierwszy is None:
        pierwszy = int(ustawienia().get('cashflow_pierwszy_dzien_tygodnia', PIERWSZY_DZIEN_TYGODNIA))
    granulacja = granulacja or 'tydzien'
    p_od = _d(od) if od else stan
    p_do = _d(do) if do else stan + timedelta(days=DNI)
    lista_okresow = okresy_dat(p_od, p_do, granulacja, pierwszy)
    if scenariusz not in ('ostrozny', 'pelny'):
        raise ValueError('scenariusz: ostrozny albo pelny')
    if rodzaj not in (None, '', '1', '-1', 1, -1):
        raise ValueError('rodzaj: 1 albo -1')
    # pozycje: przyszłość z prognozy, przeszłość z banku
    przyszle, _ = _zdarzenia(con, stan, max(p_do, stan))
    pozycje = [z for z in przyszle if p_od <= z['data'] <= p_do and (scenariusz == 'pelny' or z['scenariusz'] == 'oba')]
    if not arkusz and p_od <= stan:
        pozycje += _historia_banku(con, p_od, min(p_do, stan))
    if arkusz:
        pozycje = [z for z in pozycje if z.get('arkusz_id') == arkusz]
    if rodzaj not in (None, ''):
        znak = int(rodzaj)
        pozycje = [z for z in pozycje if z['kwota'] * znak > 0]
    # saldo startowe: ręczne albo gotówka na koniec dnia przed zakresem (z banku albo z prognozy między stanem a zakresem)
    if saldo_start not in (None, ''):
        start = int(saldo_start)
        zrodlo_salda = 'ręcznie'
    elif arkusz:
        start, zrodlo_salda = 0, 'arkusz'
    elif p_od <= stan:
        start, zrodlo_salda = _saldo_na_koniec_dnia(con, p_od - timedelta(days=1)) or 0, 'bank'
    else:
        start = _saldo_ing(con) + sum(z['kwota'] for z in przyszle if z['data'] < p_od
                                       and (scenariusz == 'pelny' or z['scenariusz'] == 'oba'))
        zrodlo_salda = 'bank i prognoza'
    pozycje.sort(key=lambda z: (z['data'], z['kwota']))
    granice = [_d(o['do']) for o in lista_okresow]
    i = 0
    for z in pozycje:
        while granice[i] < z['data']:
            i += 1
        z['okres'] = i
    narast = start
    for n, o in enumerate(lista_okresow):
        zp = [z for z in pozycje if z['okres'] == n]
        rzecz = lambda z: z['typ'] in ('faktura', 'bank')
        o.update(wplywy=sum(z['kwota'] for z in zp if z['kwota'] > 0), obciazenia=sum(z['kwota'] for z in zp if z['kwota'] < 0),
                 wplywy_plan=sum(z['kwota'] for z in zp if z['kwota'] > 0 and not rzecz(z)),
                 obciazenia_plan=sum(z['kwota'] for z in zp if z['kwota'] < 0 and not rzecz(z)),
                 pozycji=len(zp), biezacy=o['od'] <= dzien <= o['do'], przeszly=o['do'] < dzien)
        o['saldo'] = o['wplywy'] + o['obciazenia']
        narast += o['saldo']
        o['narastajaco'] = narast
    mx = max(range(len(lista_okresow)), key=lambda n: lista_okresow[n]['narastajaco'])
    mn = min(range(len(lista_okresow)), key=lambda n: lista_okresow[n]['narastajaco'])
    for z in pozycje:
        z['data'] = z['data'].isoformat()
        z['przesuniecie'] = (_d(z['data']) - _d(z['termin'])).days if z.get('termin') else 0
    return {'dzien_stanu': dzien, 'od': p_od.isoformat(), 'do': p_do.isoformat(), 'granulacja': granulacja,
            'pierwszy_dzien_tygodnia': pierwszy, 'scenariusz': scenariusz, 'saldo_start': start, 'zrodlo_salda': zrodlo_salda,
            'saldo_ing': _saldo_ing(con), 'okresy': lista_okresow, 'pozycje': pozycje,
            'sum': lista_okresow[-1]['narastajaco'], 'max': {'okres': mx, 'saldo': lista_okresow[mx]['narastajaco']},
            'min': {'okres': mn, 'saldo': lista_okresow[mn]['narastajaco']}}
