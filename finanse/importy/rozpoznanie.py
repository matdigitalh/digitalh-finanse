"""Rozpoznanie źródła pliku przeciągniętego do okna: po zawartości (nagłówki kolumn, arkusze), nie po nazwie.

Rozpoznajemy to, co apka umie wczytać: historia operacji ING (CSV ze średnikiem), eksport faktur z Fakturowni (CSV
z przecinkiem), eksport płatności z Budget Studio (CSV z tabulatorem), rejestr zakupów z biura (xlsx z arkuszem
„krajowe”), wyniki z biura (xls z arkuszem „RZiS”). Wszystko inne dostaje ostrzeżenie z powodem i nie jest zapisywane.
Faktury z KSeF (XML) rozpoznajemy tylko po to, żeby powiedzieć, że ich import nie jest włączony.
"""
import csv
import io
import re
from datetime import date

from . import budget_studio, fakturownia, ing

ZNANE = ('historię operacji ING (CSV), eksport faktur z Fakturowni (CSV), eksport płatności z Budget Studio (CSV), '
         'rejestr zakupów z biura (Excel xlsx) i wyniki z biura (Excel xls)')
KSEF = ('To faktura z KSeF (XML). Import z KSeF nie jest włączony: koszty apka bierze z rejestru zakupów z biura, '
        'a sprzedaż z eksportu Fakturowni.')
WLASNY = ('To eksport płatności z tej apki (układ jak w Budget Studio). Apka nie wczytuje własnych eksportów jako danych '
          'z Budget Studio, bo nadpisałyby plany z BS. Przeciągnij plik pobrany z Budget Studio.')
SEPARATORY = {'ING': ';', 'Fakturownia': ',', 'Budget Studio': '\t'}
NAZWY_SEP = {';': 'średnik', ',': 'przecinek', '\t': 'tabulator'}


def _nie(powod: str) -> dict:
    return {'rodzaj': None, 'powod': powod}


def _tekst(tresc: bytes) -> str | None:
    try:
        return tresc.decode('utf-8-sig')
    except UnicodeDecodeError:
        return None


def _csv(tekst: str, nazwa: str) -> dict:
    pierwsza = tekst.splitlines()[0] if tekst.strip() else ''
    if not pierwsza:
        return _nie('Plik jest pusty.')
    sep = max((';', '\t', ','), key=pierwsza.count)
    naglowek = [h.strip() for h in next(csv.reader([pierwsza], delimiter=sep))]
    for rodzaj, wymagane in (('ING', ing.WYMAGANE), ('Fakturownia', fakturownia.WYMAGANE), ('Budget Studio', budget_studio.WYMAGANE)):
        if all(k in naglowek for k in wymagane):
            if sep != SEPARATORY[rodzaj]:
                return _nie(f'Kolumny jak w pliku {rodzaj}, ale separatorem jest {NAZWY_SEP[sep]} zamiast '
                            f'{NAZWY_SEP[SEPARATORY[rodzaj]]}. Pobierz plik jeszcze raz prosto ze źródła, bez otwierania w Excelu.')
            if rodzaj == 'Budget Studio' and (nazwa.lower().startswith('finanse') or _id_apki(tekst)):
                return _nie(WLASNY)
            return {'rodzaj': rodzaj}
    pierwsze = ', '.join(h for h in naglowek[:5] if h) or 'brak nagłówków'
    return _nie(f'Nieznany układ kolumn ({pierwsze}). Apka rozpoznaje {ZNANE}.')


def _id_apki(tekst: str) -> bool:
    """Płatność z ID nadanym w apce (plan:…, bs:…) zdradza eksport z tej apki, nie z Budget Studio."""
    for i, x in enumerate(csv.DictReader(io.StringIO(tekst), delimiter='\t')):
        if ':' in (x.get('ID') or ''):
            return True
        if i > 5000:
            break
    return False


def _xlsx(tresc: bytes) -> dict:
    import zipfile
    try:
        with zipfile.ZipFile(io.BytesIO(tresc)) as z:
            if 'xl/workbook.xml' not in z.namelist():
                return _nie('To archiwum ZIP, nie plik Excel. Rozpakuj je i przeciągnij sam plik eksportu.')
    except zipfile.BadZipFile:
        return _nie('Plik wygląda na Excel albo ZIP, ale jest uszkodzony.')
    import openpyxl
    try:
        wb = openpyxl.load_workbook(io.BytesIO(tresc), read_only=True, data_only=True)
    except Exception as e:
        return _nie(f'Nie da się otworzyć pliku Excel: {e}')
    try:
        if 'krajowe' in wb.sheetnames:
            pierwszy = next(wb['krajowe'].iter_rows(values_only=True, max_row=1), ())
            if 'Nr ewid.' in [str(c).strip() for c in pierwszy if c is not None]:
                return {'rodzaj': 'Rejestr zakupów'}
        if 'RZiS' in wb.sheetnames:
            return _nie('Wyniki z biura w formacie xlsx: apka czyta je z pliku xls, tak jak przysyła je biuro.')
        return _nie(f'Plik Excel bez arkusza „krajowe” z kolumną „Nr ewid.” (rejestr zakupów). Apka rozpoznaje {ZNANE}.')
    finally:
        wb.close()


OKRES = re.compile(r'(\d{2})\.(\d{2})\.(\d{4})\s*$')


def _xls(tresc: bytes) -> dict:
    import xlrd
    try:
        ks = xlrd.open_workbook(file_contents=tresc)
    except Exception as e:
        return _nie(f'Nie da się otworzyć pliku xls: {e}')
    if 'RZiS' not in ks.sheet_names():
        return _nie(f'Plik xls bez arkusza „RZiS” (wyniki z biura). Apka rozpoznaje {ZNANE}.')
    s = ks.sheet_by_name('RZiS')
    for r in range(min(s.nrows, 60)):
        for c in s.row_values(r):
            if isinstance(c, str) and c.startswith('Za okres') and (m := OKRES.search(c.strip())):
                return {'rodzaj': 'Wyniki biura', 'okres': f'{m.group(3)}-{m.group(2)}'}
    return _nie('Arkusz RZiS bez nagłówka „Za okres …”, więc nie wiadomo, którego miesiąca dotyczą wyniki.')


def rozpoznaj(tresc: bytes, nazwa: str = '') -> dict:
    """{'rodzaj': 'ING' | 'Fakturownia' | 'Budget Studio' | 'Rejestr zakupów' | 'Wyniki biura', 'okres'?: 'RRRR-MM'}
    albo {'rodzaj': None, 'powod': ostrzeżenie dla Mata}."""
    if not tresc:
        return _nie('Plik jest pusty.')
    poczatek = tresc[:8]
    if poczatek.startswith(b'%PDF'):
        return _nie('To PDF. Apka nie czyta PDF-ów (wyciągów, faktur, raportów). Przeciągnij eksport CSV albo plik Excel.')
    if poczatek.startswith(b'PK\x03\x04'):
        return _xlsx(tresc)
    if poczatek.startswith(b'\xd0\xcf\x11\xe0'):
        return _xls(tresc)
    tekst = _tekst(tresc)
    if tekst is None:
        return _nie('Plik nie jest tekstem w UTF-8 ani plikiem Excel. Pobierz eksport jeszcze raz (CSV w UTF-8).')
    if tekst.lstrip().startswith('<'):
        glowa = tekst[:20000]
        if '<Faktura' in glowa or 'crd.gov.pl/wzor' in glowa or 'ksef' in glowa.lower():
            return _nie(KSEF)
        return _nie(f'To plik XML albo HTML. Apka rozpoznaje {ZNANE}.')
    return _csv(tekst, nazwa)


def nazwa_docelowa(rodzaj: str, wzorzec: str, rekordy: dict, okres: str | None = None, dzis: date | None = None) -> str:
    """Nazwa w Dane/ wg konwencji źródło_rodzaj_data: ING od i do (daty operacji), rejestr od i do (miesiące dokumentów),
    wyniki okres, Fakturownia i Budget Studio dzień pobrania (każdy plik to stan na ten dzień)."""
    dzis = (dzis or date.today()).isoformat()
    prefiks, rozsz = wzorzec.split('/', 1)[1].split('*')
    if rodzaj == 'ING':
        daty = sorted(r.pola['data_ksiegowania'] for r in rekordy.values() if r.pola.get('data_ksiegowania'))
        czesc = f'{daty[0]}_{daty[-1]}' if daty else dzis
    elif rodzaj == 'Rejestr zakupów':
        daty = sorted(r.pola['data'] for r in rekordy.values() if r.pola.get('data'))
        czesc = f'{daty[0][:7]}_{daty[-1][:7]}' if daty else dzis[:7]
    elif rodzaj == 'Wyniki biura':
        czesc = okres or dzis[:7]
    else:
        czesc = dzis
    return f'{prefiks}{czesc}{rozsz}'
