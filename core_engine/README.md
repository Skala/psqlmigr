# psqlmigr-core

Python CLI engine for declarative PostgreSQL schema versioning, reverse-engineering, diff analysis, selective synchronization, and migration management.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Available CLI Commands

- `psqlmigr init` – initializes the project directory structure (`psqlmigr.yaml`, `.env`, `schemas/`, `migrations/up/`, `migrations/down/`).
- `psqlmigr set-env` – writes PostgreSQL connection parameters to the `.env` file.
- `psqlmigr test-connection` – tests connectivity to the target PostgreSQL database.
- `psqlmigr pull` – reverse-engineers all user schemas from PostgreSQL into modular DDL files under `schemas/`.
- `psqlmigr diff` – compares live database schemas against the local `schemas/` directory and outputs differences (`ADDED_IN_DB`, `MODIFIED`, `DELETED_IN_DB`) along with a unified SQL diff.
- `psqlmigr sync` – updates the local `schemas/` directory with selected database differences interactively (`[y/n/a/q]`), selectively (`--file <path>`), or all at once (`--all`).
- `psqlmigr plan <description> [--version <semver>]` – generates timestamped `up` and `down` migration scripts ordered by topological object dependencies.
- `psqlmigr validate` – executes pending migrations inside an isolated transaction with `ROLLBACK` (dry-run validation).
- `psqlmigr apply` – applies pending migrations and records execution history in `psqlmigr.schema_migrations`.
- `psqlmigr status` – displays the status of applied and pending migrations.
- `psqlmigr checksum` – calculates and displays SHA256 checksums for all migration scripts.
- `psqlmigr remove-migration <version>` – deletes the `up` and `down` migration files matching the given version or name.

## Running Tests

```powershell
pytest -v
```
