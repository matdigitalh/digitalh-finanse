"""Wspólne dla importów: wybór plików, hash, log."""
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

DATA_W_NAZWIE = re.compile(r'(\d{4}-\d{2}(?:-\d{2})?)(?!.*\d{4}-\d{2})')


def data_z_nazwy(p: Path) -> str:
    """Ostatnia data w nazwie pliku (dla zakresu OD_DO to data końca)."""
    m = DATA_W_NAZWIE.search(p.stem)
    return m.group(1) if m else ''


def pliki(katalog: Path, wzorzec: str) -> list[Path]:
    """Pliki pasujące do wzorca, najnowsze (wg daty w nazwie) pierwsze."""
    return sorted(katalog.glob(wzorzec), key=lambda p: (data_z_nazwy(p), p.name), reverse=True)


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for kawalek in iter(lambda: f.read(1 << 16), b''):
            h.update(kawalek)
    return h.hexdigest()


def teraz() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def zapisz_log(con, rodzaj, p: Path, wierszy, nowych, uwagi=''):
    zm = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec='seconds')
    con.execute('INSERT INTO import_log (rodzaj, plik, sha256, zmodyfikowany, wierszy, nowych, pominietych, uwagi, czas)'
                ' VALUES (?,?,?,?,?,?,?,?,?)',
                (rodzaj, p.name, sha256(p), zm, wierszy, nowych, wierszy - nowych, uwagi, teraz()))
