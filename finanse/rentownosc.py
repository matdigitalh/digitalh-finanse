"""Etap G: rentowność per klient i per arkusz.

Klient: obrót netto (faktury klienta), koszty klienta (wydatki przypisane, netto z dokumentu), marża, koszt pracy
według estymaty Mata (udział czasu zespołu w %, wpis „estymata” w pliku zmian) razy koszty pracy z wyniku zarządczego.
Arkusz: plan kontra wykonanie z budżetu (netto): plan = wszystkie aktualne płatności arkusza, wykonanie = opłacone
w banku (przychód przez fakturę, koszt przez wydatek).
"""
import json
from collections import defaultdict

from . import wynik


def estymaty(con) -> dict:
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='estymaty'").fetchone()
    return json.loads(r[0]) if r and r[0] else {}


def klienci(con, rok=None) -> dict:
    rok = rok or wynik._rok_domyslny(con)
    o = wynik.obroty_klientow(con, rok)
    w = wynik.wynik_zarzadczy(con, rok)
    praca = -next(x for x in w['wiersze'] if x['klucz'] == 'praca')['razem']
    est = estymaty(con)
    lista = []
    for k in o['klienci']:
        udzial = est.get(k['klient'], {}).get('udzial')
        koszt_pracy = round(praca * udzial / 100) if udzial is not None else None
        lista.append({**k, 'udzial_czasu': udzial, 'koszt_pracy': koszt_pracy,
                      'wynik_klienta': k['pna'] - koszt_pracy if koszt_pracy is not None else None})
    suma_udzialow = sum(v['udzial'] for v in est.values())
    return {'rok': rok, 'klienci': lista, 'koszty_pracy_rok': praca, 'suma_udzialow': suma_udzialow,
            'bez_estymaty': sum(1 for x in lista if x['udzial_czasu'] is None)}


def arkusze(con) -> list[dict]:
    t = defaultdict(lambda: {'plan_przychod': 0, 'plan_koszt': 0, 'wyk_przychod': 0, 'wyk_koszt': 0, 'po_terminie': 0})
    for r in con.execute('SELECT a.id, a.folder, a.kategoria, a.nazwa, p.rodzaj, p.netto, s.etap FROM bud_platnosc p'
                         ' JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz JOIN bud_stan s ON s.platnosc = p.id'
                         ' WHERE p.aktualna = 1'):
        x = t[r['id']]
        x.update(folder=r['folder'], kategoria=r['kategoria'], nazwa=r['nazwa'], id=r['id'])
        if r['rodzaj'] == 1:
            x['plan_przychod'] += r['netto']
            if r['etap'] == 'Opłacona':
                x['wyk_przychod'] += r['netto']
        else:
            x['plan_koszt'] += r['netto']
            if r['etap'] == 'Opłacona':
                x['wyk_koszt'] += r['netto']
        if r['etap'] == 'Po terminie':
            x['po_terminie'] += 1
    lista = []
    for x in t.values():
        x['plan_saldo'] = x['plan_przychod'] - x['plan_koszt']
        x['wyk_saldo'] = x['wyk_przychod'] - x['wyk_koszt']
        x['realizacja_proc'] = round(100 * x['wyk_przychod'] / x['plan_przychod'], 1) if x['plan_przychod'] else None
        lista.append(x)
    return sorted(lista, key=lambda x: (x['folder'], x['nazwa']))
