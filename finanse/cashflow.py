"""Cash flow jak w Budget Studio (pakiet 9) i prognoza 13 tygodni.

Tryb domyślny jak w BS (decyzja Mata 8): po dniu stanu WYŁĄCZNIE płatności budżetu z „W cash flow = tak”: plany
i rzeczywiste nieopłacone, na osi DNIA REALNEJ PŁATNOŚCI, kwoty brutto (A-CF-01, A-CF-02). Przed dniem stanu historia
z banku (rachunek główny i online; para przelewów między nimi się znosi, przelew na rachunek VAT to wypływ). Daniny
z arkusza systemowego Opłaty urzędowe (pakiet 8) wchodzą jak plany; saldo rachunku VAT pokazujemy osobno.

Nieopłacona = etap inny niż „Opłacona”: opłacona z banku albo decyzją Mata z datą (APK-BRAK-12); rzeczywista z BS, którą
BS ma za opłaconą, a w banku jej nie ma („Opłacona wg BS”), też nie wchodzi, ale „Niewymagana” w BS (np. przyszłe PIT
i ZUS z umów) wchodzi: to naprawa błędu z uwag pakietu 8, liczona tutaj bez zmian w łączeniu.

Etap płatności w filtrze jak w BS: Planowana, Niewymagana, Po terminie, Opłacona (domyślnie bez opłaconych). Status
aktualności jak w BS (B-MOD-09). Płatność nieopłacona z minionym dniem realnym („zaległość”) zostaje na swoim dniu
(w trybie z historią z banku nie ma jej więc w prognozie, licznik na ekranie); scenariusz pełny przenosi ją na dzień
stanu + 7 dni. Historia „z budżetu” pokazuje przeszłość jak BS: płatności budżetu wg etapu zamiast przelewów z banku.

Dodatki poza BS, każdy jako „pochodzenie” do włączenia w panelu:
  - z umowy (domyślnie włączone, decyzja 9): klient z umową, którego plany wpływów się kończą, dostaje w każdym
    miesiącu po ostatnim zaplanowanym wpływie wartość miesięczną netto z umowy + VAT wg stawki jego wiersza (23%),
    termin ostatni dzień miesiąca + dni na płatność z wiersza (7). Umowa na czas określony bez przedłużenia: nie po
    końcu (decyzja 10); jej plany po końcu zostają, z ostrzeżeniem,
  - należności z faktur spoza budżetu (termin + średnie spóźnienie nabywcy), domyślnie wyłączone,
  - szacunek kosztów pracy i stałych ze średniej 6 miesięcy tam, gdzie brak planów, domyślnie wyłączony.
Scenariusz „klienci odchodzą” (BL-01, decyzja 11): każdy klient z umową (albo wybrani) wypowiada dziś, odchodzi po okresie
wypowiedzenia; od miesiąca po odejściu brak jego wpływów (plany i pozycje z umowy). Klient bez umowy: tylko plany.
"""
from collections import defaultdict
from datetime import date, timedelta

from . import filtry
from . import plan as reguly

DNI = 91
POCHODZENIA = {'plan': 'Plany z budżetu', 'rzeczywista': 'Rzeczywiste nieopłacone', 'umowa': 'Z umowy (gdy plany klienta się kończą)',
               'bank': 'Historia z banku', 'faktura': 'Należności z faktur spoza budżetu (poza BS)',
               'szacunek': 'Szacunek kosztów pracy i stałych (poza BS)'}
POCHODZENIE_DOMYSLNE = ('plan', 'rzeczywista', 'umowa', 'bank')
ETAPY = ('Planowana', 'Niewymagana', 'Po terminie', 'Opłacona')
ETAPY_DOMYSLNE = ETAPY[:3]
AKTUALNOSCI = ('Aktualna', 'Nieaktualna')
# filtr daty → pole pozycji i czy miesięczny (A-FIL-01); dzień realny = oś wykresu
DATY = {'wystawienie': ('wystawienie', False), 'termin': ('termin', False), 'realny': ('data', False), 'ksiegowanie': ('ksiegowanie', True)}
ZALEGLOSC_DNI = 7

# Zapisane widoki startowe (A-CF-05): zakres liczony od dnia stanu przy każdym otwarciu (filtry ruchome z pakietu 7).
# Pierwszy jest domyślny. Mat może je zmienić, usunąć (poza domyślnym) i dodać własne: zdarzenie „widok”, ekran „cashflow”.
WIDOKI_STARTOWE = [
    {'id': '13tyg', 'nazwa': '13 tyg. w przód', 'ik': 'kalendarz', 'parametry': {'granulacja': 'tydzien', 'd_realny': 'ruchomy:dzien:91:0'}},
    {'id': '2tyg', 'nazwa': '2 tygodnie w przód', 'ik': 'kalendarz', 'parametry': {'granulacja': 'dzien', 'd_realny': 'ruchomy:dzien:14:0'}},
    {'id': '6mies', 'nazwa': '6 mies. w przód', 'ik': 'kalendarz', 'parametry': {'granulacja': 'tydzien', 'd_realny': 'ruchomy:dzien:182:0'}},
    {'id': '12mies', 'nazwa': '12 miesięcy w przód', 'ik': 'kalendarz', 'parametry': {'granulacja': 'miesiac', 'd_realny': 'ruchomy:miesiac:12:0'}},
    {'id': 'rok', 'nazwa': 'Ten rok: historia i prognoza', 'ik': 'fale', 'parametry': {'granulacja': 'miesiac', 'd_realny': 'biezacy:rok'}},
    {'id': 'dni', 'nazwa': 'Dzień po dniu (30 dni)', 'ik': 'fale', 'parametry': {'granulacja': 'dzien', 'd_realny': 'ruchomy:dzien:30:0'}},
]

# Tydzień w BS (zrzuty 14.10 i 19.10.2026): od wtorku do poniedziałku („13 paź. – 19 paź.”). Parametr w
# Finanse/Aplikacja/ustawienia.json: "cashflow_pierwszy_dzien_tygodnia" (0 = poniedziałek, 1 = wtorek).
PIERWSZY_DZIEN_TYGODNIA = 1


def _d(s):
    return date.fromisoformat(s[:10]) if s else None


def _iso(d):
    return d.isoformat() if isinstance(d, date) else d


def _dzien_stanu(con) -> str:
    return (con.execute("SELECT wartosc FROM meta WHERE klucz='dzien_stanu'").fetchone() or [''])[0]


def _pierwszy_dzien_tyg() -> int:
    from .wynik import ustawienia
    return int(ustawienia().get('cashflow_pierwszy_dzien_tygodnia', PIERWSZY_DZIEN_TYGODNIA))


def _spoznienia(con) -> dict:
    """Nabywca -> średnia liczba dni od terminu do ostatniej wpłaty (tylko faktury opłacone w banku, min. 0)."""
    s = defaultdict(list)
    for r in con.execute("SELECT f.nip, f.nabywca, f.termin, st.ostatnia_wplata FROM faktury f JOIN faktury_stan st USING(numer)"
                         " WHERE st.stan = 'opłacona' AND st.ostatnia_wplata != '' AND f.termin IS NOT NULL"):
        s[r['nip'] or r['nabywca']].append(max(0, (_d(r['ostatnia_wplata']) - _d(r['termin'])).days))
    return {k: round(sum(v) / len(v)) for k, v in s.items()}


def _saldo_ing(con, rachunki=('główny', 'online')) -> int:
    """Gotówka na koniec dnia stanu: rachunek główny + online z ostatniej operacji w eksporcie ING (bez rachunku VAT)."""
    znaki = ','.join('?' * len(rachunki))
    return sum(r[0] for r in con.execute(
        f"SELECT saldo_po FROM operacje o WHERE rachunek IN ({znaki}) AND saldo_po IS NOT NULL AND id = ("
        " SELECT id FROM operacje p WHERE p.rachunek = o.rachunek AND p.saldo_po IS NOT NULL"
        " ORDER BY data_ksiegowania DESC, data_pliku DESC, wiersz ASC LIMIT 1)", rachunki))


def _zdarzenie(data, kwota, opis, rodzaj, scenariusz, zrodlo, typ, **szczegoly) -> dict:
    """Jedna pozycja cash flow. typ: plan, rzeczywista (płatności budżetu), umowa, faktura (należność spoza budżetu),
    szacunek, bank (historia z ING). rodzaj: opis słowny (do eksportu), znak: 1 wpływ, -1 obciążenie."""
    x = {'data': data, 'kwota': kwota, 'opis': opis, 'rodzaj': rodzaj, 'scenariusz': scenariusz, 'zrodlo': zrodlo, 'typ': typ,
         'znak': 1 if kwota > 0 else -1, 'zaleglosc': False, 'po_koncu_umowy': False, 'danina': False}
    x.update(szczegoly)
    x.setdefault('id', zrodlo)
    return x


# ---------- Płatności budżetu (plany i rzeczywiste) ----------

def _etap_cf(r, stan: str) -> str:
    """Etap jak w BS do filtra cash flow. Opłacona: z banku albo decyzją Mata; rzeczywista, którą BS ma za opłaconą."""
    if r['etap'] == 'Opłacona':
        return 'Opłacona'
    if r['typ'] != 'plan' and r['etap_bs'] == 'Opłacona' and r['etap'] in ('Opłacona wg BS', 'Nieaktualna'):
        return 'Opłacona'
    if r['typ'] == 'plan':
        return 'Planowana'
    return 'Po terminie' if r['termin_efektywny'] and r['termin_efektywny'] < stan else 'Niewymagana'


def _podstawa_platnosci(podstawa: str, skladowa) -> str:
    return reguly.ETYKIETY_SKLADOWYCH.get(podstawa, {}).get(skladowa) or podstawa or ''


def _budzet(con, stan: str) -> list[dict]:
    """Płatności budżetu z „W cash flow = tak” (bez ukrytych planów zerowych i anulowanych), jako pozycje cash flow.
    Kwota z rodzaju płatności (brutto, ze znakiem: wpływ +, obciążenie -); rodzaj obciążenia mają też umowy i daniny."""
    wynik = []
    for r in con.execute(
            "SELECT p.id, p.typ, p.rodzaj, p.netto, p.vat, p.brutto, p.stawka, p.nr_dok, p.tytul, p.wystawienie, p.miesiac,"
            " p.etap_bs, p.skladowa, p.generowany, COALESCE(NULLIF(p.kontrahent, ''), w.kontrahent) AS kontrahent, w.podstawa,"
            " COALESCE(NULLIF(p.metoda, ''), w.metoda) AS metoda, COALESCE(p.realny, s.termin_efektywny) AS realny, s.termin_efektywny,"
            " s.etap, s.aktualnosc, s.data_zaplaty, substr(COALESCE(p.ksiegowanie, p.wystawienie, p.miesiac || '-01'), 1, 7) AS ksiegowanie,"
            " a.id AS arkusz_id, a.nazwa AS arkusz, a.folder, a.zrodlo AS arkusz_zrodlo"
            " FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz JOIN bud_arkusz a ON a.id = w.arkusz"
            " JOIN bud_stan s ON s.platnosc = p.id"
            " WHERE p.w_cashflow = 1 AND COALESCE(p.ukryty, 0) = 0 AND COALESCE(p.decyzja, '') != 'anulowane'"):
        etap = _etap_cf(r, stan)
        data = (r['data_zaplaty'] or r['realny']) if etap == 'Opłacona' else r['realny']
        if not data:
            continue
        znak = 1 if r['rodzaj'] > 0 else -1
        plan = r['typ'] == 'plan'
        wynik.append(_zdarzenie(
            _d(data), r['brutto'] * znak, f"{r['kontrahent'] or ''} · {r['arkusz']}",
            ('plan przychodu' if znak > 0 else 'plan wydatku') if plan else ('wpływ z budżetu' if znak > 0 else 'obciążenie z budżetu'),
            'oba', r['id'], 'plan' if plan else 'rzeczywista',
            kontrahent=r['kontrahent'] or '', tytul=r['tytul'] or '', nr_dok=r['nr_dok'] or '', netto=r['netto'] * znak,
            vat=(r['vat'] or 0) * znak, stawka=r['stawka'], wystawienie=r['wystawienie'], termin=r['termin_efektywny'],
            realny=r['realny'], miesiac=r['miesiac'], ksiegowanie=r['ksiegowanie'], metoda=r['metoda'] or '', waluta='PLN',
            arkusz_id=r['arkusz_id'], arkusz=r['arkusz'], folder=r['folder'], podstawa=r['podstawa'],
            podstawa_platnosci=_podstawa_platnosci(r['podstawa'], r['skladowa']), skladowa=r['skladowa'], generowany=r['generowany'],
            etap=r['etap'], etap_cf=etap, aktualnosc='Aktualna' if etap == 'Opłacona' else (r['aktualnosc'] or 'Aktualna'),
            danina=r['arkusz_zrodlo'] == 'system'))
    return wynik


def _ostatnie_wplywy(con) -> dict:
    """Arkusz → ostatni miesiąc z jakimkolwiek wpływem w budżecie (plan albo rzeczywista, także zerowy plan „będzie płatność”)."""
    return {r[0]: r[1] for r in con.execute(
        "SELECT w.arkusz, MAX(p.miesiac) FROM bud_platnosc p JOIN bud_wiersz w ON w.id = p.wiersz WHERE p.rodzaj = 1"
        " AND COALESCE(p.decyzja, '') != 'anulowane' GROUP BY w.arkusz")}


def _z_umow(con, stan: date, koniec: date, umowy: list[dict]) -> list[dict]:
    """Pozycje „z umowy” (decyzje 9 i 10): od miesiąca po ostatnim zaplanowanym wpływie klienta do końca zakresu."""
    from .umowy import wiersz_klienta
    ostatnie = _ostatnie_wplywy(con)
    wynik = []
    for u in umowy:
        ark = u['arkusze_ids']
        netto = int(u.get('wartosc_mies') or 0)
        if not ark or netto <= 0:
            continue
        w = wiersz_klienta(con, ark)
        ostatni = max((ostatnie[a] for a in ark if a in ostatnie), default=None)
        m = reguly.przesun_miesiac(ostatni, 1) if ostatni else stan.isoformat()[:7]
        if u.get('zawarta'):
            m = max(m, u['zawarta'][:7])
        granica = (u['koniec_umowy'] or '')[:7] or None   # czas określony bez przedłużenia: nie po końcu
        vat = reguly.vat(netto, w['stawka'], 'Faktura') if w['stawka'] else 0
        while m <= koniec.isoformat()[:7] and (not granica or m <= granica):
            wyst = f'{m}-{reguly.ostatni_dzien(m):02d}'
            termin = reguly.plus_dni(wyst, w['dni'])
            if termin >= stan.isoformat():
                kontr = w['kontrahent'] or u.get('folder') or u.get('klient') or ''
                wynik.append(_zdarzenie(
                    _d(termin), netto + vat, f"{kontr} · z umowy", 'wpływ z umowy', 'oba', f"umowa:{u['id']}:{m}", 'umowa',
                    kontrahent=kontr, tytul='wartość miesięczna z umowy', nr_dok='', netto=netto, vat=vat, stawka=w['stawka'],
                    wystawienie=wyst, termin=termin, realny=termin, miesiac=m, ksiegowanie=m, metoda=w['metoda'], waluta='PLN',
                    arkusz_id=w['arkusz_id'], arkusz=w['arkusz'], folder=u.get('folder') or '', podstawa='Z umowy',
                    podstawa_platnosci='Z umowy', skladowa=None, generowany=None, etap='Planowana', etap_cf='Planowana',
                    aktualnosc='Aktualna', umowa=u['id']))
            m = reguly.przesun_miesiac(m, 1)
    return wynik


def _faktury_spoza(con, stan: date) -> list[dict]:
    """Należności z faktur, których nie ma w budżecie (dzisiejsza logika apki, opcja): termin + średnie spóźnienie nabywcy.
    Faktura połączona z płatnością budżetu jest liczona raz, jako ta płatność."""
    spoz = _spoznienia(con)
    wynik = []
    for r in con.execute("SELECT f.numer, f.nip, f.nabywca, f.termin, f.netto, f.vat, f.data_wystawienia, f.waluta, s.pozostalo,"
                         " s.dni_po_terminie, fk.klient FROM faktury_stan s JOIN faktury f USING(numer) LEFT JOIN faktury_klient fk USING(numer)"
                         " WHERE s.pozostalo > 0 AND NOT EXISTS (SELECT 1 FROM bud_powiazanie b WHERE b.typ = 'faktura' AND b.ref = f.numer)"):
        po = (r['dni_po_terminie'] or 0) > 0
        termin = _d(r['termin']) or stan
        data = termin if po else max(stan + timedelta(days=1), termin + timedelta(days=spoz.get(r['nip'] or r['nabywca'], 0)))
        kto = r['klient'] or r['nabywca']
        wynik.append(_zdarzenie(
            data, r['pozostalo'], f"{r['numer']} {kto}" + (' (po terminie)' if po else ''), 'należność po terminie' if po else 'należność',
            'oba', r['numer'], 'faktura', id=f"fv:{r['numer']}", kontrahent=kto, tytul='należność z faktury spoza budżetu',
            nr_dok=r['numer'], netto=r['netto'], vat=r['vat'], stawka=None, wystawienie=r['data_wystawienia'], termin=r['termin'],
            realny=data.isoformat(), miesiac=(r['data_wystawienia'] or '')[:7], ksiegowanie=(r['data_wystawienia'] or '')[:7],
            metoda='Przelew', waluta=r['waluta'] or 'PLN', arkusz_id='', arkusz='', folder=r['klient'] or '', podstawa='Faktura',
            podstawa_platnosci='Faktura spoza budżetu', skladowa=None, generowany=None, etap='Po terminie' if po else 'Wystawiona',
            etap_cf='Po terminie' if po else 'Niewymagana', aktualnosc='Nieaktualna' if po else 'Aktualna'))
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
                                vat=None, stawka=None, wystawienie=None, termin=o['data_ksiegowania'], realny=o['data_ksiegowania'],
                                arkusz_id='', arkusz='', folder='', miesiac=o['data_ksiegowania'][:7],
                                ksiegowanie=o['data_ksiegowania'][:7], metoda='Konto firmowe', waluta='PLN',
                                podstawa='Przelew z banku', podstawa_platnosci='Przelew z banku', skladowa=None, generowany=None,
                                etap='Opłacona', etap_cf='Opłacona', aktualnosc='Aktualna'))
    return wynik


def _szacunek(con, pozycje: list[dict], stan: date, koniec: date) -> list[dict]:
    """Miesiące bez planu kosztów (plany kończą się zwykle na grudniu): szacunek kosztów pracy i stałych ze średniej
    z 6 pełnych miesięcy (jak rezerwa na pulpicie), 10. dnia miesiąca, jako wyraźnie opisana pozycja. Opcja, poza BS."""
    from .controlling import policz as kontrolka
    srednie = kontrolka(con).get('rezerwa', {}).get('srednie_stale', 0)
    if not srednie:
        return []
    plan_kosztow = defaultdict(int)
    for z in pozycje:
        if z['kwota'] < 0 and z['typ'] in ('plan', 'rzeczywista'):
            plan_kosztow[z['data'].isoformat()[:7]] += -z['kwota']
    wynik, m = [], stan.replace(day=1)
    while m <= koniec:
        klucz = m.isoformat()[:7]
        d10 = m.replace(day=10)
        if stan < d10 <= koniec and plan_kosztow[klucz] < srednie // 2:
            kw = -(srednie - plan_kosztow[klucz])
            wynik.append(_zdarzenie(d10, kw, f'szacunek kosztów pracy i stałych {klucz} (brak planu w budżecie)', 'szacunek kosztów', 'oba',
                                    f'szacunek:{klucz}', 'szacunek', kontrahent='szacunek', tytul='koszty pracy i stałe (średnia 6 mies.)',
                                    nr_dok='', netto=kw, vat=0, stawka=None, wystawienie=None, termin=d10.isoformat(),
                                    realny=d10.isoformat(), arkusz_id='', arkusz='', folder='', miesiac=klucz, ksiegowanie=klucz,
                                    metoda='', waluta='PLN', podstawa='Szacunek', podstawa_platnosci='Szacunek kosztów', skladowa=None,
                                    generowany=None, etap='Planowana', etap_cf='Planowana', aktualnosc='Aktualna'))
        m = (m + timedelta(days=32)).replace(day=1)
    return wynik


# ---------- Parametry i wybór pozycji ----------

def parametry(scenariusz=None, rodzaj=None, arkusz=None, **q) -> dict:
    """Parametry z adresu → opcje cash flow (te same dla okresów, listy i eksportu). Nieznane klucze pomijane."""
    if scenariusz not in (None, '', 'ostrozny', 'pelny'):
        raise ValueError('scenariusz: ostrozny albo pelny')
    if rodzaj not in (None, '', '1', '-1', 1, -1):
        raise ValueError('rodzaj: 1 albo -1')
    poch = filtry.lista_wartosci(q.get('pochodzenie'))
    if not poch and q.get('typ'):   # adres sprzed pakietu 9 (?typ=plan,faktura)
        stare = {'plan': ('plan', 'rzeczywista'), 'faktura': ('faktura',), 'bank': ('bank',), 'szacunek': ('szacunek',)}
        poch = [p for t in str(q['typ']).split(',') for p in stare.get(t, ())]
    poch = poch or list(POCHODZENIE_DOMYSLNE)
    if any(p not in POCHODZENIA for p in poch):
        raise ValueError('pochodzenie: ' + ', '.join(POCHODZENIA))
    etapy = filtry.lista_wartosci(q.get('etap')) or list(ETAPY_DOMYSLNE)
    if any(e not in ETAPY for e in etapy):
        raise ValueError('etap płatności: ' + ', '.join(ETAPY))
    akt = q.get('aktualnosc') or ''
    if akt not in ('', *AKTUALNOSCI):
        raise ValueError('status aktualności: Aktualna albo Nieaktualna')
    historia = q.get('historia') or 'bank'
    if historia not in ('bank', 'budzet'):
        raise ValueError('historia: bank albo budzet')
    ode = q.get('odejscia') or ''
    return {'scenariusz': scenariusz or 'ostrozny', 'rodzaj': int(rodzaj) if rodzaj not in (None, '') else None, 'arkusz': arkusz or None,
            'pochodzenie': poch, 'etap': etapy, 'aktualnosc': akt, 'historia': historia, 'podstawa': filtry.lista_wartosci(q.get('podstawa')),
            'odejscia': 'wszyscy' if ode == 'wszyscy' else filtry.lista_wartosci(ode),
            'daty': {t: q[f'd_{t}'] for t in DATY if t != 'realny' and q.get(f'd_{t}')}}


def _pasuje(z: dict, o: dict, zakresy: dict) -> bool:
    """Filtry cech i dat (AND), jak filtry list płatności w BS (A-FIL-08). Historia z banku nie ma etapu do filtrowania."""
    if o['rodzaj'] and z['znak'] != o['rodzaj']:
        return False
    if o['podstawa'] and z['podstawa_platnosci'] not in o['podstawa']:
        return False
    if o['aktualnosc'] and z['aktualnosc'] != o['aktualnosc']:
        return False
    if z['typ'] != 'bank' and z['etap_cf'] not in o['etap']:
        return False
    for typ, (od, do) in zakresy.items():
        pole, miesieczny = DATY[typ]
        n = 7 if miesieczny else 10
        v = _iso(z.get(pole))
        v = v[:n] if v else None
        if not v or (od and v < od.isoformat()[:n]) or (do and v > do.isoformat()[:n]):
            return False
    return True


def _odejscia(umowy: list[dict], wybor) -> dict:
    """Scenariusz „klienci odchodzą”: arkusz → umowa, dzień odejścia przy wypowiedzeniu dziś, pierwszy miesiąc bez wpływów."""
    wynik = {}
    if not wybor:
        return wynik
    for u in umowy:
        kto = u.get('folder') or u.get('klient')
        if not u['arkusze_ids'] or (wybor != 'wszyscy' and kto not in wybor):
            continue
        odejscie = u['odejscie_przy_wypowiedzeniu_dzis']['klient']
        od_m = reguly.przesun_miesiac(odejscie[:7], 1)
        for a in u['arkusze_ids']:
            if a not in wynik or od_m < wynik[a]['od_miesiaca']:
                wynik[a] = {'umowa': u['id'], 'folder': kto, 'odejscie': odejscie, 'od_miesiaca': od_m}
    return wynik


def pozycje(con, stan: date, p_od: date | None, p_do: date | None, o: dict, umowy=None) -> dict:
    """Pozycje cash flow wg opcji, z dniem na osi (data). p_od/p_do = None: „Wszystko” (zakres z danych).
    Zwraca też zaległości poza prognozą, wpływy, które wypadły w scenariuszu odejść, i odejścia."""
    from .umowy import rozwiazane
    stan_iso = stan.isoformat()
    pierwszy = _pierwszy_dzien_tyg()
    zakresy = {t: filtry.zakres(s, stan, DATY[t][1], pierwszy) for t, s in o['daty'].items()}
    zakresy = {t: z for t, z in zakresy.items() if z}
    budzet = [z for z in _budzet(con, stan_iso) if z['typ'] in o['pochodzenie']] if {'plan', 'rzeczywista'} & set(o['pochodzenie']) else []
    if o['arkusz']:
        systemowy = (con.execute('SELECT zrodlo FROM bud_arkusz WHERE id = ?', (o['arkusz'],)).fetchone() or [''])[0] == 'system'
        # cash flow arkusza jak w BS (A-CF-15): tylko jego płatności, bez podatków i ZUS (liczone globalnie)
        budzet = [z for z in budzet if z['arkusz_id'] == o['arkusz'] and (systemowy or not z['danina'])
                  and z['skladowa'] not in ('us', 'zus')]
    umowy = rozwiazane(con, stan) if umowy is None else umowy
    horyzont = p_do or max([z['data'] for z in budzet] + [stan + timedelta(days=DNI)])
    kandydaci = list(budzet)
    if 'umowa' in o['pochodzenie']:
        kandydaci += [z for z in _z_umow(con, stan, horyzont, umowy) if not o['arkusz'] or z['arkusz_id'] == o['arkusz']]
    if 'faktura' in o['pochodzenie'] and not o['arkusz']:
        kandydaci += _faktury_spoza(con, stan)
    po_koncu = {}   # plany po końcu umowy na czas określony (decyzja 10): zostają, z ostrzeżeniem
    for u in umowy:
        if u['koniec_umowy']:
            for a in u['arkusze_ids']:
                po_koncu[a] = min(po_koncu.get(a, '9999-12'), u['koniec_umowy'][:7])
    odejscia = _odejscia(umowy, o['odejscia'])
    wynik, poza, wypadle = [], [], []
    for z in kandydaci:
        if z['typ'] == 'plan' and z['znak'] > 0 and z['arkusz_id'] in po_koncu and z['miesiac'] > po_koncu[z['arkusz_id']]:
            z['po_koncu_umowy'] = True
        if not _pasuje(z, o, zakresy):
            continue
        ode = odejscia.get(z['arkusz_id'])
        if ode and z['znak'] > 0 and z['typ'] in ('plan', 'umowa') and z['miesiac'] >= ode['od_miesiaca']:
            wypadle.append(z)
            continue
        if o['historia'] == 'bank' and z['etap_cf'] == 'Opłacona':
            continue   # opłacone są już w historii z banku i w saldzie startowym
        if z['data'] < stan and z['etap_cf'] != 'Opłacona':   # zaległość: nieopłacona z minionym dniem realnym
            if o['scenariusz'] == 'pelny':
                z.update(data=stan + timedelta(days=ZALEGLOSC_DNI), zaleglosc=True, scenariusz='pelny',
                         opis=z['opis'] + ' (zaległość, za 7 dni)')
            elif o['historia'] == 'bank':
                poza.append(z)
                continue
        wynik.append(z)
    if 'bank' in o['pochodzenie'] and o['historia'] == 'bank' and not o['arkusz']:
        start_banku = p_od or _d((con.execute('SELECT MIN(data_ksiegowania) FROM operacje').fetchone() or [None])[0]) or stan
        if start_banku <= stan:
            wynik += [z for z in _historia_banku(con, start_banku, min(p_do or stan, stan)) if _pasuje(z, o, zakresy)]
    if 'szacunek' in o['pochodzenie'] and not o['arkusz']:
        wynik += [z for z in _szacunek(con, wynik, stan, horyzont) if _pasuje(z, o, zakresy)]
    return {'pozycje': wynik, 'poza': poza, 'wypadle': wypadle, 'odejscia': odejscia, 'umowy': umowy}


# ---------- Prognoza 13 tygodni (ekran sprzed pakietu UX, eksport pod starym adresem) ----------

def prognoza(con) -> dict:
    """13 tygodni od dnia stanu w trybie jak w BS: plany i rzeczywiste nieopłacone na dzień realny. Scenariusz ostrożny
    bez zaległości, pełny z zaległościami za 7 dni. Lista „po terminie”: zaległości (minął dzień realny)."""
    dzien = _dzien_stanu(con)
    if not dzien:
        return {'brak_danych': True}
    start = _d(dzien)
    koniec = start + timedelta(days=DNI)
    saldo = _saldo_ing(con)
    o = parametry(scenariusz='pelny')
    o['pochodzenie'] = [p for p in o['pochodzenie'] if p != 'bank']
    zdarzenia = [z for z in pozycje(con, start, start, koniec, o)['pozycje'] if start < z['data'] <= koniec]
    po_terminie = [{'platnosc': z['id'], 'termin': z['termin'], 'kwota': z['kwota'], 'opis': z['opis']} for z in zdarzenia if z['zaleglosc']]
    dni = []
    s_ostr, s_peln = saldo, saldo
    po_dniu = defaultdict(list)
    for z in zdarzenia:
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
                                      'scenariusz': z['scenariusz']} for z in sorted(zt, key=lambda z: (z['data'], z['kwota']))]})
    minimum = min(dni, key=lambda x: x['ostrozny'])
    return {'dzien_stanu': dzien, 'saldo_start': saldo, 'dni': dni, 'tygodnie': tygodnie, 'po_terminie': po_terminie,
            'minimum_ostrozny': {'data': minimum['data'], 'saldo': minimum['ostrozny']},
            'koniec': {'ostrozny': dni[-1]['ostrozny'], 'pelny': dni[-1]['pelny']}}


# ---------- Cash flow jak w Budget Studio: okresy wg granulacji (dzień, tydzień, miesiąc) ----------

GRANULACJE = ('dzien', 'tydzien', 'miesiac')
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


def _zakres(stan: date, od, do, d_realny, pierwszy: int):
    """Zakres osi: filtr dnia realnej płatności (tryby BS z pakietu 7), statyczne od i do albo domyślnie 13 tygodni od
    dnia stanu. (None, None) = „Wszystko” (zakres z danych)."""
    if d_realny:
        if d_realny == 'wszystko':
            return None, None
        z = filtry.zakres(d_realny, stan, False, pierwszy)
        if z:
            if z[0] and z[1]:
                return z
            return z[0] or stan, z[1] or (z[0] or stan) + timedelta(days=DNI - 1)
    p_od = _d(od) if od else None
    p_do = _d(do) if do else None
    if not p_od and not p_do:
        return stan, stan + timedelta(days=DNI - 1)
    return p_od or stan, p_do or (p_od or stan) + timedelta(days=DNI - 1)


def _okresy_z(lista_okresow: list[dict], pozycje: list[dict], start: int, dzien: str):
    """Sumy okresów (A-CF-04): wpływy, obciążenia, saldo okresu i narastające; osobno części do wykresu (plany, z umowy,
    szacunek, zaległości) i liczba planów po końcu umowy."""
    pozycje.sort(key=lambda z: (z['data'], z['kwota']))
    granice = [_d(o['do']) for o in lista_okresow]
    i = 0
    po_okresie = defaultdict(list)
    for z in pozycje:
        while granice[i] < z['data']:
            i += 1
        z['okres'] = i
        po_okresie[i].append(z)
    narast = start
    for n, o in enumerate(lista_okresow):
        zp = po_okresie[n]
        def suma(warunek):
            return sum(z['kwota'] for z in zp if warunek(z))
        o.update(wplywy=suma(lambda z: z['kwota'] > 0), obciazenia=suma(lambda z: z['kwota'] < 0),
                 wplywy_plan=suma(lambda z: z['kwota'] > 0 and z['typ'] == 'plan'),
                 obciazenia_plan=suma(lambda z: z['kwota'] < 0 and z['typ'] == 'plan'),
                 wplywy_umowa=suma(lambda z: z['kwota'] > 0 and z['typ'] == 'umowa'),
                 obciazenia_szacunek=suma(lambda z: z['kwota'] < 0 and z['typ'] == 'szacunek'),
                 zaleglosci=suma(lambda z: z['zaleglosc']),
                 pozycji=len(zp), biezacy=o['od'] <= dzien <= o['do'], przeszly=o['do'] < dzien,
                 po_koncu_umowy=sum(1 for z in zp if z['po_koncu_umowy']))
        o['saldo'] = o['wplywy'] + o['obciazenia']
        narast += o['saldo']
        o['narastajaco'] = narast


def okresy(con, granulacja='tydzien', od=None, do=None, saldo_start=None, rodzaj=None, scenariusz='ostrozny', arkusz=None,
           pierwszy=None, **q) -> dict:
    """Cash flow jak w BS (A-CF-01 do 13): kolumny okresów wg granulacji, w każdej wpływy, obciążenia, saldo okresu
    i saldo narastające; SUM, MAX, MIN z okresem; lista pozycji z numerem okresu.

    Zakres osi: d_realny (filtr dnia realnej płatności jak w BS), od i do, domyślnie 13 tygodni od dnia stanu.
    Filtry (q): pochodzenie, etap, aktualnosc, podstawa, historia (bank, budzet), odejscia (wszyscy albo foldery „|”),
    d_wystawienie, d_termin, d_ksiegowanie. Saldo startowe = gotówka na koniec dnia przed zakresem, chyba że podane ręcznie.
    Arkusz: tylko jego płatności (bez banku, danin, PIT i ZUS z umów, szacunku), saldo startowe 0."""
    dzien = _dzien_stanu(con)
    if not dzien:
        return {'brak_danych': True}
    stan = _d(dzien)
    if pierwszy is None:
        pierwszy = _pierwszy_dzien_tyg()
    granulacja = granulacja or 'tydzien'
    if granulacja not in GRANULACJE:
        raise ValueError('granulacja: dzien, tydzien albo miesiac')
    o = parametry(scenariusz=scenariusz, rodzaj=rodzaj, arkusz=arkusz, **q)
    p_od, p_do = _zakres(stan, od, do, q.get('d_realny'), pierwszy)
    if p_od and p_do and p_do < p_od:
        raise ValueError('koniec zakresu przed początkiem')
    p = pozycje(con, stan, p_od, p_do, o)
    wszystkie = p['pozycje']
    if p_od is None:   # „Wszystko”: od pierwszej pozycji (z historią banku) do ostatniej, najwyżej 5 lat
        daty = [z['data'] for z in wszystkie] + [stan]
        p_od, p_do = min(daty), max(daty)
        if (p_do - p_od).days > MAKS_DNI:
            p_do = p_od + timedelta(days=MAKS_DNI)
    lista_okresow = okresy_dat(p_od, p_do, granulacja, pierwszy)
    pozycje_zakresu = [z for z in wszystkie if p_od <= z['data'] <= p_do]
    # saldo startowe: ręczne albo gotówka na koniec dnia przed zakresem (z banku albo z prognozy między stanem a zakresem)
    if saldo_start not in (None, ''):
        start, zrodlo_salda = int(saldo_start), 'ręcznie'
    elif o['arkusz']:
        start, zrodlo_salda = 0, 'arkusz'
    elif p_od <= stan:
        start, zrodlo_salda = _saldo_na_koniec_dnia(con, p_od - timedelta(days=1)) or 0, 'bank'
    else:
        start = _saldo_ing(con) + sum(z['kwota'] for z in wszystkie if stan <= z['data'] < p_od and z['typ'] != 'bank')
        zrodlo_salda = 'bank i prognoza'
    _okresy_z(lista_okresow, pozycje_zakresu, start, dzien)
    mx = max(range(len(lista_okresow)), key=lambda n: lista_okresow[n]['narastajaco'])
    mn = min(range(len(lista_okresow)), key=lambda n: lista_okresow[n]['narastajaco'])
    for z in pozycje_zakresu:
        z['data'] = z['data'].isoformat()
        z['przesuniecie'] = (_d(z['data']) - _d(z['termin'])).days if z.get('termin') else 0
    wynik = {'dzien_stanu': dzien, 'od': p_od.isoformat(), 'do': p_do.isoformat(), 'granulacja': granulacja,
             'pierwszy_dzien_tygodnia': pierwszy, 'scenariusz': o['scenariusz'], 'saldo_start': start, 'zrodlo_salda': zrodlo_salda,
             'saldo_ing': _saldo_ing(con), 'saldo_vat': _saldo_ing(con, ('VAT',)), 'okresy': lista_okresow, 'pozycje': pozycje_zakresu,
             'sum': lista_okresow[-1]['narastajaco'], 'max': {'okres': mx, 'saldo': lista_okresow[mx]['narastajaco']},
             'min': {'okres': mn, 'saldo': lista_okresow[mn]['narastajaco']},
             'parametry': {**{k: v for k, v in o.items()}, 'd_realny': q.get('d_realny') or ''}}
    wynik.update(_dodatki(p, p_od, p_do))
    if o['odejscia'] and wynik['odejscia']:   # porównanie z wariantem bez odejść (kafel „najgorszy scenariusz”)
        baza = okresy(con, granulacja, p_od.isoformat(), p_do.isoformat(), saldo_start, rodzaj, scenariusz, arkusz, pierwszy,
                      **{**q, 'odejscia': '', 'd_realny': ''})
        wynik['bez_odejsc'] = {'sum': baza['sum'], 'min': baza['min'], 'min_etykieta': baza['okresy'][baza['min']['okres']]['etykieta']}
    return wynik


def _dodatki(p: dict, p_od: date, p_do: date) -> dict:
    """Liczniki i opcje do ekranu: zaległości poza prognozą, plany po końcu umowy, odejścia, klienci z umową, podstawy."""
    poza = p['poza']
    po_koncu = [z for z in p['pozycje'] if z['po_koncu_umowy']]
    klienci = sorted({(u.get('folder') or u.get('klient')) for u in p['umowy'] if u['arkusze_ids']}, key=filtry.klucz_pl)
    odejscia = {}
    for x in p['odejscia'].values():
        odejscia.setdefault(x['folder'], {'folder': x['folder'], 'umowa': x['umowa'], 'odejscie': x['odejscie'],
                                          'od_miesiaca': x['od_miesiaca'], 'wplywy_wypadle': 0})
    for z in p['wypadle']:
        if p_od <= z['data'] <= p_do:
            ode = p['odejscia'].get(z['arkusz_id'])
            if ode:
                odejscia[ode['folder']]['wplywy_wypadle'] += z['kwota']
    podstawy = sorted({z['podstawa_platnosci'] for z in p['pozycje'] + poza if z['podstawa_platnosci']}, key=filtry.klucz_pl)
    return {'poza_prognoza': {'ile': len(poza), 'kwota': sum(z['kwota'] for z in poza)},
            'plany_po_koncu_umowy': {'ile': len(po_koncu), 'kwota': sum(z['kwota'] for z in po_koncu),
                                      'klienci': sorted({z['folder'] for z in po_koncu}, key=filtry.klucz_pl)},
            'odejscia': sorted(odejscia.values(), key=lambda x: (x['odejscie'], filtry.klucz_pl(x['folder']))),
            'opcje': {'pochodzenie': [[k, v] for k, v in POCHODZENIA.items()], 'etap': list(ETAPY), 'podstawa': podstawy,
                      'klienci_umowy': klienci, 'pochodzenie_domyslne': list(POCHODZENIE_DOMYSLNE), 'etap_domyslny': list(ETAPY_DOMYSLNE)}}


# ---------- Lista płatności pod wykresem (silnik list z pakietu 7) ----------

KOLUMNY_LISTY = {
    'rodzaj': (lambda z: z['znak'], False), 'typ': (lambda z: z['typ'], True), 'pochodzenie': (lambda z: POCHODZENIA.get(z['typ'], ''), True),
    'etap': (lambda z: z['etap_cf'], True), 'aktualnosc': (lambda z: z['aktualnosc'], True),
    'podstawa': (lambda z: z['podstawa_platnosci'], True), 'kontrahent': (lambda z: z['kontrahent'], True),
    'tytul': (lambda z: z['tytul'], True), 'nr_dok': (lambda z: z['nr_dok'], True), 'netto': (lambda z: z['netto'], False),
    'brutto': (lambda z: z['kwota'], False), 'vat': (lambda z: z['vat'], False), 'stawka': (lambda z: z['stawka'], False),
    'wystawienie': (lambda z: z['wystawienie'], False), 'termin': (lambda z: z['termin'], False), 'data': (lambda z: z['data'], False),
    'przesuniecie': (lambda z: z['przesuniecie'], False), 'ksiegowanie': (lambda z: z['ksiegowanie'], False),
    'miesiac': (lambda z: z['miesiac'], False), 'arkusz': (lambda z: z['arkusz'], True), 'folder': (lambda z: z['folder'], True),
    'metoda': (lambda z: z['metoda'], True), 'waluta': (lambda z: z['waluta'], True),
}
POMIJANE_W_LISCIE = ('w_od', 'w_do', 'q', 'strona', 'ile', 'sortuj', 'kolejnosc', 'wszystkie', 'kol', 'opcje', 'serie', 'widok', 'zm')


def lista(con, q: dict) -> dict:
    """Płatności widocznego wycinka (w_od, w_do) z tymi samymi filtrami co wykres: wyszukiwarka (kontrahent, tytuł, numer
    dokumentu, arkusz), sortowanie po każdej kolumnie (puste na końcu, tekst po polsku), strony, podsumowanie wszystkich wyników."""
    from . import zapytania
    from .zapytania_budzet import planowanie
    par = {k: v for k, v in q.items() if k not in POMIJANE_W_LISCIE}
    d = okresy(con, **par)
    if d.get('brak_danych'):
        return {'razem': 0, 'strona': 1, 'ile': 100, 'wiersze': [], 'podsumowanie': filtry.podsumuj([]), 'dzien_stanu': ''}
    poz = d['pozycje']
    w_od, w_do = q.get('w_od') or '', q.get('w_do') or ''
    if w_od or w_do:
        poz = [z for z in poz if (not w_od or z['data'] >= w_od) and (not w_do or z['data'] <= w_do)]
    if q.get('q'):
        f = q['q'].casefold()
        poz = [z for z in poz if f in f"{z['kontrahent']} {z['tytul']} {z['nr_dok']} {z['arkusz']} {z['opis']}".casefold()]
    sortuj = q.get('sortuj') if q.get('sortuj') in KOLUMNY_LISTY else 'data'
    fn, tekst = KOLUMNY_LISTY[sortuj]
    malejaco = (q.get('kolejnosc') or 'rosnaco') == 'malejaco'
    pelne = sorted((z for z in poz if fn(z) not in (None, '')), key=lambda z: (z['data'], z['kwota'], str(z['id'])))
    pelne.sort(key=lambda z: filtry.klucz_pl(fn(z)) if tekst else fn(z), reverse=malejaco)
    poz = pelne + [z for z in poz if fn(z) in (None, '')]
    ile, maks = zapytania._ile(q.get('ile'), q.get('wszystkie') == '1')
    ile = max(1, min(int(ile or zapytania.STRONA), maks))
    strona = max(1, int(q.get('strona') or 1))
    podsumowanie = filtry.podsumuj([{'rodzaj': z['znak'], 'netto': z['netto'], 'vat': z['vat'], 'brutto': z['kwota']} for z in poz])
    return {'razem': len(poz), 'strona': strona, 'ile': ile, 'wiersze': poz[(strona - 1) * ile:strona * ile],
            'podsumowanie': podsumowanie, 'dzien_stanu': d['dzien_stanu'], 'planowanie': planowanie(con),
            'sortuj': sortuj, 'kolejnosc': 'malejaco' if malejaco else 'rosnaco'}
