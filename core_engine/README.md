# psqlmigr-core

Silnik CLI w języku Python do deklaratywnego wersjonowania, porównywania (diff), selektywnej synchronizacji (sync) i migracji schematów baz danych PostgreSQL.

## Instalacja

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Dostępne Komendy CLI

- `psqlmigr init` – inicjalizuje strukturę projektu (`psqlmigr.yaml`, `.env`, `schemas/`, `migrations/up/`, `migrations/down/`).
- `psqlmigr set-env` – zapisuje parametry połączenia z bazą PostgreSQL w pliku `.env`.
- `psqlmigr test-connection` – testuje połączenie z bazą danych.
- `psqlmigr pull` – pobiera wszystkie schematy z bazy danych do plików DDL w katalogu `schemas/`.
- `psqlmigr diff` – porównuje schematy w bazie danych z lokalnym katalogiem `schemas/` i wyświetla różnice (`ADDED_IN_DB`, `MODIFIED`, `DELETED_IN_DB`) wraz z unified diff SQL.
- `psqlmigr sync` – pozwala interaktywnie (`[y/n/a/q]`), selektywnie (`--file <ścieżka>`) lub całościowo (`--all`) zaktualizować lokalny katalog `schemas/` o wybrane różnice z bazy danych.
- `psqlmigr plan <opis> [--version <wersja>]` – generuje pliki migracji `up` i `down` z sortowaniem topologicznym zależności.
- `psqlmigr validate` – wykonuje testowe uruchomienie oczekujących migracji w transakcji z `ROLLBACK` (dry-run).
- `psqlmigr apply` – wdraża oczekujące migracje i zapisuje historię w tabeli `psqlmigr.schema_migrations`.
- `psqlmigr status` – wyświetla status zastosowanych i oczekujących migracji.
- `psqlmigr checksum` – przelicza sumy kontrolne SHA256 dla plików migracji.
- `psqlmigr remove-migration <wersja>` – usuwa wskazane pliki migracji `up` i `down`.

## Testy

```powershell
pytest -v
```
