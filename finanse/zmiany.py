"""Wpisy Mata (reguły, umowy, zatwierdzenia dopasowań) jako dziennik zmian w iCloud.

Każdy Mac dopisuje wyłącznie do własnego pliku `zmiany/<nazwa-Maca>.jsonl`, więc iCloud nigdy nie
widzi dwóch wersji jednego pliku. Stan powstaje przez złożenie wpisów ze wszystkich plików po czasie.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import konfig


def _plik_tego_maca() -> Path:
    return konfig.katalog_prywatny(konfig.katalog_zmian()) / f'{konfig.nazwa_maca()}.jsonl'


def zapisz(typ: str, dane: dict) -> dict:
    """Dopisuje jeden wpis. Zapis jednym write + fsync, plik 600."""
    wpis = {'czas': datetime.now(timezone.utc).isoformat(timespec='microseconds'), 'id': uuid.uuid4().hex,
            'mac': konfig.nazwa_maca(), 'typ': typ, 'dane': dane}
    p = _plik_tego_maca()
    fd = os.open(p, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(wpis, ensure_ascii=False) + '\n').encode('utf-8'))
        os.fsync(fd)
    finally:
        os.close(fd)
    return wpis


def wczytaj() -> tuple[list[dict], list[str]]:
    """Wszystkie wpisy ze wszystkich Maców, po czasie. Drugi element: ostrzeżenia (np. ucięta linia)."""
    katalog = konfig.katalog_zmian()
    wpisy, ostrzezenia = [], []
    if not katalog.exists():
        return wpisy, ostrzezenia
    for p in sorted(katalog.glob('*.jsonl')):
        for nr, linia in enumerate(p.read_text(encoding='utf-8').splitlines(), start=1):
            if not linia.strip():
                continue
            try:
                wpisy.append(json.loads(linia))
            except json.JSONDecodeError:
                ostrzezenia.append(f'{p.name}, linia {nr}: nieczytelny wpis (może jeszcze się synchronizuje)')
    for p in katalog.glob('*conflict*'):
        ostrzezenia.append(f'iCloud zrobił kopię konfliktu: {p.name}')
    wpisy.sort(key=lambda w: (w.get('czas', ''), w.get('id', '')))
    return wpisy, ostrzezenia


def odcisk() -> str:
    """Stan plików zmian (nazwa, rozmiar, czas) do wykrycia wpisów z drugiego Maca."""
    katalog = konfig.katalog_zmian()
    if not katalog.exists():
        return ''
    return ';'.join(f'{p.name}:{p.stat().st_size}:{int(p.stat().st_mtime)}' for p in sorted(katalog.glob('*.jsonl')))
