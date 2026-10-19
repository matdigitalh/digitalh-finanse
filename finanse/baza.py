"""Schemat SQLite. Baza jest cache'em: zawsze da się ją odbudować z plików (odbudowa.py)."""
import os
import sqlite3
from pathlib import Path

SCHEMAT = """
CREATE TABLE meta (klucz TEXT PRIMARY KEY, wartosc TEXT);

CREATE TABLE import_log (
  id INTEGER PRIMARY KEY, rodzaj TEXT NOT NULL, plik TEXT NOT NULL, sha256 TEXT NOT NULL,
  zmodyfikowany TEXT, wierszy INTEGER, nowych INTEGER, pominietych INTEGER, uwagi TEXT, czas TEXT NOT NULL
);

-- Operacje z banku ING. Klucz: numer referencyjny + rachunek (podzielona płatność ma ten sam
-- numer na rachunku głównym i VAT), gdy numer pusty: data + kwota + tytuł + rachunek.
CREATE TABLE operacje (
  id INTEGER PRIMARY KEY, klucz TEXT NOT NULL UNIQUE, rachunek TEXT NOT NULL, nrb TEXT,
  data_transakcji TEXT, data_ksiegowania TEXT NOT NULL, kwota INTEGER NOT NULL, waluta TEXT,
  kwota_oryg INTEGER, waluta_oryg TEXT, saldo_po INTEGER, kontrahent TEXT, rachunek_kontrahenta TEXT,
  opis TEXT, tytul TEXT, nr_ref TEXT, wewnetrzna INTEGER NOT NULL DEFAULT 0,
  plik TEXT NOT NULL, wiersz INTEGER NOT NULL, data_pliku TEXT NOT NULL
);
CREATE INDEX operacje_data ON operacje(data_ksiegowania);

CREATE TABLE faktury (
  numer TEXT PRIMARY KEY, typ TEXT, status TEXT, data_wystawienia TEXT, data_sprzedazy TEXT,
  termin TEXT, nabywca TEXT, nip TEXT, netto INTEGER, vat INTEGER, brutto INTEGER, oplacono INTEGER,
  waluta TEXT, ksef TEXT, korekta INTEGER NOT NULL DEFAULT 0, oryginal TEXT, przyczyna_korekty TEXT,
  uwagi TEXT, plik TEXT NOT NULL, wiersz INTEGER NOT NULL
);

CREATE TABLE faktury_pozycje (
  numer TEXT NOT NULL, lp INTEGER NOT NULL, nazwa TEXT, ilosc TEXT, stawka TEXT,
  netto INTEGER, vat INTEGER, brutto INTEGER, plik TEXT NOT NULL, wiersz INTEGER NOT NULL,
  PRIMARY KEY (numer, lp)
);

CREATE TABLE zakupy (
  nr_ewid TEXT PRIMARY KEY, nr_dok TEXT, data TEXT, data_zaewid TEXT, podmiot TEXT, podmiot_kod TEXT,
  rejestr TEXT NOT NULL, netto INTEGER, vat INTEGER, brutto INTEGER, plik TEXT NOT NULL, wiersz INTEGER NOT NULL
);

CREATE TABLE wyniki_biura (
  okres TEXT NOT NULL, zestawienie TEXT NOT NULL, kod TEXT NOT NULL, opis TEXT, wartosc INTEGER,
  wartosc_poprzednia INTEGER, plik TEXT NOT NULL, wiersz INTEGER NOT NULL,
  PRIMARY KEY (okres, zestawienie, wiersz)
);

-- Etap 2: liczone przy odbudowie (dopasowanie.py), nie importowane.
CREATE TABLE dopasowania (
  operacja_id INTEGER NOT NULL REFERENCES operacje(id), numer TEXT NOT NULL REFERENCES faktury(numer),
  kwota INTEGER NOT NULL, metoda TEXT NOT NULL, pewnosc TEXT NOT NULL, zrodlo TEXT NOT NULL
);
CREATE INDEX dopasowania_op ON dopasowania(operacja_id);
CREATE INDEX dopasowania_fv ON dopasowania(numer);

-- Każda wpłata od klienta (wpływ, nie ruch wewnętrzny): stan dopasowania.
CREATE TABLE wplaty (
  operacja_id INTEGER PRIMARY KEY REFERENCES operacje(id), stan TEXT NOT NULL, pewnosc TEXT,
  nadplata INTEGER NOT NULL DEFAULT 0, uwaga TEXT, podpowiedz TEXT, wpis TEXT
);

-- Każda faktura (bez korekt): należność po korektach, zapłacono z banku, wiekowanie na dzień stanu.
CREATE TABLE faktury_stan (
  numer TEXT PRIMARY KEY REFERENCES faktury(numer), naleznosc INTEGER, korekty INTEGER, zaplacono INTEGER,
  pozostalo INTEGER, stan TEXT, dni_po_terminie INTEGER, przedzial TEXT, ostatnia_wplata TEXT, uwaga TEXT, wpis TEXT
);

CREATE TABLE dokumenty (plik TEXT, folder TEXT, wystawca TEXT, numer TEXT, kwota INTEGER, waluta TEXT, data TEXT, tag TEXT, konto TEXT);
CREATE TABLE konta_reklamowe (konto TEXT PRIMARY KEY, platnosci INTEGER, suma INTEGER, ostatnia TEXT, klient TEXT,
  podpowiedz TEXT, klient_podpowiedz TEXT, wpis TEXT);
CREATE TABLE korekty_reczne (numer TEXT PRIMARY KEY, faktura TEXT NOT NULL, brutto INTEGER, netto INTEGER, wpis TEXT);
CREATE TABLE zwroty_zakupow (wplata_id INTEGER NOT NULL, wydatek_id INTEGER NOT NULL);

-- Budget Studio (najnowszy eksport): wyłącznie podpowiedzi klientów i kategorii kosztów.
CREATE TABLE bs (
  id TEXT, rodzaj INTEGER, status TEXT, numer TEXT, kontrahent TEXT, netto INTEGER, brutto INTEGER, miesiac TEXT,
  arkusz TEXT, folder TEXT, kategoria TEXT, dzien TEXT, plik TEXT NOT NULL, wiersz INTEGER NOT NULL
);

-- Etap 3: liczone przy odbudowie (klienci.py).
CREATE TABLE faktury_klient (numer TEXT PRIMARY KEY REFERENCES faktury(numer), klient TEXT NOT NULL, zrodlo TEXT, wpis TEXT);

CREATE TABLE wydatki (
  operacja_id INTEGER PRIMARY KEY REFERENCES operacje(id), kontrahent_klucz TEXT, rodzaj TEXT NOT NULL, klient TEXT,
  zrodlo TEXT, wpis TEXT, dokument TEXT, netto_dok INTEGER, konto TEXT
);
CREATE TABLE wydatki_dok (operacja_id INTEGER NOT NULL, nr_ewid TEXT NOT NULL, metoda TEXT);
CREATE INDEX wydatki_dok_op ON wydatki_dok(operacja_id);
CREATE TABLE reguly (typ TEXT, klucz TEXT, wartosc TEXT, wpis TEXT);

-- Budżet (budzet.py): import z Budget Studio + zdarzenia Mata.
CREATE TABLE bud_arkusz (id TEXT PRIMARY KEY, folder TEXT, kategoria TEXT, nazwa TEXT, od TEXT, do TEXT, zrodlo TEXT);
CREATE TABLE bud_wiersz (id TEXT PRIMARY KEY, arkusz TEXT, rodzaj INTEGER, podstawa TEXT, kontrahent TEXT, komentarz TEXT,
  przedmiot TEXT, sekcja TEXT, stawka_vat TEXT, dzien_wystawienia TEXT, dni_na_platnosc TEXT, metoda TEXT, ksiegowane INTEGER,
  w_cashflow INTEGER, cykl TEXT, plan TEXT, zrodlo TEXT, split INTEGER, proporcje TEXT, kup INTEGER);
CREATE INDEX bud_wiersz_ark ON bud_wiersz(arkusz);
CREATE TABLE bud_platnosc (id TEXT PRIMARY KEY, bs_id TEXT, wiersz TEXT, miesiac TEXT, typ TEXT, etap_bs TEXT, aktualna INTEGER,
  netto INTEGER, vat INTEGER, brutto INTEGER, stawka INTEGER, rodzaj INTEGER, nr_dok TEXT, nr_wewn TEXT, tytul TEXT, wystawienie TEXT, termin TEXT,
  realny TEXT, ksiegowanie TEXT, metoda TEXT, w_cashflow INTEGER, komentarz TEXT, decyzja TEXT, zrodlo TEXT, wiersz_pliku INTEGER,
  kontrahent TEXT, ksiegowane INTEGER, skladowa TEXT, spinacz TEXT, generowany INTEGER, nadpisane TEXT, ukryty INTEGER);
CREATE INDEX bud_platnosc_w ON bud_platnosc(wiersz);
-- Kwoty komórek (wiersz × miesiąc) wpisane w apce; plany z nich są pochodną (pakiet 2).
CREATE TABLE bud_komorka (wiersz TEXT, miesiac TEXT, kwota INTEGER, PRIMARY KEY (wiersz, miesiac));
CREATE TABLE bud_historia (wpis TEXT, czas TEXT, mac TEXT, op TEXT, obiekt TEXT, bylo TEXT, jest TEXT);
-- Zdarzenia budżetu, które nie mają do czego się odnieść (np. płatności nie ma już w eksporcie BS): pokazywane, nie gubione.
CREATE TABLE bud_osierocone (wpis TEXT, czas TEXT, mac TEXT, op TEXT, obiekt TEXT, powod TEXT);
-- Łączenie plan ↔ faktura / dokument ↔ bank (laczenie.py) i etap wynikający z banku.
CREATE TABLE bud_powiazanie (platnosc TEXT, typ TEXT, ref TEXT, kwota INTEGER, metoda TEXT, pewnosc TEXT);
CREATE INDEX bud_powiazanie_p ON bud_powiazanie(platnosc);
CREATE TABLE umowy (id TEXT PRIMARY KEY, dane TEXT);
CREATE TABLE bud_rozjazd (rodzaj TEXT, ref TEXT, kwota INTEGER, opis TEXT);
-- etap: nasz (z banku i Fakturowni); etap_wg_bs i aktualnosc: reguły BS (B-MOD-08 do 10) na dzień stanu.
CREATE TABLE bud_stan (platnosc TEXT PRIMARY KEY, etap TEXT, zaplacono INTEGER, data_zaplaty TEXT, termin_efektywny TEXT, uwaga TEXT,
  etap_wg_bs TEXT, aktualnosc TEXT);
CREATE TABLE zakupy_stan (nr_ewid TEXT PRIMARY KEY REFERENCES zakupy(nr_ewid), stan TEXT, operacja_id INTEGER);

-- Pakiet 7 (widoki.py): zapisane widoki list (zdarzenie „widok”) i pozycje oznaczone do sprawdzenia („do_weryfikacji”).
CREATE TABLE widoki (ekran TEXT NOT NULL, id TEXT NOT NULL, nazwa TEXT, parametry TEXT, kolumny TEXT, usuniety INTEGER NOT NULL DEFAULT 0,
  wpis TEXT, czas TEXT, PRIMARY KEY (ekran, id));
CREATE TABLE oznaczone (obiekt TEXT NOT NULL, ref TEXT NOT NULL, powod TEXT, wpis TEXT, czas TEXT, PRIMARY KEY (obiekt, ref));
"""


def polacz(sciezka: Path, tylko_odczyt=False) -> sqlite3.Connection:
    if tylko_odczyt:
        con = sqlite3.connect(f'file:{sciezka}?mode=ro', uri=True, check_same_thread=False)
    else:
        con = sqlite3.connect(sciezka, check_same_thread=False)
        con.execute('PRAGMA journal_mode=DELETE')
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    from .filtry import porownaj_pl
    con.create_collation('PL', porownaj_pl)   # sortowanie tekstu na listach po polsku (pakiet 7)
    return con


def nowa(sciezka: Path) -> sqlite3.Connection:
    """Pusta baza z aktualnym schematem, plik z uprawnieniami 600."""
    if sciezka.exists():
        sciezka.unlink()
    fd = os.open(sciezka, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(fd)
    con = polacz(sciezka)
    con.executescript(SCHEMAT)
    return con
