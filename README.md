# PsqlMigr - PostgreSQL Schema & Migration Manager

**PsqlMigr** to nowoczesne narzędzie do deklaratywnego wersjonowania, analizy diff, reverse-engineeringu oraz zarządzania migracjami baz danych PostgreSQL w procesach DevOps i środowisku Visual Studio Code / Antigravity IDE.

## Główne Funkcje

- **Deklaratywna Struktura Schematu**: Przechowywanie stanu bazy danych w czytelnych plikach DDL: `schema/<schemat>/<typ_obiektu>/<nazwa>.sql`.
- **Reverse-Engineering (`psqlmigr pull`)**: Pobieranie i automatyczne dzielenie istniejącej struktury PostgreSQL na pliki DDL.
- **Wersjonowane Skrypty Migracji**: Generowanie par plików `.up.sql` i `.down.sql` ze znacznikiem czasowym `YYYYMMDDHHMMSS`.
- **Weryfikacja Dry-Run (`psqlmigr validate`)**: Testowanie skryptów w izolowanej transakcji (`BEGIN ... ROLLBACK`).
- **Zarządzanie Sumami Kontrolnymi SHA256 (`psqlmigr checksum`)**: Rejestracja i przeliczanie sum kontrolnych dla ręcznie edytowanych plików.
- **Integracja z .env**: Szybkie testowanie połączenia z bazą i obsługa zmiennych środowiskowych.
- **Dedykowane Rozszerzenie VS Code & Antigravity IDE**: Dedykowane panele boczne (TreeView) oraz przyciski szybkich akcji na pasku nawigacyjnym.
- **Gotowość DevOps**: Szablony dla Docker i GitHub Actions (`.github/workflows/db-migration.yml`).

## Szybki Start (CLI)

```bash
# Inicjalizacja projektu
psqlmigr init

# Konfiguracja i test połączenia z .env
psqlmigr config set-env --host localhost --port 5432 --user postgres --password secret --database my_db
psqlmigr test-connection

# Pobranie schematu z bazy danych
psqlmigr pull

# Generowanie migracji
psqlmigr plan "create_users_table"

# Weryfikacja dry-run
psqlmigr validate

# Wykonanie migracji
psqlmigr apply
```

## Licencja

MIT
