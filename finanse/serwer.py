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

from . import baza, konfig, odbudowa, zapytania

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
                dane = zapytania.faktury(con, **{k: q.get(k) for k in ('status', 'q', 'od', 'do', 'strona', 'ile')})
            elif sciezka == 'zakupy':
                dane = zapytania.zakupy(con, **{k: q.get(k) for k in ('rejestr', 'q', 'od', 'do', 'strona', 'ile')})
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
        self._json({'blad': 'nieznany adres'}, 404)

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
