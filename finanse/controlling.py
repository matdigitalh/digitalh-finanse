"""Pulpit kontrolingowy: rezerwa gotówki, cel roczny obrotu, marża, porządek w danych.

Cele Mata: domyślne z Finanse/Aplikacja/ustawienia.json, nadpisywane wpisami „cel” z pliku zmian (z apki).
Wszystko to szacunki z danych na dzień stanu; każdy kafel ma status (dobrze / uwaga / źle) z opisem i odnośnikiem.
"""
import json
from datetime import date

from . import wynik
from .wynik import _poprzedni

CELE_DOMYSLNE = {'cel_obrot_rok': 120000000, 'cel_marza_proc': 15, 'rezerwa_miesiecy': 3}
KLUCZE_CELOW = tuple(CELE_DOMYSLNE)
KOSZTY_OPERACYJNE = ('przenoszony', 'praca', 'staly', 'nieprzypisany', 'podatki')
OKNO_MIESIECY = 6


def cele(con) -> dict:
    c = dict(CELE_DOMYSLNE)
    c.update({k: v for k, v in wynik.ustawienia().items() if k in KLUCZE_CELOW})
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='cele'").fetchone()
    if r and r[0]:
        c.update(json.loads(r[0]))
    return c


def _status(wartosc, dobrze, uwaga, wiecej_lepiej=True):
    if wartosc is None:
        return 'brak'
    if wiecej_lepiej:
        return 'dobrze' if wartosc >= dobrze else 'uwaga' if wartosc >= uwaga else 'zle'
    return 'dobrze' if wartosc <= dobrze else 'uwaga' if wartosc <= uwaga else 'zle'


def policz(con) -> dict:
    c = cele(con)
    dzien = (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0]
    if not dzien:
        return {'cele': c, 'brak_danych': True}
    rok = dzien[:4]

    # 1. Rezerwa: gotówka (główny + online) kontra średni miesięczny wypływ na koszty z ostatnich pełnych miesięcy.
    #    Wypływ z banku (kasowo), bez VAT, podziału zysku, zwrotów i ruchu wewnętrznego.
    gotowka = sum(r[0] for r in con.execute(
        "SELECT saldo_po FROM operacje o WHERE rachunek IN ('główny', 'online') AND saldo_po IS NOT NULL AND id = ("
        " SELECT id FROM operacje p WHERE p.rachunek = o.rachunek AND p.saldo_po IS NOT NULL"
        " ORDER BY data_ksiegowania DESC, data_pliku DESC, wiersz ASC LIMIT 1)"))
    pelne = []
    m = _poprzedni(dzien[:7])
    while len(pelne) < OKNO_MIESIECY:
        pelne.append(m)
        m = _poprzedni(m)
    miesieczne = {m: 0 for m in pelne}
    stale = {m: 0 for m in pelne}   # bez kosztów klientów: to, co utrzymuje agencję niezależnie od zleceń
    for r in con.execute('SELECT substr(o.data_ksiegowania, 1, 7) AS m, w.rodzaj, -SUM(o.kwota) FROM wydatki w JOIN operacje o'
                         f" ON o.id = w.operacja_id WHERE w.rodzaj IN ({','.join('?' * len(KOSZTY_OPERACYJNE))}) GROUP BY m, w.rodzaj",
                         KOSZTY_OPERACYJNE):
        if r[0] in miesieczne:
            miesieczne[r[0]] += r[2]
            if r[1] != 'przenoszony':
                stale[r[0]] += r[2]
    z_danymi = [v for v in miesieczne.values() if v]
    srednia = round(sum(z_danymi) / len(z_danymi)) if z_danymi else 0
    srednia_stale = round(sum(stale.values()) / len(z_danymi)) if z_danymi else 0
    wymagana = srednia * c['rezerwa_miesiecy']
    pokrycie = round(gotowka / srednia, 1) if srednia else None
    rezerwa = {'gotowka': gotowka, 'srednie_koszty': srednia, 'miesiecy_cel': c['rezerwa_miesiecy'], 'wymagana': wymagana,
               'pokrycie_miesiecy': pokrycie, 'nadwyzka': gotowka - wymagana, 'srednie_stale': srednia_stale,
               'pokrycie_stalych': round(gotowka / srednia_stale, 1) if srednia_stale else None,
               'wymagana_stale': srednia_stale * c['rezerwa_miesiecy'],
               'status': _status(pokrycie, c['rezerwa_miesiecy'], c['rezerwa_miesiecy'] * 2 / 3),
               'okno': sorted(pelne), 'miesieczne': [{'miesiac': m, 'kwota': miesieczne[m], 'stale': stale[m]} for m in sorted(pelne)]}

    # 2. Obrót: od początku roku, plan liniowy na dziś i prognoza na koniec roku ze średniej pełnych miesięcy.
    w = wynik.wynik_zarzadczy(con, rok)
    wiersz = {x['klucz']: x for x in w['wiersze']}
    pelne_rok = [m for m in w['miesiace'] if m not in w['niepelne']]
    obrot_ytd = wiersz['obrot']['razem']
    obrot_pelne = sum(wiersz['obrot']['miesiace'][m] for m in pelne_rok)
    prognoza_obrot = round(obrot_pelne / len(pelne_rok) * 12) if pelne_rok else None
    czesc_roku = date.fromisoformat(dzien).timetuple().tm_yday / (366 if int(rok) % 4 == 0 else 365)
    plan_na_dzis = round(c['cel_obrot_rok'] * czesc_roku)
    obrot = {'ytd': obrot_ytd, 'cel': c['cel_obrot_rok'], 'plan_na_dzis': plan_na_dzis, 'czesc_roku': round(czesc_roku, 3),
             'prognoza': prognoza_obrot, 'srednio_miesiecznie': round(obrot_pelne / len(pelne_rok)) if pelne_rok else None,
             'potrzeba_miesiecznie': round((c['cel_obrot_rok'] - obrot_pelne) / max(1, 12 - len(pelne_rok))),
             'status': _status(prognoza_obrot / c['cel_obrot_rok'] if prognoza_obrot else None, 1, 0.9)}

    # 3. Marża wyniku zarządczego (pełne miesiące) kontra cel; zysk potrzebny do celu.
    wynik_pelne = sum(wiersz['wynik']['miesiace'][m] for m in pelne_rok)
    marza = round(100 * wynik_pelne / obrot_pelne, 1) if obrot_pelne else None
    cel_zysk = round(c['cel_obrot_rok'] * c['cel_marza_proc'] / 100)
    prognoza_wynik = round(wynik_pelne / len(pelne_rok) * 12) if pelne_rok else None
    marza_d = {'proc': marza, 'cel_proc': c['cel_marza_proc'], 'wynik_ytd': wiersz['wynik']['razem'], 'wynik_pelne': wynik_pelne,
               'cel_zysk': cel_zysk, 'prognoza_wynik': prognoza_wynik,
               'status': _status(marza, c['cel_marza_proc'], c['cel_marza_proc'] / 2),
               'miesiace': [{'miesiac': m, 'proc': round(100 * wiersz['wynik']['miesiace'][m] / wiersz['obrot']['miesiace'][m], 1)
                             if wiersz['obrot']['miesiace'][m] else None} for m in pelne_rok]}

    # 4. Należności i porządek w danych
    nal = con.execute('SELECT COALESCE(SUM(pozostalo), 0), COALESCE(SUM(CASE WHEN dni_po_terminie > 30 THEN pozostalo END), 0)'
                      ' FROM faktury_stan WHERE pozostalo > 0').fetchone()
    po_30_proc = round(100 * nal[1] / nal[0], 1) if nal[0] else 0
    porzadek = {'do_polaczenia': con.execute("SELECT COUNT(*) FROM wplaty WHERE stan='nieznana'").fetchone()[0],
                'nieprzypisane': con.execute("SELECT COUNT(*) FROM wydatki WHERE rodzaj='nieprzypisany'").fetchone()[0],
                'nieprzypisane_kwota': -con.execute("SELECT COALESCE(SUM(o.kwota), 0) FROM wydatki w JOIN operacje o ON o.id = w.operacja_id"
                                                    " WHERE w.rodzaj='nieprzypisany'").fetchone()[0]}
    naleznosci = {'razem': nal[0], 'po_30_dniach': nal[1], 'po_30_proc': po_30_proc, 'status': _status(po_30_proc, 15, 30, False)}
    return {'cele': c, 'dzien_stanu': dzien, 'rok': rok, 'rezerwa': rezerwa, 'obrot': obrot, 'marza': marza_d,
            'naleznosci': naleznosci, 'porzadek': porzadek, 'pelne_miesiace': pelne_rok}
