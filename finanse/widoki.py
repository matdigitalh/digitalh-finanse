"""Zapisane widoki list i pozycje oznaczone do sprawdzenia (pakiet 7). Liczone przy odbudowie z pliku zmian:
- „widok” (B-LIS-03, A-FIL-07): nazwany zestaw filtrów, sortowania i kolumn listy; ten sam identyfikator nadpisuje widok
  (także startowy), „usun” go ukrywa. Daty względne zapisane jako tryb (np. „ruchomy:dzien:14:0”), więc przeliczają się
  przy każdym otwarciu.
- „do_weryfikacji”: pozycja z dowolnej listy przeniesiona do sprawdzenia (Do weryfikacji); „usun” = sprawdzone.
- pakiet 11: „widok” z ekranem „arkusz” to zapisany widok arkusza budżetu (A-ARK-02: grupowanie, sortowanie, sekcje,
  kolumny ustawień, serie wykresu), parametr „arkusz” mówi, którego arkusza dotyczy; „przypiecie” przypina arkusz
  w menu Budżet (sekcja Przypięte, A-OPS-07).
Cofnięcie wpisu (także całej serii) przywraca stan sprzed niego."""
import json

# Listy z zapisanymi widokami (klucz ekranu w zdarzeniu „widok”)
EKRANY = ('platnosci', 'bank', 'faktury', 'naleznosci', 'zakupy', 'wplaty', 'do_weryfikacji', 'wydatki')
EKRANY += ('arkusz',)   # pakiet 11: widoki arkusza budżetu (osobno dla każdego arkusza, parametr „arkusz”)
# Ustawienia arkusza, które zapisuje widok arkusza (te same nazwy co parametry adresu ekranu arkusza)
KLUCZE_WIDOKU_ARKUSZA = ('grupuj', 'sortuj', 'kolejnosc', 'sekcje', 'sekcje_kier', 'ustawienia', 'serie')
# Co można przenieść do Do weryfikacji: rodzaj obiektu → czym jest ref
OBIEKTY = {'operacja': 'klucz operacji z banku', 'faktura': 'numer faktury', 'zakup': 'numer ewidencyjny dokumentu z rejestru',
           'platnosc': 'identyfikator płatności budżetu'}


def sprawdz_przypiecie(d: dict) -> dict:
    """Wpis „przypiecie” (pakiet 11): arkusz i czy przypięty. Czy arkusz istnieje, sprawdza serwer w bazie."""
    aid = d.get('arkusz')
    if not isinstance(aid, str) or not aid.strip() or len(aid) > 80:
        raise ValueError('przypięcie: brak arkusza')
    if not isinstance(d.get('przypiety', True), bool):
        raise ValueError('przypięcie: przypięty tak albo nie')
    return {'arkusz': aid, 'przypiety': d.get('przypiety', True)}


def zbuduj(con, wpisy: list[dict]) -> dict:
    cofniete = {w['dane'].get('wpis') for w in wpisy if w.get('typ') == 'cofnij'}
    widoki, oznaczone, przypiete_ = {}, {}, {}
    for w in wpisy:
        if w.get('id') in cofniete:
            continue
        d = w.get('dane') or {}
        if w.get('typ') == 'widok':
            klucz = (d['ekran'], d['id'])
            if d.get('usun'):
                widoki[klucz] = {**widoki.get(klucz, {}), 'usuniety': 1, 'wpis': w['id'], 'czas': w['czas']}
            else:
                widoki[klucz] = {'nazwa': d['nazwa'], 'parametry': d.get('parametry') or {}, 'kolumny': d.get('kolumny') or [],
                                 'usuniety': 0, 'wpis': w['id'], 'czas': w['czas']}
        elif w.get('typ') == 'do_weryfikacji':
            klucz = (d['obiekt'], d['ref'])
            if d.get('usun'):
                oznaczone.pop(klucz, None)
            else:
                oznaczone[klucz] = {'powod': d.get('powod', ''), 'wpis': w['id'], 'czas': w['czas']}
        elif w.get('typ') == 'przypiecie':   # ostatni wpis dla arkusza wygrywa; kolejność w menu = kolejność przypinania
            przypiete_.pop(d['arkusz'], None)
            if d.get('przypiety', True):
                przypiete_[d['arkusz']] = w['czas']
    con.executemany('INSERT INTO widoki (ekran, id, nazwa, parametry, kolumny, usuniety, wpis, czas) VALUES (?,?,?,?,?,?,?,?)',
                    [(e, i, v.get('nazwa', ''), json.dumps(v.get('parametry', {}), ensure_ascii=False, sort_keys=True),
                      json.dumps(v.get('kolumny', []), ensure_ascii=False), v['usuniety'], v['wpis'], v['czas'])
                     for (e, i), v in sorted(widoki.items())])
    con.executemany('INSERT INTO oznaczone (obiekt, ref, powod, wpis, czas) VALUES (?,?,?,?,?)',
                    [(o, r, v['powod'], v['wpis'], v['czas']) for (o, r), v in sorted(oznaczone.items())])
    con.execute("INSERT INTO meta VALUES ('przypiete', ?)", (json.dumps(list(przypiete_), ensure_ascii=False),))
    return {'widokow': sum(1 for v in widoki.values() if not v['usuniety']), 'oznaczonych': len(oznaczone),
            'przypietych': len(przypiete_)}


# ---------- Pakiet 11: przypięte arkusze i widoki arkusza ----------

def przypiete(con) -> list[dict]:
    """Arkusze przypięte w menu Budżet, w kolejności przypinania; arkusza, którego już nie ma, lista nie pokazuje."""
    r = con.execute("SELECT wartosc FROM meta WHERE klucz = 'przypiete'").fetchone()
    ids = json.loads(r[0]) if r and r[0] else []
    ark = {x['id']: dict(x) for x in con.execute('SELECT id, nazwa, folder, kategoria FROM bud_arkusz')}
    return [ark[i] for i in ids if i in ark]


def arkusza(con, aid: str) -> list[dict]:
    """Zapisane widoki jednego arkusza (A-ARK-02), w kolejności zapisu. Widok główny to stan bez parametrów: nie jest
    zapisywany i zawsze jest pierwszy w menu (dokłada go interfejs)."""
    wynik = []
    for r in con.execute("SELECT * FROM widoki WHERE ekran = 'arkusz' AND usuniety = 0 ORDER BY czas, id"):
        par = json.loads(r['parametry'] or '{}')
        if par.get('arkusz') != aid:
            continue
        wynik.append({'id': r['id'], 'nazwa': r['nazwa'], 'wpis': r['wpis'],
                      'parametry': {k: v for k, v in par.items() if k in KLUCZE_WIDOKU_ARKUSZA}})
    return wynik
