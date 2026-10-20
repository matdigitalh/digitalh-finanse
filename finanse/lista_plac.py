"""Lista płac za miesiąc (decyzja Mata 12, rozszerzona 2026-10-20): kwoty z listy płac od biura to dane rzeczywiste.

Wpis „lista_plac” w pliku zmian (nie zdarzenie budżetu „bud”), więc:
- działa przy wyłączonym planowaniu i przetrwa przyjęcie kopii z BS (zdarzenia „bud” sprzed kopii przestają obowiązywać,
  listy płac nie); nakładany na budżet po wszystkich zdarzeniach „bud”, przy każdej odbudowie;
- obowiązuje ostatni nie cofnięty wpis za dany miesiąc (cała lista to jedna decyzja; „usun” = wraca estymacja albo BS).

Co robi wpis z komórkami budżetu (osoba × miesiąc × składowa):
- wypłata (na konto), PIT i ZUS (pracownika, pracodawcy i zdrowotna, jeden przelew) zastępują w komórce plan albo płatność
  rzeczywistą z kopii BS (kwota BS to estymacja z podziałem procentowym); zastąpiona płatność BS zostaje w zapisie połączenia
  (kwota BS do wglądu, różnica, powrót po usunięciu listy);
- wiersz bez umowy (powołanie zarządu: w BS jedna kwota brutto) dostaje trzy płatności: na konto, zdrowotna (ZUS), PIT;
- PPK (pracownika i pracodawcy) to jedna płatność w zbiorczym wierszu PPK z BS, w miesiącu budżetowym listy (decyzja Mata
  2026-10-20: jak ZUS i PIT tej listy; koszt, rentowność i wynik w miesiącu, za który jest lista). BS trzyma PPK wg miesiąca
  przelewu, więc lista zastępuje komórkę BS wskazaną we wpisie (domyślnie miesiąc terminu: lista za styczeń → komórka marzec)
  i stawia PPK w komórce miesiąca listy; nic się nie dubluje, a rozjazd z BS to układ miesięcy, nie kwota. Komórki BS bez
  listy (np. styczeń i luty 2026 = PPK z list za XI i XII 2025) zostają z kwotą BS;
- pakiet medyczny i potrącenia z wypłaty (np. Luxmed) to część kosztu pracodawcy osoby, ale bez osobnej płatności: opłaca je
  faktura za pakiet medyczny, która już jest w budżecie (inaczej koszt liczyłby się dwa razy);
- pole puste (brak na liście) = ta składowa zostaje jak w BS albo w planie; nic nie zgadujemy.
Terminy: wypłata = data wypłaty z listy; ZUS i PPK 15., PIT 20. dnia miesiąca po miesiącu wypłaty. Etap „opłacona” jak dotąd
z banku; płatność BS, którą zastępujemy, przekazuje swój etap BS (lista poprawia kwotę, nie zmienia faktu zapłaty).
"""
from . import plan

SKLADOWE = ('osoba', 'us', 'zus')           # płatności w wierszach wynagrodzenia
PPK = ('ppk_pracownik', 'ppk_pracodawca')    # jedna płatność w zbiorczym wierszu PPK
INFO = ('pakiet', 'potracenia')              # część kosztu pracodawcy bez osobnej płatności
POLA = SKLADOWE + PPK + INFO
NAZWY = {'osoba': 'wypłata na konto', 'us': 'PIT', 'zus': 'ZUS', 'ppk_pracownik': 'PPK pracownika',
         'ppk_pracodawca': 'PPK pracodawcy', 'pakiet': 'pakiet medyczny', 'potracenia': 'potrącenia z wypłaty'}
DZIEN = {'us': 20, 'zus': 15, 'ppk': 15}     # dzień terminu w miesiącu po miesiącu wypłaty
ZRODLO = 'lista płac'


def koszt_pracodawcy(k: dict) -> int:
    """Koszt pracodawcy osoby z listy: wypłata + ZUS (wszystkie składki) + PIT + PPK obu stron + pakiet + potrącenia
    (potrącenie jest częścią wynagrodzenia brutto; pokrywa część faktury za pakiet medyczny)."""
    return sum(int(k.get(p) or 0) for p in POLA)


def obowiazujace(wpisy: list[dict]) -> dict[str, dict]:
    """Miesiąc → ostatni nie cofnięty wpis „lista_plac” (po czasie)."""
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    wynik = {}
    for w in sorted((w for w in wpisy if w.get('typ') == 'lista_plac' and w.get('id') not in cofniete),
                    key=lambda w: (w.get('czas', ''), w.get('id', ''))):
        wynik[w['dane']['miesiac']] = w
    return dict(sorted(wynik.items()))


def _bs(p: dict) -> bool:
    """Płatność rzeczywista z kopii BS (albo z importu eksportu BS): ma ID z BS i nie jest połączona w apce."""
    return p['typ'] != 'plan' and bool(p.get('bs_id')) and not p.get('dokument')


def _pierwsza(ps: list[dict]) -> dict | None:
    """Wzór dat i cech: najpierw płatność BS, potem plan; w obrębie najwcześniejsze wystawienie."""
    return sorted(ps, key=lambda p: (not _bs(p), p.get('wystawienie') or '', p['id']))[0] if ps else None


def wiersz_ppk_domyslny(wiersze) -> str | None:
    """Zbiorczy wiersz PPK z BS: obciążenie bez faktury z „PPK” w komentarzu, kontrahencie albo przedmiocie."""
    for w in sorted(wiersze, key=lambda w: w['id']):
        if w.get('rodzaj') == -1 and (w.get('podstawa') or '').startswith('Bez faktury') and 'PPK' in ' '.join(
                str(w.get(k) or '') for k in ('komentarz', 'kontrahent', 'przedmiot')).upper():
            return w['id']
    return None


def _kto(w: dict) -> str:
    return w.get('kontrahent') or w.get('komentarz') or 'Ta osoba'


def _plan_pozycji(st: dict, m: str, x: dict, scisle: bool):
    """Co zrobi jedna pozycja listy (bez zmian w stanie): (powód odrzucenia, plan). Plan: wiersz osoby, ref, rodzaj
    wiersza, składowe {s: (wiersz docelowy, płatności zastępowane)}, kwoty."""
    from .budzet import _mies_pl, rodzenstwo_umowy
    wie, pla = st['wiersz'], st['platnosc']
    wid = x['wiersz']
    w = wie.get(wid)
    if not w:
        return 'nie ma wiersza z listy płac (wiersz usunięty albo inny eksport BS)', None
    rodz = rodzenstwo_umowy(wie, w)
    if rodz:   # import z BS: wypłata, PIT i ZUS osobnymi wierszami; lista płac na wiersz wypłaty
        wid = rodz.get('osoba') or wid
        w = wie[wid]
    kto = _kto(w)
    if rodz:
        rodzaj = 'skladowe'
    elif plan.jest_umowa(w.get('podstawa', '')):
        rodzaj = 'umowa'
    elif w.get('rodzaj') == -1 and (w.get('lista_plac') or w.get('podstawa') == 'Bez faktury'):
        rodzaj = 'bez_umowy'   # np. powołanie zarządu: w BS jedna kwota brutto
    else:
        return (f'Wiersz „{kto}” nie jest wierszem wynagrodzenia (umowa, wiersz bez faktury albo wiersz oznaczony do listy '
                'płac).'), None
    kwoty = {k: x[k] for k in POLA if x.get(k) is not None}
    if scisle and not any(k in kwoty for k in SKLADOWE + PPK):
        return f'{kto}: wpisz co najmniej jedną kwotę z listy płac (wypłata, PIT, ZUS albo PPK).', None
    umowa = plan.skladowa_umowy(w['podstawa'])[0] if rodzaj == 'skladowe' else w.get('podstawa')
    dozwolone = plan.UMOWY.get(umowa, SKLADOWE)
    skl = {}
    w_komorce = lambda wiersz: [p for p in pla.values() if p['wiersz'] == wiersz and p['miesiac'] == m]
    for s in SKLADOWE:
        if s not in kwoty:
            continue
        if s not in dozwolone:
            if scisle and kwoty[s]:
                return f'{kto}: {umowa} nie ma składowej {NAZWY[s]}.', None
            continue
        cel = rodz.get(s) if rodzaj == 'skladowe' else wid
        if not cel:
            if scisle:
                return f'{kto}: w arkuszu nie ma wiersza {NAZWY[s]} tej umowy, więc tej kwoty nie zapiszesz.', None
            continue
        ps = w_komorce(cel)
        if rodzaj == 'umowa':
            ps = [p for p in ps if (p.get('skladowa') or 'osoba') == s]
        elif rodzaj == 'bez_umowy':
            ps = ps if s == 'osoba' else []   # BS ma jedną kwotę: zastępuje ją komplet części
        skl[s] = (cel, ps)
    if (rodzaj == 'bez_umowy' and scisle and w_komorce(wid) and any(s in kwoty for s in SKLADOWE)
            and not all(s in kwoty for s in SKLADOWE)):
        return f'{kto}: w budżecie to jedna kwota brutto, więc wpisz wszystkie części (na konto, ZUS, PIT; 0, gdy brak).', None
    for s, (cel, ps) in skl.items():
        obce = [p for p in ps if p['typ'] != 'plan' and not _bs(p)]
        if obce:
            return (f'{kto}: w komórce za {_mies_pl(m)} jest płatność połączona w apce ({obce[0].get("dokument") or obce[0]["id"]}). '
                    'Odłącz ją, zanim wpiszesz listę płac.'), None
    if rodzaj == 'umowa' and scisle and skl:   # plan z komórki (generowany) zastępujemy tylko w całości
        gen = {(p.get('skladowa') or 'osoba') for p in w_komorce(wid) if p.get('generowany')}
        brak = sorted(gen - set(skl))
        if brak and (wid, m) in st['komorka']:
            return f'{kto}: plan za {_mies_pl(m)} liczy się z kwoty komórki, więc wpisz wszystkie składowe listy (brakuje: {", ".join(NAZWY[s] for s in brak)}).', None
    return None, {'wid': wid, 'w': w, 'ref': f'lista:{m}:{wid}', 'rodzaj': rodzaj, 'skl': skl, 'kwoty': kwoty,
                  'data_wyplaty': x.get('data_wyplaty'), 'uwaga': x.get('uwaga') or ''}


def _wspolne(m: str, ref: str, wzor: dict | None, w: dict) -> dict:
    wzor = wzor or {}
    return {'miesiac': m, 'typ': 'rzeczywista', 'etap_bs': wzor.get('etap_bs', '') if wzor and _bs(wzor) else '', 'aktualna': True,
            'vat': 0, 'stawka': None, 'nr_dok': f'lista płac {m[5:7]}/{m[:4]}', 'nr_wewn': '', 'komentarz': wzor.get('komentarz', ''),
            'kontrahent': wzor.get('kontrahent') or w.get('kontrahent', ''), 'metoda': wzor.get('metoda') or w.get('metoda', ''),
            'ksiegowane': bool(wzor.get('ksiegowane', w.get('ksiegowane', True))),
            'w_cashflow': bool(wzor.get('w_cashflow', w.get('w_cashflow', True))), 'zrodlo': ZRODLO, 'dokument': ref}


def _tytul(m: str, bs: int | None) -> str:
    from .budzet import _mies_pl
    from .format import zl
    return f'Lista płac za {_mies_pl(m)}' + (f' (w BS było {zl(bs)})' if bs is not None else '')


def _zastap(st: dict, rek: dict, cel: str, m: str, ps: list[dict]):
    """Płatności komórki ustępują liście płac (plany i płatności z kopii BS); zostają w zapisie do przywrócenia."""
    for p in ps:
        rek['zastapione'].append(dict(p))
        st['platnosc'].pop(p['id'], None)
    k = f'{cel}|{m}'
    # komórka z kwotą (plany generowane): zamknięta, żeby plan nie wrócił przy przeliczeniu
    rek['komorki'][k] = 'zamknieta' if (cel, m) in st['komorka'] else rek['komorki'].get(k)


def _zastosuj_pozycje(st: dict, m: str, pp: dict):
    from .budzet import _przelicz_realizacje, id_rzeczywistej
    pla = st['platnosc']
    w, wid, ref, kw = pp['w'], pp['wid'], pp['ref'], pp['kwoty']
    rek = {'czesci': [], 'platnosci': [], 'komorki': {}, 'zastapione': [], 'dodane': [], 'reszta': 'usun', 'zrodlo': ZRODLO,
           'kwoty': kw, 'bs': {}, 'plan': {}, 'data_wyplaty': pp['data_wyplaty'], 'uwaga': pp['uwaga']}
    wzory = {s: _pierwsza(ps) for s, (_, ps) in pp['skl'].items()}
    osoba_wzor = wzory.get('osoba') or next((x for x in wzory.values() if x), None)
    if pp['rodzaj'] == 'bez_umowy':
        wzory.update({s: osoba_wzor for s in ('us', 'zus') if s in wzory})
    wyplata = pp['data_wyplaty'] or (osoba_wzor or {}).get('termin')
    mies_wyplaty = (wyplata or f'{plan.przesun_miesiac(m, 1)}-01')[:7]
    baza_id = id_rzeczywistej(ref)
    for s, (cel, ps) in pp['skl'].items():
        wz = wzory.get(s) or osoba_wzor
        bs = [p for p in ps if _bs(p)]
        if bs:
            rek['bs'][s] = sum(p['netto'] for p in bs)
        if any(p['typ'] == 'plan' for p in ps):
            rek['plan'][s] = sum(p['netto'] for p in ps if p['typ'] == 'plan')
        _zastap(st, rek, cel, m, ps)
        if s == 'osoba':
            termin = pp['data_wyplaty'] or (wz or {}).get('termin') or f'{mies_wyplaty}-10'
            realny = pp['data_wyplaty'] or (wz or {}).get('realny') or termin
        else:
            termin = realny = f'{plan.przesun_miesiac(mies_wyplaty, 1)}-{DZIEN[s]:02d}'
        p = {**_wspolne(m, ref, wz, w), 'id': f'{baza_id}:{s}', 'wiersz': cel, 'netto': kw[s], 'brutto': kw[s],
             'tytul': _tytul(m, rek['bs'].get(s)), 'wystawienie': (wz or {}).get('wystawienie') or wyplata or termin,
             'termin': termin, 'realny': realny,
             'ksiegowanie': (wz or {}).get('ksiegowanie') or (osoba_wzor or {}).get('ksiegowanie') or f'{mies_wyplaty}-01'}
        if pp['rodzaj'] != 'skladowe':
            p['skladowa'] = s
        if s == 'osoba':
            p['skladniki'] = dict(kw)   # cała pozycja listy (także PPK, pakiet, potrącenia) do wglądu na karcie
        elif 'osoba' in pp['skl']:
            p['spinacz'] = f'{baza_id}:osoba'   # PIT i ZUS opłacone dopiero po wypłacie dla osoby
        pla[p['id']] = p
        rek['czesci'].append({'wiersz': cel, 'miesiac': m, 'kwota': kw[s]})
        rek['platnosci'].append(p['id'])
    if pp['rodzaj'] == 'bez_umowy' and not w.get('lista_plac'):
        st['wiersz'][wid] = {**w, 'lista_plac': True}   # od teraz wiersz wynagrodzenia (ostrzeżenia, bez dokumentów)
    st['polaczenia'][ref] = rek
    _przelicz_realizacje(st, [k for k in rek['komorki']])


def _ppk_z_listy(p: dict) -> bool:
    """Płatność PPK z innej listy płac (stoi w komórce miesiąca swojej listy)."""
    return (p.get('dokument') or '').startswith('lista:') and p['dokument'].endswith(':ppk')


def _plan_ppk(st: dict, m: str, d: dict, plany: list[dict], scisle: bool):
    """PPK z listy: (powód, plan albo None). Kwota = suma PPK pracownika i pracodawcy wszystkich osób z listy. Płatność
    w komórce miesiąca listy (m), termin 15. dnia miesiąca po wypłacie; zastępowana komórka BS = miesiąc przelewu."""
    from .budzet import _mies_pl
    kwoty = {pp['wid']: sum(int(pp['kwoty'].get(k) or 0) for k in PPK) for pp in plany if any(k in pp['kwoty'] for k in PPK)}
    ppk = d.get('ppk') or {}
    if not kwoty:
        return None, None
    if not ppk.get('wiersz'):
        return None, None   # PPK bez wskazanego wiersza: tylko do kosztu pracodawcy, BS bez zmian
    w = st['wiersz'].get(ppk['wiersz'])
    if not w:
        return 'nie ma zbiorczego wiersza PPK wskazanego w liście płac', None
    if w.get('rodzaj') != -1 or plan.jest_umowa(w.get('podstawa', '')) or plan.skladowa_umowy(w.get('podstawa', '')):
        return f'Wiersz „{_kto(w)}” nie nadaje się na PPK (wybierz obciążenie bez faktury, np. wiersz PPK z Budget Studio).', None
    wyplaty = sorted(pp['data_wyplaty'] for pp in plany if pp['data_wyplaty'])
    mies_wyplaty = wyplaty[0][:7] if wyplaty else plan.przesun_miesiac(m, 1)
    termin = ppk.get('termin') or f'{plan.przesun_miesiac(mies_wyplaty, 1)}-{DZIEN["ppk"]:02d}'
    kom_bs = ppk.get('miesiac') or termin[:7]
    w_bs = [p for p in st['platnosc'].values() if p['wiersz'] == ppk['wiersz'] and p['miesiac'] == kom_bs and not _ppk_z_listy(p)]
    obce = [p for p in w_bs if p['typ'] != 'plan' and not _bs(p)]
    if obce:
        return (f'Komórka PPK za {_mies_pl(kom_bs)} ma już płatność spoza BS ({obce[0].get("dokument") or obce[0]["id"]}). '
                'Wybierz inną komórkę BS do zastąpienia.'), None
    return None, {'wiersz': ppk['wiersz'], 'w': w, 'miesiac': kom_bs, 'termin': termin, 'kwoty': kwoty, 'ps': w_bs,
                  'ref': f'lista:{m}:ppk'}


def _zastosuj_ppk(st: dict, m: str, pk: dict):
    from .budzet import _mies_pl, _przelicz_realizacje, id_rzeczywistej
    from .format import zl
    rek = {'czesci': [], 'platnosci': [], 'komorki': {}, 'zastapione': [], 'dodane': [], 'reszta': 'usun', 'zrodlo': ZRODLO,
           'kwoty': {'ppk': sum(pk['kwoty'].values())}, 'osoby': pk['kwoty'], 'bs': {}, 'plan': {}, 'ppk': True,
           'miesiac_listy': m, 'komorka_bs': pk['miesiac']}
    ps, cel, kom_bs = pk['ps'], pk['wiersz'], pk['miesiac']
    bs = [p for p in ps if _bs(p)]
    if bs:
        rek['bs']['ppk'] = sum(p['netto'] for p in bs)
    if any(p['typ'] == 'plan' for p in ps):
        rek['plan']['ppk'] = sum(p['netto'] for p in ps if p['typ'] == 'plan')
    wz = _pierwsza(ps)
    _zastap(st, rek, cel, kom_bs, ps)   # komórka BS (miesiąc przelewu) ustępuje liście
    suma = rek['kwoty']['ppk']
    gdzie = f' (w BS w komórce {_mies_pl(kom_bs)}' + (f': {zl(rek["bs"]["ppk"])})' if 'ppk' in rek['bs'] else ')')
    p = {**_wspolne(m, pk['ref'], wz, pk['w']), 'id': id_rzeczywistej(pk['ref']), 'wiersz': cel, 'netto': suma, 'brutto': suma,
         'tytul': f'PPK z listy płac za {_mies_pl(m)}' + gdzie,
         'wystawienie': (wz or {}).get('wystawienie') or pk['termin'], 'termin': pk['termin'], 'realny': pk['termin'],
         'ksiegowanie': f'{m}-01', 'skladniki': dict(pk['kwoty'])}
    st['platnosc'][p['id']] = p
    rek['czesci'].append({'wiersz': cel, 'miesiac': m, 'kwota': suma})
    rek['platnosci'].append(p['id'])
    st['polaczenia'][pk['ref']] = rek
    _przelicz_realizacje(st, list(rek['komorki']))


def usun_miesiac(st: dict, m: str):
    """Lista płac za miesiąc znika (przed nowym wpisem albo „usun”): wracają plany i płatności z BS."""
    from .budzet import _odlacz
    for ref in reversed([r for r in st['polaczenia'] if r.startswith(f'lista:{m}:')]):
        _odlacz(st, ref, False)
    st.setdefault('listy', {}).pop(m, None)


def zastosuj(st: dict, d: dict, scisle: bool = False) -> str | None:
    """Wpis listy płac za miesiąc na stanie budżetu. Zwraca powód odrzucenia (scisle) albo pozycji, których nie dało się
    odnieść (odbudowa: reszta listy działa). Przy scisle i powodzie stan jest do wyrzucenia (próba na kopii)."""
    m = d['miesiac']
    usun_miesiac(st, m)
    if d.get('usun'):
        return None
    plany, bledy = [], []
    for x in d.get('pozycje', []):
        powod, pp = _plan_pozycji(st, m, x, scisle)
        if powod:
            if scisle:
                return powod
            bledy.append(powod)
            continue
        if pp['ref'] in {q['ref'] for q in plany}:
            if scisle:
                return f"{_kto(pp['w'])} jest na liście dwa razy (ten sam wiersz wypłaty)."
            continue
        plany.append(pp)
    powod, pk = _plan_ppk(st, m, d, plany, scisle)
    if powod:
        if scisle:
            return powod
        bledy.append(powod)
    for pp in plany:
        _zastosuj_pozycje(st, m, pp)
    if pk:
        _zastosuj_ppk(st, m, pk)
    st.setdefault('listy', {})[m] = {'uwaga': d.get('uwaga') or '', 'ppk': ({'wiersz': pk['wiersz'], 'miesiac': pk['miesiac'], 'termin': pk['termin']}
                                                                          if pk else d.get('ppk')),
                                      'pozycje': [pp['wid'] for pp in plany]}
    return '; '.join(bledy) or None
