# Brief: Finanse lokalne (warstwa CFO dla DigitalH)

Zlecający: Mat (CEO DigitalH). Przygotowano: 2026-10-14, w sesji trybu finansowego.
Wykonawca: sesja Claude Code w trybie deweloperskim w tym repo.

## 1. Po co

DigitalH prowadzi finanse zarządcze w Budget Studio (SaaS). Uzgodnienie z bankiem z 13.10.2026 pokazało, że Budget Studio jest niekompletne: prowadzone od lutego, płatności nieodhaczone w terminie same przechodzą w „Nieaktualne” i wypadają z wyliczeń, VAT nieodhaczany, dywidenda wpisana jako koszt. Efekt: Budget Studio pokazywało stratę, a według ksiąg I półrocze to 63,5 tys. zł zysku brutto.

Budujemy **lokalną aplikację**, która z danych źródłowych (bank, faktury, księgi) liczy sama to, czego Budget Studio nie robi albo robi źle. Najważniejsze: **automatyczne dopasowanie płatności z banku**, żeby nikt nie musiał niczego ręcznie odhaczać. Przez 2–3 miesiące działa równolegle z Budget Studio; potem Mat decyduje, czy z Budget Studio rezygnuje.

Użytkownik: jeden (Mat), na jednym Macu. Nie ma zespołu, logowania ani pracy wielu osób.

## 2. Zasady twarde (nie do negocjacji)

1. **Dane finansowe nigdy w repo.** To repo ma zdalną kopię na GitHubie. W repo tylko kod, testy na danych zmyślonych i dokumentacja. Dane i baza żyją w `~/Documents/DigitalH/Finanse/` (iCloud z szyfrowaniem end-to-end). Ścieżki do danych w konfiguracji poza repo albo jako stałe wskazujące na ten folder; w `.gitignore` zabezpiecz `*.sqlite`, `*.csv`, `*.xlsx`, `*.xls` w katalogu apki.
2. **Surowe pliki w `Finanse/Raporty/Dane/` są tylko do odczytu.** Aplikacja ich nie zmienia ani nie przenosi.
3. **Tylko odczyt z narzędzi zewnętrznych.** Jedyny dozwolony ruch sieciowy: `GET` do API Budget Studio (lista płatności). Zero zapisu do Budget Studio, Fakturowni, banku, Gmaila, ClickUp. Zero bibliotek z CDN, zero analityki, zero wysyłki danych gdziekolwiek.
4. **Serwer tylko na `127.0.0.1`**, nigdy na wszystkie interfejsy (audyt Maca z 11.10 wykrył podgląd widoczny w sieci Wi-Fi).
5. **Sekrety tylko w pęku kluczy macOS.** Budget Studio: `security find-generic-password -s digitalh-budget-studio -a BUDGET_STUDIO_API_KEY -w`. Klucz nigdy w pliku, logu ani wyjściu; do curla przez stdin (wzór w `Finanse/Raporty/Skrypty/Pobierz dane z Budget Studio.command`).
6. **Pliki z danymi i baza z uprawnieniami 600.**
7. **Liczby tylko z kodu, testowalne.** Każda wartość na ekranie ma źródło (plik, wiersz). Zgadywanie i ręcznie wpisane liczby w kodzie są zabronione, poza stałymi celami biznesowymi opisanymi niżej.
8. Interfejs po polsku, prosty język, **bez długich myślników (—)** w tekstach UI. Kwoty w formacie `12 345,67 zł`.
9. Reguły repo z `CLAUDE.md` obowiązują: pytaj przed wszystkim, czego nie da się cofnąć; push na GitHub i zmiany konfiguracji tylko za zgodą Mata; po każdym etapie wpis w vaulcie `_Wewnętrzne/Aplikacje wewnętrzne.md` (Kronika) i wiersz w `apps/STAN.md`.

## 3. Dane wejściowe (formaty sprawdzone 13–14.10.2026)

Katalog: `~/Documents/DigitalH/Finanse/Raporty/Dane/` (mapa i zasady nazw w `~/Documents/DigitalH/Finanse/CLAUDE.md`). Zawsze bierz **najnowszy** plik danego rodzaju (data w nazwie).

| Źródło | Plik | Format | Uwagi |
|---|---|---|---|
| Bank ING | `ING/ing_historia_RRRR-MM-DD_RRRR-MM-DD.csv` | CSV UTF-8 z BOM, `;`, przecinek dziesiętny, cudzysłowy, nagłówek | kolumny: data transakcji, data księgowania, kwota, waluta operacji, oryginalna kwota/waluta, saldo po transakcji, nazwa i adres kontrahenta, rachunek kontrahenta, nazwa transakcji i opis, szczegóły płatności linia 1–4 (= tytuł), rachunek ING "NRB" (26 znaków), numer referencyjny. **Kolejność: najnowsze na górze** (saldo bieżące = pierwszy wiersz danego rachunku). Rachunki po końcówce NRB: `5263` główny, `5271` online (karty, subskrypcje), `5289` VAT. Przelewy między nimi (kontrahent „DIGITALH SPÓŁKA…”) i cały rachunek VAT to ruch wewnętrzny. Kolejne eksporty mogą się nakładać: deduplikacja po numerze referencyjnym (gdy pusty: data+kwota+tytuł+rachunek). |
| Fakturownia, sprzedaż | `Fakturownia/fakturownia_sprzedaz_RRRR-MM-DD.csv` | CSV UTF-8, `,` | **jeden wiersz = jedna pozycja faktury** (faktura może mieć kilka wierszy; deduplikuj po `numer`). Kluczowe: numer, Status (Wystawiona/Opłacona), Data wystawienia, Data sprzedaży, Termin płatności, Nabywca, NIP, Wartość netto/VAT/brutto PLN, Kwota opłacona, Numer KSeF, Produkt/usługa. Korekty mają własny numer i ujemne wartości. |
| Budget Studio | `Budget Studio/budget_studio_RRRR-MM-DD.csv` | CSV UTF-8, **tabulator** | z API (`GET https://api.budget.studio/api/payments-list/csv?separateBudgets=true`, nagłówek `API-KEY`). Kolumny m.in.: ID, Rodzaj (1 przychód / -1 koszt), Status aktualności, Etap płatności, Podstawa płatności, Numer dokumentu, Kontrahent, Netto/Brutto (wartość, przecinek), Miesiąc budżetowy, Dzień płatności, Dzień płatności - realny, Arkusz, Folder (= klient), Kategoria. Uwaga: ID może się powtarzać w eksporcie (ten sam rekord w kilku budżetach). |
| Biuro, rejestr zakupów | `Biuro/biuro_rejestr_zakupow_OD_DO.xlsx` | xlsx | arkusze `krajowe` (Nr ewid., Nr dok., Data, Data zaewid., Podmiot, 8% Netto, 8% VAT, 23% Netto, 23% VAT, Brutto) i `zagraniczne` (… Podmiot, Netto). Podmiot ma sufiks „(00024)” do obcięcia. Ostatnie wiersze to sumy, pomiń. Pełna lista kosztów fakturowych. |
| Biuro, wyniki | `Biuro/biuro_wyniki_RRRR-MM.xls` | xls (enova), arkusze `RZiS` i `Bilans` | wynik według ksiąg narastająco; punkt odniesienia do testów. Czytane przez `xlrd`. |
| Dysk Google (lokalna synchronizacja) | `~/Library/CloudStorage/GoogleDrive-mat@digitalh.pl/Mój dysk/Administracyjne/Faktury/<rok>/` | PDF | opcjonalnie; od kwietnia nazwy `{Wystawca}-{Nr}_{Kwota}{Waluta}_{RRRR-MM-DD}.pdf`. |

## 4. Co już istnieje (użyj, nie pisz od nowa)

`~/Documents/DigitalH/Finanse/Raporty/Skrypty/` (poza repo, z danymi obok):
- `wspolne.py`: wczytywanie ING i Budget Studio, parsowanie kwot.
- `uzgodnienie_bs_ing.py`: dopasowanie Budget Studio ↔ bank (kwota, data, nazwa, wiele faktur w jednym przelewie, podatki osobno, normalizacja polskich znaków).
- `naleznosci.py`: należności z Fakturowni sprawdzone w banku po numerze faktury w tytule (regex odporny na `FV20 26_08_3`) i po numerze KSeF bez sumy kontrolnej.
- `koszty_z_dysku.py`: spis dokumentów z Dysku.
- `dashboard.py`: dashboard HTML, paleta zwalidowana (jasny: `#3D4BE0` / `#E0601F`, ciemny: `#6F7BF2` / `#E36D30`), tryb ciemny, tooltipy, tabela pod wykresem.
- `.venv` z `xlrd` i `openpyxl` (systemowy Python ma PEP 668, instaluj tylko w venv).

Przenieś logikę do apki (z testami), skrypty mogą zostać jako narzędzia awaryjne.

## 5. Zakres MVP (kolejność = priorytet)

1. **Import i księga operacji.** Jedna baza SQLite (w `~/Documents/DigitalH/Finanse/Aplikacja/`), import idempotentny (ponowny import tego samego pliku nic nie dubluje), oznaczanie ruchu wewnętrznego, rachunek przy każdej operacji, log importów.
2. **Automatyczne dopasowanie wpłat do faktur sprzedażowych.** Po numerze faktury w tytule, po numerze KSeF, po sumie kilku faktur tego samego nabywcy (jeden przelew za kilka faktur), po kwocie i dacie jako ostatni wybór z oznaczeniem „prawdopodobne”. Korekty pomniejszają należność.
3. **Należności z wiekowaniem** (przed terminem, 1–30, 31–60, 61–90, ponad 90 dni). **Bez rekompensat ustawowych** (decyzja Mata 13.10).
4. **Dopasowanie wydatków z banku do rejestru zakupów** (kwota, data ±40 dni, nazwa; karty w walutach z tolerancją kursową). Wynik: co opłacone, co w banku bez dokumentu, co w rejestrze bez płatności.
5. **Mapa klientów.** Reguły „płatnik → klient” (płatnik o innej nazwie niż klient, firma z grupy klienta), najlepiej po NIP z Fakturowni; edytowalne w aplikacji (to są dane, nie kod). Reguły „koszt → klient / koszt przenoszony / koszt stały”.
6. **Wynik zarządczy miesięcznie:** przychód netto agencji (obrót minus koszty przenoszone: media, druk, podwykonawcy), koszty pracy z banku (wypłaty + ZUS + PIT-4), koszty stałe, wynik. **Dywidenda to „Podział zysku”, nie koszt**. VAT poza wynikiem. Uwaga przy porównaniu z Budget Studio: tam pensje są wpisane jako **koszt pracodawcy** per osoba (w tym zdrowotna i PIT), a bank pokazuje przelew na rękę plus zbiorcze ZUS i PIT-4; porównywać sumę kosztu pracy w miesiącu, nie pojedyncze przelewy.
7. **Prognoza gotówki na 13 tygodni:** saldo dziś + wpływy z należności (wg faktycznego zachowania płatniczego klienta, nie terminu) + płatności cykliczne (pensje ok. 7.–10., ZUS 15., PIT 20., VAT 25.) edytowalne w aplikacji.
8. **Rejestr umów z klientami:** klient, data zawarcia, czas (określony do / nieokreślony), okres wypowiedzienia, wartość miesięczna, wyliczony ostatni dzień na wypowiedzenie, alert X dni wcześniej (na ekranie; kanał zewnętrzny później, za zgodą). Dane wpisuje Mat.
9. **Dashboard** (przenieś `dashboard.py`): gotówka, wynik, należności, postęp do celu, saldo, kto zalega, problemy z danymi.

**Później (nie w MVP):** szacunek czasu zespołu na klientów (procent miesięcznie per osoba) i rentowność klienta; porównanie z Budget Studio pozycja po pozycji; import Budget Studio jako trzecie źródło do równoległego okresu.

**Poza zakresem:** wystawianie faktur, KSeF, OCR, logowanie i wielu użytkowników, Apps Script, publikacja czegokolwiek w sieci.

Stałe biznesowe (ze `Strategia wzrostu DigitalH` w vaulcie): cel roczny obrót 1,1 mln zł, zysk ok. 120 tys. zł; marża na kliencie min. 30% (próg do rewizji).

## 6. Technologia (propozycja, do potwierdzenia z Matem przed startem)

Python 3 (venv w katalogu apki) + SQLite + prosty serwer HTTP na 127.0.0.1 + HTML/CSS/vanilla JS bez frameworków i CDN. Uruchamianie jednym poleceniem (np. `./start.command`), które otwiera przeglądarkę. Bez Dockera, bez Node, chyba że jest dobry powód.

## 7. Kryteria odbioru (testy na prawdziwych danych, lokalnie, bez commitowania danych)

Konkretne wartości oczekiwane leżą poza repo: `~/Documents/DigitalH/Finanse/Aplikacja/odbior.md` (opis) i `odbior.json` (liczby dla testu). Zasady stałe:
- Import tego samego pliku dwa razy nie zmienia żadnej liczby.
- `git status` po pracy nie pokazuje żadnego pliku z danymi.

## 8. Jak pracować

1. Przeczytaj `CLAUDE.md` repo, `apps/STAN.md`, ten brief, `~/Documents/DigitalH/Finanse/CLAUDE.md` i notę vaulta `AIOS/Tryby/Tryb — Finansowy.md`.
2. **Najpierw plan do akceptacji Mata** (krótko: struktura, model danych, kolejność etapów, decyzja o technologii). Bez kodu przed „tak”.
3. Etapami wg sekcji 5; po każdym: test na danych, demo dla Mata, wpis w `STAN.md` i w Kronice vaulta.
4. Commit lokalny wolno; **push na GitHub tylko za zgodą Mata** i po sprawdzeniu, że w commitach nie ma danych.
5. Równolegle w innej karcie działa sesja trybu finansowego (poprawki w Budget Studio). Nie zmieniaj plików w `Finanse/Raporty/Skrypty/` ani `Dane/`; jeśli potrzebujesz zmiany w skrypcie, skopiuj logikę do apki.
