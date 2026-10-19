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
.venv/bin/python -m unittest discover testy_odbioru   # prawdziwe pliki, baza w katalogu tymczasowym (iCloud może najpierw pobierać pliki)
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

## Pakiet 2: model planu jak w Budget Studio (2026-10-19)

Reguły w `finanse/plan.py` (bez bazy, testowalne wprost), zdarzenia w `finanse/budzet.py`.

- **Komórka = kwota, plany = pochodna.** Nowe zdarzenie `bud` `op: "komorka"` (`wiersz`, `miesiac`, `kwota` w groszach, `null` = pusta
  komórka, 0 = ukryty plan zerowy). Plany komórki (`plan:<wiersz>:<miesiąc>:<część>`) liczą się przy każdej odbudowie z kwoty, ustawień
  wiersza i ręcznych zmian planu. Kwoty komórek w tabeli `bud_komorka`. Komórka wpisana na wierszu z importu BS zastępuje plany BS
  tej komórki (cofnięcie przywraca). Plany z BS bez komórki zostają jak w eksporcie.
- **Podstawy:** faktura i bez faktury (1 plan), worek (tygodnie przycięte do miesiąca, kwota proporcjonalnie do dni, reszta groszy do
  ostatniego), umowa o pracę i zlecenie (osoba, PIT, ZUS), dzieło (osoba, PIT), daniny (1 plan bez VAT). Umowy: kwoty referencyjne
  od księgowej (`proporcje`), udział = kwota / suma (Fraction), PIT i ZUS połówkami w górę, reszta do osoby; PIT 20., ZUS 15. dnia
  miesiąca po wypłacie; wystawienie PIT i ZUS = osoby. Umowa zawsze obciążenie, Księgowane tak, VAT „-”.
- **Reguła dnia wystawienia** w wierszu: `Ostatni`, `1.`, `10.`, `10. +1`, `9. +1 B` (B = księgowanie wg miesiąca budżetu, tylko dzień
  1 do 15), `20. -1`; przesunięcie do 12 miesięcy. Termin = wystawienie + dni (0 do 99), dzień realny = termin.
- **Reguła nadpisań:** ręczna zmiana planu (kontrahent, komentarz, daty, metoda, Księgowane, W cash flow; stawka tylko w fakturze
  jednej; w worku tylko kontrahent i komentarz; PIT i ZUS umowy nic) zapisuje się przy planie. Zmiana tej samej cechy w wierszu kasuje
  ręczny wyjątek we wszystkich planach wiersza (także planach z BS); rzeczywistych nie rusza. Zapis wiersza bez zmiany wartości niczego nie kasuje.
- **Blokady** (sprawdzane przy zapisie, nie przy odtwarzaniu historii): po pierwszej rzeczywistej w wierszu podstawa, rodzaj i proporcje
  umowy o pracę i zlecenia; komórka z rzeczywistą (worek: nie mniej niż suma rzeczywistych); miesiąc poza zakresem arkusza; data planu
  ponad 5 lat od dnia stanu; PIT i ZUS zapłacone dopiero po wypłacie dla osoby. Komunikat mówi, co zrobić zamiast.
- **Etap i aktualność wg BS** w `bud_stan.etap_wg_bs` i `bud_stan.aktualnosc` (obok naszego etapu z banku): plan nieaktualny, gdy minął
  dzień wystawienia, płatności albo realny; rzeczywista nieopłacona, gdy minął dzień realny.
- **Cechy płatności:** kontrahent planu (z wiersza albo ręczny), Księgowane (OFF = poza rentownością arkuszy), W cash flow, split
  payment w wierszu (zapisany, liczenie w pakiecie 8). Arkusz, folder, sekcja, przedmiot zawsze ze złączenia, więc zmiana nazwy arkusza
  od razu widać na listach.
- **Parametr worka:** `worek_pierwszy_dzien_tygodnia` w `Finanse/Aplikacja/ustawienia.json` (0 = poniedziałek, domyślnie, decyzja Mata;
  eksport BS z 14.10.2026 dzieli od wtorku, czyli 1). Zmiana pliku wymaga „Wczytaj pliki na nowo”.
- **Interfejs (minimum, pełny arkusz w pakiecie 3):** klik w pustą komórkę = kwota; klik w komórkę = kwota komórki i karty płatności
  z polami dozwolonymi dla tej podstawy; karta wiersza z nowymi ustawieniami i wpisaniem kwot w miesiącach (seria komórek). Zapis
  wiersza wysyła tylko zmienione cechy.

## Pakiet UX: wygląd jak w Budget Studio (2026-10-19)

Zrzuty BS (19.10) i pomiar `getComputedStyle` jako wzór; nazwa i znak zostają „Finanse DigitalH”. Zrzuty po zmianie:
`Finanse/Aplikacja/zwiad-bs-2026-10-19/po/`.

- **Wygląd wspólny:** tokeny kolorów BS na `:root` w `web/styl.css` (wpływy, obciążenia, fiolet akcentu, pomarańcz „dziś”, niebieski
  planów, tła kafli) i pełna wersja ciemna (przełącznik w pasku). Font Roboto Flex (licencja OFL, `web/fonty/OFL.txt`) leży lokalnie,
  podzbiór łaciński, osie wagi i rozmiaru optycznego; zero zasobów z sieci.
- **Rama:** wąski ciemny pasek ikon (rozwija się po najechaniu), na dole Ustawienia, Pomoc, tryb. Panel sekcji: Budżet = Arkusze
  budżetu z wyszukiwarką i drzewem folder, kategoria, arkusz plus pozostałe ekrany budżetu; Płatności = grupy z ikonami, licznikami
  oczekujących i liczbą płatności list; Cash flow = zapisane widoki. Tytuł cienką czcionką, pigułka widoku, zakładki.
- **Wspólna tabela** (`tabela()` w `web/app.js`): fioletowe nagłówki z linią, numer, opcjonalna kropka statusu (`kropka`), tło wiersza
  (`wierszKlasa`: `wiersz-plan`, `wiersz-po`, `wiersz-plus`), sortowanie strzałką: po stronie serwera (`sort`) albo lokalnie dla list bez
  stron (`sortLokalny`, `sortKlucz`). Stopka „Max widocznych / Wyświetlono 1-100 z N / Wyszukaj”.
- **Pulpit:** baner oczekujących, 6 kafli BS z `GET /api/budzet/kafle` (te same warunki co listy planu), wykres 6 mies. w przód
  tygodniowo, kafle kontrolingu niżej.
- **Cash flow:** `GET /api/cashflow/okresy?granulacja=dzien|tydzien|miesiac&od&do&saldo_start&rodzaj&scenariusz&arkusz`
  (`finanse/cashflow.py: okresy`). Tydzień od wtorku do poniedziałku jak w BS (`cashflow_pierwszy_dzien_tygodnia` w `ustawienia.json`,
  0 = poniedziałek). Przed dniem stanu przepływy z banku (para przelewów główny/online się znosi, przelew na VAT to wypływ), po nim
  prognoza jak w 13 tygodniach. Ekran: zapisane widoki (2 tyg., 13 tyg., 6 mies., 12 mies., ten rok, 30 dni), pasek filtrów, panel
  Wygląd i filtry, tabela okresów z MAX/MIN, minimapa z ramką (do 120 punktów), wykres, lista płatności wycinka.
- **Arkusz:** zakładki Arkusz, Płatności (lista planu z `arkusz=`), Cash flow (okresy z `arkusz=`), Zarządzaj (menu); Grupuj wiersze wg,
  Sekcje, Ustawienia planowanych płatności, wykres nad miesiącami, kolory komórek BS (tło planów, po terminie, kropki), stopka z
  ustawieniami zaznaczonego wiersza i wyszukiwarką. Edycja bez zmian (pakiet 3).

## Pakiet 10: eksport i import (2026-10-19)

**Eksport** (`finanse/eksport.py`, adres `GET /api/eksport/<ścieżka zapytania>?format=xlsx|csv&<parametry>`). Plik powstaje
w pamięci i idzie do przeglądarki jako pobranie (`Content-Disposition`); apka nic nie zapisuje na dysku, więc plik ma
takie uprawnienia, jakie nada mu przeglądarka w Pobranych.
- **Płatności budżetu w układzie Budget Studio:** zapytanie `budzet/lista` z bieżącymi filtrami, kolumny 1:1 jak w
  `budget_studio_*.csv` (ID, rodzaj, status, etap, podstawa w zapisie BS, kwoty ze znakiem, daty, przesunięcie, księgowanie,
  arkusz, folder, kategoria, sekcja, przedmiot, data utworzenia i modyfikacji). CSV w formacie pliku BS (tabulator, UTF-8
  bez BOM, kwoty jak w BS: `-10,31`, `0`, `9999,9`). Dla płatności z importu BS pełny „Miesiąc budżetowy” i daty utworzenia
  i modyfikacji idą z pliku eksportu, dla zmienionych w apce z historii zmian. Odbiór: na eksporcie BS z 14.10 wszystkie
  wiersze zgodne z plikiem BS w 26 kolumnach (status i etap liczymy sami, z banku, więc mogą się różnić).
- **Każda lista z bieżącymi filtrami:** przyciski „Pobierz: Excel, CSV” w nagłówku ekranu. `api()` w `app.js` zapamiętuje
  zapytanie ekranu (hook `zapamietajZapytanie`), a `pokaz()` po narysowaniu woła `poWidoku`, więc eksport dostaje dokładnie
  te parametry, z którymi ekran pytał serwer. Serwer woła tę samą funkcję zapytań (`eksport.wolaj`: parametry po nazwie,
  aliasy jak w `serwer.py`, wszystkie strony po 500), więc suma eksportu = stopka listy.
- **Zestawienia:** faktury, należności z wiekowaniem (arkusz z sumami przedziałów), bank, rejestr zakupów, wydatki, wpłaty do
  połączenia, do weryfikacji, wyniki biura, rozjazdy, klienci, wynik zarządczy, obroty, koszty, VAT, rentowność klientów
  i arkuszy, cash flow wg granulacji (okres w wierszu, pozycje, podsumowanie z SUM, MAX, MIN), arkusz budżetu (wiersze ×
  miesiące, saldo okresu, wpływy, obciążenia, narastająco). Stare adresy (`arkusz`, `cashflow` 13 tygodni, `rentownosc`) działają.
- Excel: kwoty jako liczby (format „zł”), daty jako daty, arkusz „Podsumowanie” z filtrami i sumami. CSV list: UTF-8 z BOM,
  średnik, przecinek dziesiętny. Tekst zaczynający się od `=`, `+`, `@` albo minusa przed literą dostaje apostrof (nie formuła).
- Ekran **Eksport** (`web/eksport.js`) jak w BS: zakładki Excel i CSV, kafle zakresów z polami (lista, rodzaj, daty, rok,
  granulacja, arkusz).

**Import** (`finanse/importy/`).
- **Historia importów** (`podsumowanie.py`, `GET /api/importy/historia`): każdy plik w `Dane/` to import z licznikami jak w BS:
  Dodane, Zaktualizowane (ta sama pozycja, inne dane, np. faktura opłacona), Bez zmian, Pominięte (z powodem). Liczone przy
  otwarciu ekranu z samych plików (odbudowa bazy się nie wydłuża): pliki źródła w kolejności trafienia do folderu (data pliku),
  każdy porównany ze stanem sprzed niego; ING, rejestr i wyniki ze wszystkimi wcześniejszymi, Fakturownia i BS z poprzednim
  (liczy się tylko najnowszy). Klucze jak w bazie. Pominięte: drugi raz ten sam klucz w pliku (np. dwie operacje ING bez
  numeru, ten sam dzień, kwota i tytuł), wiersz rejestru bez numeru ewidencyjnego z danymi (sumy arkusza nie), wiersz BS bez
  rodzaju 1 albo -1, cały plik, którego nie da się wczytać.
- **Podsumowanie importu** (`GET /api/importy/podsumowanie?id=&kategoria=&q=&strona=&ile=`, ekran `#/platnosci/import`):
  zakładki z licznikami, domyślnie Pominięte, gdy są; przy Zaktualizowanych lista zmian „pole: było → jest”.
- **Plik przeciągnięty do okna** (`reczny.py`, `POST /api/import?tryb=podglad|zapisz`, nagłówek `X-Finanse`, nazwa w
  `X-Nazwa-Pliku`, limit 20 MB): rozpoznanie źródła po zawartości (`rozpoznanie.py`: nagłówki CSV i separator, arkusze
  Excela; ING, Fakturownia, Budget Studio, rejestr xlsx, wyniki xls z okresem z nagłówka „Za okres”), podgląd z licznikami
  i przykładami, dopiero „Importuj” zapisuje surowy plik bez zmian do właściwego podfolderu `Dane/` pod nazwą wg konwencji
  (`ing_historia_<od>_<do>.csv`, `fakturownia_sprzedaz_<dziś>.csv`, `budget_studio_<dziś>.csv`,
  `biuro_rejestr_zakupow_<od>_<do>.xlsx`, `biuro_wyniki_<okres>.xls`; przy kolizji nazwy `_2`), plik 600, i przelicza bazę.
  Kopia robocza do odczytu leży w lokalnym katalogu bazy (`import-roboczy`, 700) i znika od razu. Ten sam plik drugi raz
  (ta sama treść): pliku nie zapisujemy, podgląd i historia pokazują „Bez zmian” = liczba wierszy. Nieznany format, PDF,
  XML z KSeF, własny eksport apki: ostrzeżenie z powodem, nic nie jest zapisywane.
- **Dziennik importów** (`dziennik.py`): `Finanse/Aplikacja/importy/<Mac>.jsonl` (600, jak plik zmian: każdy Mac swój plik),
  wpis na każdy import z okna: nazwa oryginalna, gdzie zapisany, liczniki; z niego Historia pokazuje sposób dodania
  i ponowne importy tego samego pliku.
- **KSeF z pliku: nie zrobione.** Eksport z KSeF to XML FA(2)/FA(3) (struktura z wieloma wariantami pozycji, stawek
  i korekt), apka nie ma przykładowego pliku, a decyzja M9 jest otwarta; koszty idą z rejestru biura. Plik KSeF jest
  rozpoznawany i dostaje ostrzeżenie.

Testy: `testy/test_pakiet10.py` (układ i zapis kwot jak w BS, sumy jak w stopce listy, CSV i Excel, zabezpieczenie formuł,
rozpoznanie źródła, liczniki importu, przeciągnięcie, serwer), `testy_odbioru/test_pakiet10.py` (prawdziwe pliki: eksport
1:1 z plikiem BS, rozpoznanie każdego pliku z `Dane/`, ponowny import pliku ING = same „Bez zmian”, bez zapisu).
