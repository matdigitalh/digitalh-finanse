"""Faktury kosztowe z folderu Finanse/Faktury/<Miesiąc RRRR>/Zweryfikowane (tylko odczyt nazw plików).

Wzór nazwy: Wystawca-Nr_KwotaWaluta_RRRR-MM-DD[_tag], np. GoogleAds-5550001111_975.52PLN_2026-09-30_konto-123-456-7890.pdf.
Służą do dwóch rzeczy: dokument dla miesięcy, których rejestr biura jeszcze nie obejmuje, oraz numer konta
reklamowego (Google Ads: konto-NNN-NNN-NNNN, Meta: konto-NAZWA albo FBADS-NNN w numerze).
Plików nie otwieramy; zmiana listy plików odświeża bazę (odcisk w odbudowa.py).
"""
import re
from pathlib import Path

from .. import konfig
from ..format import grosze

WZOR = re.compile(r'^(?P<wystawca>[^_]+?)(?:-(?P<nr>[^_]+))?_(?P<kwota>\d+(?:\.\d{1,2})?)(?P<waluta>[A-Z]{3})_'
                  r'(?P<data>\d{4}-\d{2}-\d{2})(?:_(?P<tag>.+))?$')
KONTO_GOOGLE = re.compile(r'konto-(\d{3}-\d{3}-\d{4})')
KONTO_NAZWA = re.compile(r'konto-([A-Za-z][\w.-]*)')
FBADS = re.compile(r'FBADS-(\d{3})')


def pliki():
    katalog = konfig.katalog_finanse() / 'Faktury'
    if not katalog.exists():
        return []
    return sorted(p for p in katalog.glob('*/Zweryfikowane/*') if p.is_file() and not p.name.startswith('.'))


def konto(wystawca: str, nr: str, tag: str) -> str:
    tekst = f'{nr or ""} {tag or ""}'
    if (m := KONTO_GOOGLE.search(tekst)):
        return f'Google Ads {m.group(1)}'
    if wystawca.lower().startswith('meta'):
        if (m := KONTO_NAZWA.search(tag or '')):
            return f'Meta {m.group(1)}'
        if (m := FBADS.search(nr or '')):
            return f'Meta FBADS-{m.group(1)}'
    return ''


def importuj(con) -> int:
    ile = 0
    for p in pliki():
        m = WZOR.match(p.stem)
        if not m:
            continue
        d = m.groupdict()
        con.execute('INSERT INTO dokumenty (plik, folder, wystawca, numer, kwota, waluta, data, tag, konto) VALUES (?,?,?,?,?,?,?,?,?)',
                    (p.name, p.parent.parent.name, d['wystawca'], d['nr'] or '', grosze(d['kwota'], przecinek_dziesietny=False),
                     d['waluta'], d['data'], d['tag'] or '', konto(d['wystawca'], d['nr'], d['tag'])))
        ile += 1
    return ile


def podpowiedzi_kont() -> dict:
    """Konto -> nazwa z wykazów faktur (np. „Google Ads · konto ALFA (123-456-7890)”, „FBADS-720 … Konto ALFA”)."""
    wynik = {}
    katalog = konfig.katalog_finanse() / 'Faktury'
    for p in sorted(katalog.glob('*/wykaz_faktur.md')) if katalog.exists() else []:
        for linia in p.read_text(encoding='utf-8', errors='ignore').splitlines():
            if (m := re.search(r'konto\s+([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż][\w ./&-]*?)\**\s*\((\d{3}-\d{3}-\d{4})\)', linia, re.I)):
                wynik.setdefault(f'Google Ads {m.group(2)}', m.group(1).strip())
            if (f := FBADS.search(linia)) and (m := re.search(r'Konto\s+([A-Z][\w /]+?)[.,|]', linia)):
                wynik.setdefault(f'Meta FBADS-{f.group(1)}', m.group(1).strip())
    return wynik
