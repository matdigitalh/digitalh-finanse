# Finanse lokalne (warstwa CFO DigitalH)

Lokalna aplikacja finansowa: z plików z banku, Fakturowni i biura sama liczy to, czego Budget Studio
nie robi albo robi źle. Zlecenie i kryteria odbioru: [BRIEF.md](BRIEF.md). Układ ekranów jak w Budget
Studio, kolory DigitalH.

## Uruchomienie

Dwuklik `start.command` (albo `./start.command` w terminalu). Pierwsze uruchomienie zakłada `.venv`
z `openpyxl` i `xlrd`. Apka otwiera się pod `http://127.0.0.1:8765/`; zamknięcie okna terminala ją wyłącza.

**Skrót w Aplikacjach** (raz na Macu): `./narzedzia/zrob-skrot.sh` zakłada „Finanse DigitalH” w `~/Applications`
(Launchpad, Spotlight). Klik uruchamia apkę w tle i otwiera przeglądarkę; gdy już działa, tylko otwiera stronę.
Apka w tle działa do wylogowania lub restartu Maca. Wyłączenie ręczne: `pkill -f finanse.serwer`.
Log: `~/Library/Logs/DigitalH-Finanse.log`.

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
.venv/bin/python -m unittest testy_odbioru.test_etap1 testy_odbioru.test_etap2 testy_odbioru.test_etap3 testy_odbioru.test_etap4 testy_odbioru.test_budzet   # prawdziwe pliki, baza w katalogu tymczasowym
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
| 2 | Dopasowanie wpłat do faktur, należności z wiekowaniem, Do połączenia / Do weryfikacji | gotowy 2026-10-14 |
| 3 | Mapa klientów, wydatki ↔ rejestr zakupów, ekran Budżet | gotowy 2026-10-14 |
| 4 | Wynik zarządczy, ekran Rentowność | gotowy 2026-10-14 |
| 5 | Prognoza gotówki 13 tyg., rejestr umów z alertami (`finanse/umowy.py`), ekran Cash flow | gotowy 2026-10-15 |
| 6 | Pulpit jak w Budget Studio, eksport | |

## Dopasowanie wpłat (etap 2)

Liczone od zera przy każdej odbudowie (`finanse/dopasowanie.py`), w kolejności od najpewniejszej metody:
ręczne połączenie, numer faktury w tytule, numer KSeF (bez NIP-u i sumy kontrolnej, bo klienci podają kolejne
numery w skrócie), reszta wpłaty równa innej fakturze nabywcy, kwota + nazwa, suma 2–6 faktur nabywcy, kwota + data.
Dwie pierwsze metody to „pewne”, reszta „prawdopodobne” i czeka na potwierdzenie w „Do weryfikacji”.
Numer cudzej, już opłaconej faktury w tytule jest traktowany jako pomyłka klienta. Korekty pomniejszają
należność faktury pierwotnej. Wiekowanie liczone na ostatni dzień w eksporcie ING, nie na dziś.

Decyzje Mata (`polacz`, `bez_faktury`, `zatwierdz`, `odrzuc`, `poza_bankiem`, `cofnij`) idą do pliku zmian tego
Maca. Zmiana kodu dopasowania albo układu bazy sama wymusza przebudowę bazy przy starcie.

## Klienci i koszty (etap 3)

`finanse/klienci.py`. Klient faktury: decyzja Mata (faktura, potem nabywca), folder z Budget Studio po numerze
faktury, ten sam nabywca, nazwa nabywcy. Jeden nabywca może płacić za kilku klientów, więc przypisanie idzie
faktura po fakturze. Rodzaj wydatku (koszt klienta, stały, praca, podatki, VAT, podział zysku, zwrot): decyzja Mata,
reguła Mata dla kontrahenta, reguły wbudowane (ZUS, urząd skarbowy, wynagrodzenia, zwrot nadpłaty, opłaty ING),
Budget Studio. Budget Studio łączymy z bankiem po kwocie i dacie, nie po nazwie (nazwy są zapisane różnie),
i tylko jako podpowiedź; plik jest opcjonalny.

Wydatek a rejestr zakupów biura: numer dokumentu w tytule, numer KSeF (data faktury i kwota), kwota i nazwa,
kwota po kursie (zagraniczne, tolerancja 6%), suma dokumentów dostawcy, faktura miesięczna = suma płatności kartą
w miesiącu (Google Ads, narzędzia). Koszt klienta w Budżecie to netto z dokumentu, bez dokumentu kwota z banku.
Atrybuty `style` w HTML blokuje CSP, wymiary ustawiamy ze skryptu.

## Wynik zarządczy (etap 4)

`finanse/wynik.py`, liczone przy zapytaniu. Obrót netto (faktury wg daty sprzedaży) minus koszty klientów = przychód
netto agencji; minus koszty pracy, stałe i nieprzypisane = wynik zarządczy. VAT, podział zysku, zwroty dla klientów
i podatki (CIT, opłaty) poza wynikiem. Koszt z dokumentem: netto i miesiąc dokumentu (także podwykonawca na fakturze);
koszty pracy: miesiąc z tytułu przelewu („ZA 07.2026”, „DRA 01/07”, „OKR/26M07”, „PPK 2026 07”), bez okresu: do 25.
dnia poprzedni miesiąc. Miesiąc stanu i poprzedni oznaczone jako niepełne. Cele roczne w
`Finanse/Aplikacja/ustawienia.json` (poza repo). Kontrola z RZiS biura na ostatni okres z pliku wyników.

## Pulpit kontrolingowy i pomoc

`finanse/controlling.py`. Cztery kafle ze statusem (dobrze, uwaga, źle; kolor + znak + opis): rezerwa gotówki
(gotówka kontra średni miesięczny wypływ na koszty z 6 pełnych miesięcy, bez VAT, podziału zysku i zwrotów; druga
miara bez kosztów klientów), obrót do celu (plan liniowy i prognoza ze średniej pełnych miesięcy), marża zysku
(pełne miesiące), należności po 30 dniach. Cele: domyślne w `Finanse/Aplikacja/ustawienia.json`, zmiany z przycisku
Cele jako wpis `cel` w pliku zmian. Pomoc: przycisk „?” przy kaflach i wykresach (dymek po najechaniu, panel po
kliknięciu) i „Pomoc” w menu; treści w `POMOC` w `web/app.js`. Wykresy: `web/wykresy.js`.

## Budżet jak w Budget Studio (zadanie nocne 14/15.10)

Folder → kategoria → arkusz → wiersz → płatność (`finanse/budzet.py`). Źródła: plik importu
`Finanse/Aplikacja/import_bs.json` generowany deterministycznie z najnowszego eksportu BS (+ lista arkuszy z zakresami
`Finanse/Aplikacja/arkusze_bs.json` ze zwiadu, bo eksport ich nie ma), zapis tylko przy zmianie treści; na to zdarzenia
`bud` z pliku zmian (plany Mata). ID płatności z BS zachowane (`bs:<ID>:<wiersz>`; to samo ID dla części wynagrodzenia).
Edycja w apce wyłączona do włączenia przez Mata (Budżet, Ustawienia; serwer odrzuca zmiany w trybie podglądu).

Łączenie (`finanse/laczenie.py`): przychód ↔ faktura (numer, potem klient + kwota netto + miesiąc ±1), koszt ↔ dokument
z rejestru ↔ bank albo wprost bank (kwota brutto, ±5 dni karta, ±3 przelew); koszty pracy, VAT, podatek dochodowy sumą
w miesiącu płatności. Etap „Opłacona” tylko z banku; plan po terminie zostaje „Po terminie” do decyzji Mata
(przesuń, zapłacone, anuluj). Rozjazdy BS ↔ bank ↔ Fakturownia w `bud_rozjazd`.

Cash flow (`finanse/cashflow.py`): 13 tygodni i dziennie, saldo z ING, należności z terminem + średnie spóźnienie
nabywcy, plany bez faktury; scenariusz ostrożny i pełny; szacunek kosztów pracy i stałych w miesiącach bez planu.
Rentowność (`finanse/rentownosc.py`): klient z kosztem pracy z estymaty udziału czasu (wpis `estymata`), arkusz plan
kontra wykonanie. Eksport Excel (`finanse/eksport.py`): arkusz, cash flow, rentowność, generowany w pamięci.

## Pakiet 1: naprawa błędów psujących dane (2026-10-19)

- **Stałe ID.** `Finanse/Aplikacja/mapa_id.json` (600, zapis tylko przy zmianie) pamięta: płatność BS → wiersz, wiersz → arkusz,
  nazwa arkusza → arkusz, klucz atrybutów wiersza → wiersz. ID płatności to `bs:<ID z BS>` (gdy BS dzieli dokument na kilka
  komórek: `bs:<ID>:2`, `:3`). Zmiana kontrahenta, komentarza czy folderu w kolejnym eksporcie zmienia atrybuty, nie ID.
  ID nadawane z klucza w chwili pierwszego pojawienia się, więc dwa Maki nadają te same. Wpisy ze starymi ID
  (`bs:<ID>:<hash wiersza>`) są tłumaczone przy odczycie; plik zmian nie jest przepisywany.
- **Zmiany bez obiektu** nie znikają: tabela `bud_osierocone`, lista na ekranie Historia zmian, baner na Arkuszach.
- **VAT liczy serwer** z netto i stawki (płatność, a gdy brak, wiersz), połówki w górę, bez float. Podstawy bez faktury: VAT 0.
  BS eksportuje stawkę efektywną (np. 0,2299): do 0,1 pkt proc. od 23, 8, 5 to ta stawka; faktura z kilkoma stawkami
  zachowuje proporcję VAT do netto. Kopie (duplikuj, scal, podziel) powstają na serwerze ze wzoru: ta sama stawka i daty.
- **Seria**: `bud` z `op: "seria"` i listą operacji w jednym wpisie; serwer próbnie nakłada cały wpis na bieżący model
  i zapisuje go w całości albo wcale (jedno przeliczenie, cofnięcie całej serii). Akcje na wierszach arkusza wysyłają serię.
- **Biała lista pól** obiektów `bud` (`zmiany.POLA_BUD`): nieznane pole albo zła wartość = odrzucenie z komunikatem.
- **Listy planu** ze stronicowaniem 50/100/200/500 i wyszukiwarką; suma w stopce ze wszystkich pozycji.
- Drobne: tabela podpina zdarzenia tylko w sobie, klik w plan po terminie w Cash flow otwiera kartę, umowy od dnia stanu,
  część roku z 366 dniami w roku przestępnym.
