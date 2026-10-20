"""Pulpit kontrolingowy: rezerwa gotówki, cel roczny obrotu, marża, porządek w danych.

Cele Mata: domyślne z Finanse/Aplikacja/ustawienia.json, nadpisywane wpisami „cel” z pliku zmian (z apki).
Wszystko to szacunki z danych na dzień stanu; każdy kafel ma status (dobrze / uwaga / źle) z opisem i odnośnikiem.
"""
import calendar
import json
from datetime import date

from . import wynik
from .wynik import _poprzedni

# Awaryjne, gdy brak Finanse/Aplikacja/ustawienia.json; obowiązują wartości z tego pliku (APK-BUG-08, do potwierdzenia z Matem).
CELE_DOMYSLNE = {'cel_obrot_rok': 120000000, 'cel_marza_proc': 15, 'rezerwa_miesiecy': 3}
KLUCZE_CELOW = tuple(CELE_DOMYSLNE)
KOSZTY_OPERACYJNE = ('przenoszony', 'praca', 'staly', 'nieprzypisany', 'podatki')
OKNO_MIESIECY = 6
# Rezerwa na koszty krytyczne (decyzja Mata 2026-10-20): koszty, których nie można nie zapłacić; Mat sam wybiera pozycje.
# (klucz, nazwa, co wchodzi). Pozycja wynika z rodzaju wydatku; księgowość to koszty stałe kontrahentów z listy w ustawieniach.
POZYCJE_REZERWY = (
    ('wynagrodzenia', 'Wynagrodzenia', 'pensje, ZUS, PIT, PPK, Medicover'),
    ('ksiegowosc', 'Księgowość', 'biuro rachunkowe (lista niżej)'),
    ('narzedzia', 'Narzędzia i inne stałe', 'koszty stałe bez księgowości'),
    ('podatki', 'Podatki', 'daniny poza VAT'),
    ('klienci', 'Koszty klientów', 'zakupy pod zlecenia'),
    ('nieprzypisane', 'Nieprzypisane', 'wydatki bez rodzaju'),
)
KLUCZE_POZYCJI = tuple(p[0] for p in POZYCJE_REZERWY)
POZYCJE_WLACZONE = ('wynagrodzenia', 'ksiegowosc')
KSIEGOWOSC_DOMYSLNA = ['brixen fk']   # nadpisuje klucz „rezerwa_ksiegowosc” w ustawienia.json i wpis „rezerwa” z apki
_POZYCJA_RODZAJU = {'praca': 'wynagrodzenia', 'podatki': 'podatki', 'przenoszony': 'klienci', 'nieprzypisany': 'nieprzypisane'}


def cele(con) -> dict:
    c = dict(CELE_DOMYSLNE)
    c.update({k: v for k, v in wynik.ustawienia().items() if k in KLUCZE_CELOW})
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='cele'").fetchone()
    if r and r[0]:
        c.update(json.loads(r[0]))
    return c


def ustawienia_rezerwy(con) -> dict:
    """Pozycje rezerwy: domyślne, potem ustawienia.json (lista księgowości), potem wpisy „rezerwa” z pliku zmian (meta, po cofnięciach)."""
    pozycje = {k: {'wlaczona': k in POZYCJE_WLACZONE, 'kwota': None} for k in KLUCZE_POZYCJI}
    ksiegowosc = wynik.ustawienia().get('rezerwa_ksiegowosc')
    ksiegowosc = list(ksiegowosc) if isinstance(ksiegowosc, list) else list(KSIEGOWOSC_DOMYSLNA)
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='rezerwa'").fetchone()
    zapis = json.loads(r[0]) if r and r[0] else {}
    for k, v in (zapis.get('pozycje') or {}).items():
        if k in pozycje:
            pozycje[k].update({p: v[p] for p in ('wlaczona', 'kwota') if p in v})
    if 'ksiegowosc' in zapis:
        ksiegowosc = list(zapis['ksiegowosc'])
    return {'pozycje': pozycje, 'ksiegowosc': ksiegowosc}


def pozycja_wydatku(rodzaj: str, kontrahent_klucz: str, ksiegowosc) -> str | None:
    if rodzaj == 'staly':
        return 'ksiegowosc' if kontrahent_klucz in ksiegowosc else 'narzedzia'
    return _POZYCJA_RODZAJU.get(rodzaj)


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

    # 1. Rezerwa: gotówka (główny + online) kontra miesięczny koszt krytyczny (suma włączonych pozycji: średnia z banku
    #    z ostatnich pełnych miesięcy albo kwota własna Mata). Wypływ z banku (kasowo), bez VAT, podziału zysku, zwrotów i ruchu wewnętrznego.
    gotowka = sum(r[0] for r in con.execute(
        "SELECT saldo_po FROM operacje o WHERE rachunek IN ('główny', 'online') AND saldo_po IS NOT NULL AND id = ("
        " SELECT id FROM operacje p WHERE p.rachunek = o.rachunek AND p.saldo_po IS NOT NULL"
        " ORDER BY data_ksiegowania DESC, data_pliku DESC, wiersz ASC LIMIT 1)"))
    pelne = []
    m = _poprzedni(dzien[:7])
    while len(pelne) < OKNO_MIESIECY:
        pelne.append(m)
        m = _poprzedni(m)
    ust = ustawienia_rezerwy(con)
    ksieg = set(ust['ksiegowosc'])
    miesieczne = {m: 0 for m in pelne}
    stale = {m: 0 for m in pelne}   # bez kosztów klientów: to, co utrzymuje agencję niezależnie od zleceń
    poz = {k: {m: 0 for m in pelne} for k in KLUCZE_POZYCJI}
    kontr_stale = {}
    for r in con.execute('SELECT substr(o.data_ksiegowania, 1, 7) AS m, w.rodzaj, COALESCE(w.kontrahent_klucz, \'\'), -SUM(o.kwota)'
                         ' FROM wydatki w JOIN operacje o ON o.id = w.operacja_id'
                         f" WHERE w.rodzaj IN ({','.join('?' * len(KOSZTY_OPERACYJNE))}) GROUP BY m, w.rodzaj, w.kontrahent_klucz",
                         KOSZTY_OPERACYJNE):
        m, rodzaj, kk, kwota = r
        if m not in miesieczne:
            continue
        miesieczne[m] += kwota
        if rodzaj != 'przenoszony':
            stale[m] += kwota
        poz[pozycja_wydatku(rodzaj, kk, ksieg)][m] += kwota
        if rodzaj == 'staly' and kk:
            kontr_stale[kk] = kontr_stale.get(kk, 0) + kwota
    z_danymi = [v for v in miesieczne.values() if v]
    ile = len(z_danymi)
    srednia = round(sum(z_danymi) / ile) if ile else 0
    srednia_stale = round(sum(stale.values()) / ile) if ile else 0
    pozycje, koszt = [], 0
    for k, nazwa, opis in POZYCJE_REZERWY:
        u = ust['pozycje'][k]
        sr = round(sum(poz[k].values()) / ile) if ile else 0
        liczona = u['kwota'] if u['kwota'] is not None else sr
        if u['wlaczona']:
            koszt += liczona
        pozycje.append({'klucz': k, 'nazwa': nazwa, 'opis': opis, 'wlaczona': u['wlaczona'], 'srednia': sr, 'kwota_wlasna': u['kwota'],
                        'liczona': liczona, 'miesieczne': [poz[k][m] for m in sorted(pelne)]})
    miesiecy = c['rezerwa_miesiecy']
    wymagana = round(koszt * miesiecy)
    pokrycie = round(gotowka / koszt, 1) if koszt else None
    rezerwa = {'gotowka': gotowka, 'koszt_krytyczny': koszt, 'pozycje': pozycje, 'ksiegowosc': ust['ksiegowosc'],
               'kontrahenci_stali': [k for k, _ in sorted(kontr_stale.items(), key=lambda x: -x[1])][:40],
               'wlaczone': [p['nazwa'] for p in pozycje if p['wlaczona']],
               'miesiecy_cel': miesiecy, 'wymagana': wymagana, 'pokrycie_miesiecy': pokrycie, 'nadwyzka': gotowka - wymagana,
               'status': _status(pokrycie, miesiecy, miesiecy * 2 / 3),
               # miary sprzed 2026-10-20 (wszystkie koszty i bez kosztów klientów); cashflow.py czyta srednie_stale
               'srednie_koszty': srednia, 'pokrycie_wszystkich': round(gotowka / srednia, 1) if srednia else None,
               'wymagana_wszystkie': round(srednia * miesiecy), 'srednie_stale': srednia_stale,
               'pokrycie_stalych': round(gotowka / srednia_stale, 1) if srednia_stale else None,
               'wymagana_stale': round(srednia_stale * miesiecy),
               'okno': sorted(pelne), 'miesieczne': [{'miesiac': m, 'kwota': miesieczne[m], 'stale': stale[m]} for m in sorted(pelne)]}

    # 2. Obrót: od początku roku, plan liniowy na dziś i prognoza na koniec roku ze średniej pełnych miesięcy.
    w = wynik.wynik_zarzadczy(con, rok)
    wiersz = {x['klucz']: x for x in w['wiersze']}
    pelne_rok = [m for m in w['miesiace'] if m not in w['niepelne']]
    obrot_ytd = wiersz['obrot']['razem']
    obrot_pelne = sum(wiersz['obrot']['miesiace'][m] for m in pelne_rok)
    prognoza_obrot = round(obrot_pelne / len(pelne_rok) * 12) if pelne_rok else None
    czesc_roku = date.fromisoformat(dzien).timetuple().tm_yday / (366 if calendar.isleap(int(rok)) else 365)
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
