"""Dziennik importów ręcznych (pliki przeciągnięte do okna): Finanse/Aplikacja/importy/<nazwa-Maca>.jsonl.

Jak plik zmian: każdy Mac dopisuje tylko do własnego pliku (iCloud nie widzi dwóch wersji), odczyt składa wszystkie.
Wpis mówi, skąd plik przyszedł (nazwa oryginalna), jak go zapisaliśmy w Dane/ i co import przyniósł. Import pliku,
który już był w Dane/, też ma wpis (pliku nie zapisujemy drugi raz), żeby Historia importów go pokazała.
Sam plik w Dane/ jest źródłem danych; dziennik to tylko opis zdarzenia, odtwarzalny na każdym Macu z iCloud.
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .. import konfig


def katalog() -> Path:
    return konfig.katalog_finanse() / 'Aplikacja' / 'importy'


def zapisz(dane: dict) -> dict:
    """Dopisuje wpis (jeden write + fsync, plik 600, katalog 700)."""
    wpis = {'czas': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'id': uuid.uuid4().hex,
            'mac': konfig.nazwa_maca(), **dane}
    p = konfig.katalog_prywatny(katalog()) / f'{konfig.nazwa_maca()}.jsonl'
    fd = os.open(p, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(wpis, ensure_ascii=False) + '\n').encode('utf-8'))
        os.fsync(fd)
    finally:
        os.close(fd)
    return wpis


def wczytaj() -> list[dict]:
    """Wszystkie wpisy ze wszystkich Maców, po czasie. Linia nieczytelna (np. w trakcie synchronizacji) jest pomijana."""
    k = katalog()
    wpisy = []
    for p in sorted(k.glob('*.jsonl')) if k.exists() else []:
        for linia in p.read_text(encoding='utf-8').splitlines():
            try:
                w = json.loads(linia)
            except json.JSONDecodeError:
                continue
            if isinstance(w, dict) and w.get('id'):
                wpisy.append(w)
    return sorted(wpisy, key=lambda w: (w.get('czas', ''), w['id']))
