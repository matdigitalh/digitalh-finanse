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
| 6 | Pulpit jak w Budget Studio, eksport | gotowy 2026-10-19 (pakiety UX, 10 i 11); planowanie w apce od 1.11.2026 |

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

**Rezerwa na koszty krytyczne (decyzja Mata 2026-10-20).** Rezerwa liczy się od kosztów, których nie można nie zapłacić,
a pozycje wybiera Mat (Pulpit, Cele). Pozycje (`controlling.POZYCJE_REZERWY`): wynagrodzenia (rodzaj `praca`), księgowość
(`staly` kontrahentów z listy, domyślnie `brixen fk`; lista nadpisywalna kluczem `rezerwa_ksiegowosc` w `ustawienia.json`
i wpisem z apki), narzędzia i inne stałe (`staly` bez księgowości), podatki, koszty klientów (`przenoszony`), nieprzypisane.
Domyślnie włączone: wynagrodzenia i księgowość. Każda pozycja: średnia miesięczna z banku z tego samego okna 6 pełnych miesięcy
co dotąd (grosze), przełącznik i opcjonalna kwota własna miesięcznie (zastępuje średnią; `null` = średnia). Wynik: `koszt_krytyczny`
(suma włączonych), `wymagana` = koszt × `rezerwa_miesiecy`, `pokrycie_miesiecy`, `nadwyzka`, `status` (zielony od celu, żółty od 2/3),
rozbicie w `pozycje`. Stare pola zostają (`srednie_koszty`, `srednie_stale` czytane przez `cashflow.py`, `pokrycie_stalych`),
plus `pokrycie_wszystkich` i `wymagana_wszystkie`. Zapis: wpis `rezerwa` w pliku zmian (`{pozycje: {klucz: {wlaczona, kwota}},
ksiegowosc: [...]}`, tylko podane pola; kolejne wpisy nakładają się po czasie, `cofnij` przywraca stan sprzed wpisu). Walidacja
w `zmiany._sprawdz_rezerwe` (znane klucze, kwota int ≥ 0 albo null), serwer sprawdza, że kontrahent księgowości jest w wydatkach
z banku; złożenie w `klienci.wczytaj_reczne` (meta `rezerwa`). Testy: `testy/test_controlling.py` (`TestRezerwaKrytyczna`).

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
- **Parametr worka:** `worek_pierwszy_dzien_tygodnia` w `Finanse/Aplikacja/ustawienia.json`; domyślnie 1 = wtorek, jak w BS
  (decyzja Mata 2026-10-19, wieczór; 0 = poniedziałek). Zmiana pliku wymaga „Wczytaj pliki na nowo”.
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

## Pakiet 3: edycja arkusza jak w Budget Studio (2026-10-19)

Interfejs w `web/arkusz.js` (tabela arkusza, edycja, akcje, Zarządzaj), reguły i blokady na serwerze w `finanse/budzet.py`
(zawsze sprawdzane przed zapisem, wpis w całości albo wcale). Edycja działa tylko przy włączonym planowaniu (Budżet, Ustawienia
budżetu); bez niego arkusz jest do odczytu, a serwer odrzuca zmiany z komunikatem.

- **Zaznaczanie i klawiatura (A-ARK-14):** klik zaznacza komórkę (nie otwiera karty), strzałki, Tab i Shift+Tab przesuwają,
  Shift rozszerza zakres, Cmd+strzałka skacze do krawędzi, Cmd+A cały arkusz. Pisanie cyfr na komórce miesiąca nadpisuje kwotę,
  Enter, F2 albo dwuklik edytuje (zawartość zaznaczona), Enter zapisuje i schodzi niżej, Tab zapisuje i idzie w prawo, Esc anuluje,
  Backspace i Enter czyści komórkę. Tylko liczby (format polski, spacje tysięcy, „zł” ignorowane, trzecie miejsce po przecinku
  zaokrąglane połówkami w górę). Cmd+Enter albo Cmd+dwuklik: karta płatności; Cmd+F: wyszukiwarka arkusza.
- **Kolumny ustawień i opisu w miejscu:** kontrahent, sekcja, przedmiot, metoda: lista z filtrowaniem i „Dodaj …” (słownik = wartości
  z wierszy i planów całego budżetu do czasu Biblioteki z pakietu 4); podstawa, VAT, dni (0 do 99): lista; dzień wystawienia: panel
  (ostatni, pierwszy, wybrany dzień, przesunięcie o miesiące, księgowanie wg budżetu przy dniu 1 do 15, przykład dla pierwszej
  kolumny); Split, Księgowane, W cash flow, Rodzaj: klik albo Enter. Umowa wybrana z listy otwiera kartę wiersza po kwoty od księgowej.
  Zapis wysyła tylko zmienione pole (reguła nadpisań z pakietu 2).
- **Kopiuj i wklej:** Cmd+C kopiuje zakres jako tekst z tabulatorami (Excel), Cmd+V wkleja blok od lewego górnego rogu zaznaczenia:
  kwoty i kolumny ustawień, jedna wartość na cały zaznaczony zakres, nowe wiersze, gdy blok wychodzi poza tabelę. Całe wklejenie to
  jedna seria (jeden wpis w historii, Cmd+Z cofa całość); zła wartość albo komórka z rzeczywistą: nic nie zapisane, komunikat
  z numerem wiersza i kolumną. Komórki bez zmiany są pomijane.
- **Wiersz „Dodaj +” (A-ARK-10):** wpisanie wartości w dowolnej kolumnie tworzy wiersz (obciążenie, faktura jedna, 23 %, ostatni dzień,
  14 dni, Konto firmowe). Kontrahent wpisany jako pierwsza akcja bierze ustawienia z jego wiersza w budżecie (A-KOL-04, przybliżenie
  do czasu Biblioteki). Wiersze dodane w apce są na końcu, w kolejności powstania (`bud_wiersz.kolejnosc`).
- **Zapis i cofanie:** zmiany idą po kolei (szybkie wpisywanie nie wyprzedza zapisu), po zapisie odświeża się sam arkusz z zachowaniem
  zaznaczenia i przewinięcia. Każdy zapis ma „Cofnij”; Cmd+Z cofa ostatnią obowiązującą zmianę budżetu (`GET /api/budzet/ostatni`,
  wpis `cofnij`), kolejne Cmd+Z cofa wcześniejsze.
- **Akcje na wierszach (A-OPS-08 do 13):** checkbox po najechaniu na numer, pasek na dole z liczbą wierszy i sumą wpływów i obciążeń.
  Operacje na serwerze, każda jednym wpisem: `scal` (ten sam rodzaj i podstawa, faktura z fakturą w worku wolno; wynik = pierwszy
  zaznaczony wiersz ze wszystkimi płatnościami, bez sumowania; kilka płatności w miesiącu = podstawa w worku; plany z komórek
  utrwalone jako zwykłe plany), `podziel` (tyle wierszy, ile płatności; umowa nie), `duplikuj` (kwoty komórek, rzeczywiste stają się
  planami z ustawień), `przenies` (także do nowego arkusza tworzonego w tej samej serii), usuń (tylko bez rzeczywistych). „Podziel
  procentem” zostaje jako osobna akcja (pytanie M6), tylko dla faktury jednej i bez faktury bez rzeczywistych. Akcja nieaktywna
  ma podpowiedź, dlaczego.
- **Karta komórki (A-ARK-13, B-LIS-13, B-MOD-11):** `GET /api/budzet/komorka?wiersz=&miesiac=`: wszystkie płatności komórki (bez limitu),
  kwota komórki, przeniesienie kwoty na inny miesiąc (komórka z kwotą: kwota; plany z BS: daty przesunięte o tyle samo miesięcy),
  usunięcie planu, decyzje po terminie, rzeczywista edytowalna dopiero po „Edytuj dane”. Cechy planu różne od ustawień wiersza,
  czyli ręczne wyjątki (`plan.odstepstwa`: kontrahent, komentarz, metoda, Księgowane, W cash flow, stawka, daty wg reguły), na
  pomarańczowo w karcie i w panelu podglądu w stopce (A-ARK-11); rzeczywista ma dane z dokumentu, więc jej nie podświetlamy.
- **Kolory komórek (A-KOM-02):** niebieskie tło = tylko plany, białe = rzeczywiste, ukośny podział = plany i rzeczywiste, różowe =
  rzeczywiste po terminie, czerwona kropka = płatność nieaktualna, zielony ptaszek = jest opłacona, pomarańczowa kreska = opłacona
  tylko wg BS.
- **Zarządzaj (A-OPS-02 do 07, A-ARK-01):** zmiana nazwy (też klik w tytuł; do 80 znaków), zakres miesięcy w kalendarzu (kłódka =
  miesiąc z rzeczywistą, musi zostać; znak planu = plany znikną po wycięciu; najwyżej 240 miesięcy), przesunięcie startu (tylko bez
  rzeczywistych, plany od nowa z ustawień), folder i kategoria (też ikona przy tytule; nowa nazwa równa istniejącej, także inną wielkością
  liter, odrzucona), duplikat (bez zmian, wybrany zakres albo przesunięty start; z wartościami albo sama struktura; rzeczywiste stają się
  planami), usunięcie arkusza bez rzeczywistych. Przypinanie arkuszy: pakiet 4.
- **Sekcje (A-ARK-05):** kolejność sekcji z sortowania kolumny Sekcja sprzed włączenia przełącznika (`sekcje_kier` w adresie).
- **Blokady z komunikatem „co zrobić zamiast” (A-INN-05):** podstawa i rodzaj wiersza z rzeczywistą, komórka nie-worek z rzeczywistą,
  worek poniżej sumy rzeczywistych, usunięcie wiersza, płatności rzeczywistej i arkusza z rzeczywistymi, wycięcie miesiąca
  z rzeczywistą, przesunięcie startu z rzeczywistymi, przeniesienie wierszy poza zakres arkusza docelowego, rzeczywista do innej
  komórki, nazwa ponad 80 znaków, komentarz ponad 170, dni ponad 99, zakres ponad 20 lat, ponad 1000 wierszy w arkuszu, duplikat
  nazwy folderu i kategorii, nieliczbowa kwota. Łączenie rzeczywistych z planami (pusta komórka, inny rodzaj) w pakiecie 5; usuwanie
  folderów, kontrahentów i przedmiotów z Biblioteki w pakiecie 4.
- Testy: `testy/test_pakiet3.py` (scal, podziel, duplikuj, usuń, przenieś, limit wierszy, zakres, przesunięcie, duplikat arkusza,
  usunięcie arkusza, odstępstwa, karta komórki, plan na inny miesiąc, ostatnia zmiana do cofnięcia, komunikaty).

## Pakiet 4: struktura budżetu i Biblioteka (2026-10-19)

Reguły w `finanse/biblioteka.py`, ekran Budżet, Biblioteka (`web/biblioteka.js`, `web/biblioteka.css`), API `GET /api/budzet/biblioteka`.

- **Model.** Słowniki (kontrahenci, przedmioty transakcji, sekcje, metody płatności) i struktura folderów i kategorii są częścią
  stanu budżetu, obok arkuszy i wierszy. Zmiany to zdarzenia `bud` z nowymi operacjami `slownik` (dodaj, zmien, polacz, usun)
  i `struktura` (dodaj_folder, dodaj_kategorie, zmien_folder, zmien_kategorie, usun_folder, usun_kategorie, kolejnosc), więc
  działają jak reszta budżetu: próba na modelu z blokadami, cały wpis albo nic, seria, Historia zmian, Cmd+Z. Bez wpisów
  słowniki i struktura wynikają z danych (kopia z BS albo import): każda nazwa z wierszy, płatności i ręcznych zmian planów,
  foldery i kategorie z arkuszy; ustawienia domyślne kontrahenta z jego najczęstszego wiersza. Plików Mata nic nie przepisuje.
  Tabele `bud_slownik` i `bud_struktura` w bazie; liczniki wystąpień liczy zapytanie.
- **Wpisy systemowe.** Pusty kontrahent (na liście „Bez kontrahenta”) to kontrahent domyślny na start, z ustawieniami, które apka
  wpisywała do nowego wiersza w pakiecie 3; pusty przedmiot to „Przedmiot transakcji”, pusta sekcja to „-”. Nie zmienisz ich nazwy
  ani nie usuniesz. Wartości używane przez arkusz systemowy Opłaty urzędowe (Urząd Skarbowy, Przelew, przedmioty podatkowe) mają
  znacznik „podatki” i nie dają się usunąć. Arkusze podatkowe z BS zastąpione przez arkusz systemowy nie liczą się do folderów.
- **Biblioteka (A-KON-01 do 12).** Zakładki: Kontrahenci, Przedmioty transakcji, Sekcje, Metody płatności, Foldery i kategorie,
  Arkusze budżetu. Słownik: licznik wystąpień (wiersze i płatności), sortowanie, wyszukiwarka, strony, zaznaczanie z paskiem
  (Usuń tylko przy liczniku 0, Połącz zaznaczone), karta po kliknięciu: nazwa (zmiana przepina wszystkie wiersze, płatności
  i ręczne zmiany planów), kontrahent: pełna nazwa, NIP (suma kontrolna, prefiks PL, numery VAT UE), „Domyślny dla nowych
  wierszy” (zawsze dokładnie jeden), ustawienia domyślne (rodzaj, podstawa bez umów, VAT, dzień wystawienia, dni, metoda, split,
  Księgowane, W cash flow, przedmiot, sekcja); przedmiot: domyślny; metoda: rachunek ING (główny, online, VAT, karta) i bank.
  Pełna nazwa i NIP podpowiadają się z Fakturowni (nabywca o tej samej krótkiej nazwie, jednoznaczny NIP): szary NIP ze znakiem
  zapytania, „Wpisz z Fakturowni” w karcie. **Łączenie duplikatów** (A-KON-06): drugi wpis z wyszukiwarki albo zaznaczone, wybór
  nazwy i danych, które zostają; wszystkie wystąpienia przechodzą na jeden wpis jednym wpisem w pliku zmian.
- **Nowy wiersz wg reguły BS (A-ARK-10, A-KOL-03 do 05).** Wiersz „Dodaj +” wysyła tylko pole pierwszej akcji z flagą `domyslne`;
  serwer uzupełnia resztę: gdy pierwszą akcją był wybór kontrahenta, jego ustawienia domyślne, inaczej kontrahent domyślny i jego
  ustawienia, przedmiot domyślny. Do pliku zmian trafia już pełny wiersz (historia nie zależy od późniejszych zmian w Bibliotece).
  Wybór kontrahenta w istniejącym wierszu nie zmienia jego ustawień. Nowa nazwa wpisana w wierszu („Dodaj …”) trafia do Biblioteki
  sama jako wpis uproszczony (pełna = skrócona, NIP pusty); nowy kontrahent dostaje bieżące ustawienia wiersza jako domyślne
  (wiersz zaczęty od niego ma ustawienia kontrahenta domyślnego, więc te). Zmiana w wierszu nie zmienia Biblioteki. Na dole listy
  w komórce link „Edycja kontrahentów …” (przedmiotów, sekcji, metod) do Biblioteki.
- **Foldery i kategorie (A-BUD-05 do 11).** Trzy kolumny jak w BS (Folder, Kategoria, Arkusze): dodanie folderu z pierwszą
  kategorią, nazwa folderu unikalna w całej apce, kategorii w folderze (bez względu na wielkość liter), zmiana nazwy ołówkiem
  (✓ zapis, × anuluj, Enter, Esc; arkusze przechodzą razem), usunięcie pustego po potwierdzeniu albo z przeniesieniem arkuszy
  (folder: kategorie z arkuszami do innego folderu, ta sama nazwa kategorii łączy się; kategoria: do innej kategorii; ostatniej
  kategorii folderu nie usuniesz), kolejność strzałkami (drzewo budżetu i listy idą w tej kolejności), przeniesienie arkusza z listy.
  Pusty folder istnieje, ale nie ma go w drzewie, dopóki nie ma arkusza; można go wybrać przy dodawaniu arkusza i w „Zmień folder /
  kategorię”. Folder „System” zarezerwowany dla arkusza z podatkami. Klik w folder i kategorię w drzewie (panel Budżet i ekran
  Arkusze budżetu) otwiera Bibliotekę na tym miejscu (A-BUD-08). Arkusz w folderze różniącym się tylko wielkością liter: odrzucony
  na serwerze. Nowy arkusz: zakres domyślnie 12 miesięcy od bieżącego (A-OPS-01).
- **Przypinanie arkuszy (A-OPS-07) i menu Budżet (A-BUD-12).** Pole `przypiety` arkusza w zdarzeniu `bud` (op `arkusz`, biała
  lista pól, cofanie jak każda zmiana arkusza); bez decyzji arkusz jest przypięty (kopia z BS i nowe), kopia arkusza zawsze
  przypięta; przypięcie nie zmienia źródła arkusza. Drzewo w menu Budżet pokazuje tylko przypięte; wyszukiwarka filtruje je po
  fragmencie nazwy arkusza, kategorii albo folderu i dopisuje pod spodem pasujące nieprzypięte. „Zobacz wszystkie arkusze”
  (ekran Arkusze budżetu) pokazuje wszystkie, z pinezką do przypięcia lub odpięcia, znacznikiem „nieprzypięty” i wyszukiwarką
  w miejscu; to samo w Bibliotece, zakładka Arkusze budżetu (kolumna Przypięty). Pinezka w tytule arkusza i pozycja w Zarządzaj.
  Historia zmian opisuje to jako „przypięty do drzewa” albo „odpięty z drzewa”. Kolumna `bud_arkusz.przypiety`.
  To jedyny mechanizm przypinania: osobny wpis `przypiecie` z pakietu 11 usunięty przy scaleniu (w dzienniku zmian nie było
  takich wpisów), pinezka i `GET /api/budzet/przypiete` czytają to pole. Jak każda zmiana budżetu wymaga włączonego planowania.
- **Zarządzaj (A-OPS-01 do 07):** Dodaj nowy arkusz (nazwa do 80 znaków, nieunikalna; podpowiedzi kategorii z wybranego folderu,
  także pustego z Biblioteki; zakres domyślnie 12 miesięcy od bieżącego, co najmniej 1 miesiąc, najwyżej 20 lat; po zapisie
  apka otwiera nowy arkusz), zmień nazwę, folder i kategorię, zakres z kłódką i znakiem planu, przesuń start, duplikuj z i bez
  wartości, przypnij lub odepnij, usuń (z pakietu 3 i wyżej).
- Zmiany w istniejących plikach: `budzet.py` (stan i zapis Biblioteki, operacje przez `_zastosuj_op`, uzupełnienie nowego wiersza,
  wchłanianie nowych nazw po wpisie), `zmiany.py` (operacje `slownik`, `struktura`, flaga `domyslne`), `zapytania_budzet.py`
  (listy w arkuszu, wzorce kontrahentów i kolejność drzewa z Biblioteki), `baza.py`, `odbudowa.py`, `serwer.py` (jedna ścieżka),
  `web/arkusz.js` (link „Edycja …”, nowy wiersz i wklejanie z flagą, wybór miejsca arkusza ze struktury), `web/budzet.js`,
  `web/app.js` (pozycja menu, linki w drzewie), `web/index.html`.
- Testy: `testy/test_pakiet4.py` (słowniki z danych i liczniki, łączenie duplikatów jedną serią z cofnięciem, zmiana nazwy
  wszędzie, blokada usuwania użytych, systemowych, domyślnych i podatkowych, NIP, ustawienia domyślne kontrahenta wg reguły BS
  w pięciu wariantach, seria wszystko albo nic, foldery i kategorie: unikalność, zmiana nazwy, usuwanie z przeniesieniem,
  kolejność, cofnięcie), przypinanie (domyślnie przypięty, odpięcie zdarzeniem i cofnięcie, źródło bez zmian, kopia przypięta,
  walidacja pola) i osobna klasa `TestKryteriumOdbioru` z każdą regułą kryterium odbioru pakietu (wydłużenie o 2027 bez zmiany
  płatności, wycięcie miesiąca z rzeczywistą odrzucone bez wpisu, duplikat 2026 na 2027 bez wartości i z wartościami, połączenie
  dwóch kontrahentów, blokada usunięcia folderu z arkuszem z powodem, kontrahent jako pierwsza i druga akcja).

Do dokończenia:
- Automatyczne dodawanie kontrahentów z importów (B-LIS-12, Fakturownia i ING jako nowe wpisy): jest tylko podpowiedź pełnej
  nazwy i NIP-u z Fakturowni; apka nie tworzy płatności rzeczywistych z dokumentów w budżecie, więc nie ma momentu „zatwierdzenia”.
- Wpisy Biblioteki sprzed przyjęcia kopii z BS przestają obowiązywać razem z innymi zmianami budżetu sprzed kopii (jak w pakiecie 6).

## Pakiet 5: rzeczywiste vs planowane i łączenie (2026-10-19, dokończony 2026-10-20)

Zasada jak w BS: płatność rzeczywista (faktura z Fakturowni, dokument z rejestru biura, przelew ING bez dokumentu,
płatność dodana ręcznie, plan zamieniony na rzeczywistą, lista płac) liczy się do budżetu dopiero po połączeniu z komórką.
**Nic nie łączy się samo** (decyzja Mata 2). Dokumenty sprzed dnia „Łączenie w apce od” (domyślnie 1.11.2026, zmiana na
liście Do połączenia) są połączone w Budget Studio i przychodzą z kopii BS.

Co działa:
- **Do połączenia** (Płatności): poczekalnia z podpowiedzią planu przy każdej pozycji (arkusz, wiersz, miesiąc, pewność,
  uzasadnienie: kontrahent, kwota, miesiąc, wcześniejsze połączenia). „Połącz” = podpowiedź jednym kliknięciem (komunikat
  z różnicą od planu, „Zostaw resztę planu”, „Cofnij”). Akcje grupowe: połącz wg podpowiedzi (jedna seria), połącz
  z budżetem jako nowe wiersze (B-LACZ-07; dzień wystawienia, stawka VAT i dni na płatność z dokumentu), odłącz,
  do weryfikacji, usuń płatność dodaną ręcznie. Zakładki: do połączenia, starsze niż start, połączone w apce.
- **Ekran łączenia** (klik w pozycję albo „Inny plan”): podpowiedzi i wyszukiwarka komórek, wybrane komórki z kwotami,
  „Do rozliczenia” (Połącz aktywne przy 0,00), „Różnica od planu”, podział na wiele komórek i arkuszy, co z resztą planu.
- Reguły: tylko komórka z planem (choćby 0), ten sam rodzaj, zgodna podstawa (stawka VAT wiersza bez znaczenia), plan
  znika, komórka = kwota rzeczywistej i jest zablokowana, wiersz ma zablokowaną podstawę; odłączenie przywraca plan.
- **Worek**: przyjmuje kolejne rzeczywiste; komórka bez zmian, dopóki suma ≤ plan. Karta komórki pokazuje podpięte
  rzeczywiste i niezrealizowane plany tygodniowe, „Zamknij worek” (operacja `zamknij_worek`) i „Otwórz worek”.
- **Zmień na rzeczywistą** na karcie planu (numer dokumentu, 1:1, nie worek, nie z przyszłym wystawieniem).
- **Dodaj płatność** (formularz jak w BS: faktura albo bez faktury, walidacje dat BS).
- **Opłacona** wyłącznie z banku; ręcznie tylko wyjątek poza bankiem i zawsze z datą przelewu (serwer odrzuca bez daty).
- **Lista płac za miesiąc** (Budżet, decyzja 12): od 2026-10-20 dane rzeczywiste z osobnym wpisem, szczegóły w sekcji
  „Lista płac jako dane rzeczywiste” niżej. Plan wynagrodzenia nigdy nie zamyka się sam (etap BS, przelew, zamiana planu);
  „Niewymagana” z BS nie jest opłacona i zostaje w cash flow.
- **Odłącz od budżetu** masowo: na liście Do połączenia (zakładka połączone), na liście płatności i w cash flow
  (przycisk nad listą płatności wycinka).
- Rozjazdy „Faktura bez pozycji w BS” i „Wydatek z banku bez pozycji w BS”: klik prowadzi do ekranu łączenia, przycisk
  „Połącz z budżetem: nowe wiersze” dla całej grupy.

API: `GET /api/lista/do-polaczenia`, `GET /api/laczenie/dokument?ref=&q=`, `GET /api/laczenie/polaczone`,
`GET /api/lista-plac?miesiac=`, `GET /api/ostrzezenia` (lista z polami `typ`, `opis`, `osoba`, `miesiac`, `kwota_gr`,
`link`). Zdarzenia „bud”: `polacz`, `odlacz` (także `worek:`, `zamiana:`), `rzeczywista`, `zamien`, `zamknij_worek`
(lista płac to od 2026-10-20 osobny wpis `lista_plac`, nie zdarzenie budżetu). Kod: `finanse/budzet.py`, `finanse/laczenie.py`, `web/laczenie.js`, `web/laczenie.css`.

## Lista płac jako dane rzeczywiste (2026-10-20)

Decyzja Mata 12 uzupełniona 2026-10-20 („żeby w aplikacji było dobrze”). Kod: `finanse/lista_plac.py` (silnik),
`finanse/laczenie.py` (`lista_plac`, `ostrzezenia`), `web/laczenie.js` (ekran `#/budzet/lista-plac`), testy
`testy/test_lista_plac.py`.

- **Osobny wpis `lista_plac`, nie planowanie.** Lista płac od biura to dane rzeczywiste: zapis działa przy wyłączonym
  planowaniu, w miesiącach z płatnościami z kopii BS i przed dniem „Łączenie w apce od”. Wpis leży w pliku zmian
  (`zmiany/<Mac>.jsonl`) i jest nakładany na budżet po wszystkich zdarzeniach „bud”, przy każdej odbudowie, więc przetrwa
  nowy eksport BS i przyjęcie kopii z BS (zdarzenia „bud” sprzed kopii przestają obowiązywać, lista płac nie). Obowiązuje
  ostatni nie cofnięty wpis za miesiąc (cała lista to jedna decyzja); `usun` albo „Cofnij” przywraca BS albo estymację.
  Serwer sprawdza wpis próbą na bieżącym budżecie (`budzet.sprawdz_liste`); zdarzenie „bud” `lista_plac` jest odrzucane,
  a „odłącz” listy płac z list płatności i cash flow też (zmienia się ją tylko na ekranie listy).
- **Pierwszeństwo przed BS.** Dla osoby, miesiąca i składowej kwota z listy zastępuje plan albo płatność rzeczywistą z kopii
  BS (kwota BS to estymacja z podziałem procentowym). Zastąpiona płatność BS zostaje w zapisie połączenia: ekran listy pokazuje
  kwotę BS przy każdym polu, razem i różnicę, tytuł płatności „Lista płac za … (w BS było …)”. Cash flow, rentowność budżetu,
  koszt pracy i wynik liczą się z listy. W arkuszu komórka z listy ma znak „L”, płatność ma źródło „lista płac”. Płatność
  połączona w apce w tej komórce (dokument) blokuje zapis z komunikatem.
- **Pola per osoba:** wypłata na konto, PIT, ZUS (pracownika, pracodawcy, zdrowotna: jeden przelew), PPK pracownika,
  PPK pracodawcy, pakiet medyczny, potrącenia z wypłaty (np. Luxmed), data wypłaty, uwaga; do miesiąca uwaga i PPK. Pole
  puste = brak na liście: składowa zostaje jak w BS albo w planie (nic nie zgadujemy); 0 = zero.
- **Terminy:** wypłata = data wypłaty z listy; ZUS i PPK do 15., PIT do 20. dnia miesiąca po miesiącu wypłaty (lista za
  styczeń, wypłata 4.02: ZUS 15.03, PIT 20.03, PPK 15.03, zgodnie z przelewami w ING). Etap BS przechodzi z płatności
  zastąpionej (lista poprawia kwotę, nie fakt zapłaty); „Opłacona” nadal z banku.
- **PPK:** jedna płatność (suma PPK pracownika i pracodawcy wszystkich osób) w zbiorczym wierszu PPK z BS (domyślnie wiersz
  bez faktury z „PPK” w komentarzu). **Miesiąc budżetowy = miesiąc listy** (decyzja Mata 2026-10-20: PPK działa jak ZUS
  i PIT tej listy), więc koszt, rentowność budżetu, wynik i koszt pracy liczą PPK w miesiącu, za który jest lista. Termin
  i cash flow bez zmian: 15. dnia miesiąca po wypłacie (lista za styczeń, wypłata 4.02, PPK 15.03). BS trzyma PPK wg miesiąca
  przelewu, więc lista zastępuje komórkę BS wskazaną we wpisie (`ppk.miesiac`, domyślnie miesiąc terminu: komórka marzec
  594,78 = lista za styczeń); ta komórka BS nie wraca po nowym eksporcie ani kopii z BS, więc nic się nie dubluje. Komórki BS
  bez listy (styczeń i luty 2026 = PPK z list za XI i XII 2025) zostają z kwotą BS w swoim miesiącu. Rozjazd z BS w PPK to
  układ miesięcy, nie kwota: mapa PPK na ekranie listy płac pokazuje miesiąc w budżecie, listę, komórkę BS (przelew)
  z przesunięciem w miesiącach, termin, kwotę BS, z listy i różnicę; tytuł płatności „PPK z listy płac za … (w BS w komórce
  …: kwota)”. Bez wskazanego wiersza PPK zostaje tylko w koszcie pracodawcy. W bazie połączenie listy trzyma ID płatności BS,
  które zastąpiło (`bs_zastapione`); odbiór „eksport 1:1 z plikiem BS” pomija je jawnie.
- **Pakiet medyczny i potrącenia** są częścią kosztu pracodawcy osoby, ale bez osobnej płatności: opłaca je faktura za pakiet
  medyczny (Mediccentre 364 zł = pakiet 89 zł × 2 + potrącenia 80 i 106 zł), która już jest w budżecie. Osobna płatność
  liczyłaby ten koszt dwa razy.
- **Wiersz bez umowy** (powołanie zarządu, w BS jedna kwota brutto) trafia na listę wprost z ekranu („Dodaj do tej listy”):
  dostaje trzy płatności (na konto, zdrowotna jako ZUS, PIT) zamiast jednej kwoty, suma bez zmian; wpis wymaga wszystkich
  trzech części. Wiersz staje się wierszem listy płac (ostrzeżenia, bez dokumentów z Do połączenia).
- **Koszt pracodawcy** = wypłata + ZUS + PIT + PPK pracownika i pracodawcy + pakiet + potrącenia; zgodny co do grosza
  z kolumną „Koszt pracodawcy” w zestawieniu list płac (40 osobomiesięcy I–IX 2026). Ekran pokazuje go per osoba i w tabeli
  „Koszt pracy z list płac” (koszt, w budżecie, przez fakturę za pakiet, zastąpione kwoty BS).
- **Ostrzeżenia** (pulpit, arkusz, Do weryfikacji, ekran listy): dotychczasowe (a) lista niewpisana po terminie wypłaty,
  (b) estymacja niższa niż ostatnia lista, (c) lista inna niż przelew o ponad 1 zł, plus „Lista płac do wpisania”: w miesiącu
  są płatności wynagrodzeń z kopii BS, a listy nie ma. ZUS (DRA) i PIT-4 z list porównywane z przelewem za miesiąc wypłaty
  (wcześniej ZUS porównywał się z okresem o miesiąc za wcześnie).
- API: `GET /api/lista-plac?miesiac=` (osoby z polami `wpisane`, `bs`, `bs_razem`, `roznica_bs`, `koszt_pracodawcy`,
  `data_wyplaty`; `ppk`, `ppk_mapa`, `koszt`, `uwaga`), zapis `POST /api/zmiana` z `typ: lista_plac`
  (`{miesiac, pozycje: [{wiersz, osoba, us, zus, ppk_pracownik, ppk_pracodawca, pakiet, potracenia, data_wyplaty, uwaga}],
  ppk: {wiersz, miesiac, termin}, uwaga}` albo `{miesiac, usun: true}`).

## Pakiet 6: kopia z Budget Studio i kontrola zgodności (2026-10-19)

Moduł `finanse/kopia_bs.py`, ekran Budżet, „Zgodność z BS i kopia” (`web/kopia_bs.js`), karta w Ustawieniach budżetu.

- **Kopia jako model planu, nie zrzut płatności.** Z najnowszego eksportu BS (cały 2026 z historią): arkusze (zakres poszerzony do
  miesięcy płatności), wiersze z ustawieniami wyprowadzonymi z planów (reguła dnia wystawienia, dni na płatność, stawka, metoda,
  Księgowane, W cash flow), komórki z kwotami. Plany liczy generator z pakietu 2; to, czym plan BS różni się od reguły wiersza (data,
  aktualność, komentarz, stawka planu zerowego), przechodzi jako ręczna zmiana pojedynczego planu. Umowa o pracę: trzy wiersze BS
  („- dla wykonawcy”, „- PIT”, „- ZUS”, ta sama płatność BS) scalone w jeden wiersz „Umowa o pracę” z proporcjami z najpóźniejszej
  komórki z planami; płatności dostają składową i spinacz. Rzeczywiste przechodzą 1:1. Komórka, której generator nie odtworzy co do
  grosza (np. dwa plany faktury w jednym miesiącu), zostaje jako plany z eksportu.
- **Podział z eksportu:** worek zawsze z kwot tygodni BS (także miniony miesiąc zwinięty do jednego planu i bieżący z pozostałymi
  tygodniami), umowa, gdy proporcje wiersza dają inny grosz. Podział obowiązuje, dopóki sumuje się do kwoty komórki; zmiana kwoty,
  podstawy albo proporcji wraca do reguły. Raport podaje, ile komórek zgadza się z regułą (worek od wtorku, umowy z proporcji).
- **Podgląd przed zapisem:** `GET /api/budzet/kopia` liczy kopię i raport kontroli sum bez żadnego zapisu (mapa ID w kopii roboczej).
  **Przyjęcie:** `POST /api/kopia-bs` z sumą eksportu z podglądu; tylko przy 0 różnic i tym samym eksporcie. Zapis:
  `Finanse/Aplikacja/kopia_bs_RRRR-MM-DD.json` (600), raport `..._kontrola.xlsx` (600) i jeden wpis `kopia_bs` (plik i jego SHA-256)
  w pliku zmian. Wpisu `kopia_bs` nie da się dodać przez `/api/zmiana`. Kopię można powtórzyć albo cofnąć (`cofnij`).
- **Kopia źródłem budżetu:** przy odbudowie model to kopia, a na nią nakładają się zdarzenia `bud` zapisane po niej (wcześniejsze
  przestają obowiązywać; podgląd mówi, ile ich jest). Kolejne eksporty BS jej nie nadpisują. Brak pliku kopii albo inna treść niż przy
  przyjęciu: błąd w raporcie odbudowy i budżet z importu. Pliki kopii są w odcisku źródeł (iCloud dociągnie kopię, baza przeliczy się sama).
- **Kontrola sum:** arkusz × miesiąc × rodzaj × typ (plan, rzeczywista): liczba, netto, VAT, brutto w BS i w apce; salda arkuszy i
  całości; cash flow (brutto wg miesiąca dnia realnej płatności) i wynik (netto wg miesiąca księgowania) w każdym miesiącu; płatność po
  płatności po ID z BS (arkusz, miesiąc, typ, kwoty, dzień wystawienia i realny, Księgowane, W cash flow, aktualność) z przyczyną.
  Strona BS czyta kwoty, daty i przełączniki wprost z wierszy pliku; liczba płatności sprawdzana też wprost z pliku.
  Po kopii aktualność nie jest różnicą (BS sam przestawia plan na nieaktualny, gdy minie data), a cash flow i wynik liczą wszystkie płatności.
- **Okres równoległy (od 1.11):** ekran „Zgodność z BS” porównuje najnowszy eksport z bazą apki tym samym raportem, a odbudowa dopisuje
  do Rozjazdów grupy „Plan w BS inny niż w apce” (komórka wiersz × miesiąc, suma netto), „Wiersz jest tylko w BS” i „Wiersz jest tylko
  w apce”. Wiersze łączone po mapie stałych ID (pakiet 1), umowy po scaleniu składowych, wiersz dodany osobno w obu miejscach po
  arkuszu, rodzaju, kontrahencie, komentarzu i przedmiocie.
- **Daniny po pakiecie 8:** w bazie wiersze VAT i podatku dochodowego z BS zastępuje arkusz systemowy „Opłaty urzędowe”, więc ekran
  zgodności (baza kontra eksport) i grupy okresu równoległego porównują tylko zwykłe wiersze (bez danin po obu stronach; liczba
  płatności też bez nich). Zgodność danin z BS pokazuje ekran Podatki. Podgląd i przyjęcie kopii porównują całą kopię, z daninami.
- **Przełącznik `import_bs`** (wpis `ustawienie`, domyślnie tak): „nie” = apka nie czyta eksportów BS (ani budżetu, ani podpowiedzi
  klientów); z kopią budżet działa dalej, bez kopii jest pusty (APK-FLAG-02).
- **Wynik na eksporcie z 14.10.2026** (kopia danych, nie prawdziwy folder): 0 różnic, ta sama liczba płatności w pliku, w imporcie i w apce;
  po przyjęciu kopii salda arkuszy, etapy, rozjazdy z bankiem, cash flow 13 tygodni i rentowność arkuszy identyczne jak przy imporcie.
  Testy: `testy/test_pakiet6.py`, `testy_odbioru/test_pakiet6.py` (opcjonalnie klucz `kopia_bs` w `odbior.json`).

## Pakiet 7: listy płatności, filtry i UX tabel (2026-10-19)

Wszystkie listy menu Płatności (połączone z budżetem, Do połączenia, Do weryfikacji, bank, faktury, należności, rejestr
zakupów) i wydatki z banku działają na jednym silniku (`web/listy.js`), z jedną drogą danych `GET /api/lista/<ekran>`
(`finanse/zapytania_listy.py`, zapytania list w `finanse/zapytania.py`). Stan listy (filtry, sortowanie, kolumny) żyje w adresie.

- **Sortowanie po stronie serwera** po każdej kolumnie: biała lista per lista (`KOL_*`: klucz z interfejsu → wyrażenie SQL),
  tekst po polsku (porządek `PL` rejestrowany na połączeniu, `filtry.klucz_pl`), puste na końcu, stały dalszy porządek.
- **Filtry podręczne** nad listą (płatności: rodzaj, podstawa z nazwami składowych umów, status aktualności, etap; wielokrotny
  wybór rozdzielony `|`) i **panel „Wygląd i filtry”** (`web/panel.js`, wspólny z cash flow): widoczne kolumny i ich kolejność,
  sortowanie, zakres listy, typ (plan, rzeczywista), kontrahent, folder, kategoria, arkusz, sekcja, przedmiot, metoda,
  Księgowane, W cash flow i daty. Kolumny pamięta przeglądarka per lista (wygoda); zapisany widok ma własne kolumny.
- **Filtr daty jak w BS** (`finanse/filtry.py`, A-FIL-01 do 07): dzień wystawienia, płatności, realnej płatności, miesiąc
  księgowania i budżetowy; tryby wszystko, bieżący okres, od dziś do końca okresu, zakres statyczny, zakres ruchomy
  (jednostka, długość N, przesunięcie K, kotwica dnia tygodnia) i szybki wybór (najbliższe 2 tyg., ten miesiąc, poprzedni
  miesiąc…). Zapis w adresie, np. `d_realny=ruchomy:dzien:14:0`; „dziś” to dzień stanu, więc daty względne liczą się od nowa
  przy każdym otwarciu. Podgląd „dziś, jutro, za miesiąc” liczy serwer (`GET /api/zakres`), tą samą funkcją co filtr.
- **Zapisane widoki** (B-LIS-03): zdarzenie `widok` w pliku zmian (`finanse/widoki.py` → tabela `widoki`): zapisz jako, zapisz
  zmiany, zmień nazwę, usuń (domyślnego nie), „Przywróć” wraca do filtrów widoku. Startowe (`WIDOKI_STARTOWE`): dawne listy menu
  (wszystkie, nieopłacone, niewystawione, po terminie, do wystawienia i do zapłacenia w 2 tyg., zapłacone) oraz do wystawienia do
  końca miesiąca i największe koszty miesiąca; też dla banku, faktur, należności, rejestru i wydatków. Stare linki
  (`?lista=…&rodzaj=…`, `?od=&do=`) działają.
- **Menu z licznikami**: widoki każdej listy z liczbą pozycji (`GET /api/listy/menu`, liczone przy każdym otwarciu menu).
- **Zaznaczanie** (APK-BRAK-08): numer wiersza zamienia się w pole wyboru, Shift + klik zaznacza zakres, w nagłówku „zaznacz
  wszystkie na stronie”, w pasku „Zaznacz wszystkie wyniki” (do 5000). **Pasek podsumowania zaznaczenia**: liczba, netto, VAT,
  brutto osobno dla wpływów i obciążeń i razem (podsumowanie wszystkich wyników liczy też serwer: `podsumowanie` w odpowiedzi).
- **Akcje grupowe**, każda jako jeden wpis w pliku zmian (wszystko albo nic, cofnięcie całości): płatności budżetu: zmień dzień
  realnej płatności i opłacona poza bankiem z datą (seria `bud`, przy włączonym planowaniu); faktury i należności: opłacona poza
  bankiem z datą (`poza_bankiem` z polem `data`, data zapłaty trafia do stanu faktury), przypisz klienta; wpłaty: nie dotyczy
  faktury; wydatki: rodzaj i klient (tylko te płatności albo reguła dla kontrahentów); Do weryfikacji: potwierdź, odrzuć,
  sprawdzone; wszędzie: przenieś do Do weryfikacji i eksport zaznaczonych do CSV (UTF-8 z BOM, średnik, przecinek dziesiętny,
  daty ISO, kolumny jak na liście; plik powstaje w przeglądarce). Akcja niepasująca do zaznaczenia jest nieaktywna z powodem.
- **Seria z listy**: nowy typ wpisu `seria` (`zmiany.TYPY_W_SERII`, do 1000 wpisów); serwer sprawdza odwołania każdego wpisu,
  zanim cokolwiek zapisze; `zmiany.wczytaj()` rozwija serię w zwykłe wpisy, więc moduły liczące nie wymagały zmian.
- **Do weryfikacji**: nowy typ `do_weryfikacji` (operacja, faktura, dokument z rejestru, płatność budżetu; `usun` = sprawdzone),
  pozycje w grupie „Przeniesione do sprawdzenia”; lista ma strony, sortowanie, wyszukiwarkę i filtr daty.
- **Widoczny typ płatności**: kolumny Podstawa płatności i Typ (plan, rzeczywista), piguła rodzaju, chip etapu, kropka
  aktualności, tło planu i po terminie.

Po scaleniu z pakietem 10: przyciski „Pobierz: Excel, CSV” nad listą eksportują `lista/<ekran>` z tymi samymi parametrami
(widok, filtry dat i cech, sortowanie), wszystkie strony; suma = stopka listy (`eksport.lista_wszystkie`, testy w `test_pakiet10.py`).
Z pakietem 8: daniny z arkusza systemowego Opłaty urzędowe są na liście płatności, ale akcje grupowe budżetu (dzień realny,
opłacona poza bankiem) są dla nich nieaktywne z podpowiedzią (kwota od biura i dzień realny w Budżet, Podatki).

Poza zakresem: typy dat „data dodania” i „data ostatniej edycji” (A-FIL-01; dane z importu ich nie mają), usuwanie i łączenie
rzeczywistych z listy (pakiet 5), skrót Ctrl/Cmd+F (pakiet 11).

## Pakiet 8: VAT, podatki, wynagrodzenia (2026-10-19)

Reguły w `finanse/podatki.py` (rdzeń bez bazy, testowalny wprost), ekran w `web/podatki.js` (Budżet, Podatki: „Podatki i ZUS”
i „Ustawienia podatków”), API `GET /api/podatki`.

- **Arkusz systemowy „Opłaty urzędowe RRRR”** (folder System, jeden na każdy rok od najwcześniejszego do najdalszego miesiąca
  arkuszy budżetu) liczony przy każdej odbudowie, po zdarzeniach Mata (`podatki.dolacz` w `budzet.zbuduj`). Wiersze z podstawą
  Podatek VAT i Podatek dochodowy z eksportu BS wychodzą z modelu: rzeczywiste stają się kwotami od biura, plany prognozą BS
  (kolumna do porównania), puste arkusze podatkowe BS znikają. Liczby w raporcie odbudowy (`arkuszy`, `wierszy`, `platnosci`)
  są jak w eksporcie BS, bez arkusza systemowego. Zmiany `bud` na obiektach `sys:` i podstawy podatkowe w zwykłych wierszach serwer odrzuca.
- **VAT** = VAT wpływów − VAT obciążeń z płatności z podstawą Faktura (plany i rzeczywiste, także nieaktualne, jak w BS),
  Księgowane = tak, okres wg miesiąca księgowania. Nadpłata przechodzi na kolejne okresy, a po ostatnim okresie budżetu staje się
  planem zwrotu (wystawienie 30.04, termin z ustawień, BS: 14.06 roku następnego). Termin 25. dnia po okresie. Na eksporcie BS
  z 14.10.2026 prognozy wrzesień 2026 do grudnia 2027 i zwrot są równe BS co do grosza.
- **CIT** = max(0, podstawa narastająco w roku × stawka − zaliczki wcześniejszych okresów roku), podstawa = netto księgowanych
  wpływów − netto księgowanych obciążeń (bez faktury: wartość, umowy: składowe). Po roku zwrot nadpłaty zaliczek (wpływ);
  niedopłaty system nie planuje, tylko ją pokazuje. Wynik zarządczy bez zmian (daniny mają Księgowane = nie, jak w BS).
- **Kwota od biura** (wpis `danina`: VAT, CIT, zwrot VAT, CIT roczny; kwota, kierunek: do zapłaty, nadwyżka do przeniesienia,
  zwrot; termin, dzień realny, komentarz; `usun` = powrót do prognozy) zamraża okres: płatność rzeczywista, bez przeliczeń,
  kwota zasila saldo nadpłaty. Wpis w apce wygrywa z kwotą z eksportu BS. Dzień realny najwcześniej dzień po końcu okresu.
- **Ustawienia** (wpis `ustawienie`, klucz `podatki`, część pól wystarczy): okres VAT, termin VAT, przenoszenie nadpłaty,
  nadwyżka VAT na start, termin zwrotu, okres CIT (domyślnie kwartał), stawka CIT (domyślnie 19, brak = bez prognozy), termin CIT,
  zaokrąglenie zaliczki, co płacimy z rachunku VAT. Domyślne jak w BS DigitalH, wszystkie do potwierdzenia z biurem.
- **Przelewy z banku**: urząd skarbowy i ZUS z rachunku głównego i online, okres z tytułu (`/OKR/26M08/`, kwartał `26K01`,
  `DRA 01/08`); okres VAT równy miesiącowi przelewu albo późniejszy to pomyłka w tytule, wtedy poprzedni miesiąc.
- **PIT-4 i ZUS**: składowe umów z budżetu (pakiet 2) wg miesiąca wypłaty, obok przelewy; terminy 20. i 15.
- **Rachunek VAT** (13 tygodni): start z ING, wpływy = VAT z wpłat MPP (należności i plany; wiersz ze Split payment = cały VAT,
  inaczej udział MPP klienta z historii wpłat połączonych z fakturami), wypływy = VAT z kosztów ze Split payment i daniny płacone
  najpierw z rachunku VAT (jak w wyciągach ING), resztę dokłada rachunek główny. Gotówka w cash flow dalej bez rachunku VAT.
- `GET /api/vat` (ekran Podatek VAT) ma dodatkowo `prognoza`, `od_biura`, `roznica_biuro` z arkusza systemowego.

## Pakiet 9: cash flow jak w BS, umowy w cash flow (2026-10-19)

Serwer: `finanse/cashflow.py` (okresy, pozycje, lista wycinka, prognoza 13 tygodni), `finanse/umowy.py` (powiązanie umowy
z budżetem). Ekran: `web/cashflow.js` (przeniesiony z `web/budzet.js`, ładowany po `listy.js`).

- **Tryb domyślny jak w BS (decyzja 8):** po dniu stanu wyłącznie płatności budżetu z „W cash flow = tak”: plany
  i rzeczywiste nieopłacone, na dniu realnej płatności, brutto; przed dniem stanu historia z banku. Szacunek kosztów
  i należności z faktur spoza budżetu to opcje („Pochodzenie” w „Wygląd i filtry”), domyślnie wyłączone, wyróżnione.
- **Etap i aktualność jak w BS:** filtr etapu (domyślnie bez opłaconych), statusu aktualności, podstawy, rodzaju i dat
  (wystawienia, płatności, realnej, miesiąc księgowania; tryby z pakietu 7). Zaległość (nieopłacona, minął dzień realny)
  zostaje na swoim dniu, scenariusz pełny liczy ją za 7 dni. Rzeczywista „Niewymagana” w BS (np. przyszły ZUS) jest
  w cash flow (uwaga z pakietu 8, naprawiona u źródła w `laczenie.py` przez pakiet 5; `_etap_cf` bierze etap stamtąd). Historia „z budżetu” pokazuje przeszłość jak BS.
- **Umowy (decyzje 9 do 11):** umowa ma folder klienta i arkusze przychodowe (domyślnie wszystkie arkusze folderu
  z wpływami; stary wpis z samym klientem dopasowany po nazwie przy odczycie). Pozycje „z umowy” po ostatnim planie
  wpływu klienta (netto z umowy + VAT wg wiersza, termin koniec miesiąca + dni z wiersza, domyślnie 23% i 7 dni),
  bez nich po końcu umowy na czas określony (plany zostają z ostrzeżeniem). Scenariusz „klienci odchodzą”.
  API: `/api/umowy` (folder, arkusze, stan, ostatni dzień wypowiedzenia obu stron, odejście przy wypowiedzeniu dziś,
  plany po końcu, klienci bez umowy), `/api/umowy?arkusz=`, pole `umowa` w `/api/budzet/arkusz`.
- **Lista wycinka:** `GET /api/lista/cashflow` (silnik list z pakietu 7), zapisane widoki: zdarzenie `widok`, ekran `cashflow`.
- **Odbiór na eksporcie BS z 14.10.2026:** tryb domyślny od dnia stanu: 16 z 17 miesięcy co do grosza; październik
  różni się tylko etapem opłacenia (1 płatność opłacona w banku, w BS nieopłacona; 2 opłacone w BS po dniu stanu ING).

- **Ekran Umowy:** formularz z folderem klienta i arkuszami przychodowymi (puste zaznaczenie = wszystkie arkusze folderu
  z wpływami), nasz okres wypowiedzenia osobno, kolumna „Odejście przy wypowiedzeniu dziś”, lista klientów bez umowy
  z przyciskiem „dodaj umowę”. Arkusz z planami wpływów po końcu umowy na czas określony ma ostrzeżenie nad tabelą
  (decyzja 10), cash flow znacznik „!” w nagłówku okresu.
- **Akcje masowe na liście wycinka:** zmiana dnia realnej płatności (jeden wpis `bud` z `op: seria`, wszystko albo nic,
  wykres i tabela przeliczone od razu), opłacona poza bankiem z datą (wyjątki, decyzja 3), do weryfikacji, eksport CSV.
  „Odłącz od budżetu” (pakiet 5, `web/laczenie.js`) nad listą wycinka: bierze cały wycinek z serwera, plany i rzeczywiste
  połączone w apce.
- **Cash flow arkusza:** zakładka „Cash flow” w arkuszu, tylko jego płatności, bez danin, PIT i ZUS z umów, saldo startowe 0.
- **Testy:** `testy/test_pakiet9.py` (21, w tym klasa `TestKryteriumOdbioru`: przesunięcie 3 planów o tydzień jedną serią,
  seria wszystko albo nic, MIN i MAX jak ręczne przeliczenie, miesiąc = suma tygodni i dni, faktura połączona z planem
  liczona raz), `testy_odbioru/test_pakiet9.py` (3). Ekran sprawdzony w przeglądarce na kopii danych w katalogu tymczasowym.

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
  Raport kontroli sum kopii z BS (`kontrola-bs`, pakiet 6) ma własną drogę w serwerze. Płatności budżetu w układzie BS zawierają
  arkusz systemowy Opłaty urzędowe z pakietu 8 (ID `sys:…`) zamiast wierszy VAT i podatku dochodowego z BS.
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

## Pakiet 11: karta klienta z umową, rentowność budżetu, widoki arkusza, wygoda (2026-10-19)

Moduły serwera: `finanse/karta_klienta.py` (lista i karta klienta, alerty umów), `finanse/przestawna.py` (rentowność budżetu),
`finanse/ostrzezenia_wierszy.py` (ustawienia wierszy psujące prognozę), `finanse/ekrany.py` (odczyty nowych ekranów w jednym miejscu,
serwer woła `ekrany.ODCZYTY`). Interfejs w nowych plikach: `web/klienci.js`, `web/pulpit.js`, `web/przestawna.js`,
`web/arkusz_widoki.js`, `web/skroty.js`, `web/dodatki.css`.

- **Karta klienta (BL-02, część formalna)**, `#/budzet/klient?nazwa=` (`GET /api/klienci/karta?nazwa=&rok=`): dane klienta (NIP i nabywcy
  z faktur, folder budżetu, arkusze, ostatni plan wpływu), umowa edytowana na miejscu (data podpisania, czas określony albo nieokreślony,
  koniec, przedłużanie, okres wypowiedzenia, na koniec miesiąca, wartość netto miesięcznie, alert w dniach, uwagi; zapis istniejącym
  wpisem `umowa`), stan umowy (ok, alert, minął, brak umowy), ostatni dzień na wypowiedzenie z naszej i ich strony, termin odejścia przy
  wypowiedzeniu dziś, obroty i należności, rentowność (wynik zarządczy klienta obok wyniku budżetu jego folderu), plany w budżecie na
  12 miesięcy obok wartości z umowy, faktury i koszty. Ostrzeżenia: brak umowy przy planach wpływów, plany wpływów po końcu umowy
  na czas określony (decyzja Mata 10: plany zostają w cash flow, apka ostrzega na karcie, w arkuszu i na pulpicie).
- **Lista klientów** (`#/budzet`): kolumny umowy (stan, typ, wypowiedzenie, termin, wartość) i plany wpływów 12 miesięcy obok obrotów;
  filtry rok, stan umowy (także „do decyzji”), typ umowy, szukaj; sortowanie po każdej kolumnie (lokalnie, lista ma kilkadziesiąt
  pozycji). Dane: `GET /api/klienci` (z niego eksport do Excela) + `GET /api/klienci/umowy`.
- **Pulpit:** w żółtym pasku „Plany nieaktualne” (licznik i link do listy planów z filtrem, rytuał tygodniowy B-INNE-03) i „Ustawienia
  wierszy do sprawdzenia”; baner alertów umów (`GET /api/pulpit/alerty`), kafel umów, kafel rachunku VAT (`/api/podatki` →
  `rachunek_vat.vat_najblizszy`: kwota, termin, ile dołożyć z rachunku głównego), kafel „Lista płac do wpisania” (patrz niżej).
- **Ekran Podatek VAT:** kolumny prognoza z budżetu, kwota od biura, różnica (`wynik.vat`), filtr roku; miesiące z samą prognozą też
  na liście. Te same kolumny w eksporcie VAT.
- **Rentowność budżetu** (`#/rentownosc/przestawna`, `GET /api/rentownosc/przestawna?rok=&poziomy=&os=&folder=`): tabela przestawna
  płatności budżetu z Księgowane = tak (plany i rzeczywiste, netto, aktualne jak w komórkach arkusza, bez arkusza systemowego), wiersze
  wg do czterech poziomów (folder, kategoria, arkusz, sekcja, przedmiot, kontrahent) z rozwijaniem, kolumny miesięcy, wartości wynik,
  wpływy, obciążenia albo marża; oś miesiąc budżetu albo księgowania. Pod tabelą wynik zarządczy z banku i faktur i różnica.
  Wynik folderu = suma jego arkuszy (test).
- **Arkusz:** widoki arkusza (A-ARK-02, wpis `widok` z ekranem `arkusz` i parametrem `arkusz`; menu w pigułce pod tytułem: zapisz jako,
  zapisz zmiany, zmień nazwę, usuń, przywróć), przypinanie (model z pakietu 4: pole `przypiety` arkusza, `GET /api/budzet/przypiete`),
  wybór serii wykresu (A-ARK-07, parametr `serie`), ostrzeżenia ustawień wierszy (A-CF-17: worek przy stałej opłacie, faktura kosztowa
  poza cash flow, 23% u kontrahenta z zagranicy, dzień wystawienia inny niż na fakturach; znak „!” przy wierszu, lista nad tabelą,
  ekran `#/budzet/ostrzezenia`), daniny brązowym tekstem (A-INN-07) na listach i w arkuszu systemowym.
- **Skróty (A-INN-06):** „?” lista skrótów, Cmd+K pomoc z wyszukiwarką (pole wyszukiwania w panelu pomocy zawsze), Cmd+F wyszukiwarka
  listy, Cmd+Enter karta zaznaczonego albo wskazanego wiersza listy.
- **Pomoc:** nowe i krótsze teksty: podatki, kopia z BS, łączenie z budżetem, Podatek VAT, karta i lista klientów, rentowność budżetu,
  alerty umów, rachunek VAT, lista płac, plany nieaktualne, widoki arkusza, ustawienia wierszy, skróty.
- Drobne: filtr roku w Obrotach wg klientów i Rentowności klientów (APK-BRAK-14), martwy `wBudowie()` usunięty (APK-BUG-09).

**Dane z pakietów 9 i 5 (po scaleniu 2026-10-20):** karta klienta bierze z `umowy.lista()` (pakiet 9) folder, arkusze wskazane
w umowie, ostatni dzień na wypowiedzenie obu stron (`{klient, my}` jako `{ich, nasza}`), odejście przy wypowiedzeniu dziś (strona
klienta, jak scenariusz „klienci odchodzą” w cash flow) i plany po końcu umowy (`umowy.plany_po_koncu`); sama już tego nie liczy.
Bez umowy: folder o nazwie klienta. Formularz karty odsyła surowy wpis umowy (folder i arkusze tak, jak zapisane), więc zapis
z karty nie utrwala wartości wyliczonych. Kafel „Lista płac do wpisania” na pulpicie czyta `GET /api/ostrzezenia` (pakiet 5):
`lista_niewpisana` = czerwony, `estymacja_nizsza` i `lista_vs_przelew` = żółty, link do listy płac za miesiąc; pasek nad pulpitem
z pakietu 5 pokazuje wtedy tylko Do połączenia.

**Testy:** `testy/test_pakiet11.py` (zmyślone dane: wynik folderu = suma arkuszy, tylko Księgowane, ostrzeżenie dla worka z jedną
płatnością miesięcznie i pozostałe reguły ostrzeżeń, terminy umowy, alerty, przypięcia i widoki z cofnięciem, licznik planów
nieaktualnych, kolumny VAT, nowe adresy serwera), `testy_odbioru/test_pakiet11.py` (prawdziwe pliki, te same reguły).

**Nie w tym pakiecie:** waluty (APK-BRAK-15, brak planów w walucie), estymata czasu per osoba (APK-BRAK-05, czeka na decyzję Mata).

### Stan etapów i planowania (APK-BRAK-04)

Etap 6 (pulpit jak w Budget Studio, eksport) jest gotowy: pakiet UX (pulpit, kafle), pakiet 10 (eksport) i pakiet 11 (alerty, kafle VAT
i umów). Planowanie w apce jest wyłączone do 1.11.2026; włącza je Mat w Budżet, Ustawienia budżetu (decyzja Mata 5).
