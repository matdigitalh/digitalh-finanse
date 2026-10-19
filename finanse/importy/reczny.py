"""Import ręczny: plik przeciągnięty do okna apki (POST /api/import).

Kolejność: rozpoznanie źródła po zawartości → odczyt w katalogu tymczasowym bazy (lokalnie, 700, plik 600, sprzątany)
→ podsumowanie względem tego, co już jest w Dane/ (Dodane, Zaktualizowane, Bez zmian, Pominięte) → przy zapisie surowy
plik trafia bez zmian do właściwego podfolderu Dane/ pod nazwą wg konwencji (źródło_rodzaj_data.rozszerzenie, plik 600)
i wpis do dziennika importów. Ten sam plik drugi raz (ta sama treść) nie jest zapisywany: wpis w dzienniku mówi
„Bez zmian” = liczba wierszy. Nieznany format: ostrzeżenie, nic nie jest zapisywane.
"""
import hashlib
import os
import re
import uuid
from pathlib import Path

from .. import konfig
from . import dziennik, podsumowanie, rozpoznanie
from .wspolne import sha256

MAKS_ROZMIAR = 20 * 1024 * 1024   # 20 MB: eksport ING za rok to ok. 0,5 MB
PRZYKLADY = 5


def czysta_nazwa(nazwa: str) -> str:
    """Nazwa pliku od przeglądarki tylko do opisu (nigdy jako ścieżka): bez katalogów i znaków sterujących."""
    n = re.sub(r'[\x00-\x1f\x7f]', '', (nazwa or '').replace('\\', '/').split('/')[-1]).strip()
    return n[:200] or 'plik bez nazwy'


def _zrodlo(rodzaj: str) -> tuple[str, bool]:
    return next((wz, wsz) for r, wz, wsz in podsumowanie._zrodla() if r == rodzaj)


def _odczytaj(rodzaj: str, tresc: bytes, rozsz: str, okres: str | None) -> podsumowanie.Wczytanie:
    """Odczyt z kopii roboczej w lokalnym katalogu bazy (nie w /tmp i nie w iCloud); kopia znika od razu."""
    katalog = konfig.katalog_prywatny(konfig.plik_bazy().parent / 'import-roboczy')
    p = katalog / f'{uuid.uuid4().hex}{rozsz}'
    fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(tresc)
        return podsumowanie.wczytaj(rodzaj, p, okres)
    finally:
        p.unlink(missing_ok=True)


def _wolna_nazwa(katalog: Path, nazwa: str) -> str:
    """Gdy plik o tej nazwie już jest (inna treść): _2, _3… przed rozszerzeniem (nowszy wg nazwy, więc ten liczy się dalej)."""
    if not (katalog / nazwa).exists():
        return nazwa
    rdzen, rozsz = os.path.splitext(nazwa)
    i = 2
    while (katalog / f'{rdzen}_{i}{rozsz}').exists():
        i += 1
    return f'{rdzen}_{i}{rozsz}'


def _zapisz_plik(cel: Path, tresc: bytes):
    """Surowy plik bez zmian, 600, atomowo (najpierw ukryty plik obok, potem zmiana nazwy); nie nadpisuje istniejącego.
    Wywołujący trzyma blokadę serwera, więc między sprawdzeniem a zmianą nazwy nikt w apce nie zapisze tego pliku."""
    if not cel.parent.exists():
        konfig.katalog_prywatny(cel.parent)
    tmp = cel.parent / f'.{cel.name}.{uuid.uuid4().hex[:8]}.tmp'
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(tresc)
            f.flush()
            os.fsync(f.fileno())
        if cel.exists():
            raise ValueError(f'plik {cel.name} już jest w Dane/, nic nie nadpisuję')
        os.rename(tmp, cel)
    finally:
        tmp.unlink(missing_ok=True)


def przyjmij(tresc: bytes, nazwa: str, zapisz: bool = False) -> dict:
    """Podgląd (zapisz=False) albo import pliku. Zwraca podsumowanie do pokazania Matowi; nic nie rzuca przy złym
    pliku (ostrzeżenie w polu 'ostrzezenie')."""
    nazwa = czysta_nazwa(nazwa)
    if len(tresc) > MAKS_ROZMIAR:
        return {'rozpoznany': False, 'plik_zrodlowy': nazwa, 'ostrzezenie': 'Plik większy niż 20 MB. To nie wygląda na eksport z banku ani z biura.'}
    roz = rozpoznanie.rozpoznaj(tresc, nazwa)
    if not roz['rodzaj']:
        return {'rozpoznany': False, 'plik_zrodlowy': nazwa, 'ostrzezenie': roz['powod']}
    rodzaj = roz['rodzaj']
    wzorzec, wszystkie = _zrodlo(rodzaj)
    rozsz = '.' + wzorzec.rsplit('.', 1)[1]
    w = _odczytaj(rodzaj, tresc, rozsz, roz.get('okres'))
    odp = {'rozpoznany': True, 'zrodlo': rodzaj, 'opis_zrodla': podsumowanie.OPISY[rodzaj], 'plik_zrodlowy': nazwa}
    if w.blad:
        return {**odp, 'ostrzezenie': f'Plik wygląda na {podsumowanie.OPISY[rodzaj]}, ale nie da się go wczytać: {w.blad}. Nic nie zapisano.'}
    katalog = konfig.katalog_dane() / wzorzec.split('/')[0]
    sha = hashlib.sha256(tresc).hexdigest()
    duplikat = next((p for p in sorted(konfig.katalog_dane().glob(wzorzec)) if p.is_file() and sha256(p) == sha), None)
    por = podsumowanie.porownaj(w, podsumowanie.stan_przed(rodzaj))
    liczniki = {'dodane': len(por['dodane']), 'zaktualizowane': len(por['zaktualizowane']), 'bez_zmian': len(por['bez_zmian']),
                'pominiete': len(w.pominiete)}
    cel = None if duplikat else _wolna_nazwa(katalog, rozpoznanie.nazwa_docelowa(rodzaj, wzorzec, w.rekordy, roz.get('okres')))
    uwagi = []
    if duplikat:
        uwagi.append(f'Ten sam plik już jest w Dane/{duplikat.parent.name} jako {duplikat.name}; drugi raz go nie zapiszę.')
    elif not wszystkie:
        uwagi.append('Apka czyta tylko najnowszy plik tego źródła: ten zastąpi poprzedni (poprzedni zostaje w folderze).')
    odp.update(liczniki=liczniki, wierszy=w.wierszy, cel=f'{katalog.name}/{cel}' if cel else None,
               duplikat=f'{duplikat.parent.name}/{duplikat.name}' if duplikat else None, uwagi=uwagi,
               przyklady={'pominiete': [f"{('wiersz ' + str(x['wiersz']) + ': ') if x.get('wiersz') else ''}{x['opis']} ({x['powod']})"
                                        for x in w.pominiete[:PRZYKLADY]],
                          'dodane': [r.opis for r in por['dodane'][:PRZYKLADY]],
                          'zaktualizowane': [r.opis for r, _ in por['zaktualizowane'][:PRZYKLADY]]},
               zapisano=False)
    if not zapisz:
        return odp
    if cel:
        _zapisz_plik(katalog / cel, tresc)
    wpis = dziennik.zapisz({'plik_zrodlowy': nazwa, 'zrodlo': rodzaj, 'sha256': sha, 'zapisany_jako': odp['cel'],
                            'duplikat_z': odp['duplikat'], 'liczniki': liczniki, 'wierszy': w.wierszy})
    odp.update(zapisano=True, id=f"plik:{odp['cel']}" if cel else f"wpis:{wpis['id']}")
    return odp
