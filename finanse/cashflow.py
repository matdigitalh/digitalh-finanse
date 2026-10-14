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


def prognoza(con) -> dict:
    dzien = (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0]
    if not dzien:
        return {'brak_danych': True}
    start = _d(dzien)
    koniec = start + timedelta(days=DNI)
    saldo = sum(r[0] for r in con.execute(
        "SELECT saldo_po FROM operacje o WHERE rachunek IN ('główny', 'online') AND saldo_po IS NOT NULL AND id = ("
        " SELECT id FROM operacje p WHERE p.rachunek = o.rachunek AND p.saldo_po IS NOT NULL"
        " ORDER BY data_ksiegowania DESC, data_pliku DESC, wiersz ASC LIMIT 1)"))
    spoz = _spoznienia(con)
    zdarzenia = []   # (data, kwota, opis, rodzaj, scenariusz: 'oba'|'pelny', zrodlo)
    for r in con.execute('SELECT f.numer, f.nip, f.nabywca, f.termin, s.pozostalo, s.dni_po_terminie, fk.klient FROM faktury_stan s'
                         ' JOIN faktury f USING(numer) LEFT JOIN faktury_klient fk USING(numer) WHERE s.pozostalo > 0'):
        if (r['dni_po_terminie'] or 0) > 0:
            zdarzenia.append((start + timedelta(days=7), r['pozostalo'], f"{r['numer']} {r['klient'] or r['nabywca']} (po terminie)",
                              'należność po terminie', 'pelny', r['numer']))
        else:
            d = max(start + timedelta(days=1), _d(r['termin']) + timedelta(days=spoz.get(r['nip'] or r['nabywca'], 0)))
            zdarzenia.append((d, r['pozostalo'], f"{r['numer']} {r['klient'] or r['nabywca']}", 'należność', 'oba', r['numer']))
    po_terminie = []
    for r in con.execute("SELECT p.id, p.rodzaj, p.brutto, s.termin_efektywny, s.etap, w.kontrahent, a.nazwa FROM bud_platnosc p"
                         ' JOIN bud_stan s ON s.platnosc = p.id JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz'
                         " WHERE p.aktualna = 1 AND p.w_cashflow = 1 AND s.etap IN ('Planowana', 'Po terminie')"
                         " AND NOT EXISTS (SELECT 1 FROM bud_powiazanie b WHERE b.platnosc = p.id AND b.typ = 'faktura')"):
        kwota = r['brutto'] * r['rodzaj']
        opis = f"{r['kontrahent'] or ''} · {r['nazwa']}"
        if r['etap'] == 'Po terminie':
            po_terminie.append({'platnosc': r['id'], 'termin': r['termin_efektywny'], 'kwota': kwota, 'opis': opis})
            zdarzenia.append((start + timedelta(days=7), kwota, opis + ' (plan po terminie)', 'plan po terminie', 'pelny', r['id']))
        else:
            d = _d(r['termin_efektywny'])
            if d and start < d <= koniec:
                zdarzenia.append((d, kwota, opis, 'plan przychodu' if kwota > 0 else 'plan wydatku', 'oba', r['id']))
    # Miesiące bez planu kosztów (plany BS kończą się zwykle na grudniu): szacunek kosztów pracy i stałych ze średniej
    # z 6 pełnych miesięcy (jak rezerwa na pulpicie), 10. dnia miesiąca, jako wyraźnie opisana pozycja.
    from .controlling import policz as kontrolka
    srednie = kontrolka(con).get('rezerwa', {}).get('srednie_stale', 0)
    plan_kosztow = defaultdict(int)
    for z in zdarzenia:
        if z[1] < 0 and z[3] == 'plan wydatku':
            plan_kosztow[z[0].isoformat()[:7]] += -z[1]
    m = start.replace(day=1)
    while m <= koniec:
        klucz = m.isoformat()[:7]
        d10 = m.replace(day=10)
        if srednie and start < d10 <= koniec and plan_kosztow[klucz] < srednie // 2:
            zdarzenia.append((d10, -(srednie - plan_kosztow[klucz]), f'szacunek kosztów pracy i stałych {klucz} (brak planu w budżecie)',
                              'szacunek kosztów', 'oba', ''))
        m = (m + timedelta(days=32)).replace(day=1)
    dni = []
    s_ostr, s_peln = saldo, saldo
    po_dniu = defaultdict(list)
    for z in zdarzenia:
        if z[0] <= koniec:
            po_dniu[z[0]].append(z)
    for i in range(DNI + 1):
        d = start + timedelta(days=i)
        for z in po_dniu.get(d, []):
            s_peln += z[1]
            if z[4] == 'oba':
                s_ostr += z[1]
        dni.append({'data': d.isoformat(), 'ostrozny': s_ostr, 'pelny': s_peln,
                    'wplywy': sum(z[1] for z in po_dniu.get(d, []) if z[1] > 0), 'wydatki': sum(z[1] for z in po_dniu.get(d, []) if z[1] < 0)})
    tygodnie = []
    for t in range(13):
        od, do = start + timedelta(days=7 * t + 1), start + timedelta(days=7 * t + 7)
        zt = [z for z in zdarzenia if od <= z[0] <= do]
        tygodnie.append({'od': od.isoformat(), 'do': do.isoformat(),
                         'wplywy': sum(z[1] for z in zt if z[1] > 0 and z[4] == 'oba'),
                         'wydatki': sum(z[1] for z in zt if z[1] < 0 and z[4] == 'oba'),
                         'tylko_pelny': sum(z[1] for z in zt if z[4] == 'pelny'),
                         'saldo_ostrozny': dni[min(7 * t + 7, DNI)]['ostrozny'], 'saldo_pelny': dni[min(7 * t + 7, DNI)]['pelny'],
                         'pozycje': [{'data': z[0].isoformat(), 'kwota': z[1], 'opis': z[2], 'rodzaj': z[3], 'scenariusz': z[4]}
                                     for z in sorted(zt, key=lambda z: z[0])]})
    minimum = min(dni, key=lambda x: x['ostrozny'])
    return {'dzien_stanu': dzien, 'saldo_start': saldo, 'dni': dni, 'tygodnie': tygodnie, 'po_terminie': po_terminie,
            'minimum_ostrozny': {'data': minimum['data'], 'saldo': minimum['ostrozny']},
            'koniec': {'ostrozny': dni[-1]['ostrozny'], 'pelny': dni[-1]['pelny']}}
