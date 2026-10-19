"""Lokalny serwer: tylko 127.0.0.1, zero ruchu wychodzącego, zero CDN.

Ochrona: nasłuch wyłącznie na 127.0.0.1; żądania z obcym nagłówkiem Host odrzucane (DNS rebinding);
zapis tylko POST z nagłówkiem X-Finanse (cudza strona w przeglądarce nie wyśle go bez zgody CORS);
CSP pozwala ładować wyłącznie zasoby z tej apki.
"""
import json
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import (baza, budzet, cashflow, controlling, eksport, konfig, odbudowa, rentownosc, wynik, zapytania,
               zapytania_budzet, zmiany)

mimetypes.add_type('font/woff2', '.woff2')   # font interfejsu leży lokalnie w web/fonty
WEB = Path(__file__).resolve().parent.parent / 'web'
BLOKADA = threading.Lock()
NAGLOWKI = {
    'Content-Security-Policy': "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self';"
                               " connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Cache-Control': 'no-store',
    'Cross-Origin-Resource-Policy': 'same-origin',
}


def czy_aktualna() -> bool:
    p = konfig.plik_bazy()
    if not p.exists():
        return False
    con = baza.polacz(p, tylko_odczyt=True)
    try:
        r = con.execute("SELECT wartosc FROM meta WHERE klucz='odcisk'").fetchone()
    finally:
        con.close()
    return bool(r) and r[0] == odbudowa.odcisk_zrodel()


def odbuduj_jesli_trzeba(wymus=False):
    with BLOKADA:
        if wymus or not czy_aktualna():
            return odbudowa.odbuduj()
    return None


def _rok(q):
    r = q.get('rok', '')
    return r if len(r) == 4 and r.isdigit() else None


def _sprawdz_bud(con, d):
    """Zmiany budżetu tylko przy włączonym planowaniu i tylko do istniejących obiektów: wpis (także cała seria) jest
    najpierw próbnie nakładany na bieżący model; gdy którakolwiek operacja nie ma do czego się odnieść, nic nie trafia do pliku."""
    if not zapytania_budzet.planowanie(con):
        raise ValueError('Planowanie w apce jest wyłączone, więc edycja budżetu też. Włączysz je w Budżet, Ustawienia budżetu.')
    dzis = zapytania_budzet._dzien_stanu(con)
    for o in (d['operacje'] if d['op'] == 'seria' else [d]):
        if o['op'] == 'decyzja_planu' and o['decyzja'] == 'zaplacone':   # PIT i ZUS umowy dopiero po wypłacie dla osoby
            r = con.execute('SELECT p.spinacz, s.etap FROM bud_platnosc p LEFT JOIN bud_stan s ON s.platnosc = p.spinacz'
                            ' WHERE p.id = ?', (o['platnosc'],)).fetchone()
            if r and r['spinacz'] and r['etap'] != 'Opłacona':
                raise ValueError('PIT i ZUS oznaczysz jako zapłacone dopiero, gdy wypłata dla osoby jest opłacona.')
    budzet.sprawdz_wpis(d, zmiany.wczytaj()[0], dzis=dzis)


class Obsluga(BaseHTTPRequestHandler):
    server_version = 'Finanse'
    sys_version = ''

    def log_message(self, fmt, *args):  # bez zapytań w logu (mogą zawierać nazwy kontrahentów)
        sys.stderr.write(f'{self.command} {urlparse(self.path).path} {args[1] if len(args) > 1 else ""}\n')

    def _host_ok(self) -> bool:
        return self.headers.get('Host', '') in {f'127.0.0.1:{konfig.PORT}', f'localhost:{konfig.PORT}'}

    def _wyslij(self, kod, tresc: bytes, typ='application/json; charset=utf-8'):
        self.send_response(kod)
        self.send_header('Content-Type', typ)
        self.send_header('Content-Length', str(len(tresc)))
        for k, v in NAGLOWKI.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(tresc)

    def _plik(self, nazwa: str, tresc: bytes):
        from urllib.parse import quote
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{quote(nazwa)}")
        self.send_header('Content-Length', str(len(tresc)))
        for k, v in NAGLOWKI.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(tresc)

    def _json(self, dane, kod=200):
        self._wyslij(kod, json.dumps(dane, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        if not self._host_ok():
            return self._wyslij(403, b'Niedozwolony host', 'text/plain; charset=utf-8')
        u = urlparse(self.path)
        if u.path.startswith('/api/'):
            return self._api_get(u.path[5:], {k: v[0] for k, v in parse_qs(u.query).items()})
        nazwa = 'index.html' if u.path in ('', '/') else u.path.lstrip('/')
        plik = (WEB / nazwa).resolve()
        if WEB not in plik.parents or not plik.is_file():
            return self._wyslij(404, b'Nie ma', 'text/plain; charset=utf-8')
        typ = mimetypes.guess_type(plik.name)[0] or 'application/octet-stream'
        if typ.startswith('text/') or typ.endswith('javascript'):
            typ += '; charset=utf-8'
        self._wyslij(200, plik.read_bytes(), typ)

    def _api_get(self, sciezka, q):
        if not konfig.plik_bazy().exists():
            odbuduj_jesli_trzeba()
        con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
        try:
            if sciezka == 'stan':
                dane = zapytania.stan(con)
                dane['aktualna'] = czy_aktualna()
            elif sciezka == 'operacje':
                dane = zapytania.operacje(con, **{k: q.get(k) for k in ('rachunek', 'kierunek', 'wewnetrzne', 'q', 'od', 'do', 'strona', 'ile', 'sortuj')},
                                          malejaco=q.get('kolejnosc', 'malejaco') == 'malejaco')
            elif sciezka == 'faktury':
                dane = zapytania.faktury(con, **{k: q.get(k) for k in ('status', 'q', 'od', 'do', 'strona', 'ile', 'bank')})
            elif sciezka == 'zakupy':
                dane = zapytania.zakupy(con, **{k: q.get(k) for k in ('rejestr', 'q', 'od', 'do', 'strona', 'ile', 'stan')})
            elif sciezka == 'naleznosci':
                dane = zapytania.naleznosci(con, **{k: q.get(k) for k in ('przedzial', 'po_terminie', 'q', 'strona', 'ile')})
            elif sciezka == 'wplaty':
                dane = zapytania.wplaty(con, **{k: q.get(k) for k in ('stan', 'q', 'strona', 'ile') if q.get(k)})
            elif sciezka == 'wplata':
                dane = zapytania.wplata(con, q.get('id', ''))
            elif sciezka == 'do-weryfikacji':
                dane = zapytania.do_weryfikacji(con)
            elif sciezka == 'klienci':
                dane = zapytania.klienci_lista(con, q.get('rok'))
            elif sciezka == 'klient':
                dane = zapytania.klient(con, q.get('nazwa', ''), q.get('rok'))
            elif sciezka == 'wydatki':
                dane = zapytania.wydatki(con, **{k: q.get(k) for k in ('rodzaj', 'klient', 'dokument', 'zrodlo', 'q', 'od', 'do', 'strona', 'ile')})
            elif sciezka == 'reguly':
                dane = zapytania.reguly(con)
            elif sciezka == 'budzet/drzewo':
                dane = zapytania_budzet.drzewo(con)
            elif sciezka == 'budzet/arkusz':
                dane = zapytania_budzet.arkusz(con, q.get('id', ''))
            elif sciezka == 'budzet/platnosc':
                dane = zapytania_budzet.platnosc(con, q.get('id', ''))
            elif sciezka == 'budzet/komorka':
                dane = zapytania_budzet.komorka(con, q.get('wiersz', ''), q.get('miesiac', ''))
            elif sciezka == 'budzet/ostatni':
                dane = {'ostatni': zapytania_budzet.ostatni(con)}
            elif sciezka == 'budzet/lista':
                dane = zapytania_budzet.lista(con, q.get('lista', 'wszystkie'), q.get('rodzaj'), q.get('q'), q.get('strona'), q.get('ile'),
                                              q.get('arkusz'))
            elif sciezka == 'budzet/kafle':
                dane = zapytania_budzet.kafle(con)
            elif sciezka == 'budzet/rozjazdy':
                dane = zapytania_budzet.rozjazdy(con)
            elif sciezka == 'budzet/historia':
                dane = zapytania_budzet.historia(con)
            elif sciezka == 'umowy':
                from . import umowy
                dane = umowy.lista(con)
            elif sciezka == 'cashflow':
                dane = cashflow.prognoza(con)
            elif sciezka == 'cashflow/okresy':
                dane = cashflow.okresy(con, **{k: q.get(k) for k in ('granulacja', 'od', 'do', 'saldo_start', 'rodzaj', 'arkusz')},
                                       scenariusz=q.get('scenariusz') or 'ostrozny')
            elif sciezka == 'rentownosc/klienci':
                dane = rentownosc.klienci(con, _rok(q))
            elif sciezka == 'rentownosc/arkusze':
                dane = rentownosc.arkusze(con)
            elif sciezka.startswith('eksport/'):
                rodzaj = sciezka.split('/', 1)[1]
                nazwa, tresc = (eksport.arkusz(con, q.get('id', '')) if rodzaj == 'arkusz' else eksport.cash_flow(con)
                                if rodzaj == 'cashflow' else eksport.rentownosc_xls(con, _rok(q)) if rodzaj == 'rentownosc' else (None, None))
                if not tresc:
                    return self._json({'blad': 'nieznany eksport'}, 404)
                return self._plik(nazwa, tresc)
            elif sciezka == 'konta-reklamowe':
                dane = zapytania.konta_reklamowe(con)
            elif sciezka == 'nieprzypisane-grupy':
                dane = zapytania.nieprzypisane_grupy(con)
            elif sciezka == 'controlling':
                dane = controlling.policz(con)
            elif sciezka == 'saldo-historia':
                dane = zapytania.historia_salda(con)
            elif sciezka == 'wynik':
                dane = wynik.wynik_zarzadczy(con, _rok(q))
            elif sciezka == 'obroty-klientow':
                dane = wynik.obroty_klientow(con, _rok(q))
            elif sciezka == 'koszty-kategorii':
                dane = wynik.koszty_kategorii(con, _rok(q), q.get('rodzaj') or None)
            elif sciezka == 'vat':
                dane = wynik.vat(con, _rok(q))
            elif sciezka == 'importy':
                dane = zapytania.importy(con)
            elif sciezka == 'wyniki-biura':
                dane = zapytania.wyniki_biura(con)
            else:
                return self._json({'blad': 'nieznany adres'}, 404)
        except (ValueError, TypeError) as e:
            return self._json({'blad': str(e)}, 400)
        finally:
            con.close()
        self._json(dane)

    def do_POST(self):
        if not self._host_ok() or self.headers.get('X-Finanse') != '1':
            return self._wyslij(403, b'Zablokowane', 'text/plain; charset=utf-8')
        u = urlparse(self.path)
        if u.path == '/api/odbuduj':
            raport = odbuduj_jesli_trzeba(wymus=True)
            return self._json({'ok': True, 'bledy': raport['bledy'] if raport else []})
        if u.path == '/api/zmiana':
            return self._zmiana()
        self._json({'blad': 'nieznany adres'}, 404)

    def _zmiana(self):
        """Decyzja Mata (połącz, bez faktury, zatwierdź, odrzuć, poza bankiem, cofnij): dopisanie do pliku zmian
        tego Maca i przeliczenie bazy. Odwołania sprawdzane w bazie, żeby do pliku nie trafiło nic zmyślonego."""
        try:
            dlugosc = int(self.headers.get('Content-Length', '0'))
            if not 0 < dlugosc <= 500000:   # seria (wklejenie bloku, duplikowanie wierszy) bywa duża
                raise ValueError('pusty albo za duży wpis')
            cialo = json.loads(self.rfile.read(dlugosc))
            typ = cialo.get('typ')
            dane = zmiany.sprawdz(typ, cialo.get('dane'))
            con = baza.polacz(konfig.plik_bazy(), tylko_odczyt=True)
            try:
                if 'operacja' in dane and not con.execute('SELECT 1 FROM operacje WHERE klucz = ? AND wewnetrzna = 0',
                                                          (dane['operacja'],)).fetchone():
                    raise ValueError('nie ma takiej operacji')
                if typ == 'bud':
                    _sprawdz_bud(con, dane)
                for n in dane.get('faktury', []) + ([dane['faktura']] if 'faktura' in dane else []):
                    if not con.execute('SELECT 1 FROM faktury WHERE numer = ?', (n,)).fetchone():
                        raise ValueError(f'nie ma faktury {n}')
            finally:
                con.close()
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            return self._json({'blad': str(e)}, 400)
        wpis = zmiany.zapisz(typ, dane)
        raport = odbuduj_jesli_trzeba(wymus=True)
        self._json({'ok': True, 'wpis': wpis['id'], 'bledy': raport['bledy'] if raport else []})

    def do_PUT(self):
        self._wyslij(405, b'', 'text/plain')

    do_DELETE = do_PATCH = do_PUT


def main():
    otworz = '--bez-przegladarki' not in sys.argv
    print('Sprawdzam dane…', flush=True)
    raport = odbuduj_jesli_trzeba()
    if raport and raport['bledy']:
        print('Uwagi:', *raport['bledy'], sep='\n  ')
    serwer = ThreadingHTTPServer((konfig.HOST, konfig.PORT), Obsluga)
    adres = f'http://{konfig.HOST}:{konfig.PORT}/'
    print(f'Finanse lokalne: {adres} (tylko ten komputer). Zamknij okno terminala, żeby wyłączyć.', flush=True)
    if otworz:
        threading.Timer(0.5, lambda: webbrowser.open(adres)).start()
    try:
        serwer.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        serwer.server_close()


if __name__ == '__main__':
    main()
