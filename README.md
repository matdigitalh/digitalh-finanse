# Finanse lokalne (warstwa CFO DigitalH)

Lokalna aplikacja finansowa: z plików z banku, Fakturowni i biura sama liczy to, czego Budget Studio
nie robi albo robi źle. Zlecenie i kryteria odbioru: [BRIEF.md](BRIEF.md). Układ ekranów jak w Budget
Studio, kolory DigitalH.

## Uruchomienie

Dwuklik `start.command` (albo `./start.command` w terminalu). Pierwsze uruchomienie zakłada `.venv`
z `openpyxl` i `xlrd`. Apka otwiera się pod `http://127.0.0.1:8765/`; zamknięcie okna terminala ją wyłącza.

## Gdzie co leży

| Co | Gdzie |
|---|---|
| Kod, testy na zmyślonych danych | to repo |
| Surowe pliki (tylko odczyt) | `~/Documents/DigitalH/Finanse/Raporty/Dane/` (iCloud) |
| Wpisy Mata (reguły, umowy, zatwierdzenia), od etapu 2 | `~/Documents/DigitalH/Finanse/Aplikacja/zmiany/<nazwa-Maca>.jsonl` (iCloud) |
| Baza SQLite (cache, odbudowywana z plików) | `~/Library/Application Support/DigitalH-Finanse/finanse.sqlite` (lokalnie) |

Baza nie jest źródłem prawdy: przy starcie i po kliknięciu „Wczytaj pliki na nowo” powstaje od zera
z plików w `Dane/` i `zmiany/`. Dzięki temu apka działa na dwóch Macach bez konfliktów iCloud:
każdy Mac ma własną bazę i pisze tylko do własnego pliku zmian.

## Zasady (skrót z briefu)

- Dane nigdy w repo: `.gitignore` + hook `narzedzia/pre-commit` (instalacja raz na maszynę:
  `cp narzedzia/pre-commit .git/hooks/pre-commit`) + test `testy/test_repo.py`.
- Serwer tylko na `127.0.0.1`, obcy nagłówek `Host` odrzucany, zapis tylko POST z nagłówkiem `X-Finanse`,
  CSP bez zewnętrznych zasobów. Zero ruchu sieciowego w MVP.
- Kwoty liczone w groszach (int), każda pozycja ma źródło (plik, wiersz).

## Testy

```bash
.venv/bin/python -m unittest discover -s testy -t .        # zmyślone dane
.venv/bin/python -m unittest testy_odbioru.test_etap1      # prawdziwe pliki, baza w katalogu tymczasowym
```

## Formaty plików (sprawdzone 14.10.2026, różnice wobec briefu)

- **ING:** numer referencyjny nie jest unikalny. Podzielona płatność ma ten sam numer na rachunku
  głównym i VAT, więc klucz operacji to numer + rachunek.
- **Fakturownia:** jeden wiersz to faktura, nie pozycja. Pozycje są w blokach po 12 kolumn od kolumny 45;
  wiersze z pustym „Typ” to uwagi do faktury.
- **Wyniki biura:** podpozycje „w tym” mają puste kody i bywają identyczne, klucz to numer wiersza.

## Etapy

| Etap | Zakres | Stan |
|---|---|---|
| 1 | Import, księga operacji, rama UI, Płatności, Historia importów | gotowy 2026-10-14 |
| 2 | Dopasowanie wpłat do faktur, należności z wiekowaniem, Do połączenia / Do weryfikacji | |
| 3 | Mapa klientów, wydatki ↔ rejestr zakupów, ekran Budżet | |
| 4 | Wynik zarządczy, ekran Rentowność | |
| 5 | Prognoza gotówki 13 tyg., rejestr umów, ekran Cash flow | |
| 6 | Pulpit jak w Budget Studio, eksport | |
