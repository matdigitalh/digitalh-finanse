"""Zmyślone dane testowe w katalogu tymczasowym. Żadna liczba nie pochodzi z prawdziwych plików."""
import csv
import os
import tempfile
from pathlib import Path

NAGLOWEK_ING = ['data transakcji', 'data księgowania', 'kwota', 'waluta operacji', 'oryginalna kwota transakcji',
                'oryginalna waluta transakcji', 'saldo po transakcji', 'nazwa i adres kontrahenta', 'rachunek kontrahenta',
                'nazwa transakcji i opis', 'szczegóły płatności linia 1', 'szczegóły płatności linia 2',
                'szczegóły płatności linia 3', 'szczegóły płatności linia 4', 'rachunek ING "NRB" (26 znaków)',
                'numer referencyjny']
GLOWNY, ONLINE, VAT = '11105000000000000000005263', '11105000000000000000005271', '11105000000000000000005289'


def operacja(data, kwota, saldo, kontrahent, tytul, rachunek=GLOWNY, ref='', opis='Przelew'):
    return [data, data, kwota, 'PLN', '', '', saldo, kontrahent, '', opis, tytul, '', '', '', rachunek, ref]


def zapisz_ing(katalog: Path, nazwa: str, wiersze):
    p = katalog / 'ING' / nazwa
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f, delimiter=';', quoting=csv.QUOTE_ALL)
        w.writerow(NAGLOWEK_ING)
        w.writerows(wiersze)
    return p


NAGLOWEK_FAKTUROWNIA = (['LP', 'numer', 'Typ', 'Sprzedający', 'Nazwa skrócona działu', 'NIP sprzedającego', 'Status',
    'Data wystawienia', 'Data sprzedaży', 'Termin płatności', 'Nabywca', 'NIP', 'Ulica i nr', 'Kod pocztowy', 'Miejscowość',
    'Kraj', 'E-mail klienta', 'Telefon klienta', 'Telefon komórkowy', 'Dodatkowi odbiorcy', 'Dodatkowi wystawcy',
    'Wartość netto', 'VAT', 'Wartość brutto', 'Wartość netto PLN', 'VAT PLN', 'Wartość brutto PLN', 'Płatność',
    'Data płatności', 'Kwota opłacona', 'Waluta', 'Nr zamówienia', 'Adresat', 'Kategoria', 'Kody GTU',
    'Oznaczenia dotyczące procedur', 'Dodatkowe pole na pozycjach faktury', 'Oryginalny dokument', 'Przyczyna korekty',
    'Numer KSeF', 'Status KSeF', 'Data wystawienia w KSeF', 'Data wysyłki do KSeF', 'Rodzaj marży',
    'Numery powiązanych faktur (Zamówienia i Zaliczki)', 'Produkt/usługa', 'Ilość', 'Cena netto', 'Cena brutto',
    'Stawka VAT', 'Wartość VAT', 'Wartość netto', 'Wartość brutto', 'Kod GTU', 'rodzaj pozycji', 'Jednostka',
    'Wartość dodatkowego pola na pozycjach faktury', 'Numer pozycji faktury', 'Rodzaj informacji', 'Treść informacji'])


def faktura(lp, numer, status, wyst, termin, nabywca, nip, pozycje, oplacono='0.0', ksef='', oryginal=''):
    """pozycje: lista (nazwa, netto). VAT 23%."""
    netto = sum(n for _, n in pozycje)
    vat = round(netto * 0.23, 2)
    w = [''] * 45
    w[0], w[1], w[2], w[6], w[7], w[8], w[9], w[10], w[11] = str(lp), numer, 'DigitalH_faktura', status, wyst, wyst, termin, nabywca, nip
    w[24], w[25], w[26], w[29], w[30], w[37], w[39] = str(netto), str(vat), str(round(netto + vat, 2)), oplacono, 'PLN', oryginal, ksef
    for nazwa, n in pozycje:
        v = round(n * 0.23, 2)
        w += [nazwa, '1.0', str(n), str(n + v), '23', str(v), str(n), str(round(n + v, 2)), 'GTU_12', '', 'szt', '']
    return w


def uwaga(lp, numer, tresc):
    w = [''] * 60
    w[0], w[1], w[58], w[59] = str(lp), numer, 'Uwaga', tresc
    return w


def zapisz_fakturownie(katalog: Path, nazwa: str, wiersze):
    p = katalog / 'Fakturownia' / nazwa
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(NAGLOWEK_FAKTUROWNIA)
        w.writerows(wiersze)
    return p


def zapisz_rejestr(katalog: Path, nazwa: str, krajowe, zagraniczne):
    import openpyxl
    p = katalog / 'Biuro' / nazwa
    p.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'krajowe'
    ws.append(['Nr ewid.', 'Nr dok.', 'Data', 'Data zaewid.', 'Podmiot', '8% Netto', '8% VAT', '23% Netto', '23% VAT', 'Brutto'])
    for r in krajowe:
        ws.append(r)
    ws.append([None] * 10)
    ws.append([None, None, None, None, None, 'Suma', 'Suma', 'Suma', 'Suma', 'Suma'])
    z = wb.create_sheet('zagraniczne')
    z.append(['Nr ewid.', 'Nr dok.', 'Data', 'Data zaewid.', 'Podmiot', 'Netto'])
    for r in zagraniczne:
        z.append(r)
    wb.save(p)
    return p


class Srodowisko:
    """Tymczasowy folder Finanse i baza; ustawia zmienne środowiskowe i sprząta po sobie."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.katalog = Path(self._tmp.name)
        self.dane = self.katalog / 'Finanse' / 'Raporty' / 'Dane'
        self.dane.mkdir(parents=True)
        self._stare = {k: os.environ.get(k) for k in ('FINANSE_KATALOG', 'FINANSE_BAZA', 'FINANSE_MAC')}
        os.environ['FINANSE_KATALOG'] = str(self.katalog / 'Finanse')
        os.environ['FINANSE_BAZA'] = str(self.katalog / 'lokalnie' / 'finanse.sqlite')
        os.environ['FINANSE_MAC'] = 'Mac-testowy'
        return self

    def __exit__(self, *a):
        for k, v in self._stare.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmp.cleanup()
