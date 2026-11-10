# PsqlMigr - PostgreSQL Schema & Migration Manager

**PsqlMigr** to nowoczesne narzędzie do deklaratywnego wersjonowania, analizy różnic (diff), reverse-engineeringu oraz zarządzania migracjami baz danych PostgreSQL w procesach DevOps i środowisku Visual Studio Code / Antigravity IDE.

## Główne Funkcje

- **Deklaratywna Struktura Schematów (`schemas/`)**: Przechowywanie stanu bazy danych w czytelnych plikach DDL z podziałem na schematy i typy obiektów: `schemas/<schemat>/<typ_obiektu>/<nazwa>.sql` (`tables`, `views`, `functions`, `procedures`, `sequences`, `indexes`).
- **Reverse-Engineering (`psqlmigr pull`)**: Pobieranie i automatyczne dzielenie istniejącej struktury bazy PostgreSQL na pliki DDL (wraz z obsługą tabel partycjonowanych, indeksów i sekwencji `nextval`).
- **Porównywanie i Selektywna Synchronizacja (`psqlmigr diff` / `psqlmigr sync`)**: Porównywanie schematów w bazie danych z lokalnym katalogiem `schemas/`, wykrywanie obiektów nowych (`ADDED_IN_DB`), zmodyfikowanych (`MODIFIED`) oraz usuniętych (`DELETED_IN_DB`), podgląd różnic SQL (Unified Diff) oraz możliwość wyboru, które zmiany mają zaktualizować projekt.
- **Wersjonowane Skrypty Migracji (`psqlmigr plan`)**: Automatyczna analiza zależności topologicznych (sekwencje → tabele → funkcje/procedury/widoki → indeksy) i generowanie par plików w `migrations/up/` oraz `migrations/down/` z wersją semantyczną i znacznikiem czasowym (`v0.1.0_YYYYMMDDHHMMSS_nazwa.sql`).
- **Weryfikacja Dry-Run (`psqlmigr validate`)**: Testowanie oczekujących skryptów migracji w izolowanej transakcji (`BEGIN ... ROLLBACK`) bez modyfikacji danych w bazie.
- **Zarządzanie Sumami Kontrolnymi SHA256 (`psqlmigr checksum`)**: Rejestracja i weryfikacja sum kontrolnych plików migracji.
- **Integracja z `.env`**: Bezpieczna konfiguracja połączenia (z obsługą znaków specjalnych w hasłach) i szybki test połączenia z bazą.
- **Rozszerzenie VS Code & Antigravity IDE**: Dedykowane widoki drzewa (*Database Connection*, *Schema Objects Explorer*, *Migration History & Status*), okno wielokrotnego wyboru przy synchronizacji schematów oraz natywny podgląd porównania *Side-by-Side Diff* (`Local Project ↔ Database`).

---

## Struktura Projektu

Po uruchomieniu `psqlmigr init` tworzona jest następująca struktura:

```text
.
├── psqlmigr.yaml          # Konfiguracja projektu (wersja, ścieżki schemas/ i migrations/)
├── .env                   # Parametry połączenia z bazą PostgreSQL
├── schemas/               # Deklaratywny stan schematów bazy danych
│   └── public/
│       ├── sequences/
│       ├── tables/
│       ├── views/
│       ├── functions/
│       ├── procedures/
│       └── indexes/
└── migrations/            # Wersjonowane skrypty migracji
    ├── up/                # Skrypty wdrażające zmiany (UP)
    └── down/              # Skrypty wycofujące zmiany (DOWN)
```

---

## Szybki Start (CLI)

```bash
# 1. Inicjalizacja struktury projektu (tworzy psqlmigr.yaml, .env, schemas/, migrations/)
psqlmigr init

# 2. Konfiguracja połączenia w pliku .env oraz test połączenia z bazą PostgreSQL
psqlmigr set-env --host localhost --port 5432 --user postgres --password secret --database my_db
psqlmigr test-connection

# 3. Pełne pobranie schematów z bazy danych do katalogu schemas/
psqlmigr pull

# 4. Porównanie bazy danych z lokalnym katalogiem schemas/ (wyświetla tabelę różnic i SQL diff)
psqlmigr diff

# 5. Selektywna synchronizacja projektu z bazą danych:
# a) Tryb interaktywny (pyta o każdy obiekt: [y = tak, n = nie, a = wszystkie pozostałe, q = zakończ])
psqlmigr sync

# b) Aktualizacja wyłącznie wskazanych plików w schemas/
psqlmigr sync --file public/tables/users.sql --file public/views/v_active_users.sql

# c) Aktualizacja wszystkich wykrytych różnic bez pytania
psqlmigr sync --all

# 6. Generowanie migracji (automatyczne podbicie wersji lub własna flaga --version)
psqlmigr plan "create_users_table"
psqlmigr plan "add_audit_views" --version 0.2.0

# 7. Weryfikacja migracji w transakcji testowej (Dry-Run z ROLLBACK)
psqlmigr validate

# 8. Wdrożenie oczekujących migracji na bazę danych
psqlmigr apply

# 9. Sprawdzenie statusu migracji i przeliczenie sum kontrolnych SHA256
psqlmigr status
psqlmigr checksum

# 10. Usunięcie lokalnej migracji (plików UP i DOWN)
psqlmigr remove-migration v0.2.0
```

> Wszystkie komendy obsługują również flagę `--json` na potrzeby integracji z narzędziami CI/CD oraz rozszerzeniem VS Code.

---

## Rozszerzenie VS Code / Antigravity IDE

W panelu bocznym **PsqlMigr** dostępne są trzy sekcje z przyciskami szybkich akcji:

1. **Database Connection (.env)**
   - **Configure Connection & Save .env** – interaktywny formularz konfiguracji połączenia.
   - **Test PostgreSQL Connection** – sprawdzenie statusu połączenia i wersji serwera.
2. **Schema Objects Explorer**
   - **Pull Schema from Database** (`$(cloud-download)`) – pełny zrzut obiektów z bazy do `schemas/`.
   - **Compare & Sync Schema from Database** (`$(diff)`) – porównuje bazę z katalogiem `schemas/`, wyświetla listę wykrytych różnic (`ADDED_IN_DB`, `MODIFIED`, `DELETED_IN_DB`) z możliwością zaznaczenia wybranych obiektów do aktualizacji oraz otwarcia natywnego widoku porównania **Side-by-Side Diff** (*Local Project ↔ Database*).
3. **Migration History & Status**
   - **Generate Migration (Plan)** (`$(add)`) – generuje nową parę migracji `up`/`down`.
   - **Validate Migrations (Debug Dry-Run)** (`$(bug)`) – testuje migracje w transakcji próbnej.
   - **Apply Pending Migrations** (`$(play)`) – wykonuje oczekujące migracje na bazie danych.
   - **Delete Migration Script** (`$(trash)`) – usuwa wybraną migrację z dysku.

---

## Uruchomienie i Testowanie Rozwoju Projektu

### Silnik Python (`core_engine`)
```powershell
cd core_engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
pytest -v
```

### Rozszerzenie VS Code
```powershell
npm install
npm run compile
npm run lint
```
Aby uruchomić rozszerzenie w oknie deweloperskim, naciśnij **`F5`** w VS Code / Antigravity IDE (*Run Extension*).

## Licencja

MIT
