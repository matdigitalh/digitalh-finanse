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
"""


def polacz(sciezka: Path, tylko_odczyt=False) -> sqlite3.Connection:
    if tylko_odczyt:
        con = sqlite3.connect(f'file:{sciezka}?mode=ro', uri=True, check_same_thread=False)
    else:
        con = sqlite3.connect(sciezka, check_same_thread=False)
        con.execute('PRAGMA journal_mode=DELETE')
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
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
