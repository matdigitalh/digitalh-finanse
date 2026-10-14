"""Ścieżki i ustawienia. Dane leżą poza repo; testy podmieniają ścieżki zmiennymi środowiskowymi."""
import os
import re
import subprocess
from pathlib import Path

HOST = '127.0.0.1'          # nigdy 0.0.0.0 (audyt Maca 2026-10-11)
PORT = int(os.environ.get('FINANSE_PORT', '8765'))


def katalog_finanse() -> Path:
    return Path(os.environ.get('FINANSE_KATALOG', Path.home() / 'Documents' / 'DigitalH' / 'Finanse'))


def katalog_dane() -> Path:
    return katalog_finanse() / 'Raporty' / 'Dane'


def katalog_zmian() -> Path:
    """Wpisy Mata (reguły, umowy, zatwierdzenia). iCloud, jeden plik na Maca."""
    return katalog_finanse() / 'Aplikacja' / 'zmiany'


def plik_bazy() -> Path:
    """Baza to lokalny cache odbudowywany z plików, poza iCloud."""
    domyslny = Path.home() / 'Library' / 'Application Support' / 'DigitalH-Finanse' / 'finanse.sqlite'
    return Path(os.environ.get('FINANSE_BAZA', domyslny))


def nazwa_maca() -> str:
    """Nazwa tego komputera do nazwy pliku zmian, np. 'Mac-mini-DigitalH'."""
    nazwa = os.environ.get('FINANSE_MAC')
    if not nazwa:
        try:
            nazwa = subprocess.run(['scutil', '--get', 'ComputerName'], capture_output=True,
                                   text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            nazwa = ''
        nazwa = nazwa or os.uname().nodename
    nazwa = re.sub(r'[^A-Za-z0-9]+', '-', nazwa).strip('-')
    return nazwa or 'mac'


def katalog_prywatny(sciezka: Path) -> Path:
    """Tworzy katalog z uprawnieniami 700 (tylko właściciel)."""
    sciezka.mkdir(parents=True, exist_ok=True)
    os.chmod(sciezka, 0o700)
    return sciezka
