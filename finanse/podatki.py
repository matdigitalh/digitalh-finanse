"""Pakiet 8: VAT, podatek dochodowy (CIT), PIT-4 i ZUS jak w Budget Studio (sp. z o.o., VAT miesięcznie memoriałowo).

Arkusz systemowy „Opłaty urzędowe RRRR” (folder System, jeden na każdy rok horyzontu budżetu) liczony od nowa przy każdej
odbudowie. Bez własnych wzorów podatkowych:
  - VAT okresu = VAT wpływów − VAT obciążeń z płatności z podstawą Faktura (plany i rzeczywiste, także nieaktualne, jak
    w BS), Księgowane = tak, okres wg miesiąca księgowania. Nadpłata przechodzi na kolejne okresy, a nadpłata, która
    zostanie po ostatnim okresie horyzontu, staje się planem zwrotu (wpływ),
  - zaliczka CIT = max(0, podstawa narastająco × stawka od Mata − zaliczki wcześniejszych okresów roku), podstawa = netto
    księgowanych wpływów − netto księgowanych obciążeń (bez faktury: wartość, umowy: składowe); po roku: zwrot nadpłaty,
  - kwota od biura (wpis „danina”) zamraża okres: plan staje się płatnością rzeczywistą, nic się dalej nie przelicza,
    a kwota zasila saldo nadpłaty. Rzeczywiste daniny z eksportu BS są kwotami od biura, plany BS punktem odniesienia,
  - PIT-4 i ZUS to składowe umów z budżetu (pakiet 2): tu kalendarz i porównanie z bankiem,
  - prognoza salda rachunku VAT (split payment): start z ING, wpływy = VAT z wpłat MPP, wypływy = daniny z rachunku VAT.
Reguły [DOMYSŁ] (stawka i okres CIT, przenoszenie nadpłaty, terminy) są ustawieniem (wpis „ustawienie”, klucz podatki)
z wartościami domyślnymi jak w BS, do potwierdzenia z biurem. Kwoty w groszach, proporcje jako Fraction.
"""
import json
import re
from collections import defaultdict
from datetime import date, timedelta
from fractions import Fraction

from . import plan
from .format import grosze, norm

MIESIACE = ['styczeń', 'luty', 'marzec', 'kwiecień', 'maj', 'czerwiec', 'lipiec', 'sierpień', 'wrzesień', 'październik',
            'listopad', 'grudzień']
KWARTALY = ['I', 'II', 'III', 'IV']
URZAD = 'Urząd Skarbowy'

# Ustawienia podatkowe (B-DAN-01). Domyślne jak w Budget Studio DigitalH (eksport z 14.10.2026: CIT kwartalnie, 19%,
# zwrot nadpłaty 14.06 roku następnego); każde do potwierdzenia z biurem.
USTAWIENIA_DOMYSLNE = {
    'vat_okres': 'miesiac',          # miesiąc albo kwartał
    'vat_dzien': 25,                 # termin VAT: dzień miesiąca po okresie
    'vat_przenoszenie': 'tak',       # nadpłata przechodzi na kolejne okresy (BS); „nie” = zwrot za każdy okres
    'vat_saldo_startowe': 0,         # nadwyżka VAT przeniesiona sprzed pierwszego okresu horyzontu (grosze)
    'zwrot_termin': '06-14',         # termin zwrotu nadpłaty (VAT na końcu horyzontu, CIT po roku): MM-DD roku następnego
    'cit_okres': 'kwartal',
    'cit_stawka': 19,                # 9 albo 19; brak = brak prognozy CIT
    'cit_dzien': 20,
    'cit_zaokraglenie': 'grosze',    # grosze (jak BS) albo pełne zł
    'rachunek_vat_na': 'wszystkie',  # z rachunku VAT idą: tylko VAT albo VAT, CIT, PIT-4 i ZUS (tak jest w wyciągach ING)
}
STALE = {'forma': 'sp. z o.o.', 'vat': 'czynny, memoriałowo', 'pit4_dzien': 20, 'zus_dzien': 15}
DANINY = ('vat', 'cit', 'vat_zwrot', 'cit_roczny')
KIERUNKI = ('zaplata', 'przeniesienie', 'zwrot')


# ---------- Walidacja wpisów ----------

def _dzien_miesiaca(v, pole):
    if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 28:
        raise ValueError(f'{pole}: dzień miesiąca od 1 do 28')
    return v


def _wybor(*dozwolone):
    def f(v, pole):
        if v not in dozwolone or isinstance(v, bool):
            raise ValueError(f'{pole}: dozwolone {", ".join(str(x) for x in dozwolone if x is not None)}'
                             + (' albo puste' if None in dozwolone else ''))
        return v
    return f


def _kwota(v, pole):
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < 10 ** 11:
        raise ValueError(f'{pole}: kwota w groszach, liczba całkowita od 0')
    return v


def _mm_dd(v, pole):
    if not isinstance(v, str) or not re.fullmatch(r'(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])', v):
        raise ValueError(f'{pole}: dzień i miesiąc w zapisie MM-DD')
    date.fromisoformat(f'2001-{v}')
    return v


POLA_USTAWIEN = {
    'vat_okres': _wybor('miesiac', 'kwartal'), 'vat_dzien': _dzien_miesiaca, 'vat_przenoszenie': _wybor('tak', 'nie'),
    'vat_saldo_startowe': _kwota, 'zwrot_termin': _mm_dd, 'cit_okres': _wybor('miesiac', 'kwartal'),
    'cit_stawka': _wybor(9, 19, None), 'cit_dzien': _dzien_miesiaca, 'cit_zaokraglenie': _wybor('grosze', 'zl'),
    'rachunek_vat_na': _wybor('vat', 'wszystkie'),
}


def sprawdz_ustawienia(v) -> dict:
    """Ustawienia podatkowe z interfejsu (część pól wystarczy): tylko znane pola, każde ze swoim zakresem."""
    if not isinstance(v, dict) or not v:
        raise ValueError('ustawienia podatkowe: oczekiwany obiekt z co najmniej jednym polem')
    nieznane = sorted(set(v) - set(POLA_USTAWIEN))
    if nieznane:
        raise ValueError(f'ustawienia podatkowe: nieznane pole {", ".join(nieznane)}')
    return {k: POLA_USTAWIEN[k](x, k) for k, x in v.items()}


def _data(v, pole):
    if v in (None, ''):
        return None
    if not isinstance(v, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', v):
        raise ValueError(f'{pole}: data RRRR-MM-DD')
    date.fromisoformat(v)
    return v


def sprawdz_danine(d) -> dict:
    """Wpis „danina”: kwota od biura za okres (zamraża go), termin albo dzień realnej płatności planu, albo odmrożenie."""
    if not isinstance(d, dict):
        raise ValueError('danina: oczekiwany obiekt')
    nieznane = sorted(set(d) - {'danina', 'okres', 'kwota', 'kierunek', 'termin', 'realny', 'komentarz', 'usun'})
    if nieznane:
        raise ValueError(f'danina: nieznane pole {", ".join(nieznane)}')
    danina, okres = d.get('danina'), d.get('okres')
    if danina not in DANINY:
        raise ValueError('danina: VAT, CIT, zwrot VAT albo CIT roczny')
    roczna = danina in ('vat_zwrot', 'cit_roczny')
    if not isinstance(okres, str) or not re.fullmatch(r'\d{4}' if roczna else r'\d{4}-(0[1-9]|1[0-2])', okres):
        raise ValueError('okres: rok RRRR' if roczna else 'okres: miesiąc RRRR-MM (pierwszy miesiąc okresu)')
    if d.get('usun'):
        return {'danina': danina, 'okres': okres, 'usun': True}
    wynik = {'danina': danina, 'okres': okres}
    if d.get('kwota') is not None:
        wynik['kwota'] = _kwota(d['kwota'], 'kwota')
        kier = d.get('kierunek') or ('zwrot' if danina == 'vat_zwrot' else 'zaplata')
        dozwolone = {'vat': KIERUNKI, 'cit': ('zaplata',), 'vat_zwrot': ('zwrot',), 'cit_roczny': ('zaplata', 'zwrot')}[danina]
        if kier not in dozwolone:
            raise ValueError('kierunek: ' + ', '.join({'zaplata': 'do zapłaty', 'przeniesienie': 'nadwyżka do przeniesienia',
                                                         'zwrot': 'zwrot'}[k] for k in dozwolone))
        wynik['kierunek'] = kier
    for k in ('termin', 'realny'):
        if d.get(k):
            wynik[k] = _data(d[k], k)
    if d.get('komentarz') is not None:
        if not isinstance(d['komentarz'], str) or len(d['komentarz']) > 170:
            raise ValueError('komentarz: najwyżej 170 znaków')
        wynik['komentarz'] = d['komentarz'].strip()
    if len(wynik) == 2:
        raise ValueError('danina: podaj kwotę od biura, termin albo dzień realnej płatności')
    return wynik


def sprawdz_bud(d: dict):
    """Arkusz systemowy zmienia tylko system (B-DAN-02): zwykłe zmiany budżetu nie dotykają jego obiektów, a podstaw
    podatkowych nie ma w zwykłych wierszach. Kwotę od biura i dzień realny wpisuje się w Podatkach (wpis „danina”)."""
    for o in (d['operacje'] if d.get('op') == 'seria' else [d]):
        ids = [(o.get('obiekt') or {}).get('id'), (o.get('obiekt') or {}).get('arkusz'), (o.get('obiekt') or {}).get('wiersz'),
               (o.get('obiekt') or {}).get('wzor'), o.get('platnosc'), o.get('wiersz'), o.get('do_arkusza'), o.get('arkusz'),
               *(o.get('wiersze') or [])]   # o.get('arkusz'): przesunięcie i duplikat arkusza (pakiet 3)
        if any(isinstance(x, str) and x.startswith('sys:') for x in ids):
            raise ValueError('To arkusz systemowy z podatkami: plany liczy apka. Kwotę od biura i dzień realnej płatności '
                             'wpiszesz w Budżet, Podatki.')
        if o.get('op') == 'wiersz' and (o.get('obiekt') or {}).get('podstawa') in plan.PODATKI:
            raise ValueError('VAT i podatek dochodowy liczy arkusz systemowy Opłaty urzędowe. W zwykłym wierszu wybierz inną podstawę.')


# ---------- Ustawienia i wpisy Mata ----------

def wczytaj_reczne(wpisy: list[dict]) -> tuple[dict, dict]:
    """(ustawienia, daniny): ostatni wpis wygrywa, cofnięte pomijamy. Danina: pola z kolejnych wpisów się składają,
    „usun” odmraża okres (także kwotę z eksportu BS) i kasuje wcześniejsze pola."""
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    ust, daniny = dict(USTAWIENIA_DOMYSLNE), {}
    for w in wpisy:
        if w.get('id') in cofniete:
            continue
        d = w.get('dane') or {}
        if w.get('typ') == 'ustawienie' and d.get('klucz') == 'podatki' and isinstance(d.get('wartosc'), dict):
            ust.update({k: v for k, v in d['wartosc'].items() if k in USTAWIENIA_DOMYSLNE})
        elif w.get('typ') == 'danina':
            klucz = (d['danina'], d['okres'])
            if d.get('usun'):
                daniny[klucz] = {'odmrozony': True, 'wpis': w['id'], 'czas': w['czas']}
                continue
            x = daniny.setdefault(klucz, {})
            x.update({k: v for k, v in d.items() if k not in ('danina', 'okres')})
            x.update(wpis=w['id'], czas=w['czas'])
    return ust, daniny


# ---------- Okresy i daty ----------

def _nastepny(m: str, o: int = 1) -> str:
    return plan.przesun_miesiac(m, o)


def _miesiace(od: str, do: str) -> list[str]:
    wynik, m = [], od
    while m <= do:
        wynik.append(m)
        m = _nastepny(m)
    return wynik


def _poczatek(m: str, dlugosc: int) -> str:
    """Pierwszy miesiąc okresu (miesiąc albo kwartał kalendarzowy), do którego należy miesiąc m."""
    if dlugosc == 1:
        return m
    return f'{m[:4]}-{(int(m[5:7]) - 1) // 3 * 3 + 1:02d}'


def okresy(od: str, do: str, dlugosc: int) -> list[tuple[str, str]]:
    """(pierwszy, ostatni miesiąc) okresów zahaczających o zakres miesięcy od, do."""
    wynik, s = [], _poczatek(od, dlugosc)
    while s <= do:
        wynik.append((s, _nastepny(s, dlugosc - 1)))
        s = _nastepny(s, dlugosc)
    return wynik


def _dzien_po(koniec: str, dzien: int) -> str:
    """Ustawowy termin: dany dzień miesiąca po ostatnim miesiącu okresu."""
    m = _nastepny(koniec)
    return f'{m}-{min(dzien, plan.ostatni_dzien(m)):02d}'


def nazwa_okresu(start: str, koniec: str) -> str:
    if start == koniec:
        return f'{MIESIACE[int(start[5:7]) - 1]} {start[:4]}'
    return f'{KWARTALY[(int(start[5:7]) - 1) // 3]} kwartał {start[:4]}' if int(koniec[5:7]) - int(start[5:7]) == 2 \
        else f'{start} do {koniec}'


def okres_ksiegowania(p: dict) -> str:
    """Miesiąc księgowania płatności (RRRR-MM): z płatności, a gdy brak, z dnia wystawienia, potem miesiąc budżetu."""
    return (p.get('ksiegowanie') or p.get('wystawienie') or f"{p['miesiac']}-01")[:7]


def _zaokr(x: Fraction) -> int:
    return plan._zaokr(x) if x >= 0 else -plan._zaokr(-x)


# ---------- Rdzeń: VAT i CIT z modelu budżetu (bez bazy) ----------

def do_prognozy(p: dict, w: dict) -> bool:
    """Wejście do prognoz (A-POD-01, B-DAN-03): płatność budżetu z Księgowane = tak, poza danią i decyzją „anuluj”."""
    return (bool(p.get('ksiegowane', True)) and w.get('podstawa') not in plan.PODATKI and w.get('zrodlo') != 'system'
            and p.get('decyzja') != 'anulowane')


def sumy_miesieczne(platnosci: list[dict], wiersze: dict) -> tuple[dict, dict]:
    """({miesiąc księgowania: VAT należny − naliczony}, {miesiąc: netto wpływów − netto obciążeń}) w groszach."""
    vat, netto = defaultdict(int), defaultdict(int)
    for p in platnosci:
        w = wiersze.get(p['wiersz'])
        if not w or not do_prognozy(p, w):
            continue
        m = okres_ksiegowania(p)
        znak = 1 if w.get('rodzaj') == 1 else -1
        netto[m] += znak * int(p.get('netto') or 0)
        if plan.ma_vat(w.get('podstawa', '')):
            vat[m] += znak * int(p.get('vat') or 0)
    return dict(vat), dict(netto)


def _zamrozenie(klucz, bs_biuro: dict, reczne: dict) -> dict:
    """Stan okresu: kwota od biura (wpis w apce wygrywa z eksportem BS), termin i dzień realny."""
    a = reczne.get(klucz, {})
    x = {} if a.get('odmrozony') else dict(bs_biuro.get(klucz, {}))
    if 'kwota' in a:
        x.update(kwota=a['kwota'], kierunek=a.get('kierunek', 'zaplata'), zrodlo='biuro (wpis w apce)', etap_bs='')
    for k in ('termin', 'realny', 'komentarz'):
        if a.get(k) is not None:
            x[k] = a[k]
    return x


def licz_vat(okr: list[tuple[str, str]], vat_m: dict, ust: dict, bs: dict, reczne: dict) -> tuple[list[dict], dict | None]:
    """Plan VAT za każdy okres z przenoszeniem nadpłaty (B-VAT-05, 06). Zwraca (okresy, zwrot na końcu horyzontu)."""
    saldo = -int(ust.get('vat_saldo_startowe') or 0)
    wynik = []
    for start, koniec in okr:
        model = sum(vat_m.get(m, 0) for m in _miesiace(start, koniec))
        dyn = model + saldo
        z = _zamrozenie(('vat', start), bs['od_biura'], reczne)
        x = {'danina': 'vat', 'okres': start, 'koniec': koniec, 'nazwa': nazwa_okresu(start, koniec), 'model': model,
             'przeniesienie': saldo, 'prognoza': max(0, dyn) if ust['vat_przenoszenie'] == 'tak' else dyn,
             'prognoza_bs': bs['prognoza'].get(('vat', start)), 'termin_ustawowy': _dzien_po(koniec, ust['vat_dzien'])}
        if 'kwota' in z:
            k, kier = z['kwota'], z.get('kierunek', 'zaplata')
            x['od_biura'] = {'kwota': k, 'kierunek': kier, 'zrodlo': z.get('zrodlo', ''), 'komentarz': z.get('komentarz', '')}
            x['plan'], saldo = (k, 0) if kier == 'zaplata' else (-k, 0) if kier == 'zwrot' else (0, -k)
            x['typ'] = 'rzeczywista'
        else:
            x['od_biura'] = None
            if dyn > 0 or ust['vat_przenoszenie'] != 'tak':
                x['plan'], saldo = dyn, 0
            else:
                x['plan'], saldo = 0, dyn
            x['typ'] = 'plan'
        x['saldo_po'] = saldo
        x.update(_daty(x, z, zwrot_po_dniach=60 if x['plan'] < 0 else 0))
        x['etap_bs'] = z.get('etap_bs', '')
        wynik.append(x)
    zwrot = None
    if okr:
        rok = okr[-1][1][:4]
        z = _zamrozenie(('vat_zwrot', rok), bs['od_biura'], reczne)
        kwota = z['kwota'] if 'kwota' in z else -saldo
        if kwota > 0:
            zwrot = {'danina': 'vat_zwrot', 'okres': rok, 'miesiac': okr[-1][1], 'nazwa': f'nadpłata na koniec {rok}',
                     'prognoza': saldo, 'prognoza_bs': bs['prognoza'].get(('vat_zwrot', rok)), 'plan': -kwota,
                     'od_biura': ({'kwota': z['kwota'], 'kierunek': 'zwrot', 'zrodlo': z.get('zrodlo', ''), 'komentarz': z.get('komentarz', '')}
                                  if 'kwota' in z else None),
                     'typ': 'rzeczywista' if 'kwota' in z else 'plan', 'etap_bs': z.get('etap_bs', '')}
            zwrot.update(_daty_zwrotu(rok, ust, z))
    return wynik, zwrot


def _daty(x: dict, z: dict, zwrot_po_dniach: int = 0) -> dict:
    wyst = x['termin_ustawowy']
    termin = z.get('termin') or ((date.fromisoformat(wyst) + timedelta(days=zwrot_po_dniach)).isoformat() if zwrot_po_dniach else wyst)
    return {'wystawienie': wyst, 'termin': termin, 'realny': z.get('realny') or termin}


def _daty_zwrotu(rok: str, ust: dict, z: dict) -> dict:
    """Zwrot nadpłaty (VAT na końcu horyzontu, CIT po roku): wystawienie 30.04, termin z ustawień (BS: 14.06) roku następnego."""
    nast = int(rok) + 1
    termin = z.get('termin') or f"{nast}-{ust['zwrot_termin']}"
    return {'wystawienie': f'{nast}-04-30', 'termin': termin, 'realny': z.get('realny') or termin, 'termin_ustawowy': termin}


def _podatek(podstawa: int, stawka, zaokr: str) -> int:
    """Podatek od podstawy (grosze) wg stawki od Mata: połówki w górę do grosza albo do pełnego złotego."""
    if podstawa <= 0 or not stawka:
        return 0
    x = Fraction(podstawa * int(stawka), 100)
    return _zaokr(x / 100) * 100 if zaokr == 'zl' else _zaokr(x)


def licz_cit(okr_lata: dict, netto_m: dict, ust: dict, bs: dict, reczne: dict) -> tuple[list[dict], list[dict]]:
    """Zaliczki CIT narastająco w roku (B-PD-02 do 05) i rozliczenie roczne: zwrot nadpłaty, gdy suma zaliczek > podatek
    roczny. Niedopłaty system nie planuje (B-PD-06), tylko ją pokazuje. Zwraca (okresy, lata)."""
    stawka, zaokr = ust.get('cit_stawka'), ust.get('cit_zaokraglenie', 'grosze')
    okresy_, lata = [], []
    for rok, okr in sorted(okr_lata.items()):
        narast, zaliczki = 0, 0
        for start, koniec in okr:
            podstawa = sum(netto_m.get(m, 0) for m in _miesiace(start, koniec))
            narast += podstawa
            podatek = _podatek(narast, stawka, zaokr)
            prognoza = max(0, podatek - zaliczki) if stawka else None
            z = _zamrozenie(('cit', start), bs['od_biura'], reczne)
            x = {'danina': 'cit', 'okres': start, 'koniec': koniec, 'rok': rok, 'nazwa': nazwa_okresu(start, koniec),
                 'podstawa': podstawa, 'podstawa_narastajaco': narast, 'podatek_narastajaco': podatek if stawka else None,
                 'zaliczki_wczesniej': zaliczki, 'prognoza': prognoza, 'prognoza_bs': bs['prognoza'].get(('cit', start)),
                 'termin_ustawowy': _dzien_po(koniec, ust['cit_dzien'])}
            if 'kwota' in z:
                x['od_biura'] = {'kwota': z['kwota'], 'kierunek': 'zaplata', 'zrodlo': z.get('zrodlo', ''), 'komentarz': z.get('komentarz', '')}
                x['plan'], x['typ'] = z['kwota'], 'rzeczywista'
            else:
                x['od_biura'], x['plan'], x['typ'] = None, prognoza or 0, 'plan'
            zaliczki += x['plan']
            x.update(_daty(x, z))
            x['etap_bs'] = z.get('etap_bs', '')
            okresy_.append(x)
        podatek_roku = _podatek(narast, stawka, zaokr)
        z = _zamrozenie(('cit_roczny', rok), bs['od_biura'], reczne)
        y = {'danina': 'cit_roczny', 'okres': rok, 'miesiac': f'{rok}-12', 'nazwa': f'rozliczenie roczne {rok}',
             'podstawa_roku': narast, 'podatek_roku': podatek_roku if stawka else None, 'zaliczki': zaliczki,
             'prognoza': (podatek_roku - zaliczki) if stawka else None,   # plus: niedopłata, minus: nadpłata do zwrotu
             'prognoza_bs': bs['prognoza'].get(('cit_roczny', rok)), 'etap_bs': z.get('etap_bs', '')}
        if 'kwota' in z:
            y['od_biura'] = {'kwota': z['kwota'], 'kierunek': z.get('kierunek', 'zwrot'), 'zrodlo': z.get('zrodlo', ''),
                             'komentarz': z.get('komentarz', '')}
            y['plan'], y['typ'] = (-z['kwota'] if y['od_biura']['kierunek'] == 'zwrot' else z['kwota']), 'rzeczywista'
        else:
            y['od_biura'], y['typ'] = None, 'plan'
            y['plan'] = y['prognoza'] if stawka and y['prognoza'] < 0 else 0   # niedopłaty system nie planuje
        y['niedoplata'] = y['prognoza'] if stawka and y['prognoza'] > 0 and y['od_biura'] is None else 0
        y.update(_daty_zwrotu(rok, ust, z))
        lata.append(y)
    return okresy_, lata


# ---------- Arkusz systemowy w modelu budżetu ----------

def _z_bs(bs: dict, p: dict, w: dict):
    """Płatność z podstawą podatkową (eksport BS): rzeczywista = kwota od biura, plan = prognoza BS (punkt odniesienia)."""
    vat = w['podstawa'] == 'Podatek VAT'
    if w.get('rodzaj') == 1:
        klucz = ('vat_zwrot' if vat else 'cit_roczny', p['miesiac'][:4])
    else:
        klucz = ('vat' if vat else 'cit', p['miesiac'])
    if p.get('typ') == 'plan':   # znak jak w planie: do zapłaty plus, zwrot minus
        bs['prognoza'][klucz] = bs['prognoza'].get(klucz, 0) + int(p.get('netto') or 0) * (-1 if w.get('rodzaj') == 1 else 1)
        return
    x = bs['od_biura'].setdefault(klucz, {'kwota': 0, 'kierunek': 'zwrot' if w.get('rodzaj') == 1 else 'zaplata',
                                          'zrodlo': 'Budget Studio', 'termin': p.get('termin'), 'realny': p.get('realny'),
                                          'etap_bs': p.get('etap_bs', ''), 'komentarz': p.get('komentarz', '')})
    x['kwota'] += int(p.get('netto') or 0)


def _arkusz(rok: str) -> dict:
    return {'id': f'sys:oplaty:{rok}', 'folder': 'System', 'kategoria': 'Podatki i daniny', 'nazwa': f'Opłaty urzędowe {rok}',
            'od': f'{rok}-01', 'do': f'{rok}-12', 'zrodlo': 'system'}


def _wiersz(wid: str, rok: str, rodzaj: int, podstawa: str, przedmiot: str, dzien: int) -> dict:
    return {'id': wid, 'arkusz': f'sys:oplaty:{rok}', 'rodzaj': rodzaj, 'podstawa': podstawa, 'kontrahent': URZAD, 'komentarz': '',
            'przedmiot': przedmiot, 'sekcja': '', 'stawka_vat': None, 'dzien_wystawienia': f'{dzien}.' if dzien else '(auto)',
            'dni_na_platnosc': 0, 'metoda': 'Przelew', 'ksiegowane': False, 'w_cashflow': True, 'cykl': 'brak', 'zrodlo': 'system'}


def _platnosc(pid: str, wid: str, miesiac: str, x: dict, tytul: str) -> dict:
    kwota = abs(x['plan'])
    od_biura = x.get('od_biura')
    return {'id': pid, 'wiersz': wid, 'miesiac': miesiac, 'typ': x['typ'], 'etap_bs': x.get('etap_bs') or ('Planowana' if x['typ'] == 'plan' else ''),
            'aktualna': True, 'netto': kwota, 'vat': 0, 'brutto': kwota, 'stawka': None, 'nr_dok': '', 'nr_wewn': '', 'tytul': tytul,
            'wystawienie': x['wystawienie'], 'termin': x['termin'], 'realny': x['realny'], 'ksiegowanie': x['wystawienie'][:7] + '-01',
            'metoda': 'Przelew', 'ksiegowane': False, 'w_cashflow': True, 'komentarz': (od_biura or {}).get('komentarz', ''),
            'zrodlo': ('kwota od biura: ' + od_biura['zrodlo']) if od_biura else 'prognoza (arkusz systemowy)', 'kontrahent': URZAD}


def dolacz(model: dict, wpisy: list[dict], con=None) -> dict:
    """Arkusz systemowy w modelu budżetu (przed zapisem do bazy): wiersze z podstawą podatkową wychodzą z modelu
    (ich rzeczywiste stają się kwotami od biura, plany prognozą BS), w ich miejsce rok po roku arkusz „Opłaty urzędowe”.
    Szczegóły okresów idą do meta „podatki” (ekran Podatki, kontrola z bankiem)."""
    ust, reczne = wczytaj_reczne(wpisy)
    wiersze = {w['id']: w for w in model['wiersze']}
    podatkowe = {wid for wid, w in wiersze.items() if w.get('podstawa') in plan.PODATKI}
    ark_podatkowe = {wiersze[wid]['arkusz'] for wid in podatkowe}
    bs = {'od_biura': {}, 'prognoza': {}}
    zostaja = []
    for p in model['platnosci']:
        if p['wiersz'] in podatkowe:
            _z_bs(bs, p, wiersze[p['wiersz']])
        else:
            zostaja.append(p)
    model['platnosci'] = zostaja
    model['wiersze'] = [w for w in model['wiersze'] if w['id'] not in podatkowe]
    zajete = {w['arkusz'] for w in model['wiersze']}
    usuniete = [a['nazwa'] for a in model['arkusze'] if a['id'] in ark_podatkowe and a['id'] not in zajete]
    model['arkusze'] = [a for a in model['arkusze'] if a['id'] not in ark_podatkowe or a['id'] in zajete]
    zwykle = [a for a in model['arkusze'] if a.get('zrodlo') != 'system']
    meta = {'ustawienia': ust, 'stale': STALE, 'horyzont': None, 'vat': [], 'vat_zwrot': None, 'cit': [], 'cit_roczny': [],
            'zastapione_arkusze_bs': usuniete, 'kwoty_bs': len(bs['od_biura']), 'prognozy_bs': len(bs['prognoza'])}
    if zwykle:
        od, do = min(a['od'] for a in zwykle), max(a['do'] for a in zwykle)
        meta['horyzont'] = [od, do]
        vat_m, netto_m = sumy_miesieczne(model['platnosci'], {w['id']: w for w in model['wiersze']})
        meta['vat'], meta['vat_zwrot'] = licz_vat(okresy(od, do, 3 if ust['vat_okres'] == 'kwartal' else 1), vat_m, ust, bs, reczne)
        okr_lata = defaultdict(list)
        for s, k in okresy(od, do, 3 if ust['cit_okres'] == 'kwartal' else 1):
            okr_lata[s[:4]].append((s, k))
        meta['cit'], meta['cit_roczny'] = licz_cit(dict(okr_lata), netto_m, ust, bs, reczne)
        _do_modelu(model, meta, ust, od, do)
    if con is not None:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('podatki', ?)", (json.dumps(meta, ensure_ascii=False),))
    return {'okresow_vat': len(meta['vat']), 'okresow_cit': len(meta['cit']), 'kwot_od_biura': sum(
        1 for x in meta['vat'] + meta['cit'] + meta['cit_roczny'] if x.get('od_biura'))}


def _do_modelu(model: dict, meta: dict, ust: dict, od: str, do: str):
    """Arkusze, wiersze i płatności systemowe. Okres bez kwoty do zapłaty ani zwrotu nie dostaje płatności (zero nie jest
    zaległością), ale zostaje w meta z prognozą."""
    lata = sorted({m[:4] for m in _miesiace(od, do)})
    model['arkusze'] += [_arkusz(r) for r in lata]
    potrzebne = set()
    for r in lata:
        model['wiersze'] += [_wiersz(f'sys:vat:{r}', r, -1, 'Podatek VAT', 'Podatek VAT', ust['vat_dzien']),
                             _wiersz(f'sys:cit:{r}', r, -1, 'Podatek dochodowy', 'Podatek dochodowy (CIT)', ust['cit_dzien'])]
    nowe = []
    for x in meta['vat']:
        r = x['okres'][:4]
        x['platnosc'] = None
        if x['plan'] > 0:
            x['platnosc'] = f"sys:vat:{x['okres']}"
            nowe.append(_platnosc(x['platnosc'], f'sys:vat:{r}', x['okres'], x, f"Podatek VAT ({x['nazwa']})"))
        elif x['plan'] < 0:
            x['platnosc'] = f"sys:vat-zwrot:{x['okres']}"
            potrzebne.add(('vat-zwrot', r))
            nowe.append(_platnosc(x['platnosc'], f'sys:vat-zwrot:{r}', x['okres'], x, f"Zwrot VAT ({x['nazwa']})"))
    z = meta['vat_zwrot']
    if z:
        r = z['okres']
        z['platnosc'] = f'sys:vat-zwrot:{r}'
        potrzebne.add(('vat-zwrot', r))
        nowe.append(_platnosc(z['platnosc'], f'sys:vat-zwrot:{r}', z['miesiac'], z, f'Zwrot nadpłaty VAT ({z["nazwa"]})'))
    for x in meta['cit']:
        x['platnosc'] = None
        if x['plan'] > 0:
            x['platnosc'] = f"sys:cit:{x['okres']}"
            nowe.append(_platnosc(x['platnosc'], f"sys:cit:{x['rok']}", x['okres'], x, f"Zaliczka CIT ({x['nazwa']})"))
    for y in meta['cit_roczny']:
        y['platnosc'] = None
        r = y['okres']
        if y['plan'] < 0:
            y['platnosc'] = f'sys:cit-rok:{r}'
            potrzebne.add(('cit-zwrot', r))
            nowe.append(_platnosc(y['platnosc'], f'sys:cit-zwrot:{r}', y['miesiac'], y, f'CIT za {r}: zwrot nadpłaty'))
        elif y['plan'] > 0:
            y['platnosc'] = f'sys:cit-rok:{r}'
            nowe.append(_platnosc(y['platnosc'], f'sys:cit:{r}', y['miesiac'], y, f'CIT za {r}: dopłata'))
    for rodzaj, r in sorted(potrzebne):
        if rodzaj == 'vat-zwrot':
            model['wiersze'].append(_wiersz(f'sys:vat-zwrot:{r}', r, 1, 'Podatek VAT', 'Zwrot VAT', 0))
        else:
            model['wiersze'].append(_wiersz(f'sys:cit-zwrot:{r}', r, 1, 'Podatek dochodowy', 'Zwrot CIT', 0))
    model['platnosci'] += nowe


# ---------- Bank: co zapłacono za okres ----------

_OKR = re.compile(r'/OKR/(\d{2})([MK])(\d{2})/', re.I)
_MPP = re.compile(r'/VAT/(\d[\d ]*,\d{2})/', re.I)
_ZA_ROK = re.compile(r'za rok (\d{4})')


def _poprzedni(m: str) -> str:
    return _nastepny(m, -1)


def rodzaj_przelewu(kontrahent: str, tekst: str) -> str | None:
    """Przelew do urzędu skarbowego albo ZUS po nazwie i tytule (jak reguły wbudowane w klienci.py)."""
    k, t = norm(kontrahent), norm(tekst)
    if k.startswith('zus') or 'zaklad ubezpieczen' in k:
        return 'zus'
    if 'urzad skarbowy' not in k:
        return None
    if re.search(r'\bpit ?8ar\b|dywidend', t):
        return 'pit8ar'
    if re.search(r'\bpit ?4', t):
        return 'pit4'
    if re.search(r'\bcit\b|cit ?8', t):
        return 'cit'
    if re.search(r'\bvat\b|vat ?7|jpk', t):
        return 'vat'
    return 'inne'


def okres_przelewu(rodzaj: str, tytul: str, data: str) -> str:
    """Okres, którego dotyczy przelew: z „/OKR/26M08/” (kwartał „26K01” = pierwszy miesiąc kwartału), z „DRA 01/08”
    (ZUS). VAT za miesiąc płaci się po jego końcu, więc okres z tytułu równy miesiącowi płatności albo późniejszy to
    pomyłka w tytule: wtedy poprzedni miesiąc (np. przelew 25.06 z „26M06” to VAT za maj)."""
    m_platnosci = data[:7]
    if rodzaj == 'zus':
        from .wynik import okres_pracy
        return okres_pracy(tytul, data)
    x = _OKR.search(tytul or '')
    if x:
        rok, typ, nr = f'20{x.group(1)}', x.group(2).upper(), int(x.group(3))
        okres = f'{rok}-{(nr - 1) * 3 + 1:02d}' if typ == 'K' else f'{rok}-{nr:02d}'
        if typ == 'K' or okres < m_platnosci:
            return okres
    return _poprzedni(m_platnosci)


def zaplaty_z_banku(con) -> list[dict]:
    """Przelewy do urzędu skarbowego i ZUS z rachunku głównego i online (pełna kwota przelewu; część pokryta z rachunku
    VAT widać w ING jako przelew wewnętrzny, więc nie liczymy jej drugi raz) oraz zwroty z urzędu."""
    wynik = []
    for o in con.execute("SELECT id, data_ksiegowania, kwota, kontrahent, tytul, opis FROM operacje"
                         " WHERE rachunek IN ('główny', 'online') ORDER BY data_ksiegowania, id"):
        tekst = f"{o['tytul'] or ''} {o['opis'] or ''}"
        r = rodzaj_przelewu(o['kontrahent'], tekst)
        if not r:
            continue
        if o['kwota'] > 0:   # zwrot z urzędu
            t = norm(tekst)
            if 'zwrot' not in t:
                continue
            rok = (_ZA_ROK.search(t) or [None, str(int(o['data_ksiegowania'][:4]) - 1)])[1]
            wynik.append({'id': o['id'], 'data': o['data_ksiegowania'], 'kwota': -o['kwota'], 'rodzaj': r,
                          'danina': 'cit_roczny' if r == 'cit' else 'vat_zwrot' if r == 'vat' else r, 'okres': rok, 'tytul': o['tytul']})
            continue
        okres = okres_przelewu(r, o['tytul'] or '', o['data_ksiegowania'])
        wynik.append({'id': o['id'], 'data': o['data_ksiegowania'], 'kwota': -o['kwota'], 'rodzaj': r, 'danina': r, 'okres': okres,
                      'tytul': o['tytul']})
    return wynik


# ---------- Udział wpłat MPP i prognoza salda rachunku VAT ----------

def udzialy_mpp(con) -> tuple[dict, Fraction]:
    """Jaka część VAT z faktur klienta wpływała podzieloną płatnością (z historii wpłat połączonych z fakturami):
    {klient: udział}, udział wszystkich klientów razem. Bez wzoru: proporcja z danych."""
    mpp, vat = defaultdict(Fraction), defaultdict(Fraction)
    for r in con.execute('SELECT d.kwota, o.kwota AS op_kwota, o.tytul, o.opis, f.vat, f.brutto, COALESCE(fk.klient, f.nabywca) AS klient'
                         ' FROM dopasowania d JOIN operacje o ON o.id = d.operacja_id JOIN faktury f ON f.numer = d.numer'
                         ' LEFT JOIN faktury_klient fk ON fk.numer = d.numer WHERE o.kwota > 0 AND f.brutto > 0'):
        x = _MPP.search(f"{r['tytul'] or ''} {r['opis'] or ''}")
        czesc = Fraction(r['kwota'], r['op_kwota']) if r['op_kwota'] else Fraction(0)
        vat[r['klient']] += Fraction(r['vat'] or 0) * Fraction(r['kwota'], r['brutto'])
        if x:
            mpp[r['klient']] += grosze(x.group(1)) * czesc
    udzialy = {k: min(Fraction(1), mpp[k] / v) for k, v in vat.items() if v > 0}
    razem = sum(vat.values())
    return udzialy, (min(Fraction(1), sum(mpp.values()) / razem) if razem else Fraction(0))


def rachunek_vat(con, ust: dict, dni: int = 91) -> dict:
    """Prognoza salda rachunku VAT obok gotówki (PRZ-03). Start: saldo rachunku VAT z ING. Wpływy: VAT z wpłat MPP
    (należności wg terminu i średniego spóźnienia nabywcy, plany przychodów: wiersz z Split payment = cały VAT, inaczej
    udział MPP klienta z historii). Wypływy: VAT z kosztów z Split payment i daniny, które ING płaci najpierw z rachunku VAT
    (VAT, a wg ustawienia także CIT, PIT-4 i ZUS), najwyżej do salda. Gotówka w cash flow zostaje bez rachunku VAT."""
    from .cashflow import _spoznienia
    dzien = (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0]
    if not dzien:
        return {'brak_danych': True}
    start = date.fromisoformat(dzien)
    koniec = start + timedelta(days=dni)
    r = con.execute("SELECT saldo_po, data_ksiegowania FROM operacje WHERE rachunek = 'VAT' AND saldo_po IS NOT NULL"
                    ' ORDER BY data_ksiegowania DESC, data_pliku DESC, wiersz ASC LIMIT 1').fetchone()
    saldo = r['saldo_po'] if r else 0
    udzialy, razem = udzialy_mpp(con)
    spoz = _spoznienia(con)
    zdarzenia = []   # (data, kierunek 1/-1, kwota, opis, rodzaj)
    for f in con.execute('SELECT f.numer, f.nip, f.nabywca, f.termin, f.vat, f.brutto, s.pozostalo, s.dni_po_terminie, fk.klient'
                         ' FROM faktury_stan s JOIN faktury f USING(numer) LEFT JOIN faktury_klient fk USING(numer)'
                         ' WHERE s.pozostalo > 0 AND f.vat > 0 AND f.brutto > 0'):
        u = udzialy.get(f['klient'] or f['nabywca'], razem)
        kwota = _zaokr(Fraction(f['vat']) * Fraction(f['pozostalo'], f['brutto']) * u)
        if (f['dni_po_terminie'] or 0) > 0 or not f['termin']:
            d = start + timedelta(days=7)
        else:
            d = max(start + timedelta(days=1), date.fromisoformat(f['termin']) + timedelta(days=spoz.get(f['nip'] or f['nabywca'], 0)))
        if kwota > 0 and d <= koniec:
            zdarzenia.append((d, 1, kwota, f"MPP z faktury {f['numer']} ({f['klient'] or f['nabywca']})", 'wpłata MPP'))
    for p in con.execute("SELECT p.id, p.rodzaj, p.vat, p.brutto, p.tytul, p.skladowa, s.etap, s.termin_efektywny, p.realny, w.split, w.podstawa,"
                         " a.folder, a.nazwa, COALESCE(NULLIF(p.kontrahent, ''), w.kontrahent) AS kontrahent FROM bud_platnosc p"
                         ' JOIN bud_stan s ON s.platnosc = p.id JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz'
                         " WHERE p.aktualna = 1 AND p.w_cashflow = 1 AND s.etap IN ('Planowana', 'Po terminie')"
                         " AND NOT EXISTS (SELECT 1 FROM bud_powiazanie b WHERE b.platnosc = p.id AND b.typ = 'faktura')"):
        d = start + timedelta(days=7) if p['etap'] == 'Po terminie' else date.fromisoformat((p['realny'] or p['termin_efektywny'])[:10])
        if not start < d <= koniec:
            continue
        pod = p['podstawa'] or ''
        if pod.startswith('Faktura') and p['vat']:
            if p['rodzaj'] == 1:
                u = Fraction(1) if p['split'] else udzialy.get(p['folder'], razem)
                kwota = _zaokr(Fraction(p['vat']) * u)
                if kwota:
                    zdarzenia.append((d, 1, kwota, f"MPP z planu: {p['kontrahent'] or ''} · {p['nazwa']}", 'plan MPP'))
            elif p['split']:
                zdarzenia.append((d, -1, p['vat'], f"VAT kosztu płacony z rachunku VAT: {p['kontrahent'] or ''}", 'koszt MPP'))
        elif pod == 'Podatek VAT' and p['rodzaj'] == -1:
            zdarzenia.append((d, -1, p['brutto'], p['tytul'] or 'Podatek VAT', 'VAT'))
        elif ust.get('rachunek_vat_na') == 'wszystkie' and p['rodzaj'] == -1 and (
                pod == 'Podatek dochodowy' or p['skladowa'] in ('us', 'zus') or pod.endswith((' - PIT', ' - ZUS'))):
            rodz = 'CIT' if pod == 'Podatek dochodowy' else 'ZUS' if (p['skladowa'] == 'zus' or pod.endswith(' - ZUS')) else 'PIT-4'
            zdarzenia.append((d, -1, p['brutto'], f"{rodz}: {p['tytul'] or p['kontrahent'] or ''}", rodz))
    zdarzenia.sort(key=lambda z: (z[0], -z[1]))
    lista, s = [], saldo
    for d, kier, kwota, opis, rodzaj in zdarzenia:
        if kier > 0:
            s += kwota
            lista.append({'data': d.isoformat(), 'rodzaj': rodzaj, 'opis': opis, 'kwota': kwota, 'z_rachunku_vat': kwota,
                          'z_glownego': 0, 'saldo': s})
        else:
            z_vat = min(max(s, 0), kwota)
            s -= z_vat
            lista.append({'data': d.isoformat(), 'rodzaj': rodzaj, 'opis': opis, 'kwota': -kwota, 'z_rachunku_vat': -z_vat,
                          'z_glownego': -(kwota - z_vat), 'saldo': s})
    vat_najblizszy = next((z for z in lista if z['rodzaj'] == 'VAT'), None)
    return {'dzien_stanu': dzien, 'saldo_start': saldo, 'saldo_koniec': s, 'zdarzenia': lista, 'udzial_mpp': float(round(razem * 100, 1)),
            'klienci_mpp': sorted(({'klient': k, 'udzial': float(round(v * 100, 1))} for k, v in udzialy.items() if v > 0),
                                  key=lambda x: -x['udzial']),
            'vat_najblizszy': vat_najblizszy and {**vat_najblizszy, 'saldo_przed': vat_najblizszy['saldo'] - vat_najblizszy['z_rachunku_vat']}}


# ---------- Widok „Podatki” ----------

def _meta(con) -> dict:
    r = con.execute("SELECT wartosc FROM meta WHERE klucz='podatki'").fetchone()
    return json.loads(r[0]) if r and r[0] else {}


def _status(x: dict, zaplacono: int, dzis: str) -> str:
    p, termin = x.get('plan') or 0, x.get('termin')
    if p > 0:
        if abs(zaplacono - p) <= 100:
            return 'zapłacone'
        if zaplacono > 0:   # u daniny liczy się przelew: inna kwota to sygnał, że plan albo kwota od biura się rozjechały
            return 'zapłacone, inna kwota'
        if termin and termin < dzis:
            return 'po terminie'
        return 'kwota od biura' if x.get('od_biura') else 'prognoza'
    if p < 0:   # zwrot: przelew z urzędu ma znak minus, jak plan
        return 'zwrot otrzymany' if zaplacono <= p + 100 else 'zwrot (kwota od biura)' if x.get('od_biura') else 'zwrot (prognoza)'
    if zaplacono > 0:
        return 'zapłacone (plan 0)'
    return 'od biura: 0' if x.get('od_biura') else 'nic do zapłaty'


def _uzupelnij(lista: list[dict], zap: dict, etapy: dict, dzis: str, klucz_okresu) -> list[dict]:
    for x in lista:
        k = (x['danina'], klucz_okresu(x))
        ops = zap.get(k, [])
        x['zaplacono'] = sum(o['kwota'] for o in ops)
        x['przelewy'] = [{'data': o['data'], 'kwota': o['kwota'], 'tytul': o['tytul']} for o in ops]
        x['status'] = _status(x, x['zaplacono'], dzis)
        x['etap'] = etapy.get(x.get('platnosc'))
        b = x.get('od_biura')
        rzecz = ({'zaplata': 1, 'zwrot': -1, 'przeniesienie': 0}[b['kierunek']] * b['kwota']) if b else (
            x['zaplacono'] if (x['zaplacono'] or (x.get('termin') or '9') < dzis) else None)
        x['rzeczywista'] = rzecz
        x['roznica'] = (x['prognoza'] - rzecz) if (rzecz is not None and x.get('prognoza') is not None) else None
        x['brak_kwoty_od_biura'] = not x.get('od_biura') and bool(x.get('termin')) and x['termin'] < dzis
    return lista


def kalendarz_wynagrodzen(con, horyzont, zap: dict, dzis: str) -> list[dict]:
    """PIT-4 i ZUS z umów (składowe z pakietu 2 i z eksportu BS) wg miesiąca wypłaty, z przelewami z banku."""
    t = defaultdict(lambda: {'pit4_plan': 0, 'zus_plan': 0, 'pit4_platnosci': 0, 'zus_platnosci': 0})
    for p in con.execute('SELECT p.brutto, p.termin, p.skladowa, p.decyzja, w.podstawa FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz'
                         " WHERE p.skladowa IN ('us', 'zus') OR w.podstawa LIKE '% - PIT' OR w.podstawa LIKE '% - ZUS'"):
        if not p['termin'] or p['decyzja'] == 'anulowane':
            continue
        rodz = 'zus' if (p['skladowa'] == 'zus' or (p['podstawa'] or '').endswith(' - ZUS')) else 'pit4'
        x = t[_poprzedni(p['termin'][:7])]
        x[f'{rodz}_plan'] += p['brutto']
        x[f'{rodz}_platnosci'] += 1
    od, do = (horyzont or [None, None])
    miesiace = sorted(set(t) | {k[1] for k in zap if k[0] in ('pit4', 'zus')})
    if od:
        miesiace = [m for m in miesiace if od <= m <= do]
    wynik = []
    for m in miesiace:
        x = {'okres': m, 'nazwa': nazwa_okresu(m, m), **t[m]}
        for rodz, dzien in (('pit4', STALE['pit4_dzien']), ('zus', STALE['zus_dzien'])):
            x[f'{rodz}_zaplacono'] = sum(o['kwota'] for o in zap.get((rodz, m), []))
            x[f'{rodz}_termin'] = _dzien_po(m, dzien)
        wynik.append(x)
    return wynik


def widok(con) -> dict:
    """Ekran Podatki: okresy VAT i CIT (prognoza, prognoza BS, kwota od biura, plan w cash flow, zapłacono, różnica, termin,
    status), rozliczenie roczne CIT, kalendarz PIT-4 i ZUS, prognoza salda rachunku VAT."""
    meta = _meta(con)
    from .zapytania_budzet import _dzien_stanu
    dzis = _dzien_stanu(con)
    ust = meta.get('ustawienia') or dict(USTAWIENIA_DOMYSLNE)
    zap = defaultdict(list)
    dl_vat, dl_cit = (3 if ust['vat_okres'] == 'kwartal' else 1), (3 if ust['cit_okres'] == 'kwartal' else 1)
    for o in zaplaty_z_banku(con):
        okres = o['okres']
        if o['danina'] == 'vat':
            okres = _poczatek(okres, dl_vat)
        elif o['danina'] == 'cit':
            okres = _poczatek(okres, dl_cit)
        zap[(o['danina'], okres)].append(o)
    etapy = {r[0]: r[1] for r in con.execute("SELECT platnosc, etap FROM bud_stan WHERE platnosc LIKE 'sys:%'")}
    vat = _uzupelnij(meta.get('vat', []), zap, etapy, dzis, lambda x: x['okres'])
    cit = _uzupelnij(meta.get('cit', []), zap, etapy, dzis, lambda x: x['okres'])
    roczne = _uzupelnij(meta.get('cit_roczny', []), zap, etapy, dzis, lambda x: x['okres'])
    zwrot = meta.get('vat_zwrot')
    if zwrot:
        _uzupelnij([zwrot], zap, etapy, dzis, lambda x: x['okres'])
    ostatni_bank = max((o['data'] for v in zap.values() for o in v), default='')
    historia = [x for x in vat if x.get('termin') and x['termin'] <= dzis]
    zgodne = sum(1 for x in historia if x['roznica'] is not None and abs(x['roznica']) <= 100)
    rach = rachunek_vat(con, ust)
    return {'dzien_stanu': dzis, 'ustawienia': ust, 'domyslne': USTAWIENIA_DOMYSLNE, 'stale': STALE, 'horyzont': meta.get('horyzont'),
            'vat': vat, 'vat_zwrot': zwrot, 'cit': cit, 'cit_roczny': roczne,
            'wynagrodzenia': kalendarz_wynagrodzen(con, meta.get('horyzont'), zap, dzis),
            'rachunek_vat': rach, 'ostatni_przelew': ostatni_bank,
            'kontrola': {'okresow': len(historia), 'zgodnych': zgodne},
            'zastapione_arkusze_bs': meta.get('zastapione_arkusze_bs', []),
            'inne_przelewy': [{'data': o['data'], 'kwota': o['kwota'], 'rodzaj': o['rodzaj'], 'tytul': o['tytul']}
                              for k, v in zap.items() if k[0] in ('pit8ar', 'inne') for o in v]}


def sprawdz_wpis(dane: dict, wpisy: list[dict], dzis: str):
    """Daty daniny względem okresu (B-DAN-08): dzień realny i termin najwcześniej dzień po końcu okresu, najpóźniej 5 lat
    od dnia stanu. Okres CIT wg ustawienia (kwartał: pierwszy miesiąc kwartału)."""
    if dane.get('usun'):
        return
    ust, _ = wczytaj_reczne(wpisy)
    if dane['danina'] in ('vat_zwrot', 'cit_roczny'):
        koniec = f"{dane['okres']}-12"
    else:
        dl = 3 if ust[f"{dane['danina']}_okres"] == 'kwartal' else 1
        if _poczatek(dane['okres'], dl) != dane['okres']:
            raise ValueError(f"Okres {dane['danina'].upper()} jest kwartalny: podaj pierwszy miesiąc kwartału "
                             f"({_poczatek(dane['okres'], dl)}).")
        koniec = _nastepny(dane['okres'], dl - 1)
        if dane['danina'] == 'cit' and dane.get('kierunek') not in (None, 'zaplata'):
            raise ValueError('Zaliczka CIT to zawsze kwota do zapłaty; zwrot wpisz w rozliczeniu rocznym.')
    najwczesniej = f'{_nastepny(koniec)}-01'
    najpozniej = f'{int(dzis[:4]) + 5}{dzis[4:]}'
    for k in ('termin', 'realny'):
        if dane.get(k) and not najwczesniej <= dane[k] <= najpozniej:
            raise ValueError(f"{'Dzień realnej płatności' if k == 'realny' else 'Termin'} daniny: najwcześniej {najwczesniej} "
                             f'(dzień po końcu okresu), najpóźniej {najpozniej}.')
