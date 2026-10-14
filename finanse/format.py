"""Kwoty w groszach (int), daty ISO, normalizacja nazw. Zero floatów w liczeniu pieniędzy."""
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def grosze(tekst, przecinek_dziesietny=True) -> int:
    """'-2 460,00' -> -246000. przecinek_dziesietny=False dla formatu '8246.01' (Fakturownia)."""
    if tekst is None:
        return 0
    if isinstance(tekst, (int, float, Decimal)):
        return int((Decimal(str(tekst)) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    s = str(tekst).replace('\xa0', '').replace(' ', '').strip()
    if not s:
        return 0
    if przecinek_dziesietny:
        s = s.replace('.', '').replace(',', '.')
    else:
        s = s.replace(',', '')
    try:
        return int((Decimal(s) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        raise ValueError(f'Nie umiem odczytać kwoty: {tekst!r}')


def zl(gr: int, waluta=True) -> str:
    """246000 -> '2 460,00 zł'. Grupowanie co 3 cyfry także dla tysięcy (brief, zasada 8)."""
    znak = '-' if gr < 0 else ''
    calosc, reszta = divmod(abs(int(gr)), 100)
    cyfry = f'{calosc:,}'.replace(',', ' ')
    return f'{znak}{cyfry},{reszta:02d}' + (' zł' if waluta else '')


def data_iso(wartosc) -> str | None:
    if wartosc in (None, ''):
        return None
    if isinstance(wartosc, datetime):
        return wartosc.date().isoformat()
    if isinstance(wartosc, date):
        return wartosc.isoformat()
    s = str(wartosc).strip()[:10]
    if re.fullmatch(r'\d{2}\.\d{2}\.\d{4}', s):
        d, m, r = s.split('.')
        s = f'{r}-{m}-{d}'
    date.fromisoformat(s)  # walidacja
    return s


def norm(s: str) -> str:
    """Małe litery, bez polskich znaków i interpunkcji: do porównywania nazw."""
    s = (s or '').replace('ł', 'l').replace('Ł', 'L')
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', s)).strip()
