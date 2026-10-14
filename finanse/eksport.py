"""Etap H: eksport do Excela (arkusz budżetu, cash flow, rentowność). Plik powstaje w pamięci i idzie prosto
do przeglądarki; nic nie zapisujemy na dysku poza tym, co Mat sam pobierze."""
import io

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from . import cashflow, rentownosc, zapytania_budzet

NAGLOWEK = Font(bold=True, color='FFFFFF')
TLO = PatternFill('solid', fgColor='171FB5')
ZL = '#,##0.00 "zł";[Red]-#,##0.00 "zł"'


def _arkusz_xls(ws, naglowki, wiersze, kolumny_kwot=()):
    ws.append(naglowki)
    for c in ws[1]:
        c.font, c.fill = NAGLOWEK, TLO
    for w in wiersze:
        ws.append(w)
    for i in kolumny_kwot:
        for c in ws.iter_rows(min_row=2, min_col=i, max_col=i):
            c[0].number_format = ZL
    for i, n in enumerate(naglowki, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, min(45, len(str(n)) + 4))
    ws.freeze_panes = 'B2'


def _zapisz(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def arkusz(con, aid: str) -> tuple[str, bytes]:
    d = zapytania_budzet.arkusz(con, aid)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Arkusz'
    m = d['miesiace']
    wiersze = [[w['kontrahent'], w['komentarz'], w['podstawa'], 'wpływy' if w['rodzaj'] == 1 else 'obciążenia',
                *[(w['komorki'][x]['netto'] / 100 if x in w['komorki'] else None) for x in m]] for w in d['wiersze']]
    wiersze.append(['Saldo', '', '', '', *[p['saldo'] / 100 for p in d['podsumowanie']]])
    wiersze.append(['Narastająco', '', '', '', *[p['narastajaco'] / 100 for p in d['podsumowanie']]])
    _arkusz_xls(ws, ['Kontrahent', 'Komentarz', 'Podstawa', 'Rodzaj', *m], wiersze, range(5, 5 + len(m)))
    return f"{d['arkusz']['nazwa']}.xlsx", _zapisz(wb)


def cash_flow(con) -> tuple[str, bytes]:
    d = cashflow.prognoza(con)
    wb = Workbook()
    ws = wb.active
    ws.title = '13 tygodni'
    _arkusz_xls(ws, ['Od', 'Do', 'Wpływy', 'Wydatki', 'Tylko w scenariuszu pełnym', 'Saldo ostrożne', 'Saldo pełne'],
                [[t['od'], t['do'], t['wplywy'] / 100, t['wydatki'] / 100, t['tylko_pelny'] / 100, t['saldo_ostrozny'] / 100,
                  t['saldo_pelny'] / 100] for t in d['tygodnie']], range(3, 8))
    ws2 = wb.create_sheet('Pozycje')
    _arkusz_xls(ws2, ['Data', 'Kwota', 'Opis', 'Rodzaj', 'Scenariusz'],
                [[p['data'], p['kwota'] / 100, p['opis'], p['rodzaj'], p['scenariusz']] for t in d['tygodnie'] for p in t['pozycje']], [2])
    ws3 = wb.create_sheet('Dziennie')
    _arkusz_xls(ws3, ['Data', 'Saldo ostrożne', 'Saldo pełne'], [[x['data'], x['ostrozny'] / 100, x['pelny'] / 100] for x in d['dni']], [2, 3])
    return f"cash flow {d['dzien_stanu']}.xlsx", _zapisz(wb)


def rentownosc_xls(con, rok=None) -> tuple[str, bytes]:
    k = rentownosc.klienci(con, rok)
    wb = Workbook()
    ws = wb.active
    ws.title = 'Klienci'
    _arkusz_xls(ws, ['Klient', 'Obrót netto', 'Koszty klienta', 'Po kosztach klienta', 'Marża %', 'Udział czasu %', 'Koszt pracy', 'Wynik klienta'],
                [[x['klient'], x['obrot'] / 100, x['koszty'] / 100, x['pna'] / 100, x['marza_proc'], x['udzial_czasu'],
                  None if x['koszt_pracy'] is None else x['koszt_pracy'] / 100,
                  None if x['wynik_klienta'] is None else x['wynik_klienta'] / 100] for x in k['klienci']], [2, 3, 4, 7, 8])
    ws2 = wb.create_sheet('Arkusze')
    _arkusz_xls(ws2, ['Folder', 'Arkusz', 'Plan przychód', 'Plan koszt', 'Wykonanie przychód', 'Wykonanie koszt', 'Realizacja %'],
                [[x['folder'], x['nazwa'], x['plan_przychod'] / 100, x['plan_koszt'] / 100, x['wyk_przychod'] / 100,
                  x['wyk_koszt'] / 100, x['realizacja_proc']] for x in rentownosc.arkusze(con)], range(3, 7))
    return f"rentownosc {k['rok']}.xlsx", _zapisz(wb)
